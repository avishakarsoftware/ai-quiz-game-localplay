#!/usr/bin/env python3
"""Migrate LocalPlay SQLite durable tables into prefixed Supabase tables.

This is intentionally a one-shot operational tool. It does not switch runtime
envs; deploy scripts handle that after verification.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path
from typing import Iterable

import httpx


TABLES = [
    "users",
    "wallets",
    "entitlements",
    "device_usage",
    "request_log",
    "pending_tokens",
    "webhook_events",
    "token_transactions",
]

COUNT_COLUMNS = {
    "users": "id",
    "wallets": "id",
    "entitlements": "id",
    "device_usage": "device_id",
    "request_log": "idempotency_key",
    "pending_tokens": "device_id",
    "webhook_events": "event_id",
    "token_transactions": "id",
}

CLEAR_ORDER = [
    "token_transactions",
    "webhook_events",
    "pending_tokens",
    "request_log",
    "device_usage",
    "entitlements",
    "wallets",
    "users",
]


def sqlite_rows(conn: sqlite3.Connection, table: str) -> list[dict]:
    rows = [dict(row) for row in conn.execute(f"SELECT * FROM {table}").fetchall()]
    if table == "token_transactions":
        # Postgres owns the BIGSERIAL ids. No app code depends on preserving
        # SQLite transaction ids, and omitting them avoids sequence repair.
        for row in rows:
            row.pop("id", None)
    if table in {"users", "wallets", "entitlements"}:
        for row in rows:
            row.setdefault("updated_at", None)
            if row["updated_at"] is None:
                row["updated_at"] = row.get("created_at")
    return rows


class SupabaseRest:
    def __init__(self, url: str, service_key: str, prefix: str) -> None:
        self.url = url.rstrip("/")
        self.prefix = prefix
        self.headers = {
            "apikey": service_key,
            "Authorization": f"Bearer {service_key}",
            "Content-Type": "application/json",
        }

    def table(self, name: str) -> str:
        return f"{self.prefix}{name}"

    def request(self, method: str, path: str, *, params=None, json_body=None, prefer: str = ""):
        headers = dict(self.headers)
        if prefer:
            headers["Prefer"] = prefer
        with httpx.Client(timeout=30) as client:
            response = client.request(
                method,
                f"{self.url}{path}",
                params=params,
                json=json_body,
                headers=headers,
            )
        if response.status_code >= 400:
            raise RuntimeError(f"{method} {path} failed: {response.status_code} {response.text}")
        return response

    def clear_all(self) -> None:
        for table in CLEAR_ORDER:
            self.request(
                "DELETE",
                f"/rest/v1/{self.table(table)}",
                params={COUNT_COLUMNS[table]: "not.is.null"},
                prefer="return=minimal",
            )

    def insert_rows(self, table: str, rows: list[dict], batch_size: int = 500) -> None:
        if not rows:
            return
        for start in range(0, len(rows), batch_size):
            batch = rows[start:start + batch_size]
            self.request(
                "POST",
                f"/rest/v1/{self.table(table)}",
                json_body=batch,
                prefer="return=minimal",
            )

    def count(self, table: str) -> int:
        headers = dict(self.headers)
        headers["Prefer"] = "count=exact"
        headers["Range"] = "0-0"
        with httpx.Client(timeout=30) as client:
            response = client.get(
                f"{self.url}/rest/v1/{self.table(table)}",
                params={"select": COUNT_COLUMNS[table]},
                headers=headers,
            )
        if response.status_code >= 400:
            raise RuntimeError(f"count {table} failed: {response.status_code} {response.text}")
        return int(response.headers["content-range"].rsplit("/", 1)[1])

    def admin_stats(self) -> dict:
        response = self.request("POST", f"/rest/v1/rpc/{self.prefix}admin_stats", json_body={})
        return response.json()


def sqlite_counts(conn: sqlite3.Connection) -> dict[str, int]:
    return {
        table: int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
        for table in TABLES
    }


def sqlite_admin_stats(conn: sqlite3.Connection) -> dict:
    return {
        "wallet_count": int(conn.execute("SELECT COUNT(*) FROM wallets").fetchone()[0]),
        "total_sparks": int(conn.execute("SELECT COALESCE(SUM(balance), 0) FROM wallets").fetchone()[0]),
        "paying_users": int(conn.execute("SELECT COUNT(*) FROM wallets WHERE lifetime_purchased > 0").fetchone()[0]),
        "purchase_count": int(conn.execute("SELECT COUNT(*) FROM token_transactions WHERE reason = 'purchase'").fetchone()[0]),
        "merge_count": int(conn.execute("SELECT COUNT(*) FROM token_transactions WHERE reason = 'merge_in'").fetchone()[0]),
        "users_count": int(conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Migrate LocalPlay SQLite tables to Supabase")
    parser.add_argument("--sqlite", required=True, type=Path)
    parser.add_argument("--supabase-url", required=True)
    parser.add_argument("--service-key-file", required=True, type=Path)
    parser.add_argument("--prefix", required=True, choices=["games_", "games_gamma_"])
    parser.add_argument("--clear-target", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    service_key = args.service_key_file.read_text().strip()
    conn = sqlite3.connect(args.sqlite)
    conn.row_factory = sqlite3.Row

    source_counts = sqlite_counts(conn)
    source_stats = sqlite_admin_stats(conn)
    print(json.dumps({"source_counts": source_counts, "source_admin_stats": source_stats}, indent=2))

    if args.dry_run:
        return 0

    sb = SupabaseRest(args.supabase_url, service_key, args.prefix)
    if args.clear_target:
        sb.clear_all()

    for table in TABLES:
        rows = sqlite_rows(conn, table)
        sb.insert_rows(table, rows)
        print(f"inserted {len(rows)} rows into {args.prefix}{table}")

    target_counts = {table: sb.count(table) for table in TABLES}
    target_stats = sb.admin_stats()
    print(json.dumps({"target_counts": target_counts, "target_admin_stats": target_stats}, indent=2))

    if source_counts != target_counts:
        print("count mismatch", file=sys.stderr)
        return 2
    for key, value in source_stats.items():
        if int(target_stats[key]) != int(value):
            print(f"admin stat mismatch for {key}: source={value} target={target_stats[key]}", file=sys.stderr)
            return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
