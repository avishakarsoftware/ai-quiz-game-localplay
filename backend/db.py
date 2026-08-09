"""SQLite database for token wallets, entitlements (legacy), and usage tracking."""
import os
import sqlite3
import time
import logging
import threading
import json
import secrets
from typing import Optional

import config

logger = logging.getLogger(__name__)


class AccountDeletedError(Exception):
    """Raised when something tries to act on a deleted account (SPEC-ACCOUNT-DELETION §2).

    Surfaced as HTTP 410 Gone. Distinct from "not found" on purpose: the caller is holding a
    valid-looking session for an account that no longer exists, and silently creating a fresh
    one would undo the deletion."""

    def __init__(self, user_id: str = ""):
        self.user_id = user_id
        super().__init__("Account has been deleted")

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
        CREATE INDEX IF NOT EXISTS idx_entitlements_user
            ON entitlements(user_id, status) WHERE user_id IS NOT NULL;

        CREATE TABLE IF NOT EXISTS device_usage (
            device_id TEXT PRIMARY KEY,
            user_id TEXT,
            games_used_free INTEGER NOT NULL DEFAULT 0,
            window_start INTEGER NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_device_usage_user
            ON device_usage(user_id) WHERE user_id IS NOT NULL;

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

        CREATE TABLE IF NOT EXISTS wallets (
            id TEXT PRIMARY KEY,
            balance INTEGER NOT NULL DEFAULT 0,
            lifetime_purchased INTEGER NOT NULL DEFAULT 0,
            last_daily_bonus_date TEXT NOT NULL DEFAULT '',
            ads_watched_today INTEGER NOT NULL DEFAULT 0,
            ads_watched_date TEXT NOT NULL DEFAULT '',
            created_at INTEGER NOT NULL
        );

        CREATE TABLE IF NOT EXISTS token_transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            wallet_id TEXT NOT NULL,
            amount INTEGER NOT NULL,
            reason TEXT NOT NULL,
            reference_id TEXT,
            balance_after INTEGER NOT NULL,
            metadata TEXT NOT NULL DEFAULT '',
            created_at INTEGER NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_txn_wallet ON token_transactions(wallet_id);
        CREATE INDEX IF NOT EXISTS idx_txn_reference ON token_transactions(reference_id) WHERE reference_id IS NOT NULL;

        CREATE TABLE IF NOT EXISTS webhook_events (
            event_id TEXT PRIMARY KEY,
            processed_at INTEGER NOT NULL
        );

        -- Achievements / badges (SPEC-ACHIEVEMENTS). One row per (wallet, badge); the PK makes
        -- awarding idempotent (INSERT OR IGNORE). badge_id is validated against config.ACHIEVEMENT_IDS.
        CREATE TABLE IF NOT EXISTS achievements (
            wallet_id TEXT NOT NULL,
            badge_id TEXT NOT NULL,
            awarded_at INTEGER NOT NULL,
            PRIMARY KEY (wallet_id, badge_id)
        );
        CREATE INDEX IF NOT EXISTS idx_achievements_wallet ON achievements(wallet_id);

        -- Share-card snapshots (SPEC-SHARE-CARD). Durable store so an OG-unfurl link survives a
        -- process restart / works across instances (was in-memory only). TTL-evicted by created_at.
        CREATE TABLE IF NOT EXISTS share_snapshots (
            token TEXT PRIMARY KEY,
            game_type TEXT NOT NULL DEFAULT '',
            winner TEXT NOT NULL DEFAULT '',
            top_score INTEGER NOT NULL DEFAULT 0,
            player_count INTEGER NOT NULL DEFAULT 0,
            created_at INTEGER NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_share_snapshots_created ON share_snapshots(created_at);

        -- Durable per-wallet game completions (SPEC-GAME-STATS). `game_history` in main.py is an
        -- in-memory ring that dies with the process, so "games played" could never be shown across
        -- restarts or instances. wallet_id is the HOST's wallet (room.wallet_id) — guests join from
        -- their phones without wallets — so these are "games hosted", which is also who pays sparks.
        -- room_code is UNIQUE so a re-broadcast podium can't double-count a single game.
        CREATE TABLE IF NOT EXISTS game_results (
            room_code TEXT PRIMARY KEY,
            wallet_id TEXT NOT NULL,
            game_type TEXT NOT NULL DEFAULT '',
            game_title TEXT NOT NULL DEFAULT '',
            player_count INTEGER NOT NULL DEFAULT 0,
            winner_nickname TEXT NOT NULL DEFAULT '',
            top_score INTEGER NOT NULL DEFAULT 0,
            completed_at INTEGER NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_game_results_wallet
            ON game_results(wallet_id, completed_at DESC);

        -- Small durable key/value store for operator settings (SPEC-REMOTE-CONFIG §admin).
        -- Holds the remote-config override layer, which must survive a redeploy: an in-memory
        -- kill switch evaporates exactly when it's needed most (during a bad rollout).
        CREATE TABLE IF NOT EXISTS app_settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL DEFAULT '',
            updated_at INTEGER NOT NULL
        );

        -- Deleted-account denylist (SPEC-ACCOUNT-DELETION §2).
        -- Session tokens are stateless JWTs and cannot be revoked, so a live token held by a
        -- just-deleted user would otherwise sail through auth and hit get_or_create_wallet,
        -- recreating the account *with a fresh signup bonus*. This table is the revocation
        -- list that makes deletion actually stick. Ids are opaque UUIDs, not PII.
        CREATE TABLE IF NOT EXISTS deleted_accounts (
            user_id TEXT PRIMARY KEY,
            deleted_at INTEGER NOT NULL
        );

        CREATE TABLE IF NOT EXISTS generated_content (
            id TEXT PRIMARY KEY,
            wallet_id TEXT NOT NULL,
            content_type TEXT NOT NULL CHECK (content_type IN ('quiz', 'mlt', 'drawing', 'housie', 'chit_pull', 'party_quests')),
            title TEXT NOT NULL DEFAULT '',
            payload TEXT NOT NULL,
            prompt TEXT,
            model TEXT,
            provider TEXT,
            created_at INTEGER NOT NULL,
            updated_at INTEGER
        );
        CREATE INDEX IF NOT EXISTS idx_generated_content_wallet
            ON generated_content(wallet_id, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_generated_content_type
            ON generated_content(content_type, created_at DESC);

        CREATE TABLE IF NOT EXISTS custom_quiz_packs (
            id TEXT PRIMARY KEY,
            owner_wallet_id TEXT NOT NULL,
            title TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'draft',
            question_count INTEGER NOT NULL DEFAULT 0,
            created_at INTEGER NOT NULL,
            updated_at INTEGER NOT NULL,
            deleted_at INTEGER
        );
        CREATE INDEX IF NOT EXISTS idx_custom_quiz_packs_owner_updated
            ON custom_quiz_packs(owner_wallet_id, updated_at DESC);

        CREATE TABLE IF NOT EXISTS custom_quiz_questions (
            id TEXT PRIMARY KEY,
            pack_id TEXT NOT NULL,
            position INTEGER NOT NULL,
            question_type TEXT NOT NULL DEFAULT 'multiple_choice',
            text TEXT NOT NULL,
            options TEXT NOT NULL,
            answer_index INTEGER NOT NULL,
            image_asset_id TEXT,
            image_url TEXT,
            image_alt TEXT,
            created_at INTEGER NOT NULL,
            updated_at INTEGER NOT NULL,
            FOREIGN KEY(pack_id) REFERENCES custom_quiz_packs(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_custom_quiz_questions_pack_position
            ON custom_quiz_questions(pack_id, position);

        CREATE TABLE IF NOT EXISTS media_assets (
            id TEXT PRIMARY KEY,
            owner_wallet_id TEXT NOT NULL,
            storage_backend TEXT NOT NULL,
            storage_path TEXT NOT NULL,
            public_url TEXT NOT NULL,
            status TEXT NOT NULL,
            mime_type TEXT NOT NULL,
            bytes INTEGER NOT NULL DEFAULT 0,
            alt_text TEXT,
            created_at INTEGER NOT NULL,
            updated_at INTEGER NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_media_assets_owner_updated
            ON media_assets(owner_wallet_id, updated_at DESC);

        CREATE TABLE IF NOT EXISTS game_sessions (
            id TEXT PRIMARY KEY,
            host_app TEXT NOT NULL,
            external_container_id TEXT NOT NULL,
            external_container_type TEXT NOT NULL DEFAULT '',
            external_container_title TEXT NOT NULL DEFAULT '',
            external_host_user_id TEXT NOT NULL DEFAULT '',
            external_host_display_name TEXT NOT NULL DEFAULT '',
            game_type TEXT NOT NULL,
            game_id TEXT NOT NULL DEFAULT '',
            game_title TEXT NOT NULL DEFAULT '',
            room_code TEXT NOT NULL,
            organizer_token TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'lobby',
            joinable INTEGER NOT NULL DEFAULT 1,
            closed_reason TEXT,
            closed_message TEXT,
            superseded_by_session_id TEXT,
            launch_routes TEXT NOT NULL DEFAULT '{}',
            feed_card TEXT NOT NULL DEFAULT '{}',
            result_summary TEXT,
            created_at INTEGER NOT NULL,
            started_at INTEGER,
            completed_at INTEGER,
            expires_at INTEGER NOT NULL,
            last_activity_at INTEGER NOT NULL,
            updated_at INTEGER NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_game_sessions_external_active
            ON game_sessions(host_app, external_container_id, status, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_game_sessions_room
            ON game_sessions(room_code);

        CREATE TABLE IF NOT EXISTS host_app_catalog_flags (
            id TEXT PRIMARY KEY,
            environment TEXT NOT NULL,
            host_app TEXT NOT NULL,
            game_id TEXT NOT NULL,
            enabled INTEGER NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'disabled'
                CHECK (status IN ('live', 'gamma', 'planned', 'disabled')),
            allowlist_party_ids TEXT NOT NULL DEFAULT '[]',
            allowlist_external_user_ids TEXT NOT NULL DEFAULT '[]',
            rollout_percentage INTEGER
                CHECK (rollout_percentage IS NULL OR (rollout_percentage >= 0 AND rollout_percentage <= 100)),
            capability_overrides TEXT NOT NULL DEFAULT '{}',
            notes TEXT NOT NULL DEFAULT '',
            updated_by TEXT NOT NULL DEFAULT '',
            updated_at INTEGER NOT NULL,
            UNIQUE(environment, host_app, game_id)
        );
        CREATE INDEX IF NOT EXISTS idx_host_app_catalog_flags_lookup
            ON host_app_catalog_flags(environment, host_app, game_id);
    """)
    conn.commit()
    # Add metadata column if missing (migration for existing databases)
    import sqlite3 as _sqlite3
    try:
        conn.execute("ALTER TABLE token_transactions ADD COLUMN metadata TEXT NOT NULL DEFAULT ''")
        conn.commit()
    except _sqlite3.OperationalError as e:
        if "duplicate column" not in str(e).lower():
            logger.error("Failed to add metadata column: %s", e)
            raise
    # Login-streak counter on wallets (SPEC-STREAK-BONUS). Idempotent add-column migration.
    try:
        conn.execute("ALTER TABLE wallets ADD COLUMN bonus_streak INTEGER NOT NULL DEFAULT 0")
        conn.commit()
    except _sqlite3.OperationalError as e:
        if "duplicate column" not in str(e).lower():
            logger.error("Failed to add bonus_streak column: %s", e)
            raise
    # Referral columns on wallets (SPEC-REFERRAL). Idempotent add-column migrations + unique code index.
    for _col, _ddl in (
        ("referral_code", "ALTER TABLE wallets ADD COLUMN referral_code TEXT"),
        ("referred_by", "ALTER TABLE wallets ADD COLUMN referred_by TEXT"),
    ):
        try:
            conn.execute(_ddl)
            conn.commit()
        except _sqlite3.OperationalError as e:
            if "duplicate column" not in str(e).lower():
                logger.error("Failed to add %s column: %s", _col, e)
                raise
    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_wallets_referral_code "
        "ON wallets(referral_code) WHERE referral_code IS NOT NULL"
    )
    conn.commit()
    _migrate_generated_content_types()
    # Run one-time migration of old entitlements to token wallets
    migrate_entitlements_to_wallets()
    logger.info("Database initialized at %s", DB_PATH)


def _migrate_generated_content_types() -> None:
    """Expand generated_content.content_type CHECK constraint for saved party setups."""
    conn = _get_conn()
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'generated_content'"
    ).fetchone()
    table_sql = row["sql"] if row else ""
    required = ("'quiz'", "'mlt'", "'drawing'", "'housie'", "'chit_pull'", "'party_quests'")
    if all(item in table_sql for item in required):
        return
    conn.executescript("""
        CREATE TABLE generated_content_new (
            id TEXT PRIMARY KEY,
            wallet_id TEXT NOT NULL,
            content_type TEXT NOT NULL CHECK (content_type IN ('quiz', 'mlt', 'drawing', 'housie', 'chit_pull', 'party_quests')),
            title TEXT NOT NULL DEFAULT '',
            payload TEXT NOT NULL,
            prompt TEXT,
            model TEXT,
            provider TEXT,
            created_at INTEGER NOT NULL,
            updated_at INTEGER
        );
        INSERT INTO generated_content_new
            (id, wallet_id, content_type, title, payload, prompt, model, provider, created_at, updated_at)
        SELECT id, wallet_id, content_type, title, payload, prompt, model, provider, created_at, updated_at
        FROM generated_content;
        DROP TABLE generated_content;
        ALTER TABLE generated_content_new RENAME TO generated_content;
        CREATE INDEX IF NOT EXISTS idx_generated_content_wallet
            ON generated_content(wallet_id, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_generated_content_type
            ON generated_content(content_type, created_at DESC);
    """)
    conn.commit()


# --- Entitlements ---

def create_entitlement(
    entitlement_id: str,
    device_id: str,
    stripe_session_id: Optional[str] = None,
    apple_transaction_id: Optional[str] = None,
    google_order_id: Optional[str] = None,
    user_id: Optional[str] = None,
    games: int = 10,
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


def is_account_deleted(user_id: str) -> bool:
    """True if this user id was deleted (SPEC-ACCOUNT-DELETION §2).

    Checked on every authenticated request and before wallet creation: session JWTs are
    stateless and outlive deletion, so this is what stops a live token from resurrecting
    the account."""
    if not user_id:
        return False
    conn = _get_conn()
    row = conn.execute(
        "SELECT 1 FROM deleted_accounts WHERE user_id = ? LIMIT 1", (user_id,)
    ).fetchone()
    return row is not None


def delete_account(user_id: str) -> bool:
    """Permanently delete a user account and its data (SPEC-ACCOUNT-DELETION §3).

    Removes the users row (all PII), the wallet keyed on this user id (including any unspent
    Spark balance), authored content, and legacy entitlement/usage rows — then denylists the id.

    `token_transactions` is deliberately RETAINED: it is a financial record with retention
    obligations, and it is what makes `credit_purchase` idempotent, so dropping it would let a
    replayed or late webhook double-credit. It is pseudonymous once `users` is gone — its only
    identifier is this random UUID. Do not "clean it up" by rewriting wallet_id; that breaks
    idempotency. See the spec for the full rationale.

    Runs in ONE transaction: a partial delete (wallet gone, PII kept) is the worst outcome.
    Returns False if the account was already deleted, so the caller can answer 410 rather than
    pretending it did work.
    """
    conn = _get_conn()
    conn.execute("BEGIN IMMEDIATE")
    try:
        already = conn.execute(
            "SELECT 1 FROM deleted_accounts WHERE user_id = ? LIMIT 1", (user_id,)
        ).fetchone()
        if already:
            conn.execute("ROLLBACK")
            return False

        # Wallet id == user id for signed-in users (get_wallet_id), so the user's Sparks and
        # authored content hang off this same value.
        conn.execute("DELETE FROM generated_content WHERE wallet_id = ?", (user_id,))
        conn.execute("DELETE FROM wallets WHERE id = ?", (user_id,))
        conn.execute("DELETE FROM entitlements WHERE user_id = ?", (user_id,))
        conn.execute("DELETE FROM device_usage WHERE user_id = ?", (user_id,))
        conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
        conn.execute(
            "INSERT INTO deleted_accounts (user_id, deleted_at) VALUES (?, ?)",
            (user_id, int(time.time())),
        )
        conn.execute("COMMIT")
        logger.info("Account deleted: %s", user_id[:8])
        return True
    except Exception:
        conn.execute("ROLLBACK")
        raise


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


def admin_grant(device_id: str, games: int = 10, hours: int = 720, user_id: Optional[str] = None) -> str:
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


# --- Token Wallets ---

def _utc_date_str() -> str:
    """Get today's UTC date as YYYY-MM-DD string."""
    import datetime
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")


def _utc_yesterday_str() -> str:
    """Get yesterday's UTC date as YYYY-MM-DD string (for login-streak continuity)."""
    import datetime
    return (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=1)).strftime("%Y-%m-%d")


def party_grace_state(wallet_id: str) -> tuple[int, int]:
    """(anchor_epoch, rooms_used) of the first-party grace window — (0, 0) if never started.
    State lives in the ledger as zero-amount 'grace_room' rows: no schema change, and the
    window anchors on the FIRST free room (REVIEW-2026-08 P1)."""
    conn = _get_conn()
    row = conn.execute(
        "SELECT MIN(created_at) AS anchor, COUNT(*) AS rooms FROM token_transactions "
        "WHERE wallet_id = ? AND reason = 'grace_room'",
        (wallet_id,),
    ).fetchone()
    return (row["anchor"] or 0, row["rooms"] or 0)


def has_room_spend(wallet_id: str) -> bool:
    """Has this wallet ever PAID for a room? Veterans predating the grace feature don't get a
    surprise free evening — grace is a first-party experience, not a refund."""
    conn = _get_conn()
    return conn.execute(
        "SELECT 1 FROM token_transactions WHERE wallet_id = ? AND reason = 'spend_room' LIMIT 1",
        (wallet_id,),
    ).fetchone() is not None


def has_signup_bonus(wallet_id: str) -> bool:
    """Did this wallet receive the normal first-party signup grant?

    Grantless wallets are still created after the per-IP allowance is exhausted so late guests can
    play, but they must not become an unlimited source of free grace rooms."""
    conn = _get_conn()
    return conn.execute(
        "SELECT 1 FROM token_transactions WHERE wallet_id = ? AND reason = 'signup_bonus' LIMIT 1",
        (wallet_id,),
    ).fetchone() is not None


def migrate_grace_proofs(from_id: str, to_id: str) -> None:
    """Carry first-party-grace identity across the device->user wallet merge at sign-in.

    merge_wallet moves BALANCE only, so without this a brand-new host who signs in before
    hosting reads as grace-ineligible (their signup_bonus row is stranded on the device
    wallet), an open grace window silently resets, and a veteran's spend_room history
    disappears — handing them a fresh free evening. Three proofs move as zero-amount marker
    rows; each piece is skipped when the target already has it, so the call is idempotent.
    """
    if from_id == to_id:
        return
    conn = _get_conn()
    now = int(time.time())
    balance = get_wallet_balance(to_id)
    if has_signup_bonus(from_id) and not has_signup_bonus(to_id):
        conn.execute(
            "INSERT INTO token_transactions (wallet_id, amount, reason, reference_id, balance_after, metadata, created_at) "
            "VALUES (?, 0, 'signup_bonus', ?, ?, '', ?)",
            (to_id, f"migrated:{from_id}", balance, now),
        )
    if has_room_spend(from_id) and not has_room_spend(to_id):
        conn.execute(
            "INSERT INTO token_transactions (wallet_id, amount, reason, reference_id, balance_after, metadata, created_at) "
            "VALUES (?, 0, 'spend_room', ?, ?, '', ?)",
            (to_id, f"migrated:{from_id}", balance, now),
        )
    from_anchor, _ = party_grace_state(from_id)
    to_anchor, _ = party_grace_state(to_id)
    if from_anchor and not to_anchor:
        # Copy the window verbatim — original timestamps, so the anchor (and therefore the
        # deadline) carries over instead of restarting a fresh window on the user wallet.
        rows = conn.execute(
            "SELECT created_at FROM token_transactions WHERE wallet_id = ? AND reason = 'grace_room'",
            (from_id,),
        ).fetchall()
        for row in rows:
            conn.execute(
                "INSERT INTO token_transactions (wallet_id, amount, reason, reference_id, balance_after, metadata, created_at) "
                "VALUES (?, 0, 'grace_room', ?, ?, '', ?)",
                (to_id, f"migrated:{from_id}", balance, row["created_at"]),
            )
    conn.commit()


def record_grace_room(wallet_id: str) -> None:
    """Ledger marker for a free grace room: amount 0, balance unchanged."""
    conn = _get_conn()
    balance = get_wallet_balance(wallet_id)
    conn.execute(
        "INSERT INTO token_transactions (wallet_id, amount, reason, reference_id, balance_after, metadata, created_at) "
        "VALUES (?, 0, 'grace_room', NULL, ?, '', ?)",
        (wallet_id, balance, int(time.time())),
    )
    conn.commit()


def wallet_exists(wallet_id: str) -> bool:
    """Cheap existence probe so the signup-bonus IP gate only spends quota on ACTUAL creations —
    a returning device's balance poll must not drain its party's allowance (REVIEW-2026-08 S2)."""
    conn = _get_conn()
    return conn.execute("SELECT 1 FROM wallets WHERE id = ?", (wallet_id,)).fetchone() is not None


def get_or_create_wallet(wallet_id: str, signup_bonus: bool = True) -> dict:
    """Get wallet by ID, or create one with optional signup bonus.
    Returns wallet dict with keys: id, balance, lifetime_purchased, last_daily_bonus_date,
    ads_watched_today, ads_watched_date, created_at."""
    conn = _get_conn()
    row = conn.execute("SELECT * FROM wallets WHERE id = ?", (wallet_id,)).fetchone()
    if row:
        return dict(row)

    # Never re-create a wallet for a deleted account. A stateless session JWT outlives
    # deletion, so without this the next request from a held token would rebuild the wallet
    # AND hand out another signup bonus — deletion would be cosmetic, and farmable.
    if is_account_deleted(wallet_id):
        raise AccountDeletedError(wallet_id)

    now = int(time.time())
    bonus = config.SIGNUP_BONUS_TOKENS if signup_bonus else 0
    try:
        conn.execute(
            "INSERT INTO wallets (id, balance, lifetime_purchased, last_daily_bonus_date, "
            "ads_watched_today, ads_watched_date, created_at) VALUES (?, ?, 0, '', 0, '', ?)",
            (wallet_id, bonus, now),
        )
        if bonus > 0:
            conn.execute(
                "INSERT INTO token_transactions (wallet_id, amount, reason, reference_id, balance_after, created_at) "
                "VALUES (?, ?, 'signup_bonus', NULL, ?, ?)",
                (wallet_id, bonus, bonus, now),
            )
        conn.commit()
        logger.info("New wallet created: %s (bonus=%d)", wallet_id[:8], bonus)
    except sqlite3.IntegrityError:
        # Race condition: another thread created it
        row = conn.execute("SELECT * FROM wallets WHERE id = ?", (wallet_id,)).fetchone()
        if row:
            return dict(row)
    return {"id": wallet_id, "balance": bonus, "lifetime_purchased": 0,
            "last_daily_bonus_date": "", "ads_watched_today": 0, "ads_watched_date": "",
            "bonus_streak": 0, "created_at": now}


def get_wallet_balance(wallet_id: str) -> int:
    """Get current token balance. Returns 0 if wallet doesn't exist."""
    conn = _get_conn()
    row = conn.execute("SELECT balance FROM wallets WHERE id = ?", (wallet_id,)).fetchone()
    return row["balance"] if row else 0


def debit_tokens(wallet_id: str, amount: int, reason: str, reference_id: str = "") -> tuple[bool, int]:
    """Atomically debit tokens. Returns (success, new_balance). Fails if insufficient balance."""
    if amount <= 0:
        raise ValueError(f"debit_tokens amount must be positive, got {amount}")
    conn = _get_conn()
    conn.execute("BEGIN IMMEDIATE")
    try:
        row = conn.execute("SELECT balance FROM wallets WHERE id = ?", (wallet_id,)).fetchone()
        if not row or row["balance"] < amount:
            conn.execute("ROLLBACK")
            return False, row["balance"] if row else 0

        new_balance = row["balance"] - amount
        now = int(time.time())
        conn.execute("UPDATE wallets SET balance = ? WHERE id = ?", (new_balance, wallet_id))
        conn.execute(
            "INSERT INTO token_transactions (wallet_id, amount, reason, reference_id, balance_after, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (wallet_id, -amount, reason, reference_id or None, new_balance, now),
        )
        conn.execute("COMMIT")
        return True, new_balance
    except Exception:
        conn.execute("ROLLBACK")
        raise


def credit_tokens(wallet_id: str, amount: int, reason: str, reference_id: str = "") -> tuple[bool, int]:
    """Credit tokens to wallet, capped at MAX_TOKEN_BALANCE. Returns (success, new_balance).
    Creates wallet if it doesn't exist."""
    if amount <= 0:
        raise ValueError(f"credit_tokens amount must be positive, got {amount}")
    conn = _get_conn()
    now = int(time.time())
    conn.execute("BEGIN IMMEDIATE")
    try:
        row = conn.execute("SELECT balance FROM wallets WHERE id = ?", (wallet_id,)).fetchone()
        if not row:
            # Create wallet without signup bonus (credit is the initial action)
            conn.execute(
                "INSERT INTO wallets (id, balance, lifetime_purchased, last_daily_bonus_date, "
                "ads_watched_today, ads_watched_date, created_at) VALUES (?, 0, 0, '', 0, '', ?)",
                (wallet_id, now),
            )
            current = 0
        else:
            current = row["balance"]

        new_balance = max(current, min(current + amount, config.MAX_TOKEN_BALANCE))
        actual_credit = new_balance - current
        if actual_credit <= 0:
            conn.execute("COMMIT")
            return True, current  # At cap, no change but not an error

        conn.execute("UPDATE wallets SET balance = ? WHERE id = ?", (new_balance, wallet_id))
        conn.execute(
            "INSERT INTO token_transactions (wallet_id, amount, reason, reference_id, balance_after, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (wallet_id, actual_credit, reason, reference_id or None, new_balance, now),
        )
        conn.execute("COMMIT")
        return True, new_balance
    except Exception:
        conn.execute("ROLLBACK")
        raise


def _streak_reward(streak: int) -> int:
    """Login-streak reward for a given (1-based) streak day. See SPEC-STREAK-BONUS."""
    return min(config.STREAK_BASE + (max(1, streak) - 1) * config.STREAK_STEP, config.STREAK_MAX)


def check_and_grant_daily_bonus(wallet_id: str) -> tuple[bool, int, int, int]:
    """Grant the login-streak daily bonus if it's a new UTC day.
    Returns (granted, new_balance, streak, reward). streak/reward reflect today's grant when granted;
    on a no-grant they reflect the wallet's current stored streak and what today *would* pay."""
    conn = _get_conn()
    today = _utc_date_str()
    yesterday = _utc_yesterday_str()
    conn.execute("BEGIN IMMEDIATE")
    try:
        row = conn.execute("SELECT * FROM wallets WHERE id = ?", (wallet_id,)).fetchone()
        if not row:
            conn.execute("ROLLBACK")
            return False, 0, 0, 0

        stored_streak = row["bonus_streak"] if "bonus_streak" in row.keys() else 0
        if row["last_daily_bonus_date"] == today:
            conn.execute("ROLLBACK")
            return False, row["balance"], stored_streak, _streak_reward(stored_streak)

        # New day — continue the streak if yesterday was claimed, else restart at 1.
        streak = stored_streak + 1 if row["last_daily_bonus_date"] == yesterday else 1
        reward = _streak_reward(streak)
        new_balance = max(row["balance"], min(row["balance"] + reward, config.MAX_TOKEN_BALANCE))
        actual_bonus = new_balance - row["balance"]  # may be < reward if wallet is at cap; streak still advances
        now = int(time.time())

        conn.execute(
            "UPDATE wallets SET balance = ?, last_daily_bonus_date = ?, bonus_streak = ?, "
            "ads_watched_today = 0, ads_watched_date = ? WHERE id = ?",
            (new_balance, today, streak, today, wallet_id),
        )
        if actual_bonus > 0:
            conn.execute(
                "INSERT INTO token_transactions (wallet_id, amount, reason, reference_id, balance_after, metadata, created_at) "
                "VALUES (?, ?, 'daily_bonus', NULL, ?, ?, ?)",
                (wallet_id, actual_bonus, new_balance, json.dumps({"streak": streak}), now),
            )
        conn.execute("COMMIT")
        if actual_bonus < reward:
            logger.info("daily_bonus capped: wallet=%s streak=%d reward=%d actual=%d",
                        wallet_id[:8], streak, reward, actual_bonus)
        return True, new_balance, streak, reward
    except Exception:
        conn.execute("ROLLBACK")
        raise


def check_and_grant_ad_reward(wallet_id: str) -> tuple[bool, int, int]:
    """Grant ad reward if under daily cap. Returns (granted, new_balance, ads_remaining_today)."""
    conn = _get_conn()
    today = _utc_date_str()
    conn.execute("BEGIN IMMEDIATE")
    try:
        row = conn.execute("SELECT * FROM wallets WHERE id = ?", (wallet_id,)).fetchone()
        if not row:
            conn.execute("ROLLBACK")
            return False, 0, 0

        # Reset ad counter if new day
        ads_today = row["ads_watched_today"] if row["ads_watched_date"] == today else 0
        if ads_today >= config.MAX_ADS_PER_DAY:
            conn.execute("ROLLBACK")
            return False, row["balance"], 0

        new_balance = max(row["balance"], min(row["balance"] + config.AD_REWARD_TOKENS, config.MAX_TOKEN_BALANCE))
        actual_reward = new_balance - row["balance"]
        ads_today += 1
        remaining = config.MAX_ADS_PER_DAY - ads_today
        now = int(time.time())

        conn.execute(
            "UPDATE wallets SET balance = ?, ads_watched_today = ?, ads_watched_date = ? WHERE id = ?",
            (new_balance, ads_today, today, wallet_id),
        )
        if actual_reward > 0:
            conn.execute(
                "INSERT INTO token_transactions (wallet_id, amount, reason, reference_id, balance_after, created_at) "
                "VALUES (?, ?, 'ad_reward', NULL, ?, ?)",
                (wallet_id, actual_reward, new_balance, now),
            )
        conn.execute("COMMIT")
        return True, new_balance, remaining
    except Exception:
        conn.execute("ROLLBACK")
        raise


def has_ever_purchased(wallet_id: str) -> bool:
    """Check if this wallet has ever purchased tokens."""
    conn = _get_conn()
    row = conn.execute("SELECT lifetime_purchased FROM wallets WHERE id = ?", (wallet_id,)).fetchone()
    return row is not None and row["lifetime_purchased"] > 0


# --- Referrals (SPEC-REFERRAL) ---
_REFERRAL_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"  # unambiguous: no 0/O/1/I/L


def _utc_midnight_epoch() -> int:
    """Epoch seconds at the start of the current UTC day (for per-day referral caps)."""
    import datetime
    now = datetime.datetime.now(datetime.timezone.utc)
    return int(now.replace(hour=0, minute=0, second=0, microsecond=0).timestamp())


def _generate_referral_code(length: int = 6) -> str:
    return "".join(secrets.choice(_REFERRAL_ALPHABET) for _ in range(length))


def get_or_create_referral_code(wallet_id: str) -> str:
    """Return this wallet's referral code, lazily generating + persisting a unique one on first call."""
    conn = _get_conn()
    row = conn.execute("SELECT referral_code FROM wallets WHERE id = ?", (wallet_id,)).fetchone()
    if row is None:
        get_or_create_wallet(wallet_id, signup_bonus=True)
    elif row["referral_code"]:
        return row["referral_code"]
    for _ in range(12):  # retry on the (rare) unique-index collision
        code = _generate_referral_code()
        try:
            conn.execute(
                "UPDATE wallets SET referral_code = ? WHERE id = ? AND referral_code IS NULL",
                (code, wallet_id),
            )
            conn.commit()
        except sqlite3.IntegrityError:
            continue
        cur = conn.execute("SELECT referral_code FROM wallets WHERE id = ?", (wallet_id,)).fetchone()
        if cur and cur["referral_code"]:
            return cur["referral_code"]
    raise RuntimeError("could not allocate a unique referral code")


def count_referrals_today(referrer_id: str) -> int:
    """How many referral rewards this wallet has earned as a referrer since UTC midnight."""
    conn = _get_conn()
    row = conn.execute(
        "SELECT COUNT(*) AS c FROM token_transactions "
        "WHERE wallet_id = ? AND reason = 'referral_reward' AND created_at >= ?",
        (referrer_id, _utc_midnight_epoch()),
    ).fetchone()
    return row["c"] if row else 0


def _credit_in_txn(conn, wallet_id: str, amount: int, reason: str, reference_id: str, now: int) -> int:
    """Credit tokens within an already-open transaction (no BEGIN/COMMIT). Caps at MAX_TOKEN_BALANCE.
    Always writes a transaction row (even a 0-amount one at cap) so idempotency + counts stay correct."""
    row = conn.execute("SELECT balance FROM wallets WHERE id = ?", (wallet_id,)).fetchone()
    current = row["balance"] if row else 0
    new_balance = max(current, min(current + amount, config.MAX_TOKEN_BALANCE))
    actual = new_balance - current
    conn.execute("UPDATE wallets SET balance = ? WHERE id = ?", (new_balance, wallet_id))
    conn.execute(
        "INSERT INTO token_transactions (wallet_id, amount, reason, reference_id, balance_after, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (wallet_id, actual, reason, reference_id, new_balance, now),
    )
    return new_balance


def redeem_referral(referee_id: str, code: str) -> dict:
    """Redeem a referral code, crediting both parties once. Returns a status dict:
    status ∈ {ok, invalid_code, self_referral, already_redeemed, cap_reached}."""
    code = (code or "").strip().upper()
    if not code:
        return {"status": "invalid_code"}
    conn = _get_conn()
    now = int(time.time())
    since = _utc_midnight_epoch()
    reward = config.REFERRAL_REWARD
    conn.execute("BEGIN IMMEDIATE")
    try:
        referrer = conn.execute("SELECT id FROM wallets WHERE referral_code = ?", (code,)).fetchone()
        if not referrer:
            conn.execute("ROLLBACK")
            return {"status": "invalid_code"}
        referrer_id = referrer["id"]
        if referrer_id == referee_id:
            conn.execute("ROLLBACK")
            return {"status": "self_referral"}

        ref_row = conn.execute("SELECT referred_by FROM wallets WHERE id = ?", (referee_id,)).fetchone()
        if ref_row is None:
            conn.execute(
                "INSERT INTO wallets (id, balance, lifetime_purchased, last_daily_bonus_date, "
                "ads_watched_today, ads_watched_date, created_at) VALUES (?, 0, 0, '', 0, '', ?)",
                (referee_id, now),
            )
        elif ref_row["referred_by"]:
            conn.execute("ROLLBACK")
            return {"status": "already_redeemed"}

        reference_id = f"referral:{referrer_id}:{referee_id}"
        existing = conn.execute(
            "SELECT 1 FROM token_transactions WHERE reference_id = ? AND reason = 'referral_reward' LIMIT 1",
            (reference_id,),
        ).fetchone()
        if existing:
            conn.execute("ROLLBACK")
            return {"status": "already_redeemed"}

        cap_row = conn.execute(
            "SELECT COUNT(*) AS c FROM token_transactions "
            "WHERE wallet_id = ? AND reason = 'referral_reward' AND created_at >= ?",
            (referrer_id, since),
        ).fetchone()
        if cap_row and cap_row["c"] >= config.MAX_REFERRALS_PER_DAY:
            conn.execute("ROLLBACK")
            return {"status": "cap_reached"}

        conn.execute("UPDATE wallets SET referred_by = ? WHERE id = ?", (referrer_id, referee_id))
        referee_balance = _credit_in_txn(conn, referee_id, reward, "referral_reward", reference_id, now)
        _credit_in_txn(conn, referrer_id, reward, "referral_reward", reference_id, now)
        conn.execute("COMMIT")
        logger.info("Referral redeemed: referrer=%s referee=%s reward=%d", referrer_id[:8], referee_id[:8], reward)
        return {"status": "ok", "reward": reward, "new_balance": referee_balance,
                "referrer_id": referrer_id}
    except Exception:
        conn.execute("ROLLBACK")
        raise


# --- Spark gifting (SPEC-GIFTING) ---
def gift_sparks(sender_id: str, recipient_code: str, amount: int, idempotency_key: str = "") -> dict:
    """Transfer `amount` sparks from `sender_id` to the wallet that owns `recipient_code`
    (the recipient's referral/"friend" code). One atomic debit-then-credit. Idempotent on the
    (sender, idempotency_key) pair so a retried request never double-sends.

    Returns a status dict: status ∈
      {ok, invalid_amount, invalid_code, self_gift, insufficient, recipient_full, daily_cap}.
    On ok: {status, amount, new_balance, recipient_id, duplicate?}. `duplicate` is True when an
    identical keyed request already went through (the reply is replayed, nothing moves)."""
    if not isinstance(amount, int) or not (config.GIFT_MIN_AMOUNT <= amount <= config.GIFT_MAX_AMOUNT):
        return {"status": "invalid_amount"}
    code = (recipient_code or "").strip().upper()
    key = (idempotency_key or "").strip()[:64]
    conn = _get_conn()
    now = int(time.time())
    since = _utc_midnight_epoch()
    reference_id = f"gift:{sender_id}:{key}" if key else ""
    conn.execute("BEGIN IMMEDIATE")
    try:
        # Idempotency: a prior keyed send with the same reference replays its original result, no
        # movement. Checked before the recipient/empty-code validation so a changed (or now-empty)
        # retry body can't fail or misreport the original gift. This ordering mirrors the Postgres
        # gift_sparks RPC exactly — both backends must give identical answers on a replay.
        if reference_id:
            prior = conn.execute(
                "SELECT sent.amount, sent.balance_after, recv.wallet_id AS recipient_id "
                "FROM token_transactions sent "
                "LEFT JOIN token_transactions recv ON recv.reference_id = sent.reference_id "
                "  AND recv.reason = 'gift_received' "
                "WHERE sent.reference_id = ? AND sent.wallet_id = ? AND sent.reason = 'gift_sent' "
                "LIMIT 1",
                (reference_id, sender_id),
            ).fetchone()
            if prior:
                conn.execute("ROLLBACK")
                original_amount = abs(int(prior["amount"]))
                return {"status": "ok", "duplicate": True, "amount": original_amount,
                        "original_amount": original_amount,
                        "new_balance": prior["balance_after"], "recipient_id": prior["recipient_id"]}

        if not code:
            conn.execute("ROLLBACK")
            return {"status": "invalid_code"}
        recipient = conn.execute(
            "SELECT id, balance FROM wallets WHERE referral_code = ?", (code,)
        ).fetchone()
        if not recipient:
            conn.execute("ROLLBACK")
            return {"status": "invalid_code"}
        recipient_id = recipient["id"]
        if recipient_id == sender_id:
            conn.execute("ROLLBACK")
            return {"status": "self_gift"}

        srow = conn.execute("SELECT balance FROM wallets WHERE id = ?", (sender_id,)).fetchone()
        sender_balance = srow["balance"] if srow else 0
        if sender_balance < amount:
            conn.execute("ROLLBACK")
            return {"status": "insufficient", "new_balance": sender_balance}

        # Per-sender daily caps: number of gifts AND total sparks sent since UTC midnight.
        cap = conn.execute(
            "SELECT COUNT(*) AS c, COALESCE(-SUM(amount), 0) AS s FROM token_transactions "
            "WHERE wallet_id = ? AND reason = 'gift_sent' AND created_at >= ?",
            (sender_id, since),
        ).fetchone()
        if cap["c"] >= config.MAX_GIFTS_PER_DAY or cap["s"] + amount > config.MAX_GIFT_TOKENS_PER_DAY:
            conn.execute("ROLLBACK")
            return {"status": "daily_cap", "new_balance": sender_balance}

        # Conserve sparks: never debit the sender if the recipient can't hold the full gift.
        if recipient["balance"] + amount > config.MAX_TOKEN_BALANCE:
            conn.execute("ROLLBACK")
            return {"status": "recipient_full", "new_balance": sender_balance}

        new_sender = sender_balance - amount
        conn.execute("UPDATE wallets SET balance = ? WHERE id = ?", (new_sender, sender_id))
        conn.execute(
            "INSERT INTO token_transactions (wallet_id, amount, reason, reference_id, balance_after, created_at) "
            "VALUES (?, ?, 'gift_sent', ?, ?, ?)",
            (sender_id, -amount, reference_id or None, new_sender, now),
        )
        new_recipient = recipient["balance"] + amount
        conn.execute("UPDATE wallets SET balance = ? WHERE id = ?", (new_recipient, recipient_id))
        conn.execute(
            "INSERT INTO token_transactions (wallet_id, amount, reason, reference_id, balance_after, created_at) "
            "VALUES (?, ?, 'gift_received', ?, ?, ?)",
            (recipient_id, amount, reference_id or None, new_recipient, now),
        )
        conn.execute("COMMIT")
        logger.info("Gift sent: sender=%s recipient=%s amount=%d", sender_id[:8], recipient_id[:8], amount)
        return {"status": "ok", "amount": amount, "new_balance": new_sender, "recipient_id": recipient_id}
    except Exception:
        conn.execute("ROLLBACK")
        raise


# --- Achievements / badges (SPEC-ACHIEVEMENTS) ---
def award_achievement(wallet_id: str, badge_id: str) -> bool:
    """Idempotently award a badge. Returns True only on the first award (so callers can fire a
    one-time analytics/notification), False if already held or the badge id is unknown."""
    if badge_id not in config.ACHIEVEMENT_IDS:
        return False
    conn = _get_conn()
    cur = conn.execute(
        "INSERT OR IGNORE INTO achievements (wallet_id, badge_id, awarded_at) VALUES (?, ?, ?)",
        (wallet_id, badge_id, int(time.time())),
    )
    conn.commit()
    return cur.rowcount > 0


def list_achievements(wallet_id: str) -> dict:
    """Return {badge_id: awarded_at} for every badge this wallet has earned."""
    conn = _get_conn()
    rows = conn.execute(
        "SELECT badge_id, awarded_at FROM achievements WHERE wallet_id = ?", (wallet_id,)
    ).fetchall()
    return {row["badge_id"]: row["awarded_at"] for row in rows}


# --- Share-card snapshots (SPEC-SHARE-CARD) ---
def save_share_snapshot(token: str, game_type: str, winner: str, top_score: int,
                        player_count: int, created_at: int) -> None:
    """Persist a share snapshot. Prunes rows older than SHARE_TTL_SECONDS opportunistically."""
    conn = _get_conn()
    cutoff = int(time.time()) - config.SHARE_TTL_SECONDS
    conn.execute("DELETE FROM share_snapshots WHERE created_at < ?", (cutoff,))
    conn.execute(
        "INSERT OR REPLACE INTO share_snapshots "
        "(token, game_type, winner, top_score, player_count, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (token, game_type, winner, int(top_score), int(player_count), int(created_at)),
    )
    conn.commit()


def get_share_snapshot(token: str) -> dict | None:
    """Return a share snapshot by token, or None if missing/expired."""
    conn = _get_conn()
    row = conn.execute(
        "SELECT game_type, winner, top_score, player_count, created_at "
        "FROM share_snapshots WHERE token = ?", (token,)
    ).fetchone()
    if not row:
        return None
    snap = dict(row)
    if int(time.time()) - snap["created_at"] > config.SHARE_TTL_SECONDS:
        return None
    return snap


# --- Game results / stats (SPEC-GAME-STATS) ---

def record_game_result(room_code: str, wallet_id: str, game_type: str, game_title: str,
                       player_count: int, winner_nickname: str, top_score: int,
                       completed_at: int) -> bool:
    """Persist one completed game for the host's wallet. Returns True if newly recorded.

    INSERT OR IGNORE on the room_code PK makes this idempotent: several engines can reach a
    podium more than once for the same room (re-broadcast, reconnect, host re-entering PODIUM),
    and double-counting would inflate every stat on the screen.
    """
    if not wallet_id or not room_code:
        return False
    conn = _get_conn()
    cur = conn.execute(
        "INSERT OR IGNORE INTO game_results "
        "(room_code, wallet_id, game_type, game_title, player_count, winner_nickname, top_score, completed_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (room_code, wallet_id, game_type or "", game_title or "", int(player_count or 0),
         (winner_nickname or "")[:60], int(top_score or 0), int(completed_at)),
    )
    conn.commit()
    return cur.rowcount > 0


def get_wallet_stats(wallet_id: str) -> dict:
    """Aggregate hosting stats for one wallet. Always returns a dict — a wallet with no games
    yields zeros rather than None, so the UI never has to special-case a first-time host."""
    conn = _get_conn()
    row = conn.execute(
        "SELECT COUNT(*) AS games_hosted, "
        "       COALESCE(SUM(player_count), 0) AS players_entertained, "
        "       COALESCE(MAX(completed_at), 0) AS last_played_at "
        "FROM game_results WHERE wallet_id = ?", (wallet_id,)
    ).fetchone()
    stats = dict(row) if row else {"games_hosted": 0, "players_entertained": 0, "last_played_at": 0}
    fav = conn.execute(
        "SELECT game_type, COUNT(*) AS n FROM game_results WHERE wallet_id = ? "
        "GROUP BY game_type ORDER BY n DESC, game_type ASC LIMIT 1", (wallet_id,)
    ).fetchone()
    stats["favorite_game_type"] = fav["game_type"] if fav else ""
    stats["favorite_game_count"] = fav["n"] if fav else 0
    by_type = conn.execute(
        "SELECT game_type, COUNT(*) AS n FROM game_results WHERE wallet_id = ? "
        "GROUP BY game_type ORDER BY n DESC, game_type ASC", (wallet_id,)
    ).fetchall()
    stats["by_game_type"] = [{"game_type": r["game_type"], "count": r["n"]} for r in by_type]
    stats["distinct_games_played"] = len(by_type)
    return stats


def get_recent_games(wallet_id: str, limit: int = 10) -> list[dict]:
    """Most recent completed games for a wallet, newest first."""
    limit = max(1, min(int(limit or 10), 50))
    conn = _get_conn()
    rows = conn.execute(
        "SELECT room_code, game_type, game_title, player_count, winner_nickname, top_score, completed_at "
        "FROM game_results WHERE wallet_id = ? ORDER BY completed_at DESC LIMIT ?",
        (wallet_id, limit),
    ).fetchall()
    return [dict(r) for r in rows]


# --- Operator settings (SPEC-REMOTE-CONFIG §admin) ---

def get_setting(key: str) -> str:
    """Return a stored setting, or '' if unset."""
    conn = _get_conn()
    row = conn.execute("SELECT value FROM app_settings WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else ""


def set_setting(key: str, value: str) -> None:
    conn = _get_conn()
    conn.execute(
        "INSERT INTO app_settings (key, value, updated_at) VALUES (?, ?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at",
        (key, value, int(time.time())),
    )
    conn.commit()


def delete_setting(key: str) -> None:
    conn = _get_conn()
    conn.execute("DELETE FROM app_settings WHERE key = ?", (key,))
    conn.commit()


def credit_purchase(wallet_id: str, amount: int, reference_id: str, metadata: str = "") -> tuple[bool, int]:
    """Credit purchased tokens and increment lifetime_purchased. Returns (success, new_balance).
    Idempotent: if reference_id was already credited, returns current balance without double-crediting.
    metadata: optional JSON string with promo info etc."""
    if amount <= 0:
        raise ValueError(f"credit_purchase amount must be positive, got {amount}")
    conn = _get_conn()
    now = int(time.time())
    conn.execute("BEGIN IMMEDIATE")
    try:
        # Idempotency check inside transaction to prevent race conditions
        if reference_id:
            existing = conn.execute(
                "SELECT balance_after FROM token_transactions WHERE reference_id = ? AND wallet_id = ? AND reason = 'purchase'",
                (reference_id, wallet_id),
            ).fetchone()
            if existing:
                conn.execute("ROLLBACK")
                logger.info("Duplicate credit_purchase skipped for reference_id=%s", reference_id)
                return True, existing["balance_after"]

        row = conn.execute("SELECT balance FROM wallets WHERE id = ?", (wallet_id,)).fetchone()
        if not row:
            # A refund or delayed purchase can land after the user deleted their account. The
            # wallet is gone by then, and re-creating it here would silently resurrect the
            # account (SPEC-ACCOUNT-DELETION §4.3). Record nothing and let the caller ack the
            # webhook so the provider stops retrying.
            deleted = conn.execute(
                "SELECT 1 FROM deleted_accounts WHERE user_id = ? LIMIT 1", (wallet_id,)
            ).fetchone()
            if deleted:
                conn.execute("ROLLBACK")
                logger.info(
                    "credit_purchase ignored for deleted account %s (ref=%s)",
                    wallet_id[:8], reference_id,
                )
                return False, 0
            conn.execute(
                "INSERT INTO wallets (id, balance, lifetime_purchased, last_daily_bonus_date, "
                "ads_watched_today, ads_watched_date, created_at) VALUES (?, 0, 0, '', 0, '', ?)",
                (wallet_id, now),
            )
            current = 0
        else:
            current = row["balance"]

        new_balance = max(current, min(current + amount, config.MAX_TOKEN_BALANCE))
        actual_credit = new_balance - current

        conn.execute(
            "UPDATE wallets SET balance = ?, lifetime_purchased = lifetime_purchased + ? WHERE id = ?",
            (new_balance, actual_credit, wallet_id),
        )
        conn.execute(
            "INSERT INTO token_transactions (wallet_id, amount, reason, reference_id, balance_after, metadata, created_at) "
            "VALUES (?, ?, 'purchase', ?, ?, ?, ?)",
            (wallet_id, actual_credit, reference_id or None, new_balance, metadata or "", now),
        )
        conn.execute("COMMIT")
        return True, new_balance
    except Exception:
        conn.execute("ROLLBACK")
        raise


def merge_wallet(from_id: str, to_id: str):
    """Transfer balance from one wallet to another (device → user on sign-in).
    The source wallet balance is set to 0. Max 1 merge per target user wallet."""
    if from_id == to_id:
        return
    conn = _get_conn()
    conn.execute("BEGIN IMMEDIATE")
    try:
        # Max 1 merge per user account — prevents consolidating many synthetic wallets
        existing_merges = conn.execute(
            "SELECT COUNT(*) as cnt FROM token_transactions WHERE wallet_id = ? AND reason = 'merge_in'",
            (to_id,),
        ).fetchone()
        if existing_merges and existing_merges["cnt"] >= 1:
            logger.warning("Merge rejected: user wallet %s already has %d merge(s)", to_id[:8], existing_merges["cnt"])
            conn.execute("ROLLBACK")
            return

        # Check if this specific merge already happened
        already_merged = conn.execute(
            "SELECT 1 FROM token_transactions WHERE wallet_id = ? AND reason = 'merge_out' AND reference_id = ? LIMIT 1",
            (from_id, to_id),
        ).fetchone()
        if already_merged:
            conn.execute("ROLLBACK")
            return

        from_row = conn.execute("SELECT * FROM wallets WHERE id = ?", (from_id,)).fetchone()
        if not from_row or from_row["balance"] == 0:
            conn.execute("ROLLBACK")
            return

        # Ensure target wallet exists
        to_row = conn.execute("SELECT * FROM wallets WHERE id = ?", (to_id,)).fetchone()
        now = int(time.time())
        if not to_row:
            conn.execute(
                "INSERT INTO wallets (id, balance, lifetime_purchased, last_daily_bonus_date, "
                "ads_watched_today, ads_watched_date, created_at) VALUES (?, 0, 0, '', 0, '', ?)",
                (to_id, now),
            )
            to_balance = 0
        else:
            to_balance = to_row["balance"]

        transfer_amount = from_row["balance"]
        new_to_balance = max(to_balance, min(to_balance + transfer_amount, config.MAX_TOKEN_BALANCE))
        actual_transfer = new_to_balance - to_balance

        if actual_transfer < transfer_amount:
            logger.warning("Wallet merge capped: %s lost %d tokens (cap %d)", from_id, transfer_amount - actual_transfer, config.MAX_TOKEN_BALANCE)

        # Also merge lifetime_purchased
        from_purchased = from_row["lifetime_purchased"]

        conn.execute("UPDATE wallets SET balance = 0 WHERE id = ?", (from_id,))
        conn.execute(
            "UPDATE wallets SET balance = ?, lifetime_purchased = lifetime_purchased + ? WHERE id = ?",
            (new_to_balance, from_purchased, to_id),
        )

        # Log both sides
        conn.execute(
            "INSERT INTO token_transactions (wallet_id, amount, reason, reference_id, balance_after, created_at) "
            "VALUES (?, ?, 'merge_out', ?, 0, ?)",
            (from_id, -transfer_amount, to_id, now),
        )
        conn.execute(
            "INSERT INTO token_transactions (wallet_id, amount, reason, reference_id, balance_after, created_at) "
            "VALUES (?, ?, 'merge_in', ?, ?, ?)",
            (to_id, actual_transfer, from_id, new_to_balance, now),
        )
        conn.execute("COMMIT")
        logger.info("Wallet merge: %s → %s (%d sparks transferred)", from_id[:8], to_id[:8], actual_transfer)
    except Exception:
        conn.execute("ROLLBACK")
        raise


def migrate_entitlements_to_wallets():
    """One-time migration: convert active entitlements to token balances."""
    conn = _get_conn()
    rows = conn.execute(
        "SELECT * FROM entitlements WHERE status = 'active'"
    ).fetchall()
    if not rows:
        return

    for row in rows:
        wallet_id = row["user_id"] or row["device_id"]
        tokens_to_credit = row["games_remaining"] * config.COST_ROOM
        if tokens_to_credit <= 0:
            continue

        # Create or get wallet (no signup bonus for migration)
        get_or_create_wallet(wallet_id, signup_bonus=False)
        credit_tokens(wallet_id, tokens_to_credit, "migration", reference_id=row["id"])

        conn.execute(
            "UPDATE entitlements SET status = 'migrated_to_tokens' WHERE id = ?",
            (row["id"],),
        )
    conn.commit()
    logger.info("Migrated %d active entitlements to token wallets", len(rows))


def admin_grant_tokens(wallet_id: str, amount: int, note: str = "") -> int:
    """Admin: grant tokens to a wallet. Returns new balance.
    `note` lands in the ledger row's reference_id — the support runbook (DEPLOY.md M2) requires
    every remediation grant to carry the provider reference (cs_… / iap:…) as its audit link."""
    if amount <= 0 or amount > config.MAX_TOKEN_BALANCE:
        raise ValueError(f"admin_grant amount must be between 1 and {config.MAX_TOKEN_BALANCE}, got {amount}")
    get_or_create_wallet(wallet_id, signup_bonus=False)
    _, new_balance = credit_tokens(wallet_id, amount, "admin_grant", reference_id=note)
    return new_balance


def admin_lookup_wallet(wallet_id: str) -> Optional[dict]:
    """Admin: look up wallet and recent transactions."""
    conn = _get_conn()
    wallet = conn.execute("SELECT * FROM wallets WHERE id = ?", (wallet_id,)).fetchone()
    if not wallet:
        return None
    txns = [dict(r) for r in conn.execute(
        "SELECT * FROM token_transactions WHERE wallet_id = ? ORDER BY created_at DESC LIMIT 50",
        (wallet_id,),
    ).fetchall()]
    return {"wallet": dict(wallet), "transactions": txns}


# ---------------------------------------------------------------------------
# Webhook event deduplication
# ---------------------------------------------------------------------------

def is_webhook_event_processed(event_id: str) -> bool:
    """Check if a webhook event has already been processed."""
    conn = _get_conn()
    row = conn.execute("SELECT 1 FROM webhook_events WHERE event_id = ?", (event_id,)).fetchone()
    return row is not None


def get_refund_debits_for_session(reference_id: str) -> int:
    """Get total tokens already debited as refunds for a given stripe session."""
    conn = _get_conn()
    row = conn.execute(
        "SELECT COALESCE(SUM(ABS(amount)), 0) as total FROM token_transactions WHERE reference_id = ? AND reason = 'refund'",
        (reference_id,),
    ).fetchone()
    return row["total"] if row else 0


def get_credit_total_for_reference(reference_id: str, reason: str) -> int:
    """Total sparks already CREDITED against (reference_id, reason).

    The idempotency gate for credit paths that do not go through `credit_purchase` — notably
    `/purchases/restore`, which pays out a legacy entitlement once. `credit_tokens` has no
    reference de-duplication of its own, so without this a repeatable request mints sparks.
    """
    if not reference_id:
        return 0
    conn = _get_conn()
    row = conn.execute(
        "SELECT COALESCE(SUM(amount), 0) as total FROM token_transactions "
        "WHERE reference_id = ? AND reason = ? AND amount > 0",
        (reference_id, reason),
    ).fetchone()
    return row["total"] if row else 0


def mark_webhook_event_processed(event_id: str):
    """Mark a webhook event as processed. Call AFTER business logic succeeds."""
    conn = _get_conn()
    conn.execute(
        "INSERT OR IGNORE INTO webhook_events (event_id, processed_at) VALUES (?, ?)",
        (event_id, int(time.time())),
    )
    conn.commit()
    # Prune events older than 7 days
    cutoff = int(time.time()) - 7 * 86400
    conn.execute("DELETE FROM webhook_events WHERE processed_at < ?", (cutoff,))
    conn.commit()


def get_admin_stats() -> dict:
    """Return live admin stats without exposing storage internals."""
    conn = _get_conn()
    wallet_count = conn.execute("SELECT COUNT(*) as cnt FROM wallets").fetchone()["cnt"]
    total_sparks = conn.execute("SELECT COALESCE(SUM(balance), 0) as total FROM wallets").fetchone()["total"]
    paying_users = conn.execute("SELECT COUNT(*) as cnt FROM wallets WHERE lifetime_purchased > 0").fetchone()["cnt"]
    purchase_count = conn.execute("SELECT COUNT(*) as cnt FROM token_transactions WHERE reason = 'purchase'").fetchone()["cnt"]
    merge_count = conn.execute("SELECT COUNT(*) as cnt FROM token_transactions WHERE reason = 'merge_in'").fetchone()["cnt"]
    users_count = conn.execute("SELECT COUNT(*) as cnt FROM users").fetchone()["cnt"]
    return {
        "wallet_count": wallet_count,
        "total_sparks": total_sparks,
        "paying_users": paying_users,
        "purchase_count": purchase_count,
        "merge_count": merge_count,
        "users_count": users_count,
    }


# --- Custom quiz packs ---

def _row_to_quiz_pack(row: sqlite3.Row, questions: Optional[list[dict]] = None) -> dict:
    pack = dict(row)
    if questions is not None:
        pack["questions"] = questions
    return pack


def _question_row_to_dict(row: sqlite3.Row) -> dict:
    question = {
        "id": row["id"],
        "pack_id": row["pack_id"],
        "position": row["position"],
        "question_type": row["question_type"],
        "text": row["text"],
        "options": json.loads(row["options"]),
        "answer_index": row["answer_index"],
        "image_asset_id": row["image_asset_id"],
        "image_url": row["image_url"],
        "image_alt": row["image_alt"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }
    return {k: v for k, v in question.items() if v is not None}


def save_quiz_pack(owner_wallet_id: str, title: str, questions: list[dict], pack_id: Optional[str] = None) -> dict:
    conn = _get_conn()
    now = int(time.time())
    pack_id = pack_id or os.urandom(16).hex()
    existing = conn.execute(
        "SELECT * FROM custom_quiz_packs WHERE id = ? AND owner_wallet_id = ? AND deleted_at IS NULL",
        (pack_id, owner_wallet_id),
    ).fetchone()
    if existing:
        created_at = existing["created_at"]
    else:
        created_at = now
    conn.execute(
        "INSERT INTO custom_quiz_packs (id, owner_wallet_id, title, status, question_count, created_at, updated_at, deleted_at) "
        "VALUES (?, ?, ?, 'ready', ?, ?, ?, NULL) "
        "ON CONFLICT(id) DO UPDATE SET title = excluded.title, status = 'ready', question_count = excluded.question_count, updated_at = excluded.updated_at, deleted_at = NULL "
        "WHERE owner_wallet_id = excluded.owner_wallet_id",
        (pack_id, owner_wallet_id, title, len(questions), created_at, now),
    )
    conn.execute("DELETE FROM custom_quiz_questions WHERE pack_id = ?", (pack_id,))
    for index, q in enumerate(questions):
        conn.execute(
            "INSERT INTO custom_quiz_questions (id, pack_id, position, question_type, text, options, answer_index, image_asset_id, image_url, image_alt, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                f"{pack_id}_{index}",
                pack_id,
                index,
                "true_false" if len(q.get("options", [])) == 2 else "multiple_choice",
                q.get("text", ""),
                json.dumps(q.get("options", [])),
                q.get("answer_index", 0),
                q.get("image_asset_id"),
                q.get("image_url"),
                q.get("image_alt"),
                now,
                now,
            ),
        )
    conn.commit()
    pack = get_quiz_pack(owner_wallet_id, pack_id)
    if not pack:
        raise RuntimeError("Failed to save quiz pack")
    return pack


def list_quiz_packs(owner_wallet_id: str, limit: int = 50) -> list[dict]:
    conn = _get_conn()
    rows = conn.execute(
        "SELECT * FROM custom_quiz_packs WHERE owner_wallet_id = ? AND deleted_at IS NULL "
        "ORDER BY updated_at DESC LIMIT ?",
        (owner_wallet_id, limit),
    ).fetchall()
    return [_row_to_quiz_pack(row) for row in rows]


def get_quiz_pack(owner_wallet_id: str, pack_id: str) -> Optional[dict]:
    conn = _get_conn()
    pack = conn.execute(
        "SELECT * FROM custom_quiz_packs WHERE id = ? AND owner_wallet_id = ? AND deleted_at IS NULL",
        (pack_id, owner_wallet_id),
    ).fetchone()
    if not pack:
        return None
    questions = conn.execute(
        "SELECT * FROM custom_quiz_questions WHERE pack_id = ? ORDER BY position ASC",
        (pack_id,),
    ).fetchall()
    return _row_to_quiz_pack(pack, [_question_row_to_dict(row) for row in questions])


def delete_quiz_pack(owner_wallet_id: str, pack_id: str) -> bool:
    conn = _get_conn()
    now = int(time.time())
    cursor = conn.execute(
        "UPDATE custom_quiz_packs SET status = 'deleted', deleted_at = ?, updated_at = ? "
        "WHERE id = ? AND owner_wallet_id = ? AND deleted_at IS NULL",
        (now, now, pack_id, owner_wallet_id),
    )
    conn.commit()
    return cursor.rowcount > 0


def _content_type_for_game(game_type: str) -> str:
    return "mlt" if game_type == "wmlt" else game_type


def _game_type_for_content_type(content_type: str) -> str:
    return "wmlt" if content_type == "mlt" else content_type


def _row_to_game_content(row) -> dict:
    item = dict(row)
    if isinstance(item.get("payload"), str):
        item["payload"] = json.loads(item["payload"])
    item["game_type"] = _game_type_for_content_type(item.get("content_type", ""))
    item["updated_at"] = item.get("updated_at") or item.get("created_at")
    return item


def save_game_content(owner_wallet_id: str, game_type: str, title: str, payload: dict, content_id: Optional[str] = None) -> dict:
    conn = _get_conn()
    now = int(time.time())
    content_id = content_id or os.urandom(16).hex()
    content_type = _content_type_for_game(game_type)
    existing = conn.execute(
        "SELECT * FROM generated_content WHERE id = ? AND wallet_id = ?",
        (content_id, owner_wallet_id),
    ).fetchone()
    created_at = existing["created_at"] if existing else now
    conn.execute(
        "INSERT INTO generated_content (id, wallet_id, content_type, title, payload, prompt, model, provider, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, NULL, NULL, NULL, ?, ?) "
        "ON CONFLICT(id) DO UPDATE SET title = excluded.title, payload = excluded.payload, updated_at = excluded.updated_at "
        "WHERE wallet_id = excluded.wallet_id",
        (content_id, owner_wallet_id, content_type, title, json.dumps(payload), created_at, now),
    )
    conn.commit()
    content = get_game_content(owner_wallet_id, content_id)
    if not content:
        raise RuntimeError("Failed to save game content")
    return content


def list_game_content(owner_wallet_id: str, game_types: Optional[list[str]] = None, limit: int = 50) -> list[dict]:
    conn = _get_conn()
    content_types = [_content_type_for_game(game_type) for game_type in (game_types or ["wmlt", "drawing"])]
    placeholders = ",".join("?" for _ in content_types)
    rows = conn.execute(
        f"SELECT * FROM generated_content WHERE wallet_id = ? AND content_type IN ({placeholders}) "
        "ORDER BY COALESCE(updated_at, created_at) DESC LIMIT ?",
        (owner_wallet_id, *content_types, limit),
    ).fetchall()
    return [_row_to_game_content(row) for row in rows]


def get_game_content(owner_wallet_id: str, content_id: str) -> Optional[dict]:
    conn = _get_conn()
    row = conn.execute(
        "SELECT * FROM generated_content WHERE id = ? AND wallet_id = ?",
        (content_id, owner_wallet_id),
    ).fetchone()
    return _row_to_game_content(row) if row else None


def delete_game_content(owner_wallet_id: str, content_id: str) -> bool:
    conn = _get_conn()
    cursor = conn.execute(
        "DELETE FROM generated_content WHERE id = ? AND wallet_id = ?",
        (content_id, owner_wallet_id),
    )
    conn.commit()
    return cursor.rowcount > 0


def _row_to_host_app_catalog_flag(row) -> dict:
    item = dict(row)
    for key in ("allowlist_party_ids", "allowlist_external_user_ids"):
        if isinstance(item.get(key), str):
            item[key] = json.loads(item[key] or "[]")
    if isinstance(item.get("capability_overrides"), str):
        item["capability_overrides"] = json.loads(item["capability_overrides"] or "{}")
    item["enabled"] = bool(item.get("enabled"))
    return item


def list_host_app_catalog_flags(environment: str, host_app: str) -> list[dict]:
    conn = _get_conn()
    rows = conn.execute(
        "SELECT * FROM host_app_catalog_flags WHERE environment = ? AND host_app = ?",
        (environment, host_app),
    ).fetchall()
    return [_row_to_host_app_catalog_flag(row) for row in rows]


def upsert_host_app_catalog_flag(environment: str, host_app: str, game_id: str, flag: dict) -> dict:
    conn = _get_conn()
    now = int(time.time())
    row_id = flag.get("id") or os.urandom(16).hex()
    conn.execute(
        "INSERT INTO host_app_catalog_flags "
        "(id, environment, host_app, game_id, enabled, status, allowlist_party_ids, "
        "allowlist_external_user_ids, rollout_percentage, capability_overrides, notes, updated_by, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
        "ON CONFLICT(environment, host_app, game_id) DO UPDATE SET "
        "enabled = excluded.enabled, status = excluded.status, "
        "allowlist_party_ids = excluded.allowlist_party_ids, "
        "allowlist_external_user_ids = excluded.allowlist_external_user_ids, "
        "rollout_percentage = excluded.rollout_percentage, "
        "capability_overrides = excluded.capability_overrides, notes = excluded.notes, "
        "updated_by = excluded.updated_by, updated_at = excluded.updated_at",
        (
            row_id,
            environment,
            host_app,
            game_id,
            1 if flag.get("enabled") else 0,
            flag.get("status") or "disabled",
            json.dumps(flag.get("allowlist_party_ids") or []),
            json.dumps(flag.get("allowlist_external_user_ids") or []),
            flag.get("rollout_percentage"),
            json.dumps(flag.get("capability_overrides") or {}),
            flag.get("notes") or "",
            flag.get("updated_by") or "",
            now,
        ),
    )
    conn.commit()
    rows = conn.execute(
        "SELECT * FROM host_app_catalog_flags WHERE environment = ? AND host_app = ? AND game_id = ?",
        (environment, host_app, game_id),
    ).fetchall()
    return _row_to_host_app_catalog_flag(rows[0])


def create_media_asset(asset_id: str, owner_wallet_id: str, storage_path: str, public_url: str, mime_type: str, bytes_size: int = 0, status: str = "pending", alt_text: str = "") -> dict:
    conn = _get_conn()
    now = int(time.time())
    conn.execute(
        "INSERT INTO media_assets (id, owner_wallet_id, storage_backend, storage_path, public_url, status, mime_type, bytes, alt_text, created_at, updated_at) "
        "VALUES (?, ?, 'ionos', ?, ?, ?, ?, ?, ?, ?, ?)",
        (asset_id, owner_wallet_id, storage_path, public_url, status, mime_type, bytes_size, alt_text, now, now),
    )
    conn.commit()
    return get_media_asset(owner_wallet_id, asset_id) or {}


def finalize_media_asset(owner_wallet_id: str, asset_id: str, bytes_size: int = 0, alt_text: str = "") -> Optional[dict]:
    conn = _get_conn()
    now = int(time.time())
    updates = {"status": "ready", "updated_at": now}
    if bytes_size > 0:
        updates["bytes"] = bytes_size
    if alt_text:
        updates["alt_text"] = alt_text
    assignments = ", ".join(f"{key} = ?" for key in updates)
    values = list(updates.values()) + [asset_id, owner_wallet_id]
    conn.execute(
        f"UPDATE media_assets SET {assignments} WHERE id = ? AND owner_wallet_id = ?",
        values,
    )
    conn.commit()
    return get_media_asset(owner_wallet_id, asset_id)


def get_media_asset(owner_wallet_id: str, asset_id: str) -> Optional[dict]:
    conn = _get_conn()
    row = conn.execute(
        "SELECT * FROM media_assets WHERE id = ? AND owner_wallet_id = ?",
        (asset_id, owner_wallet_id),
    ).fetchone()
    return dict(row) if row else None


# --- Durable game sessions for host-app integrations ---

def _session_row_to_dict(row: sqlite3.Row) -> dict:
    data = dict(row)
    for key in ("launch_routes", "feed_card", "result_summary"):
        raw = data.get(key)
        if raw:
            data[key] = json.loads(raw)
        elif key == "result_summary":
            data[key] = None
        else:
            data[key] = {}
    data["joinable"] = bool(data.get("joinable"))
    return data


def create_game_session(session: dict) -> dict:
    conn = _get_conn()
    now = int(time.time())
    row = {
        "id": session["id"],
        "host_app": session["host_app"],
        "external_container_id": session["external_container_id"],
        "external_container_type": session.get("external_container_type", ""),
        "external_container_title": session.get("external_container_title", ""),
        "external_host_user_id": session.get("external_host_user_id", ""),
        "external_host_display_name": session.get("external_host_display_name", ""),
        "game_type": session["game_type"],
        "game_id": session.get("game_id", ""),
        "game_title": session.get("game_title", ""),
        "room_code": session["room_code"],
        "organizer_token": session.get("organizer_token", ""),
        "status": session.get("status", "lobby"),
        "joinable": 1 if session.get("joinable", True) else 0,
        "closed_reason": session.get("closed_reason"),
        "closed_message": session.get("closed_message"),
        "superseded_by_session_id": session.get("superseded_by_session_id"),
        "launch_routes": json.dumps(session.get("launch_routes", {})),
        "feed_card": json.dumps(session.get("feed_card", {})),
        "result_summary": json.dumps(session["result_summary"]) if session.get("result_summary") is not None else None,
        "created_at": session.get("created_at", now),
        "started_at": session.get("started_at"),
        "completed_at": session.get("completed_at"),
        "expires_at": session.get("expires_at", now + config.REVELRY_SESSION_LOBBY_TTL_SECONDS),
        "last_activity_at": session.get("last_activity_at", now),
        "updated_at": session.get("updated_at", now),
    }
    conn.execute(
        "INSERT INTO game_sessions (id, host_app, external_container_id, external_container_type, external_container_title, "
        "external_host_user_id, external_host_display_name, game_type, game_id, game_title, room_code, organizer_token, "
        "status, joinable, closed_reason, closed_message, superseded_by_session_id, launch_routes, feed_card, result_summary, "
        "created_at, started_at, completed_at, expires_at, last_activity_at, updated_at) "
        "VALUES (:id, :host_app, :external_container_id, :external_container_type, :external_container_title, "
        ":external_host_user_id, :external_host_display_name, :game_type, :game_id, :game_title, :room_code, :organizer_token, "
        ":status, :joinable, :closed_reason, :closed_message, :superseded_by_session_id, :launch_routes, :feed_card, :result_summary, "
        ":created_at, :started_at, :completed_at, :expires_at, :last_activity_at, :updated_at)",
        row,
    )
    conn.commit()
    created = get_game_session(session["id"])
    if not created:
        raise RuntimeError("Failed to create game session")
    return created


def get_game_session(session_id: str) -> Optional[dict]:
    conn = _get_conn()
    row = conn.execute("SELECT * FROM game_sessions WHERE id = ?", (session_id,)).fetchone()
    return _session_row_to_dict(row) if row else None


def get_game_session_by_room(room_code: str) -> Optional[dict]:
    conn = _get_conn()
    row = conn.execute(
        "SELECT * FROM game_sessions WHERE room_code = ? ORDER BY created_at DESC LIMIT 1",
        (room_code,),
    ).fetchone()
    return _session_row_to_dict(row) if row else None


def get_active_game_session(host_app: str, external_container_id: str) -> Optional[dict]:
    conn = _get_conn()
    row = conn.execute(
        "SELECT * FROM game_sessions WHERE host_app = ? AND external_container_id = ? "
        "AND status IN ('lobby', 'active', 'paused') ORDER BY created_at DESC LIMIT 1",
        (host_app, external_container_id),
    ).fetchone()
    return _session_row_to_dict(row) if row else None


def get_latest_game_session(host_app: str, external_container_id: str, game_type: str = "") -> Optional[dict]:
    conn = _get_conn()
    if game_type:
        row = conn.execute(
            "SELECT * FROM game_sessions WHERE host_app = ? AND external_container_id = ? AND game_type = ? "
            "ORDER BY created_at DESC LIMIT 1",
            (host_app, external_container_id, game_type),
        ).fetchone()
    else:
        row = conn.execute(
            "SELECT * FROM game_sessions WHERE host_app = ? AND external_container_id = ? "
            "ORDER BY created_at DESC LIMIT 1",
            (host_app, external_container_id),
        ).fetchone()
    return _session_row_to_dict(row) if row else None


def game_content_has_sessions(host_app: str, external_container_id: str, game_id: str) -> bool:
    conn = _get_conn()
    row = conn.execute(
        "SELECT 1 FROM game_sessions WHERE host_app = ? AND external_container_id = ? AND game_id = ? LIMIT 1",
        (host_app, external_container_id, game_id),
    ).fetchone()
    return bool(row)


def update_game_session(session_id: str, updates: dict) -> Optional[dict]:
    allowed = {
        "status", "joinable", "closed_reason", "closed_message", "superseded_by_session_id",
        "launch_routes", "feed_card", "result_summary", "started_at", "completed_at",
        "expires_at", "last_activity_at", "updated_at",
    }
    body = {key: value for key, value in updates.items() if key in allowed}
    if not body:
        return get_game_session(session_id)
    if "joinable" in body:
        body["joinable"] = 1 if body["joinable"] else 0
    for key in ("launch_routes", "feed_card", "result_summary"):
        if key in body and body[key] is not None:
            body[key] = json.dumps(body[key])
    body["updated_at"] = body.get("updated_at", int(time.time()))
    assignments = ", ".join(f"{key} = ?" for key in body)
    values = list(body.values()) + [session_id]
    conn = _get_conn()
    conn.execute(f"UPDATE game_sessions SET {assignments} WHERE id = ?", values)
    conn.commit()
    return get_game_session(session_id)


if config.DB_BACKEND == "supabase":
    import supabase_db as _supabase_db

    _SUPABASE_EXPORTS = [
        "init_db",
        "create_entitlement",
        "revoke_entitlement_by_stripe",
        "activate_pending_entitlement",
        "get_entitlement_by_stripe_session",
        "check_idempotency",
        "record_idempotency",
        "store_pending_token",
        "pop_pending_token",
        "find_or_create_user",
        "get_user",
        "merge_device_to_user",
        "lookup_by_device",
        "lookup_entitlement",
        "admin_revoke",
        "find_restorable_entitlement",
        "admin_grant",
        "lookup_by_user",
        "lookup_user_by_email",
        "_utc_date_str",
        "wallet_exists",
        "party_grace_state",
        "has_room_spend",
        "has_signup_bonus",
        "migrate_grace_proofs",
        "record_grace_room",
        "get_or_create_wallet",
        "get_wallet_balance",
        "debit_tokens",
        "credit_tokens",
        "check_and_grant_daily_bonus",
        "check_and_grant_ad_reward",
        "get_or_create_referral_code",
        "redeem_referral",
        "gift_sparks",
        "award_achievement",
        "list_achievements",
        "save_share_snapshot",
        "get_share_snapshot",
        "get_setting",
        "set_setting",
        "delete_setting",
        "record_game_result",
        "get_wallet_stats",
        "get_recent_games",
        "has_ever_purchased",
        "credit_purchase",
        "merge_wallet",
        "delete_account",
        "is_account_deleted",
        "migrate_entitlements_to_wallets",
        "admin_grant_tokens",
        "admin_lookup_wallet",
        "is_webhook_event_processed",
        "get_refund_debits_for_session",
        "get_credit_total_for_reference",
        "mark_webhook_event_processed",
        "get_admin_stats",
        "save_quiz_pack",
        "list_quiz_packs",
        "get_quiz_pack",
        "delete_quiz_pack",
        "save_game_content",
        "list_game_content",
        "get_game_content",
        "delete_game_content",
        "create_media_asset",
        "finalize_media_asset",
        "get_media_asset",
        "create_game_session",
        "get_game_session",
        "get_game_session_by_room",
        "get_active_game_session",
        "get_latest_game_session",
        "game_content_has_sessions",
        "update_game_session",
        "list_host_app_catalog_flags",
        "upsert_host_app_catalog_flag",
    ]
    for _name in _SUPABASE_EXPORTS:
        globals()[_name] = getattr(_supabase_db, _name)
