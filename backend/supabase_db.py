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


def get_active_entitlement(device_id: str) -> Optional[dict]:
    _expire_entitlements()
    return _first(_sb().select(
        "entitlements",
        filters={"device_id": f"eq.{device_id}", "status": "eq.active", "user_id": "is.null"},
        order="games_remaining.desc,expires_at.desc",
        limit=1,
    ))


def decrement_entitlement(entitlement_id: str) -> bool:
    # NOTE: This has a TOCTOU window (read then update). The SQLite version uses
    # BEGIN IMMEDIATE for atomicity. This is acceptable because entitlements are
    # legacy — active code uses debit_tokens (RPC) instead. If entitlements are
    # ever reactivated, this should move to an RPC with FOR UPDATE.
    now = _now()
    row = _first(_sb().select("entitlements", filters={"id": f"eq.{entitlement_id}"}, limit=1))
    if not row or row["status"] != "active" or row["games_remaining"] <= 0 or row["expires_at"] <= now:
        return False
    remaining = row["games_remaining"] - 1
    status = "exhausted_games" if remaining == 0 else "active"
    updated = _sb().update(
        "entitlements",
        {"games_remaining": remaining, "status": status, "updated_at": now},
        filters={"id": f"eq.{entitlement_id}", "status": "eq.active"},
    )
    return bool(updated)


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


def check_and_increment_free_usage(device_id: str) -> tuple[bool, int]:
    result = _sb().rpc("claim_device_usage", {
        "p_device_id": device_id,
        "p_free_tier_limit": config.FREE_TIER_LIMIT,
    })
    return bool(result["allowed"]), int(result["count_after"])


def get_free_usage_count(device_id: str) -> int:
    cutoff = _now() - 86400
    row = _first(_sb().select("device_usage", filters={"device_id": f"eq.{device_id}"}, limit=1))
    if not row or row["window_start"] <= cutoff:
        return 0
    return int(row["games_used_free"])


def peek_free_usage(device_id: str) -> tuple[bool, int]:
    used = get_free_usage_count(device_id)
    return used < config.FREE_TIER_LIMIT, used


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


def get_active_entitlement_for_user(user_id: str) -> Optional[dict]:
    _expire_entitlements()
    return _first(_sb().select(
        "entitlements",
        filters={"user_id": f"eq.{user_id}", "status": "eq.active"},
        order="games_remaining.desc,expires_at.desc",
        limit=1,
    ))


def get_user_free_usage_count(user_id: str) -> int:
    cutoff = _now() - 86400
    rows = _sb().select("device_usage", filters={"user_id": f"eq.{user_id}", "window_start": f"gte.{cutoff}"})
    return sum(int(row["games_used_free"]) for row in rows)


def check_and_increment_user_free_usage(user_id: str, device_id: str) -> tuple[bool, int]:
    result = _sb().rpc("claim_user_usage", {
        "p_user_id": user_id,
        "p_device_id": device_id,
        "p_free_tier_limit": config.FREE_TIER_LIMIT,
    })
    return bool(result["allowed"]), int(result["count_after"])


def peek_user_free_usage(user_id: str) -> tuple[bool, int]:
    used = get_user_free_usage_count(user_id)
    return used < config.FREE_TIER_LIMIT, used


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
        "p_max_balance": config.MAX_TOKEN_BALANCE,
    })
    return bool(result["success"]), int(result["balance"])


def check_and_grant_daily_bonus(wallet_id: str) -> tuple[bool, int]:
    result = _sb().rpc("grant_daily_bonus", {
        "p_wallet_id": wallet_id,
        "p_today": _utc_date_str(),
        "p_amount": config.DAILY_BONUS_TOKENS,
        "p_max_balance": config.MAX_TOKEN_BALANCE,
    })
    return bool(result["granted"]), int(result["balance"])


def check_and_grant_ad_reward(wallet_id: str) -> tuple[bool, int, int]:
    result = _sb().rpc("grant_ad_reward", {
        "p_wallet_id": wallet_id,
        "p_today": _utc_date_str(),
        "p_amount": config.AD_REWARD_TOKENS,
        "p_max_ads_per_day": config.MAX_ADS_PER_DAY,
        "p_max_balance": config.MAX_TOKEN_BALANCE,
    })
    return bool(result["granted"]), int(result["balance"]), int(result["ads_remaining"])


def has_ever_purchased(wallet_id: str) -> bool:
    row = _first(_sb().select("wallets", filters={"id": f"eq.{wallet_id}"}, select="lifetime_purchased", limit=1))
    return bool(row and int(row["lifetime_purchased"]) > 0)


def credit_purchase(wallet_id: str, amount: int, reference_id: str, metadata: str = "") -> tuple[bool, int]:
    if amount <= 0:
        raise ValueError(f"credit_purchase amount must be positive, got {amount}")
    result = _sb().rpc("credit_purchase", {
        "p_wallet_id": wallet_id,
        "p_amount": amount,
        "p_reference_id": reference_id,
        "p_metadata": metadata or "",
        "p_max_balance": config.MAX_TOKEN_BALANCE,
    })
    return bool(result["success"]), int(result["balance"])


def merge_wallet(from_id: str, to_id: str):
    if from_id == to_id:
        return
    _sb().rpc("merge_wallet", {
        "p_from_id": from_id,
        "p_to_id": to_id,
        "p_max_balance": config.MAX_TOKEN_BALANCE,
    })


def migrate_entitlements_to_wallets():
    # Data migration is handled explicitly during cutover, not at app startup.
    return


def admin_grant_tokens(wallet_id: str, amount: int) -> int:
    if amount <= 0 or amount > config.MAX_TOKEN_BALANCE:
        raise ValueError(f"admin_grant amount must be between 1 and {config.MAX_TOKEN_BALANCE}, got {amount}")
    get_or_create_wallet(wallet_id, signup_bonus=False)
    _, new_balance = credit_tokens(wallet_id, amount, "admin_grant")
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
