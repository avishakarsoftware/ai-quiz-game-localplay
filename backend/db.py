"""SQLite database for persistent entitlements and usage tracking."""
import os
import sqlite3
import time
import logging
import threading
from typing import Optional

import config

logger = logging.getLogger(__name__)

DB_DIR = os.getenv("DB_DIR", os.path.join(os.path.dirname(__file__), "data"))
DB_PATH = os.path.join(DB_DIR, "revelry.db")

_local = threading.local()


def _get_conn() -> sqlite3.Connection:
    """Get a thread-local connection (SQLite is not thread-safe by default)."""
    if not hasattr(_local, "conn") or _local.conn is None:
        os.makedirs(DB_DIR, exist_ok=True)
        _local.conn = sqlite3.connect(DB_PATH, timeout=10)
        _local.conn.row_factory = sqlite3.Row
        _local.conn.execute("PRAGMA journal_mode=WAL")
        _local.conn.execute("PRAGMA busy_timeout=5000")
    return _local.conn


def init_db():
    """Create tables if they don't exist."""
    conn = _get_conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS entitlements (
            id TEXT PRIMARY KEY,
            user_id TEXT,
            device_id TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending_payment',
            games_remaining INTEGER NOT NULL DEFAULT 50,
            expires_at INTEGER NOT NULL,
            stripe_session_id TEXT,
            apple_transaction_id TEXT,
            google_order_id TEXT,
            created_at INTEGER NOT NULL
        );

        CREATE UNIQUE INDEX IF NOT EXISTS idx_entitlements_stripe
            ON entitlements(stripe_session_id) WHERE stripe_session_id IS NOT NULL;
        CREATE UNIQUE INDEX IF NOT EXISTS idx_entitlements_apple
            ON entitlements(apple_transaction_id) WHERE apple_transaction_id IS NOT NULL;
        CREATE UNIQUE INDEX IF NOT EXISTS idx_entitlements_google
            ON entitlements(google_order_id) WHERE google_order_id IS NOT NULL;

        CREATE TABLE IF NOT EXISTS device_usage (
            device_id TEXT PRIMARY KEY,
            user_id TEXT,
            games_used_free INTEGER NOT NULL DEFAULT 0,
            window_start INTEGER NOT NULL
        );

        CREATE TABLE IF NOT EXISTS request_log (
            idempotency_key TEXT PRIMARY KEY,
            device_id TEXT NOT NULL,
            result_id TEXT,
            created_at INTEGER NOT NULL
        );

        CREATE TABLE IF NOT EXISTS pending_tokens (
            device_id TEXT PRIMARY KEY,
            token TEXT NOT NULL,
            created_at INTEGER NOT NULL
        );

        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            provider TEXT NOT NULL,
            provider_subject_id TEXT NOT NULL,
            email TEXT,
            created_at INTEGER NOT NULL,
            UNIQUE(provider, provider_subject_id)
        );
    """)
    conn.commit()
    logger.info("Database initialized at %s", DB_PATH)


# --- Entitlements ---

def create_entitlement(
    entitlement_id: str,
    device_id: str,
    stripe_session_id: Optional[str] = None,
    apple_transaction_id: Optional[str] = None,
    google_order_id: Optional[str] = None,
    user_id: Optional[str] = None,
    games: int = 50,
    status: str = "active",
) -> bool:
    """Create a new entitlement. Returns False if payment ID already exists (idempotent)."""
    conn = _get_conn()
    now = int(time.time())
    expires_at = now + (config.PREMIUM_DURATION_HOURS * 3600)
    try:
        conn.execute(
            "INSERT INTO entitlements (id, user_id, device_id, status, games_remaining, "
            "expires_at, stripe_session_id, apple_transaction_id, google_order_id, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (entitlement_id, user_id, device_id, status, games,
             expires_at, stripe_session_id, apple_transaction_id, google_order_id, now),
        )
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        # Duplicate payment ID — idempotent, already processed
        logger.info("Duplicate entitlement for payment, skipping")
        return False


def get_active_entitlement(device_id: str) -> Optional[dict]:
    """Find an active entitlement for this device (guest/device-scoped only).
    For signed-in users, use get_active_entitlement_for_user() instead."""
    conn = _get_conn()
    now = int(time.time())

    # Expire entitlements that have passed their time
    conn.execute(
        "UPDATE entitlements SET status = 'expired_time' "
        "WHERE status = 'active' AND expires_at <= ?",
        (now,),
    )
    conn.commit()

    row = conn.execute(
        "SELECT * FROM entitlements WHERE device_id = ? AND status = 'active' "
        "AND user_id IS NULL "
        "ORDER BY expires_at ASC LIMIT 1",
        (device_id,),
    ).fetchone()
    return dict(row) if row else None


def decrement_entitlement(entitlement_id: str) -> bool:
    """Atomically decrement games_remaining. Returns False if already exhausted/expired."""
    conn = _get_conn()
    now = int(time.time())
    cursor = conn.execute(
        "UPDATE entitlements SET "
        "  games_remaining = games_remaining - 1, "
        "  status = CASE WHEN games_remaining - 1 = 0 THEN 'exhausted_games' ELSE status END "
        "WHERE id = ? AND status = 'active' AND games_remaining > 0 AND expires_at > ?",
        (entitlement_id, now),
    )
    conn.commit()
    return cursor.rowcount > 0


def revoke_entitlement_by_stripe(stripe_session_id: str) -> bool:
    """Revoke an entitlement by Stripe session ID (for refunds)."""
    conn = _get_conn()
    cursor = conn.execute(
        "UPDATE entitlements SET status = 'revoked_refunded' "
        "WHERE stripe_session_id = ? AND status IN ('active', 'exhausted_games', 'expired_time')",
        (stripe_session_id,),
    )
    conn.commit()
    return cursor.rowcount > 0


def activate_pending_entitlement(stripe_session_id: str) -> Optional[dict]:
    """Activate a pending entitlement when webhook arrives. Returns the entitlement or None."""
    conn = _get_conn()
    now = int(time.time())
    expires_at = now + (config.PREMIUM_DURATION_HOURS * 3600)
    cursor = conn.execute(
        "UPDATE entitlements SET status = 'active', expires_at = ? "
        "WHERE stripe_session_id = ? AND status = 'pending_payment'",
        (expires_at, stripe_session_id),
    )
    conn.commit()
    if cursor.rowcount > 0:
        row = conn.execute(
            "SELECT * FROM entitlements WHERE stripe_session_id = ?",
            (stripe_session_id,),
        ).fetchone()
        return dict(row) if row else None
    return None


def get_entitlement_by_stripe_session(stripe_session_id: str) -> Optional[dict]:
    """Look up an entitlement by Stripe session ID (any status)."""
    conn = _get_conn()
    row = conn.execute(
        "SELECT * FROM entitlements WHERE stripe_session_id = ?",
        (stripe_session_id,),
    ).fetchone()
    return dict(row) if row else None


# --- Device Usage (Free Tier) ---

def check_and_increment_free_usage(device_id: str) -> tuple[bool, int]:
    """Atomically check free limit and increment. Returns (allowed, count_after)."""
    conn = _get_conn()
    now = int(time.time())
    window_cutoff = now - (24 * 3600)

    row = conn.execute(
        "SELECT games_used_free, window_start FROM device_usage WHERE device_id = ?",
        (device_id,),
    ).fetchone()

    if row is None:
        # First usage ever
        conn.execute(
            "INSERT INTO device_usage (device_id, games_used_free, window_start) VALUES (?, 1, ?)",
            (device_id, now),
        )
        conn.commit()
        return True, 1

    if row["window_start"] <= window_cutoff:
        # Window expired, reset
        conn.execute(
            "UPDATE device_usage SET games_used_free = 1, window_start = ? WHERE device_id = ?",
            (now, device_id),
        )
        conn.commit()
        return True, 1

    if row["games_used_free"] >= config.FREE_TIER_LIMIT:
        return False, row["games_used_free"]

    # Atomic increment
    cursor = conn.execute(
        "UPDATE device_usage SET games_used_free = games_used_free + 1 "
        "WHERE device_id = ? AND games_used_free < ?",
        (device_id, config.FREE_TIER_LIMIT),
    )
    conn.commit()
    if cursor.rowcount == 0:
        return False, row["games_used_free"]
    return True, row["games_used_free"] + 1


def get_free_usage_count(device_id: str) -> int:
    """Get current free usage count for a device."""
    conn = _get_conn()
    window_cutoff = int(time.time()) - (24 * 3600)
    row = conn.execute(
        "SELECT games_used_free, window_start FROM device_usage WHERE device_id = ?",
        (device_id,),
    ).fetchone()
    if row is None or row["window_start"] <= window_cutoff:
        return 0
    return row["games_used_free"]


def peek_free_usage(device_id: str) -> tuple[bool, int]:
    """Check free usage without incrementing. Returns (can_play, used_count)."""
    conn = _get_conn()
    now = int(time.time())
    window_cutoff = now - (24 * 3600)

    row = conn.execute(
        "SELECT games_used_free, window_start FROM device_usage WHERE device_id = ?",
        (device_id,),
    ).fetchone()

    if row is None or row["window_start"] <= window_cutoff:
        return True, 0

    used = row["games_used_free"]
    if used >= config.FREE_TIER_LIMIT:
        return False, used
    return True, used


# --- Request Idempotency ---

def check_idempotency(key: str, device_id: str = "") -> Optional[str]:
    """Check if this request was already processed. Returns result_id or None.
    When device_id is provided, only returns a match if the device matches."""
    if not key:
        return None
    conn = _get_conn()
    # Clean old entries (> 1 hour)
    cutoff = int(time.time()) - 3600
    conn.execute("DELETE FROM request_log WHERE created_at < ?", (cutoff,))
    conn.commit()

    row = conn.execute(
        "SELECT result_id, device_id FROM request_log WHERE idempotency_key = ?", (key,),
    ).fetchone()
    if not row:
        return None
    # If device_id provided, reject cross-device collisions
    if device_id and row["device_id"] != device_id:
        return None
    return row["result_id"]


def record_idempotency(key: str, device_id: str, result_id: str):
    """Record a completed request for idempotency."""
    if not key:
        return
    conn = _get_conn()
    try:
        conn.execute(
            "INSERT OR IGNORE INTO request_log (idempotency_key, device_id, result_id, created_at) "
            "VALUES (?, ?, ?, ?)",
            (key, device_id, result_id, int(time.time())),
        )
        conn.commit()
    except sqlite3.IntegrityError:
        pass


# --- Pending Tokens (SQLite-backed, survives restarts) ---

_PENDING_TOKEN_TTL = 3600  # 1 hour — gives user time to complete checkout + return


def store_pending_token(device_id: str, token: str):
    """Store a token for pickup after Stripe checkout."""
    conn = _get_conn()
    now = int(time.time())
    # Cleanup expired tokens
    conn.execute("DELETE FROM pending_tokens WHERE created_at < ?", (now - _PENDING_TOKEN_TTL,))
    # Upsert: replace any existing pending token for this device
    conn.execute(
        "INSERT OR REPLACE INTO pending_tokens (device_id, token, created_at) VALUES (?, ?, ?)",
        (device_id, token, now),
    )
    conn.commit()


def pop_pending_token(device_id: str) -> Optional[str]:
    """One-time retrieval of pending token. Deleted after first read."""
    conn = _get_conn()
    now = int(time.time())
    # Cleanup expired tokens
    conn.execute("DELETE FROM pending_tokens WHERE created_at < ?", (now - _PENDING_TOKEN_TTL,))
    conn.commit()

    row = conn.execute(
        "SELECT token FROM pending_tokens WHERE device_id = ?", (device_id,),
    ).fetchone()
    if not row:
        return None
    # Delete after read (one-time retrieval)
    conn.execute("DELETE FROM pending_tokens WHERE device_id = ?", (device_id,))
    conn.commit()
    return row["token"]


# --- Users (Phase 2: Auth) ---

def find_or_create_user(provider: str, provider_subject_id: str, email: Optional[str] = None) -> dict:
    """Find existing user by provider+sub, or create new one. Returns user dict."""
    import uuid as _uuid
    conn = _get_conn()

    # Try to find existing user
    row = conn.execute(
        "SELECT * FROM users WHERE provider = ? AND provider_subject_id = ?",
        (provider, provider_subject_id),
    ).fetchone()
    if row:
        # Update email if provided and changed
        if email and row["email"] != email:
            conn.execute(
                "UPDATE users SET email = ? WHERE id = ?",
                (email, row["id"]),
            )
            conn.commit()
            # Return dict with updated email
            user_dict = dict(row)
            user_dict["email"] = email
            return user_dict
        return dict(row)

    # Create new user
    user_id = str(_uuid.uuid4())
    now = int(time.time())
    try:
        conn.execute(
            "INSERT INTO users (id, provider, provider_subject_id, email, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (user_id, provider, provider_subject_id, email, now),
        )
        conn.commit()
    except sqlite3.IntegrityError:
        # Race condition: another thread created the user — fetch it
        row = conn.execute(
            "SELECT * FROM users WHERE provider = ? AND provider_subject_id = ?",
            (provider, provider_subject_id),
        ).fetchone()
        return dict(row)
    return {"id": user_id, "provider": provider, "provider_subject_id": provider_subject_id,
            "email": email, "created_at": now}


def get_user(user_id: str) -> Optional[dict]:
    """Get user by internal ID."""
    conn = _get_conn()
    row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    return dict(row) if row else None


def merge_device_to_user(user_id: str, device_id: str):
    """Link orphaned entitlements and usage from this device to the user.
    Only updates records that don't already belong to another user."""
    conn = _get_conn()
    conn.execute(
        "UPDATE entitlements SET user_id = ? WHERE device_id = ? AND user_id IS NULL",
        (user_id, device_id),
    )
    conn.execute(
        "UPDATE device_usage SET user_id = ? WHERE device_id = ? AND user_id IS NULL",
        (user_id, device_id),
    )
    conn.commit()


def get_active_entitlement_for_user(user_id: str) -> Optional[dict]:
    """Find an active entitlement for this user (any device)."""
    conn = _get_conn()
    now = int(time.time())
    # Expire stale entitlements first
    conn.execute(
        "UPDATE entitlements SET status = 'expired_time' "
        "WHERE status = 'active' AND expires_at <= ?",
        (now,),
    )
    conn.commit()
    row = conn.execute(
        "SELECT * FROM entitlements WHERE user_id = ? AND status = 'active' "
        "ORDER BY expires_at ASC LIMIT 1",
        (user_id,),
    ).fetchone()
    return dict(row) if row else None


def get_user_free_usage_count(user_id: str) -> int:
    """Get total free usage across all devices for a signed-in user."""
    conn = _get_conn()
    window_cutoff = int(time.time()) - (24 * 3600)
    row = conn.execute(
        "SELECT COALESCE(SUM(games_used_free), 0) as total FROM device_usage "
        "WHERE user_id = ? AND window_start >= ?",
        (user_id, window_cutoff),
    ).fetchone()
    return row["total"] if row else 0


def check_and_increment_user_free_usage(user_id: str, device_id: str) -> tuple[bool, int]:
    """Atomically check and increment free usage for a signed-in user (across all devices).
    Uses BEGIN IMMEDIATE to serialize concurrent writers and prevent TOCTOU races.
    Returns (allowed, total_count_after)."""
    conn = _get_conn()
    now = int(time.time())
    window_cutoff = now - (24 * 3600)

    # BEGIN IMMEDIATE acquires a write lock before reading, preventing
    # concurrent transactions from interleaving between our SUM check and UPDATE.
    conn.execute("BEGIN IMMEDIATE")
    try:
        # Get current total across all devices for this user
        row = conn.execute(
            "SELECT COALESCE(SUM(games_used_free), 0) as total FROM device_usage "
            "WHERE user_id = ? AND window_start >= ?",
            (user_id, window_cutoff),
        ).fetchone()
        total = row["total"] if row else 0

        if total >= config.FREE_TIER_LIMIT:
            conn.execute("ROLLBACK")
            return False, total

        # Increment on the current device's row
        device_row = conn.execute(
            "SELECT * FROM device_usage WHERE device_id = ?", (device_id,),
        ).fetchone()

        if device_row is None:
            conn.execute(
                "INSERT INTO device_usage (device_id, user_id, games_used_free, window_start) "
                "VALUES (?, ?, 1, ?)",
                (device_id, user_id, now),
            )
        elif device_row["window_start"] <= window_cutoff:
            conn.execute(
                "UPDATE device_usage SET games_used_free = 1, window_start = ?, user_id = ? "
                "WHERE device_id = ?",
                (now, user_id, device_id),
            )
        else:
            conn.execute(
                "UPDATE device_usage SET games_used_free = games_used_free + 1 "
                "WHERE device_id = ?",
                (device_id,),
            )
        conn.execute("COMMIT")
        return True, total + 1
    except Exception:
        conn.execute("ROLLBACK")
        raise


def peek_user_free_usage(user_id: str) -> tuple[bool, int]:
    """Check user free usage without incrementing. Returns (can_play, used_count)."""
    count = get_user_free_usage_count(user_id)
    return count < config.FREE_TIER_LIMIT, count


# --- Admin / Support ---

def lookup_by_device(device_id: str) -> dict:
    """Admin: look up all data for a device."""
    conn = _get_conn()
    entitlements = [dict(r) for r in conn.execute(
        "SELECT * FROM entitlements WHERE device_id = ? ORDER BY created_at DESC", (device_id,),
    ).fetchall()]
    usage = conn.execute(
        "SELECT * FROM device_usage WHERE device_id = ?", (device_id,),
    ).fetchone()
    return {"device_id": device_id, "entitlements": entitlements, "usage": dict(usage) if usage else None}


def lookup_entitlement(entitlement_id: str) -> Optional[dict]:
    """Admin: look up a single entitlement by ID."""
    conn = _get_conn()
    row = conn.execute(
        "SELECT * FROM entitlements WHERE id = ?", (entitlement_id,),
    ).fetchone()
    return dict(row) if row else None


def admin_revoke(entitlement_id: str) -> bool:
    """Admin: manually revoke an entitlement. Only revokes active/expired/exhausted."""
    conn = _get_conn()
    cursor = conn.execute(
        "UPDATE entitlements SET status = 'revoked_refunded' "
        "WHERE id = ? AND status IN ('active', 'expired_time', 'exhausted_games')",
        (entitlement_id,),
    )
    conn.commit()
    return cursor.rowcount > 0


def find_restorable_entitlement(device_id: str, user_id: Optional[str] = None) -> Optional[dict]:
    """Find an active or recently-expired IAP entitlement for restore.
    Looks for entitlements with apple_transaction_id or google_order_id."""
    conn = _get_conn()

    # First check user-scoped if signed in
    if user_id:
        row = conn.execute(
            "SELECT * FROM entitlements WHERE user_id = ? "
            "AND (apple_transaction_id IS NOT NULL OR google_order_id IS NOT NULL) "
            "AND status IN ('active', 'expired_time', 'exhausted_games') "
            "ORDER BY created_at DESC LIMIT 1",
            (user_id,),
        ).fetchone()
        if row:
            return dict(row)

    # Then check device-scoped
    row = conn.execute(
        "SELECT * FROM entitlements WHERE device_id = ? "
        "AND (apple_transaction_id IS NOT NULL OR google_order_id IS NOT NULL) "
        "AND status IN ('active', 'expired_time', 'exhausted_games') "
        "ORDER BY created_at DESC LIMIT 1",
        (device_id,),
    ).fetchone()
    return dict(row) if row else None


def admin_grant(device_id: str, games: int = 50, hours: int = 12, user_id: Optional[str] = None) -> str:
    """Admin: manually grant an entitlement. Returns entitlement ID."""
    import uuid
    eid = str(uuid.uuid4())
    now = int(time.time())
    conn = _get_conn()
    conn.execute(
        "INSERT INTO entitlements (id, device_id, user_id, status, games_remaining, expires_at, created_at) "
        "VALUES (?, ?, ?, 'active', ?, ?, ?)",
        (eid, device_id, user_id, games, now + hours * 3600, now),
    )
    conn.commit()
    return eid


def lookup_by_user(user_id: str) -> dict:
    """Admin: look up all data for a user across all devices."""
    conn = _get_conn()
    user = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    if not user:
        return {"user_id": user_id, "user": None, "entitlements": [], "usage": [], "devices": []}
    user_dict = dict(user)
    entitlements = [dict(r) for r in conn.execute(
        "SELECT * FROM entitlements WHERE user_id = ? ORDER BY created_at DESC", (user_id,),
    ).fetchall()]
    usage = [dict(r) for r in conn.execute(
        "SELECT * FROM device_usage WHERE user_id = ?", (user_id,),
    ).fetchall()]
    devices = [r["device_id"] for r in conn.execute(
        "SELECT DISTINCT device_id FROM entitlements WHERE user_id = ? "
        "UNION SELECT DISTINCT device_id FROM device_usage WHERE user_id = ?",
        (user_id, user_id),
    ).fetchall()]
    return {"user_id": user_id, "user": user_dict, "entitlements": entitlements, "usage": usage, "devices": devices}


def lookup_user_by_email(email: str) -> list[dict]:
    """Admin: find users by email (partial match). Returns list of user dicts."""
    conn = _get_conn()
    # Escape LIKE wildcards to prevent unintended broad matches
    escaped = email.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    rows = conn.execute(
        "SELECT * FROM users WHERE email LIKE ? ESCAPE '\\' LIMIT 20",
        (f"%{escaped}%",),
    ).fetchall()
    return [dict(r) for r in rows]
