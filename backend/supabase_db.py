"""Supabase/PostgREST implementation of the db.py persistence contract."""
from __future__ import annotations

import datetime
import json
import time
import uuid
from typing import Optional

import httpx

import config


_PENDING_TOKEN_TTL = 3600


class SupabaseDBError(RuntimeError):
    pass


class SupabaseClient:
    def __init__(self) -> None:
        if not config.SUPABASE_URL:
            raise SupabaseDBError("SUPABASE_URL is required when DB_BACKEND=supabase")
        if not config.SUPABASE_SERVICE_KEY:
            raise SupabaseDBError("SUPABASE_SERVICE_KEY is required when DB_BACKEND=supabase")
        if config.TABLE_PREFIX not in {"games_", "games_gamma_"}:
            raise SupabaseDBError(f"Unsupported TABLE_PREFIX: {config.TABLE_PREFIX!r}")

        self.base_url = config.SUPABASE_URL.rstrip("/")
        self.prefix = config.TABLE_PREFIX
        self.timeout = config.SUPABASE_TIMEOUT_SECONDS

    def _headers(self, prefer: str = "") -> dict:
        headers = {
            "apikey": config.SUPABASE_SERVICE_KEY,
            "Authorization": f"Bearer {config.SUPABASE_SERVICE_KEY}",
            "Content-Type": "application/json",
        }
        if prefer:
            headers["Prefer"] = prefer
        return headers

    def _request(self, method: str, path: str, *, params=None, json=None, prefer: str = ""):
        url = f"{self.base_url}{path}"
        with httpx.Client(timeout=self.timeout) as client:
            response = client.request(
                method,
                url,
                params=params,
                json=json,
                headers=self._headers(prefer),
            )
        if response.status_code >= 400:
            raise SupabaseDBError(f"{method} {path} failed: {response.status_code} {response.text}")
        if not response.content:
            return None
        return response.json()

    def table_name(self, table: str) -> str:
        return f"{self.prefix}{table}"

    def rpc_name(self, name: str) -> str:
        return f"{self.prefix}{name}"

    def select(self, table: str, *, filters: Optional[dict] = None, order: str = "", limit: Optional[int] = None, select: str = "*") -> list[dict]:
        params = {"select": select}
        if filters:
            params.update(filters)
        if order:
            params["order"] = order
        if limit is not None:
            params["limit"] = str(limit)
        return self._request("GET", f"/rest/v1/{self.table_name(table)}", params=params) or []

    def insert(self, table: str, row: dict, *, ignore_duplicates: bool = False) -> list[dict]:
        prefer = "return=representation"
        if ignore_duplicates:
            prefer = "resolution=ignore-duplicates,return=representation"
        return self._request("POST", f"/rest/v1/{self.table_name(table)}", json=row, prefer=prefer) or []

    def upsert(self, table: str, row: dict, *, on_conflict: str) -> list[dict]:
        return self._request(
            "POST",
            f"/rest/v1/{self.table_name(table)}",
            params={"on_conflict": on_conflict},
            json=row,
            prefer="resolution=merge-duplicates,return=representation",
        ) or []

    def update(self, table: str, body: dict, *, filters: dict) -> list[dict]:
        return self._request(
            "PATCH",
            f"/rest/v1/{self.table_name(table)}",
            params=filters,
            json=body,
            prefer="return=representation",
        ) or []

    def delete(self, table: str, *, filters: dict) -> list[dict]:
        return self._request(
            "DELETE",
            f"/rest/v1/{self.table_name(table)}",
            params=filters,
            prefer="return=representation",
        ) or []

    def rpc(self, name: str, payload: dict):
        return self._request("POST", f"/rest/v1/rpc/{self.rpc_name(name)}", json=payload)


_client: Optional[SupabaseClient] = None


def _sb() -> SupabaseClient:
    global _client
    if _client is None:
        _client = SupabaseClient()
    return _client


def _first(rows: list[dict]) -> Optional[dict]:
    return rows[0] if rows else None


def _now() -> int:
    return int(time.time())


def _utc_date_str() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")


def init_db():
    _sb()


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
    now = _now()
    try:
        _sb().insert("entitlements", {
            "id": entitlement_id,
            "user_id": user_id,
            "device_id": device_id,
            "status": status,
            "games_remaining": games,
            "expires_at": now + (config.PREMIUM_DURATION_HOURS * 3600),
            "stripe_session_id": stripe_session_id,
            "apple_transaction_id": apple_transaction_id,
            "google_order_id": google_order_id,
            "created_at": now,
            "updated_at": now,
        })
        return True
    except SupabaseDBError as exc:
        if "409" in str(exc):
            return False
        raise


def _expire_entitlements() -> None:
    _sb().update(
        "entitlements",
        {"status": "expired_time", "updated_at": _now()},
        filters={"status": "eq.active", "expires_at": f"lte.{_now()}"},
    )


def revoke_entitlement_by_stripe(stripe_session_id: str) -> bool:
    rows = _sb().update(
        "entitlements",
        {"status": "revoked_refunded", "updated_at": _now()},
        filters={"stripe_session_id": f"eq.{stripe_session_id}", "status": "in.(active,exhausted_games,expired_time)"},
    )
    return bool(rows)


def activate_pending_entitlement(stripe_session_id: str) -> Optional[dict]:
    now = _now()
    rows = _sb().update(
        "entitlements",
        {"status": "active", "expires_at": now + (config.PREMIUM_DURATION_HOURS * 3600), "updated_at": now},
        filters={"stripe_session_id": f"eq.{stripe_session_id}", "status": "eq.pending_payment"},
    )
    return _first(rows)


def get_entitlement_by_stripe_session(stripe_session_id: str) -> Optional[dict]:
    return _first(_sb().select("entitlements", filters={"stripe_session_id": f"eq.{stripe_session_id}"}, limit=1))


def check_idempotency(key: str, device_id: str = "") -> Optional[str]:
    if not key:
        return None
    cutoff = _now() - 3600
    _sb().delete("request_log", filters={"created_at": f"lt.{cutoff}"})
    row = _first(_sb().select("request_log", filters={"idempotency_key": f"eq.{key}"}, limit=1))
    if not row:
        return None
    if device_id and row["device_id"] != device_id:
        return None
    return row.get("result_id")


def record_idempotency(key: str, device_id: str, result_id: str):
    if not key:
        return
    _sb().insert(
        "request_log",
        {"idempotency_key": key, "device_id": device_id, "result_id": result_id, "created_at": _now()},
        ignore_duplicates=True,
    )


def store_pending_token(device_id: str, token: str):
    now = _now()
    _sb().delete("pending_tokens", filters={"created_at": f"lt.{now - _PENDING_TOKEN_TTL}"})
    _sb().upsert("pending_tokens", {"device_id": device_id, "token": token, "created_at": now}, on_conflict="device_id")


def pop_pending_token(device_id: str) -> Optional[str]:
    now = _now()
    _sb().delete("pending_tokens", filters={"created_at": f"lt.{now - _PENDING_TOKEN_TTL}"})
    row = _first(_sb().delete("pending_tokens", filters={"device_id": f"eq.{device_id}"}))
    return row.get("token") if row else None


def find_or_create_user(provider: str, provider_subject_id: str, email: Optional[str] = None) -> dict:
    rows = _sb().select(
        "users",
        filters={"provider": f"eq.{provider}", "provider_subject_id": f"eq.{provider_subject_id}"},
        limit=1,
    )
    if rows:
        user = rows[0]
        if email and user.get("email") != email:
            updated = _sb().update("users", {"email": email, "updated_at": _now()}, filters={"id": f"eq.{user['id']}"})
            return updated[0] if updated else {**user, "email": email}
        return user

    now = _now()
    user = {
        "id": str(uuid.uuid4()),
        "provider": provider,
        "provider_subject_id": provider_subject_id,
        "email": email,
        "created_at": now,
        "updated_at": now,
    }
    try:
        created = _sb().insert("users", user)
        return created[0] if created else user
    except SupabaseDBError as exc:
        if "409" not in str(exc):
            raise
        row = _first(_sb().select(
            "users",
            filters={"provider": f"eq.{provider}", "provider_subject_id": f"eq.{provider_subject_id}"},
            limit=1,
        ))
        if not row:
            raise
        return row


def get_user(user_id: str) -> Optional[dict]:
    return _first(_sb().select("users", filters={"id": f"eq.{user_id}"}, limit=1))


def merge_device_to_user(user_id: str, device_id: str):
    now = _now()
    _sb().update("entitlements", {"user_id": user_id, "updated_at": now}, filters={"device_id": f"eq.{device_id}", "user_id": "is.null"})
    _sb().update("device_usage", {"user_id": user_id}, filters={"device_id": f"eq.{device_id}", "user_id": "is.null"})


def lookup_by_device(device_id: str) -> dict:
    entitlements = _sb().select("entitlements", filters={"device_id": f"eq.{device_id}"}, order="created_at.desc")
    usage = _first(_sb().select("device_usage", filters={"device_id": f"eq.{device_id}"}, limit=1))
    return {"device_id": device_id, "entitlements": entitlements, "usage": usage}


def lookup_entitlement(entitlement_id: str) -> Optional[dict]:
    return _first(_sb().select("entitlements", filters={"id": f"eq.{entitlement_id}"}, limit=1))


def admin_revoke(entitlement_id: str) -> bool:
    rows = _sb().update(
        "entitlements",
        {"status": "revoked_refunded", "updated_at": _now()},
        filters={"id": f"eq.{entitlement_id}", "status": "in.(active,expired_time,exhausted_games)"},
    )
    return bool(rows)


def find_restorable_entitlement(device_id: str, user_id: Optional[str] = None) -> Optional[dict]:
    common = {
        "status": "in.(active,expired_time,exhausted_games)",
        "or": "(apple_transaction_id.not.is.null,google_order_id.not.is.null)",
    }
    if user_id:
        row = _first(_sb().select("entitlements", filters={**common, "user_id": f"eq.{user_id}"}, order="created_at.desc", limit=1))
        if row:
            return row
    return _first(_sb().select("entitlements", filters={**common, "device_id": f"eq.{device_id}"}, order="created_at.desc", limit=1))


def admin_grant(device_id: str, games: int = 10, hours: int = 720, user_id: Optional[str] = None) -> str:
    eid = str(uuid.uuid4())
    now = _now()
    _sb().insert("entitlements", {
        "id": eid,
        "device_id": device_id,
        "user_id": user_id,
        "status": "active",
        "games_remaining": games,
        "expires_at": now + hours * 3600,
        "created_at": now,
        "updated_at": now,
    })
    return eid


def lookup_by_user(user_id: str) -> dict:
    user = get_user(user_id)
    if not user:
        return {"user_id": user_id, "user": None, "entitlements": [], "usage": [], "devices": []}
    entitlements = _sb().select("entitlements", filters={"user_id": f"eq.{user_id}"}, order="created_at.desc")
    usage = _sb().select("device_usage", filters={"user_id": f"eq.{user_id}"})
    devices = sorted({row["device_id"] for row in entitlements + usage if row.get("device_id")})
    return {"user_id": user_id, "user": user, "entitlements": entitlements, "usage": usage, "devices": devices}


def lookup_user_by_email(email: str) -> list[dict]:
    escaped = email.replace("*", "\\*")
    return _sb().select("users", filters={"email": f"ilike.*{escaped}*"}, limit=20)


def wallet_exists(wallet_id: str) -> bool:
    rows = _sb().select("wallets", filters={"id": f"eq.{wallet_id}"}, limit=1)
    return bool(rows)


def get_or_create_wallet(wallet_id: str, signup_bonus: bool = True) -> dict:
    result = _sb().rpc("ensure_wallet", {
        "p_wallet_id": wallet_id,
        "p_signup_bonus": signup_bonus,
        "p_signup_bonus_amount": config.SIGNUP_BONUS_TOKENS,
    })
    return result


def get_wallet_balance(wallet_id: str) -> int:
    row = _first(_sb().select("wallets", filters={"id": f"eq.{wallet_id}"}, select="balance", limit=1))
    return int(row["balance"]) if row else 0


def _effective_max_balance(wallet_id: str) -> int:
    return max(get_wallet_balance(wallet_id), config.MAX_TOKEN_BALANCE)


def debit_tokens(wallet_id: str, amount: int, reason: str, reference_id: str = "") -> tuple[bool, int]:
    if amount <= 0:
        raise ValueError(f"debit_tokens amount must be positive, got {amount}")
    result = _sb().rpc("debit_tokens", {
        "p_wallet_id": wallet_id,
        "p_amount": amount,
        "p_reason": reason,
        "p_reference_id": reference_id or None,
    })
    return bool(result["success"]), int(result["balance"])


def credit_tokens(wallet_id: str, amount: int, reason: str, reference_id: str = "") -> tuple[bool, int]:
    if amount <= 0:
        raise ValueError(f"credit_tokens amount must be positive, got {amount}")
    result = _sb().rpc("credit_tokens", {
        "p_wallet_id": wallet_id,
        "p_amount": amount,
        "p_reason": reason,
        "p_reference_id": reference_id or None,
        "p_metadata": "",
        "p_max_balance": _effective_max_balance(wallet_id),
    })
    return bool(result["success"]), int(result["balance"])


def check_and_grant_daily_bonus(wallet_id: str) -> tuple[bool, int, int, int]:
    """Returns (granted, balance, streak, reward). NOTE (SPEC-STREAK-BONUS): the currently-deployed
    `grant_daily_bonus` RPC still grants a FLAT bonus and does not track a streak; the call signature is
    left unchanged so it never breaks against the deployed RPC. Streak/reward are best-effort — if a future
    streak-aware RPC returns `streak`/`reward` they're used, else streak degrades to 1 on a grant. To
    activate full streak on Supabase, update `sql/games-schema.sql` `grant_daily_bonus` (add a bonus_streak
    column + streak math returning {granted,balance,streak,reward}) and redeploy."""
    result = _sb().rpc("grant_daily_bonus", {
        "p_wallet_id": wallet_id,
        "p_today": _utc_date_str(),
        "p_amount": config.STREAK_BASE,
        "p_max_balance": _effective_max_balance(wallet_id),
    })
    granted = bool(result["granted"])
    balance = int(result["balance"])
    streak = int(result.get("streak", 1 if granted else 0))
    reward = int(result.get("reward", config.STREAK_BASE))
    return granted, balance, streak, reward


def check_and_grant_ad_reward(wallet_id: str) -> tuple[bool, int, int]:
    result = _sb().rpc("grant_ad_reward", {
        "p_wallet_id": wallet_id,
        "p_today": _utc_date_str(),
        "p_amount": config.AD_REWARD_TOKENS,
        "p_max_ads_per_day": config.MAX_ADS_PER_DAY,
        "p_max_balance": _effective_max_balance(wallet_id),
    })
    return bool(result["granted"]), int(result["balance"]), int(result["ads_remaining"])


def has_ever_purchased(wallet_id: str) -> bool:
    row = _first(_sb().select("wallets", filters={"id": f"eq.{wallet_id}"}, select="lifetime_purchased", limit=1))
    return bool(row and int(row["lifetime_purchased"]) > 0)


# --- Referrals (SPEC-REFERRAL) — mirror db.py, backed by set_referral_code / redeem_referral RPCs. ---
import secrets as _secrets

_REFERRAL_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"


def _utc_midnight_epoch() -> int:
    now = datetime.datetime.now(datetime.timezone.utc)
    return int(now.replace(hour=0, minute=0, second=0, microsecond=0).timestamp())


def get_or_create_referral_code(wallet_id: str) -> str:
    for _ in range(12):
        candidate = "".join(_secrets.choice(_REFERRAL_ALPHABET) for _ in range(6))
        result = _sb().rpc("set_referral_code", {"p_wallet_id": wallet_id, "p_code": candidate})
        code = result.get("code")
        if code:
            return code
        # collision → retry with a new candidate
    raise SupabaseDBError("could not allocate a unique referral code")


def redeem_referral(referee_id: str, code: str) -> dict:
    code = (code or "").strip().upper()
    if not code:
        return {"status": "invalid_code"}
    result = _sb().rpc("redeem_referral", {
        "p_referee_id": referee_id,
        "p_code": code,
        "p_reward": config.REFERRAL_REWARD,
        "p_max_balance": _effective_max_balance(referee_id),
        "p_max_per_day": config.MAX_REFERRALS_PER_DAY,
        "p_since": _utc_midnight_epoch(),
    })
    if not isinstance(result, dict):
        return {"status": "invalid_code"}
    # The RPC returns the referee balance as `balance`; the SQLite wrapper and the
    # /referral/redeem response use `new_balance`. Normalize so both DB backends match.
    if "balance" in result and "new_balance" not in result:
        result["new_balance"] = result["balance"]
    return result


def gift_sparks(sender_id: str, recipient_code: str, amount: int, idempotency_key: str = "") -> dict:
    """Supabase wrapper for spark gifting (SPEC-GIFTING) — mirrors db.gift_sparks. The RPC does the
    whole atomic debit-then-credit + guards behind one server-side transaction. Uses the flat token
    cap: a recipient who couldn't hold the full gift is rejected (recipient_full), never truncated —
    so no sparks are destroyed. Normalizes the RPC's `balance` → `new_balance`."""
    if not isinstance(amount, int) or not (config.GIFT_MIN_AMOUNT <= amount <= config.GIFT_MAX_AMOUNT):
        return {"status": "invalid_amount"}
    code = (recipient_code or "").strip().upper()
    # NOTE: do not short-circuit an empty code here — defer to the RPC. On a keyed retry the RPC
    # replays the original gift *before* the recipient/empty-code check, so an empty (or changed)
    # retry body must not turn into an early invalid_code. This keeps the Supabase path identical to
    # the SQLite db.gift_sparks path, which does the same. (An empty code with no prior still → invalid_code.)
    key = (idempotency_key or "").strip()[:64]
    result = _sb().rpc("gift_sparks", {
        "p_sender_id": sender_id,
        "p_code": code,
        "p_amount": amount,
        "p_key": key,
        "p_min_amount": config.GIFT_MIN_AMOUNT,
        "p_max_amount": config.GIFT_MAX_AMOUNT,
        "p_max_per_day": config.MAX_GIFTS_PER_DAY,
        "p_max_tokens_per_day": config.MAX_GIFT_TOKENS_PER_DAY,
        "p_max_balance": config.MAX_TOKEN_BALANCE,
        "p_since": _utc_midnight_epoch(),
    })
    if not isinstance(result, dict):
        return {"status": "invalid_code"}
    if "balance" in result and "new_balance" not in result:
        result["new_balance"] = result["balance"]
    return result


# --- Achievements / badges (SPEC-ACHIEVEMENTS) — mirror db.py. ---
def award_achievement(wallet_id: str, badge_id: str) -> bool:
    if badge_id not in config.ACHIEVEMENT_IDS:
        return False
    result = _sb().rpc("award_achievement", {
        "p_wallet_id": wallet_id,
        "p_badge_id": badge_id,
    })
    return bool(isinstance(result, dict) and result.get("awarded"))


def list_achievements(wallet_id: str) -> dict:
    rows = _sb().select("achievements", filters={"wallet_id": f"eq.{wallet_id}"},
                        select="badge_id,awarded_at")
    return {row["badge_id"]: row["awarded_at"] for row in (rows or [])}


# --- Share-card snapshots (SPEC-SHARE-CARD) — mirror db.py. ---
def save_share_snapshot(token: str, game_type: str, winner: str, top_score: int,
                        player_count: int, created_at: int) -> None:
    _sb().upsert("share_snapshots", {
        "token": token,
        "game_type": game_type,
        "winner": winner,
        "top_score": int(top_score),
        "player_count": int(player_count),
        "created_at": int(created_at),
    }, on_conflict="token")


def get_share_snapshot(token: str) -> dict | None:
    row = _first(_sb().select("share_snapshots", filters={"token": f"eq.{token}"}, limit=1))
    if not row:
        return None
    snap = {k: row.get(k) for k in ("game_type", "winner", "top_score", "player_count", "created_at")}
    if int(time.time()) - int(snap["created_at"]) > config.SHARE_TTL_SECONDS:
        return None
    return snap


# --- Game results / stats (SPEC-GAME-STATS) ---

# Aggregation happens in Python over the wallet's rows rather than in a GROUP BY RPC:
# PostgREST has no clean grouping, and one host's lifetime games is a small set. The cap
# keeps a pathological wallet from pulling an unbounded result — stats above it are
# reported over the most recent STATS_ROW_CAP games, which is stated in the API response.
STATS_ROW_CAP = 1000


def record_game_result(room_code: str, wallet_id: str, game_type: str, game_title: str,
                       player_count: int, winner_nickname: str, top_score: int,
                       completed_at: int) -> bool:
    if not wallet_id or not room_code:
        return False
    # ignore_duplicates mirrors SQLite's INSERT OR IGNORE on the room_code PK, so a
    # re-broadcast podium for the same room can't double-count.
    rows = _sb().insert("game_results", {
        "room_code": room_code,
        "wallet_id": wallet_id,
        "game_type": game_type or "",
        "game_title": game_title or "",
        "player_count": int(player_count or 0),
        "winner_nickname": (winner_nickname or "")[:60],
        "top_score": int(top_score or 0),
        "completed_at": int(completed_at),
    }, ignore_duplicates=True)
    return bool(rows)


def _wallet_result_rows(wallet_id: str) -> list[dict]:
    return _sb().select(
        "game_results",
        filters={"wallet_id": f"eq.{wallet_id}"},
        order="completed_at.desc",
        limit=STATS_ROW_CAP,
    )


def get_wallet_stats(wallet_id: str) -> dict:
    rows = _wallet_result_rows(wallet_id)
    counts: dict[str, int] = {}
    for r in rows:
        gt = r.get("game_type") or ""
        counts[gt] = counts.get(gt, 0) + 1
    # Ties broken by game_type ascending, matching the SQLite ORDER BY n DESC, game_type ASC.
    by_type = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    return {
        "games_hosted": len(rows),
        "players_entertained": sum(int(r.get("player_count") or 0) for r in rows),
        "last_played_at": max((int(r.get("completed_at") or 0) for r in rows), default=0),
        "favorite_game_type": by_type[0][0] if by_type else "",
        "favorite_game_count": by_type[0][1] if by_type else 0,
        "by_game_type": [{"game_type": gt, "count": n} for gt, n in by_type],
        "distinct_games_played": len(by_type),
    }


def get_recent_games(wallet_id: str, limit: int = 10) -> list[dict]:
    limit = max(1, min(int(limit or 10), 50))
    rows = _sb().select(
        "game_results",
        filters={"wallet_id": f"eq.{wallet_id}"},
        order="completed_at.desc",
        limit=limit,
    )
    keys = ("room_code", "game_type", "game_title", "player_count",
            "winner_nickname", "top_score", "completed_at")
    return [{k: r.get(k) for k in keys} for r in rows]


# --- Operator settings (SPEC-REMOTE-CONFIG §admin) ---

def get_setting(key: str) -> str:
    row = _first(_sb().select("app_settings", filters={"key": f"eq.{key}"}, limit=1))
    return (row or {}).get("value") or ""


def set_setting(key: str, value: str) -> None:
    _sb().upsert("app_settings", {
        "key": key,
        "value": value,
        "updated_at": int(time.time()),
    }, on_conflict="key")


def delete_setting(key: str) -> None:
    _sb().delete("app_settings", filters={"key": f"eq.{key}"})


def credit_purchase(wallet_id: str, amount: int, reference_id: str, metadata: str = "") -> tuple[bool, int]:
    if amount <= 0:
        raise ValueError(f"credit_purchase amount must be positive, got {amount}")
    result = _sb().rpc("credit_purchase", {
        "p_wallet_id": wallet_id,
        "p_amount": amount,
        "p_reference_id": reference_id,
        "p_metadata": metadata or "",
        "p_max_balance": _effective_max_balance(wallet_id),
    })
    return bool(result["success"]), int(result["balance"])


def is_account_deleted(user_id: str) -> bool:
    """True if this user id is on the deleted-accounts denylist (SPEC-ACCOUNT-DELETION §2)."""
    if not user_id:
        return False
    return _first(_sb().select(
        "deleted_accounts", filters={"user_id": f"eq.{user_id}"}, limit=1,
    )) is not None


def delete_account(user_id: str) -> bool:
    """Delete the account and its data via the atomic RPC (SPEC-ACCOUNT-DELETION §3).

    One RPC rather than several REST deletes, so a partial failure cannot leave a
    half-deleted account (wallet gone, PII retained). Returns False if already deleted.
    """
    result = _sb().rpc("delete_account", {"p_user_id": user_id})
    if isinstance(result, dict):
        return bool(result.get("deleted"))
    return bool(result)


def merge_wallet(from_id: str, to_id: str):
    if from_id == to_id:
        return
    _sb().rpc("merge_wallet", {
        "p_from_id": from_id,
        "p_to_id": to_id,
        "p_max_balance": _effective_max_balance(to_id),
    })


def migrate_entitlements_to_wallets():
    # Data migration is handled explicitly during cutover, not at app startup.
    return


def admin_grant_tokens(wallet_id: str, amount: int, note: str = "") -> int:
    if amount <= 0 or amount > config.MAX_TOKEN_BALANCE:
        raise ValueError(f"admin_grant amount must be between 1 and {config.MAX_TOKEN_BALANCE}, got {amount}")
    get_or_create_wallet(wallet_id, signup_bonus=False)
    _, new_balance = credit_tokens(wallet_id, amount, "admin_grant", reference_id=note)
    return new_balance


def admin_lookup_wallet(wallet_id: str) -> Optional[dict]:
    wallet = _first(_sb().select("wallets", filters={"id": f"eq.{wallet_id}"}, limit=1))
    if not wallet:
        return None
    transactions = _sb().select("token_transactions", filters={"wallet_id": f"eq.{wallet_id}"}, order="created_at.desc", limit=50)
    return {"wallet": wallet, "transactions": transactions}


def is_webhook_event_processed(event_id: str) -> bool:
    row = _first(_sb().select("webhook_events", filters={"event_id": f"eq.{event_id}"}, select="event_id", limit=1))
    return row is not None


def get_refund_debits_for_session(reference_id: str) -> int:
    rows = _sb().select("token_transactions", filters={"reference_id": f"eq.{reference_id}", "reason": "eq.refund"}, select="amount")
    return sum(abs(int(row["amount"])) for row in rows)


def get_credit_total_for_reference(reference_id: str, reason: str) -> int:
    if not reference_id:
        return 0
    rows = _sb().select(
        "token_transactions",
        filters={"reference_id": f"eq.{reference_id}", "reason": f"eq.{reason}"},
        select="amount",
    )
    return sum(int(row["amount"]) for row in rows if int(row["amount"]) > 0)


def mark_webhook_event_processed(event_id: str):
    _sb().rpc("mark_webhook_processed", {"p_event_id": event_id})


def get_admin_stats() -> dict:
    result = _sb().rpc("admin_stats", {})
    return {
        "wallet_count": int(result["wallet_count"]),
        "total_sparks": int(result["total_sparks"]),
        "paying_users": int(result["paying_users"]),
        "purchase_count": int(result["purchase_count"]),
        "merge_count": int(result["merge_count"]),
        "users_count": int(result["users_count"]),
    }


def _question_from_row(row: dict) -> dict:
    question = dict(row)
    if isinstance(question.get("options"), str):
        question["options"] = json.loads(question["options"])
    return {k: v for k, v in question.items() if v is not None}


def save_quiz_pack(owner_wallet_id: str, title: str, questions: list[dict], pack_id: Optional[str] = None) -> dict:
    now = _now()
    pack_id = pack_id or uuid.uuid4().hex
    existing = _first(_sb().select(
        "quiz_packs",
        filters={"id": f"eq.{pack_id}", "owner_wallet_id": f"eq.{owner_wallet_id}", "deleted_at": "is.null"},
        limit=1,
    ))
    created_at = existing["created_at"] if existing else now
    _sb().upsert("quiz_packs", {
        "id": pack_id,
        "owner_wallet_id": owner_wallet_id,
        "title": title,
        "status": "ready",
        "question_count": len(questions),
        "created_at": created_at,
        "updated_at": now,
        "deleted_at": None,
    }, on_conflict="id")
    _sb().delete("quiz_questions", filters={"pack_id": f"eq.{pack_id}"})
    for index, q in enumerate(questions):
        _sb().insert("quiz_questions", {
            "id": f"{pack_id}_{index}",
            "pack_id": pack_id,
            "position": index,
            "question_type": "true_false" if len(q.get("options", [])) == 2 else "multiple_choice",
            "text": q.get("text", ""),
            "options": q.get("options", []),
            "answer_index": q.get("answer_index", 0),
            "image_asset_id": q.get("image_asset_id"),
            "image_url": q.get("image_url"),
            "image_alt": q.get("image_alt"),
            "created_at": now,
            "updated_at": now,
        })
    pack = get_quiz_pack(owner_wallet_id, pack_id)
    if not pack:
        raise SupabaseDBError("Failed to save quiz pack")
    return pack


def list_quiz_packs(owner_wallet_id: str, limit: int = 50) -> list[dict]:
    return _sb().select(
        "quiz_packs",
        filters={"owner_wallet_id": f"eq.{owner_wallet_id}", "deleted_at": "is.null"},
        order="updated_at.desc",
        limit=limit,
    )


def get_quiz_pack(owner_wallet_id: str, pack_id: str) -> Optional[dict]:
    pack = _first(_sb().select(
        "quiz_packs",
        filters={"id": f"eq.{pack_id}", "owner_wallet_id": f"eq.{owner_wallet_id}", "deleted_at": "is.null"},
        limit=1,
    ))
    if not pack:
        return None
    questions = _sb().select("quiz_questions", filters={"pack_id": f"eq.{pack_id}"}, order="position.asc")
    pack["questions"] = [_question_from_row(row) for row in questions]
    return pack


def delete_quiz_pack(owner_wallet_id: str, pack_id: str) -> bool:
    rows = _sb().update(
        "quiz_packs",
        {"status": "deleted", "deleted_at": _now(), "updated_at": _now()},
        filters={"id": f"eq.{pack_id}", "owner_wallet_id": f"eq.{owner_wallet_id}", "deleted_at": "is.null"},
    )
    return bool(rows)


def _content_type_for_game(game_type: str) -> str:
    return "mlt" if game_type == "wmlt" else game_type


def _game_type_for_content_type(content_type: str) -> str:
    return "wmlt" if content_type == "mlt" else content_type


def _game_content_from_row(row: dict) -> dict:
    item = dict(row)
    item["game_type"] = _game_type_for_content_type(item.get("content_type", ""))
    item["updated_at"] = item.get("updated_at") or item.get("created_at")
    return item


def save_game_content(owner_wallet_id: str, game_type: str, title: str, payload: dict, content_id: Optional[str] = None) -> dict:
    now = _now()
    content_id = content_id or uuid.uuid4().hex
    content_type = _content_type_for_game(game_type)
    existing = _first(_sb().select(
        "generated_content",
        filters={"id": f"eq.{content_id}", "wallet_id": f"eq.{owner_wallet_id}"},
        limit=1,
    ))
    created_at = existing["created_at"] if existing else now
    rows = _sb().upsert("generated_content", {
        "id": content_id,
        "wallet_id": owner_wallet_id,
        "content_type": content_type,
        "title": title,
        "payload": payload,
        "prompt": None,
        "model": None,
        "provider": None,
        "created_at": created_at,
        "updated_at": now,
    }, on_conflict="id")
    content = _game_content_from_row(rows[0]) if rows else get_game_content(owner_wallet_id, content_id)
    if not content:
        raise SupabaseDBError("Failed to save game content")
    return content


def list_game_content(owner_wallet_id: str, game_types: Optional[list[str]] = None, limit: int = 50) -> list[dict]:
    content_types = [_content_type_for_game(game_type) for game_type in (game_types or ["wmlt", "drawing"])]
    rows = _sb().select(
        "generated_content",
        filters={
            "wallet_id": f"eq.{owner_wallet_id}",
            "content_type": f"in.({','.join(content_types)})",
        },
        order="updated_at.desc,created_at.desc",
        limit=limit,
    )
    return [_game_content_from_row(row) for row in rows]


def get_game_content(owner_wallet_id: str, content_id: str) -> Optional[dict]:
    row = _first(_sb().select(
        "generated_content",
        filters={"id": f"eq.{content_id}", "wallet_id": f"eq.{owner_wallet_id}"},
        limit=1,
    ))
    return _game_content_from_row(row) if row else None


def delete_game_content(owner_wallet_id: str, content_id: str) -> bool:
    rows = _sb().delete(
        "generated_content",
        filters={"id": f"eq.{content_id}", "wallet_id": f"eq.{owner_wallet_id}"},
    )
    return bool(rows)


def _host_app_catalog_flag_from_row(row: dict) -> dict:
    item = dict(row)
    item["enabled"] = bool(item.get("enabled"))
    item["allowlist_party_ids"] = item.get("allowlist_party_ids") or []
    item["allowlist_external_user_ids"] = item.get("allowlist_external_user_ids") or []
    item["capability_overrides"] = item.get("capability_overrides") or {}
    return item


def list_host_app_catalog_flags(environment: str, host_app: str) -> list[dict]:
    try:
        rows = _sb().select(
            "host_app_catalog_flags",
            filters={"environment": f"eq.{environment}", "host_app": f"eq.{host_app}"},
        )
    except SupabaseDBError as exc:
        if "404" in str(exc) or "host_app_catalog_flags" in str(exc):
            return []
        raise
    return [_host_app_catalog_flag_from_row(row) for row in rows]


def upsert_host_app_catalog_flag(environment: str, host_app: str, game_id: str, flag: dict) -> dict:
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    row = {
        "id": flag.get("id") or uuid.uuid4().hex,
        "environment": environment,
        "host_app": host_app,
        "game_id": game_id,
        "enabled": bool(flag.get("enabled")),
        "status": flag.get("status") or "disabled",
        "allowlist_party_ids": flag.get("allowlist_party_ids") or [],
        "allowlist_external_user_ids": flag.get("allowlist_external_user_ids") or [],
        "rollout_percentage": flag.get("rollout_percentage"),
        "capability_overrides": flag.get("capability_overrides") or {},
        "notes": flag.get("notes") or "",
        "updated_by": flag.get("updated_by") or "",
        "updated_at": now,
    }
    rows = _sb().upsert("host_app_catalog_flags", row, on_conflict="environment,host_app,game_id")
    return _host_app_catalog_flag_from_row(rows[0] if rows else row)


def create_media_asset(asset_id: str, owner_wallet_id: str, storage_path: str, public_url: str, mime_type: str, bytes_size: int = 0, status: str = "pending", alt_text: str = "") -> dict:
    now = _now()
    rows = _sb().insert("media_assets", {
        "id": asset_id,
        "owner_wallet_id": owner_wallet_id,
        "storage_backend": "ionos",
        "storage_path": storage_path,
        "public_url": public_url,
        "status": status,
        "mime_type": mime_type,
        "bytes": bytes_size,
        "alt_text": alt_text,
        "created_at": now,
        "updated_at": now,
    })
    return rows[0] if rows else {}


def finalize_media_asset(owner_wallet_id: str, asset_id: str, bytes_size: int = 0, alt_text: str = "") -> Optional[dict]:
    body = {"status": "ready", "updated_at": _now()}
    if bytes_size > 0:
        body["bytes"] = bytes_size
    if alt_text:
        body["alt_text"] = alt_text
    rows = _sb().update(
        "media_assets",
        body,
        filters={"id": f"eq.{asset_id}", "owner_wallet_id": f"eq.{owner_wallet_id}"},
    )
    return rows[0] if rows else None


def get_media_asset(owner_wallet_id: str, asset_id: str) -> Optional[dict]:
    return _first(_sb().select(
        "media_assets",
        filters={"id": f"eq.{asset_id}", "owner_wallet_id": f"eq.{owner_wallet_id}"},
        limit=1,
    ))


def create_game_session(session: dict) -> dict:
    now = _now()
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
        "joinable": session.get("joinable", True),
        "closed_reason": session.get("closed_reason"),
        "closed_message": session.get("closed_message"),
        "superseded_by_session_id": session.get("superseded_by_session_id"),
        "launch_routes": session.get("launch_routes", {}),
        "feed_card": session.get("feed_card", {}),
        "result_summary": session.get("result_summary"),
        "created_at": session.get("created_at", now),
        "started_at": session.get("started_at"),
        "completed_at": session.get("completed_at"),
        "expires_at": session.get("expires_at", now + config.REVELRY_SESSION_LOBBY_TTL_SECONDS),
        "last_activity_at": session.get("last_activity_at", now),
        "updated_at": session.get("updated_at", now),
    }
    rows = _sb().insert("game_sessions", row)
    return rows[0] if rows else row


def get_game_session(session_id: str) -> Optional[dict]:
    return _first(_sb().select("game_sessions", filters={"id": f"eq.{session_id}"}, limit=1))


def get_game_session_by_room(room_code: str) -> Optional[dict]:
    return _first(_sb().select(
        "game_sessions",
        filters={"room_code": f"eq.{room_code}"},
        order="created_at.desc",
        limit=1,
    ))


def get_active_game_session(host_app: str, external_container_id: str) -> Optional[dict]:
    return _first(_sb().select(
        "game_sessions",
        filters={
            "host_app": f"eq.{host_app}",
            "external_container_id": f"eq.{external_container_id}",
            "status": "in.(lobby,active,paused)",
        },
        order="created_at.desc",
        limit=1,
    ))


def get_latest_game_session(host_app: str, external_container_id: str, game_type: str = "") -> Optional[dict]:
    filters = {
        "host_app": f"eq.{host_app}",
        "external_container_id": f"eq.{external_container_id}",
    }
    if game_type:
        filters["game_type"] = f"eq.{game_type}"
    return _first(_sb().select(
        "game_sessions",
        filters=filters,
        order="created_at.desc",
        limit=1,
    ))


def game_content_has_sessions(host_app: str, external_container_id: str, game_id: str) -> bool:
    return bool(_first(_sb().select(
        "game_sessions",
        filters={
            "host_app": f"eq.{host_app}",
            "external_container_id": f"eq.{external_container_id}",
            "game_id": f"eq.{game_id}",
        },
        limit=1,
    )))


def update_game_session(session_id: str, updates: dict) -> Optional[dict]:
    allowed = {
        "status", "joinable", "closed_reason", "closed_message", "superseded_by_session_id",
        "launch_routes", "feed_card", "result_summary", "started_at", "completed_at",
        "expires_at", "last_activity_at", "updated_at",
    }
    body = {key: value for key, value in updates.items() if key in allowed}
    if not body:
        return get_game_session(session_id)
    body["updated_at"] = body.get("updated_at", _now())
    rows = _sb().update("game_sessions", body, filters={"id": f"eq.{session_id}"})
    return rows[0] if rows else None
