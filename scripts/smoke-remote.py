#!/usr/bin/env python3
"""Remote smoke checks for deployed LocalPlay environments.

The default profile is safe for prod/gamma: it creates a fresh anonymous wallet,
generates one small quiz, retries with the same idempotency key, and verifies
the retry did not double-charge.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass
from typing import Any


EXPECTED_MODEL = "gemini-2.5-flash-lite"


@dataclass
class Response:
    status: int
    headers: dict[str, str]
    body: Any
    text: str


def request(
    method: str,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    body: dict | None = None,
    timeout: int = 180,
) -> Response:
    payload = None
    merged_headers = dict(headers or {})
    if body is not None:
        payload = json.dumps(body).encode("utf-8")
        merged_headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=payload, headers=merged_headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            text = resp.read().decode("utf-8", errors="replace")
            status = resp.status
            response_headers = dict(resp.headers.items())
    except urllib.error.HTTPError as exc:
        text = exc.read().decode("utf-8", errors="replace")
        status = exc.code
        response_headers = dict(exc.headers.items())

    parsed: Any = None
    if text:
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            parsed = None
    return Response(status=status, headers=response_headers, body=parsed, text=text)


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def api(base_url: str, path: str) -> str:
    return f"{base_url.rstrip('/')}{path}"


def smoke(base_url: str, *, skip_generate: bool = False) -> None:
    print(f"smoke: {base_url}")

    health = request("GET", api(base_url, "/health"), timeout=20)
    check(health.status == 200, f"/health returned {health.status}: {health.text}")
    check(isinstance(health.body, dict) and health.body.get("status") == "healthy", "/health did not return healthy")
    print("ok /health")

    providers = request("GET", api(base_url, "/providers"), timeout=30)
    check(providers.status == 200, f"/providers returned {providers.status}: {providers.text}")
    provider_rows = providers.body.get("providers", []) if isinstance(providers.body, dict) else []
    gemini = next((row for row in provider_rows if row.get("id") == "gemini"), None)
    check(gemini and gemini.get("available"), "Gemini provider is not available")
    print("ok /providers gemini available")

    media_status = request("GET", api(base_url, "/media/status"), timeout=30)
    check(media_status.status == 200, f"/media/status returned {media_status.status}: {media_status.text}")
    check(isinstance(media_status.body, dict), "/media/status did not return JSON")
    check("providers" in media_status.body, "/media/status missing providers")
    print("ok /media/status")

    config = request("GET", api(base_url, "/config.json"), timeout=30)
    check(config.status == 200, f"/config.json returned {config.status}: {config.text}")
    ai_models = config.body.get("ai_models", {}) if isinstance(config.body, dict) else {}
    check(ai_models.get("provider") == "gemini", f"config provider is {ai_models.get('provider')!r}")
    check(ai_models.get("free_model") == EXPECTED_MODEL, f"free model is {ai_models.get('free_model')!r}")
    check(ai_models.get("paid_model") == EXPECTED_MODEL, f"paid model is {ai_models.get('paid_model')!r}")
    print("ok /config.json Gemini Flash Lite")

    index = request("GET", api(base_url, "/"), timeout=30)
    check(index.status == 200, f"/ returned {index.status}")
    check("text/html" in index.headers.get("Content-Type", ""), "/ did not return HTML")
    print("ok SPA root")

    auth_me = request("GET", api(base_url, "/auth/me"), timeout=20)
    check(auth_me.status == 401, f"/auth/me without session should be 401, got {auth_me.status}")
    print("ok /auth/me rejects anonymous session")

    device_id = str(uuid.uuid4())
    auth_invalid = request(
        "POST",
        api(base_url, "/auth/signin"),
        headers={"X-Device-Id": device_id},
        body={"provider": "google", "id_token": "invalid-token", "device_id": device_id},
        timeout=30,
    )
    check(auth_invalid.status == 401, f"/auth/signin invalid token should be 401, got {auth_invalid.status}")
    print("ok /auth/signin invalid token rejection")

    checkout_ios = request(
        "POST",
        api(base_url, "/checkout/create"),
        headers={"X-Device-Id": device_id, "X-Platform": "ios"},
        body={"device_id": device_id},
        timeout=30,
    )
    check(checkout_ios.status == 403, f"iOS checkout should be blocked with 403, got {checkout_ios.status}")
    print("ok iOS checkout guard")

    if skip_generate:
        print("skip generation/idempotency smoke")
        return

    idem_key = str(uuid.uuid4())
    generate_body = {
        "prompt": f"smoke test simple ocean facts {int(time.time())}",
        "difficulty": "easy",
        "num_questions": 5,
    }
    headers = {"X-Device-Id": device_id, "Idempotency-Key": idem_key}

    first = request("POST", api(base_url, "/quiz/generate"), headers=headers, body=generate_body)
    check(first.status == 200, f"first /quiz/generate returned {first.status}: {first.text}")
    first_quiz_id = first.body.get("quiz_id") if isinstance(first.body, dict) else None
    check(first_quiz_id, "first /quiz/generate did not return quiz_id")
    print(f"ok first generation {first_quiz_id}")

    second = request("POST", api(base_url, "/quiz/generate"), headers=headers, body=generate_body)
    check(second.status == 200, f"second /quiz/generate returned {second.status}: {second.text}")
    second_quiz_id = second.body.get("quiz_id") if isinstance(second.body, dict) else None
    check(second_quiz_id == first_quiz_id, f"idempotent retry returned {second_quiz_id}, expected {first_quiz_id}")
    print("ok generation idempotency")

    balance = request("GET", api(base_url, "/tokens/balance"), headers={"X-Device-Id": device_id}, timeout=30)
    check(balance.status == 200, f"/tokens/balance returned {balance.status}: {balance.text}")
    balance_value = balance.body.get("balance") if isinstance(balance.body, dict) else None
    check(balance_value == 29, f"expected balance 29 after one spend + daily bonus, got {balance_value}")
    print("ok token balance no double-charge")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run remote LocalPlay smoke checks")
    parser.add_argument("--base-url", required=True, help="Base URL, e.g. https://gamesapi.revelryapp.me")
    parser.add_argument("--skip-generate", action="store_true", help="Skip live LLM generation and token spend checks")
    args = parser.parse_args()

    try:
        smoke(args.base_url, skip_generate=args.skip_generate)
    except Exception as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    print("remote smoke passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
