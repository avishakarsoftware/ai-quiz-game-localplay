#!/usr/bin/env python3
"""L5 prod/gamma regression suite (SPEC-TESTING §2/§3).

One command, grouped human-readable report, non-zero exit on any failure:

    make test-prod                 # read-mostly, safe against production any time
    make test-prod-deep            # also drives every catalog game's room + lobby
    .venv/bin/python scripts/regression.py --target gamma --deep --verbose

WHY A NEW FILE INSTEAD OF EXTENDING scripts/smoke-remote.py
-----------------------------------------------------------
smoke-remote.py is a linear "does deploy X answer at all" script: it prints as it goes,
raises on the first failure, and its whole value is being tiny. The L5 report needs the
opposite shape — a registry of checks that all run even when earlier ones fail, grouped
verdicts, warnings that don't fail the build, and a WebSocket layer. Rewriting smoke-remote
into that would churn a script the Makefile/DEPLOY.md already reference for post-deploy
smoke. So: smoke-remote stays the narrow post-deploy smoke, this is the regression suite,
and --deep re-covers smoke-remote's generation-idempotency assertion so this file alone is
enough for a full status read.

PRODUCTION-SAFETY CONTRACT (SPEC-TESTING §2) — enforced by construction
-----------------------------------------------------------------------
* No purchase is ever initiated. Payment coverage asserts the rails *reject* junk:
  /webhook/stripe (400 on prod where keys are live, 503 on gamma where they are not),
  /webhook/revenuecat (401), and the iOS checkout guard (403).
* Every wallet this run touches is minted here from a fresh random UUID. Device ids MUST be
  UUID-shaped or tokens.get_device_id() drops them and every request silently resolves to
  "no wallet" — which looks like a pass.
* Every room this run creates is closed with CANCEL_GAME and then *verified* closed, so the
  run never squats against the global MAX_ROOMS=50 cap that real hosts share.
* Spark budget: /room/create is free — the COST_ROOM (10) debit lands on START_GAME. So the
  38-game sweep costs 0 sparks on one wallet, and only the deliberate playthrough spends,
  on its own fresh wallet. (A fresh wallet gets ~20-30, i.e. 2-3 starts.)
* Synthetic players are nicknamed QA-* so support/analytics can identify them.

CONTENT-TYPE, NOT STATUS
------------------------
The backend serves the SPA as a catch-all, so a *missing* route answers 200 text/html.
Asserting on status alone therefore passes for endpoints that do not exist. This has bitten
twice, so every JSON expectation here goes through expect_json(), which fails on a non-JSON
content type, and INFRA explicitly pins both halves of the behaviour (API path -> 404 JSON,
SPA path -> 200 HTML).
"""
from __future__ import annotations

import argparse
import asyncio
import json
import re
import socket
import ssl
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional

REPO_ROOT = Path(__file__).resolve().parent.parent

# Bumped deliberately when a game ships. A catalog that shrinks is a regression; a catalog
# that grows means this constant is stale (the suite warns rather than fails, so a new game
# never blocks a prod health read).
EXPECTED_GAME_COUNT = 38
EXPECTED_MODEL = "gemini-2.5-flash-lite"
UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I)

# Games whose START_GAME has no minimum-player gate: the quiz starts with an empty lobby by
# design (a host can solo-demo it). Everything else must refuse to start — and refuse
# *before* charging, which is exactly what the gate check proves.
GATE_EXEMPT_GAME_TYPES = {"quiz"}
GATE_MESSAGE_RE = re.compile(r"at least|starts when|needs \d+|add \d+", re.I)

GROUP_ORDER = [
    "INFRA",
    "CATALOG",
    "ECONOMY",
    "PAYMENT RAILS",
    "SECURITY",
    "GAMES (deep)",
    "FLAGS",
]


# --------------------------------------------------------------------------- targets


@dataclass(frozen=True)
class Target:
    name: str
    api: str
    web: str
    # Stripe webhook status that proves the rail is wired *for this environment*:
    # 400 = signature verification ran (keys live), 503 = no keys configured. Gamma has no
    # Stripe keys, so a 400 there would be as wrong as a 503 on prod (SPEC-TESTING §6).
    stripe_reject: tuple[int, ...]
    stripe_note: str
    # RevenueCat rejects unauthorized callers with 401 wherever the shared secret is set; a
    # bare local backend has none and answers 503 "IAP not configured".
    iap_reject: tuple[int, ...] = (401,)
    # Base path the SPA is deployed under on `web`. The in-app legal links are *relative*
    # ("privacy.html"), so they resolve against this — which is a different set of files from
    # the store-facing /privacy and /support URLs at the site root.
    app_base: str = "/"
    tls: bool = True


TARGETS = {
    "prod": Target(
        name="PROD",
        api="https://gamesapi.revelryapp.me",
        web="https://games.revelryapp.me",
        stripe_reject=(400,),
        stripe_note="keys live",
        app_base="/quiz/",
    ),
    "gamma": Target(
        name="GAMMA",
        api="https://gamesapi-gamma.revelryapp.me",
        # Gamma has no separate CDN frontend — the backend serves the SPA.
        web="https://gamesapi-gamma.revelryapp.me",
        stripe_reject=(503,),
        stripe_note="no keys, expected",
    ),
    "local": Target(
        name="LOCAL",
        api="http://localhost:9100",
        web="http://localhost:9100",
        stripe_reject=(400, 503),
        stripe_note="local",
        iap_reject=(401, 503),
        tls=False,
    ),
}


# --------------------------------------------------------------------------- http


@dataclass
class Response:
    status: int
    content_type: str
    body: Any
    text: str
    headers: dict[str, str]
    elapsed_ms: int
    error: str = ""

    @property
    def is_json(self) -> bool:
        return "application/json" in self.content_type

    @property
    def is_html(self) -> bool:
        return "text/html" in self.content_type


def request(
    method: str,
    url: str,
    *,
    headers: Optional[dict[str, str]] = None,
    body: Optional[dict] = None,
    timeout: int = 30,
) -> Response:
    payload = None
    merged = dict(headers or {})
    if body is not None:
        payload = json.dumps(body).encode("utf-8")
        merged["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=payload, headers=merged, method=method)
    started = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            text = resp.read().decode("utf-8", errors="replace")
            status, raw_headers = resp.status, dict(resp.headers.items())
    except urllib.error.HTTPError as exc:
        text = exc.read().decode("utf-8", errors="replace")
        status, raw_headers = exc.code, dict(exc.headers.items())
    except Exception as exc:  # noqa: BLE001 — a dead host must be a FAIL, not a traceback
        return Response(0, "", None, "", {}, int((time.monotonic() - started) * 1000), str(exc))

    parsed: Any = None
    if text:
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            parsed = None
    lower = {k.lower(): v for k, v in raw_headers.items()}
    return Response(
        status=status,
        content_type=lower.get("content-type", ""),
        body=parsed,
        text=text,
        headers=lower,
        elapsed_ms=int((time.monotonic() - started) * 1000),
    )


# --------------------------------------------------------------------------- suite


PASS, FAIL, WARN, SKIP = "PASS", "FAIL", "WARN", "SKIP"


@dataclass
class Check:
    group: str
    label: str
    status: str
    detail: str = ""
    fact: str = ""


@dataclass
class Suite:
    checks: list[Check] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def record(
        self,
        group: str,
        label: str,
        ok: bool,
        *,
        detail: str = "",
        fact: str = "",
        warn_only: bool = False,
    ) -> bool:
        status = PASS if ok else (WARN if warn_only else FAIL)
        self.checks.append(Check(group, label, status, detail, fact if ok else ""))
        return ok

    def record_status(self, group: str, label: str, status: str, *, detail: str = "", fact: str = "") -> None:
        self.checks.append(Check(group, label, status, detail, fact if status != FAIL else ""))

    def skip(self, group: str, label: str, detail: str = "") -> None:
        self.checks.append(Check(group, label, SKIP, detail))

    def note(self, text: str) -> None:
        self.notes.append(text)

    # -- assertions ---------------------------------------------------------

    def expect_json(
        self,
        group: str,
        label: str,
        resp: Response,
        statuses: Iterable[int],
        *,
        fact: str = "",
        warn_only: bool = False,
    ) -> bool:
        """Status AND content-type. The SPA catch-all means html here is a missing route."""
        wanted = tuple(statuses)
        if resp.error:
            return self.record(group, label, False, detail=f"transport error: {resp.error}", warn_only=warn_only)
        if resp.status not in wanted:
            return self.record(
                group,
                label,
                False,
                detail=f"expected {'/'.join(map(str, wanted))}, got {resp.status} — {resp.text[:120]}",
                warn_only=warn_only,
            )
        if not resp.is_json:
            return self.record(
                group,
                label,
                False,
                detail=f"got {resp.status} but content-type is {resp.content_type or '(none)'} "
                f"— the SPA catch-all answers missing routes, so this route probably does not exist",
                warn_only=warn_only,
            )
        return self.record(group, label, True, fact=fact)

    def expect_html(
        self, group: str, label: str, resp: Response, *, contains: str = "", fact: str = ""
    ) -> bool:
        if resp.error:
            return self.record(group, label, False, detail=f"transport error: {resp.error}")
        if resp.status != 200 or not resp.is_html:
            return self.record(
                group, label, False, detail=f"got {resp.status} {resp.content_type or '(none)'}"
            )
        if contains and contains.lower() not in resp.text.lower():
            return self.record(group, label, False, detail=f"page does not contain {contains!r}")
        return self.record(group, label, True, fact=fact)

    # -- reporting ----------------------------------------------------------

    @property
    def failed(self) -> list[Check]:
        return [c for c in self.checks if c.status == FAIL]

    @property
    def warned(self) -> list[Check]:
        return [c for c in self.checks if c.status == WARN]

    def report(self, *, header: list[str], elapsed: float, verbose: bool) -> int:
        for line in header:
            print(line)
        print()

        for group in GROUP_ORDER:
            rows = [c for c in self.checks if c.group == group]
            if not rows:
                continue
            counted = [c for c in rows if c.status != SKIP]
            passed = [c for c in counted if c.status in (PASS, WARN)]
            facts = [c.fact for c in rows if c.fact]
            bad = [c.label for c in rows if c.status == FAIL]
            summary = " · ".join(bad if bad else facts[:7])
            if not bad and len(facts) > 7:
                summary += " · …"
            if not counted:
                print(f"{group:<15} {'--':>7}  not run ({rows[0].detail or 'skipped'})")
                continue
            print(f"{group:<15} {len(passed):>3}/{len(counted):<4}{summary}")
            if verbose:
                for c in rows:
                    mark = {PASS: "ok", FAIL: "FAIL", WARN: "warn", SKIP: "skip"}[c.status]
                    tail = f" — {c.detail}" if c.detail else ""
                    print(f"                     [{mark:>4}] {c.label}{tail}")

        if self.failed:
            print("\nFAILURES")
            for c in self.failed:
                print(f"  ✗ {c.group} · {c.label}: {c.detail}")
        if self.warned:
            print("\nWARNINGS (do not fail the run)")
            for c in self.warned:
                print(f"  ! {c.group} · {c.label}: {c.detail}")
        skipped = [c for c in self.checks if c.status == SKIP]
        if skipped:
            print("\nSKIPPED")
            for c in skipped:
                print(f"  - {c.group} · {c.label}{f': {c.detail}' if c.detail else ''}")
        if self.notes:
            print("\nNOTES")
            for n in self.notes:
                print(f"  · {n}")

        total = len([c for c in self.checks if c.status != SKIP])
        verdict = "FAIL" if self.failed else "PASS"
        bits = [f"{total} checks", f"{len(self.failed)} failed"]
        if self.warned:
            bits.append(f"{len(self.warned)} warning{'s' if len(self.warned) != 1 else ''}")
        bits.append(f"{elapsed:.0f}s")
        print(f"\nVERDICT: {verdict} ({', '.join(bits)})")
        return 1 if self.failed else 0


# --------------------------------------------------------------------------- groups


def check_infra(suite: Suite, t: Target) -> None:
    g = "INFRA"
    health = request("GET", f"{t.api}/health", timeout=20)
    if suite.expect_json(g, "health", health, (200,), fact=f"health 200 ({health.elapsed_ms}ms)"):
        suite.record(
            g,
            "health payload",
            isinstance(health.body, dict) and health.body.get("status") == "healthy",
            detail=f"body={health.text[:80]}",
            fact="healthy",
        )

    index = request("GET", f"{t.api}/", timeout=30)
    suite.expect_html(g, "SPA shell", index, contains='id="root"', fact="SPA shell")

    # The SPA's own hashed bundle. A 200 text/html here would mean the asset mount is broken
    # and the catch-all is answering — the exact false positive a status-only check misses.
    asset = re.search(r'src="(/[^"]*assets/[^"]+\.js)"', index.text or "")
    if asset:
        bundle = request("GET", f"{t.api}{asset.group(1)}", timeout=30)
        suite.record(
            g,
            "SPA bundle",
            bundle.status == 200 and "javascript" in bundle.content_type,
            detail=f"{asset.group(1)} -> {bundle.status} {bundle.content_type}",
            fact="assets served",
        )
    else:
        suite.record(g, "SPA bundle", False, detail="no hashed .js found in index.html")

    # Both halves of the catch-all contract, pinned so nobody has to remember it.
    missing_api = request("GET", f"{t.api}/quiz/{uuid.uuid4()}", timeout=20)
    suite.expect_json(g, "api 404 discipline", missing_api, (404,), fact="api 404 JSON")
    spa_route = request("GET", f"{t.api}/route-that-does-not-exist-{uuid.uuid4().hex[:8]}", timeout=20)
    suite.record(
        g,
        "SPA catch-all",
        spa_route.status == 200 and spa_route.is_html,
        detail=f"{spa_route.status} {spa_route.content_type}",
        fact="spa catch-all",
    )

    # Store-required legal pages. These are real static files, NOT SPA routes: a shell here
    # is a 200 that renders nothing, which is how a broken store Support URL looks healthy.
    for path, needle in (("/privacy", "privacy"), ("/support", "support")):
        page = request("GET", f"{t.web}{path}", timeout=30)
        title = re.search(r"<title>(.*?)</title>", page.text or "", re.S)
        title_text = (title.group(1) if title else "").strip()
        ok = page.status == 200 and page.is_html and needle in title_text.lower() and 'id="root"' not in page.text
        suite.record(
            g,
            f"legal {path}",
            ok,
            detail=f"{page.status} title={title_text[:60]!r}"
            + (" (SPA shell — the static page is missing)" if 'id="root"' in (page.text or "") else ""),
            fact=f"legal {path}",
        )

    # The in-app "Privacy Policy" link in SettingsDrawer is relative (privacy.html), so on the
    # CDN deployment it resolves under the app base, not the site root. Those are separate
    # files that drift independently — this pins the ones a real user can reach in-app.
    for filename, needle, hard in (("privacy.html", "privacy", True), ("support.html", "support", False)):
        page = request("GET", f"{t.web}{t.app_base}{filename}", timeout=30)
        is_shell = 'id="root"' in (page.text or "")
        ok = page.status == 200 and page.is_html and not is_shell and needle in (page.text or "").lower()
        if is_shell:
            why = "served the SPA shell — the static page is missing at this base path"
        elif ok:
            why = f"{len(page.text)} bytes of static page"
        else:
            why = f"content-type {page.content_type or '(none)'}, {needle!r} not found"
        suite.record(
            g,
            f"in-app {t.app_base}{filename}",
            ok,
            detail=f"{page.status} {why}",
            fact=f"in-app {filename}",
            warn_only=not hard,
        )

    if t.web != t.api:
        web_index = request("GET", f"{t.web}{t.app_base}", timeout=30)
        suite.expect_html(g, "web host", web_index, contains='id="root"', fact="CDN frontend")

    providers = request("GET", f"{t.api}/providers", timeout=30)
    if suite.expect_json(g, "providers", providers, (200,)):
        rows = providers.body.get("providers", []) if isinstance(providers.body, dict) else []
        gemini = next((r for r in rows if r.get("id") == "gemini"), None)
        suite.record(
            g,
            "gemini available",
            bool(gemini and gemini.get("available")),
            detail=f"gemini={gemini}",
            fact="gemini up",
        )

    media = request("GET", f"{t.api}/media/status", timeout=30)
    suite.expect_json(g, "media status", media, (200,), fact="media")

    if t.tls:
        days = tls_days_remaining(t.api)
        if days is None:
            suite.record(g, "TLS", False, detail="could not read certificate")
        else:
            # Certbot renewals need the GCP firewall opened by hand, so a cert inside the
            # renewal window is worth surfacing before it becomes an outage.
            status = FAIL if days < 7 else (WARN if days < 21 else PASS)
            suite.record_status(
                g, "TLS", status, detail=f"certificate expires in {days} days", fact=f"TLS {days}d"
            )
    else:
        suite.skip(g, "TLS", "plain http target")


def tls_days_remaining(base_url: str) -> Optional[int]:
    parsed = urllib.parse.urlparse(base_url)
    host, port = parsed.hostname, parsed.port or 443
    if not host:
        return None
    try:
        ctx = ssl.create_default_context()
        with socket.create_connection((host, port), timeout=15) as raw:
            with ctx.wrap_socket(raw, server_hostname=host) as tls:
                cert = tls.getpeercert()
    except Exception:  # noqa: BLE001
        return None
    not_after = cert.get("notAfter") if cert else None
    if not not_after:
        return None
    try:
        expires = datetime.strptime(not_after, "%b %d %H:%M:%S %Y %Z").replace(tzinfo=timezone.utc)
    except ValueError:
        return None
    return (expires - datetime.now(timezone.utc)).days


def check_catalog(suite: Suite, t: Target, public_cfg: Optional[dict]) -> list[dict]:
    g = "CATALOG"
    resp = request("GET", f"{t.api}/catalog", timeout=30)
    if not suite.expect_json(g, "catalog", resp, (200,)):
        return []
    games = resp.body.get("games") if isinstance(resp.body, dict) else None
    if not isinstance(games, list) or not games:
        suite.record(g, "catalog shape", False, detail=f"games={type(games).__name__}")
        return []

    suite.record(
        g,
        "game count",
        len(games) >= EXPECTED_GAME_COUNT,
        detail=f"{len(games)} games, expected at least {EXPECTED_GAME_COUNT}",
        fact=f"{len(games)} games",
    )
    if len(games) > EXPECTED_GAME_COUNT:
        suite.record(
            g,
            "game count drift",
            False,
            detail=f"{len(games)} games but EXPECTED_GAME_COUNT={EXPECTED_GAME_COUNT} — bump the constant",
            warn_only=True,
        )

    ids = [x.get("id") for x in games]
    suite.record(
        g, "unique ids", len(ids) == len(set(ids)), detail=f"duplicates: {dupes(ids)}", fact="unique ids"
    )
    titles = [x.get("title") for x in games]
    # Duplicate titles are how the odd_one_out / odd_question collision showed up in the UI.
    suite.record(
        g, "unique titles", len(titles) == len(set(titles)), detail=f"duplicates: {dupes(titles)}",
        fact="unique titles",
    )

    missing_meta = [
        x.get("id")
        for x in games
        if not all(x.get(k) for k in ("id", "game_type", "runtime_type", "title", "description"))
    ]
    suite.record(g, "metadata complete", not missing_meta, detail=f"incomplete: {missing_meta}", fact="metadata")

    bad_rules = []
    for x in games:
        rules = x.get("rules")
        sections = (rules or {}).get("sections") if isinstance(rules, dict) else None
        if not isinstance(rules, dict) or not rules.get("title") or not isinstance(sections, list) or not sections:
            bad_rules.append(x.get("id"))
            continue
        if any(not s.get("title") or not s.get("items") for s in sections):
            bad_rules.append(x.get("id"))
    suite.record(g, "rules resolvable", not bad_rules, detail=f"bad rules: {bad_rules}", fact="rules resolvable")

    bad_schema = [
        x.get("id")
        for x in games
        if x.get("launchable") and not (((x.get("config_schema") or {}).get("players") or {}).get("min"))
    ]
    suite.record(
        g, "player bounds", not bad_schema, detail=f"missing players.min: {bad_schema}", fact="player bounds"
    )

    enabled = (public_cfg or {}).get("enabled_game_types")
    if enabled is None:
        suite.record(g, "enabled_game_types", True, fact="no catalog gating")
    else:
        unknown = sorted(set(enabled) - set(ids))
        suite.record(
            g, "enabled_game_types", not unknown, detail=f"gated ids not in catalog: {unknown}",
            fact=f"gated to {len(enabled)}",
        )

    host_app = request("GET", f"{t.api}/catalog?host_app=revelry", timeout=30)
    if suite.expect_json(g, "host-app catalog", host_app, (200,)):
        host_ids = {x.get("id") for x in (host_app.body or {}).get("games", [])}
        suite.record(
            g,
            "host-app subset",
            bool(host_ids) and host_ids.issubset(set(ids)),
            detail=f"revelry-only ids not in base catalog: {sorted(host_ids - set(ids))}",
            fact=f"revelry {len(host_ids)}",
        )
    return games


def dupes(values: list) -> list:
    seen, out = set(), []
    for v in values:
        if v in seen and v not in out:
            out.append(v)
        seen.add(v)
    return out


def check_economy(suite: Suite, t: Target, device_id: str, public_cfg: Optional[dict]) -> None:
    g = "ECONOMY"
    h = {"X-Device-Id": device_id}
    first = request("GET", f"{t.api}/tokens/balance", headers=h, timeout=30)
    if not suite.expect_json(g, "wallet create", first, (200,), fact="wallet created"):
        return
    body = first.body if isinstance(first.body, dict) else {}
    balance = body.get("balance")
    cost_room = body.get("cost_room")
    suite.record(
        g,
        "signup bonus",
        isinstance(balance, int) and balance > 0,
        detail=f"fresh wallet balance={balance}",
        fact=f"signup {balance} sparks",
    )
    suite.record(
        g,
        "daily bonus granted",
        bool(body.get("daily_bonus_granted")),
        detail=f"first read of a fresh wallet should grant the daily bonus: {body}",
        fact="daily bonus",
    )
    suite.record(
        g,
        "playable balance",
        isinstance(balance, int) and isinstance(cost_room, int) and balance >= cost_room,
        detail=f"balance={balance} cost_room={cost_room}",
        fact="funds a room",
    )

    second = request("GET", f"{t.api}/tokens/balance", headers=h, timeout=30)
    if suite.expect_json(g, "balance reread", second, (200,)):
        s = second.body if isinstance(second.body, dict) else {}
        suite.record(
            g,
            "daily bonus idempotent",
            s.get("balance") == balance and not s.get("daily_bonus_granted"),
            detail=f"second read balance={s.get('balance')} granted={s.get('daily_bonus_granted')}",
            fact="bonus idempotent",
        )

    econ = (public_cfg or {}).get("economy") or {}
    suite.record(
        g,
        "cost parity",
        econ.get("cost_room") == body.get("cost_room") and econ.get("cost_generate") == body.get("cost_generate"),
        detail=f"/config/public {econ} vs /tokens/balance "
        f"{{'cost_room': {body.get('cost_room')}, 'cost_generate': {body.get('cost_generate')}}}",
        fact=f"room={econ.get('cost_room')} gen={econ.get('cost_generate')}",
    )

    flags = (public_cfg or {}).get("feature_flags") or {}
    if flags.get("referral_enabled"):
        ref = request("GET", f"{t.api}/referral/code", headers=h, timeout=30)
        if suite.expect_json(g, "referral code", ref, (200,), fact="referral code"):
            code = (ref.body or {}).get("code")
            again = request("GET", f"{t.api}/referral/code", headers=h, timeout=30)
            suite.record(
                g,
                "referral code stable",
                bool(code) and (again.body or {}).get("code") == code,
                detail=f"first={code} second={(again.body or {}).get('code')}",
                fact="referral stable",
            )
    else:
        suite.skip(g, "referral code", "referral_enabled=false")


def check_payment_rails(suite: Suite, t: Target, device_id: str, public_cfg: Optional[dict]) -> None:
    """Rails must REJECT. Nothing here can ever move money — no checkout is completed, no
    IAP flow is entered, and every request carries deliberately invalid input."""
    g = "PAYMENT RAILS"
    stripe = request(
        "POST",
        f"{t.api}/webhook/stripe",
        headers={"Stripe-Signature": "t=0,v1=deadbeef"},
        body={"type": "checkout.session.completed", "id": "evt_qa_invalid"},
        timeout=30,
    )
    suite.expect_json(
        g,
        "stripe rejects junk",
        stripe,
        t.stripe_reject,
        fact=f"stripe {stripe.status} ({t.stripe_note})",
    )
    unsigned = request("POST", f"{t.api}/webhook/stripe", body={"type": "ping"}, timeout=30)
    suite.expect_json(g, "stripe rejects unsigned", unsigned, t.stripe_reject, fact="unsigned rejected")

    rc = request(
        "POST",
        f"{t.api}/webhook/revenuecat",
        body={"event": {"type": "INITIAL_PURCHASE", "app_user_id": "qa-invalid"}},
        timeout=30,
    )
    suite.expect_json(
        g, "revenuecat rejects unauthorized", rc, t.iap_reject, fact=f"revenuecat {rc.status}"
    )

    ios = request(
        "POST",
        f"{t.api}/checkout/create",
        headers={"X-Device-Id": device_id, "X-Platform": "ios"},
        body={"device_id": device_id},
        timeout=30,
    )
    suite.expect_json(g, "ios checkout guard", ios, (403,), fact="ios checkout 403")

    token = request("GET", f"{t.api}/checkout/token", timeout=30)
    suite.expect_json(g, "checkout token needs device", token, (400,), fact="token needs device")

    ops = (public_cfg or {}).get("operations") or {}
    suite.record(
        g,
        "payments not killed",
        ops.get("kill_payments") is False,
        detail=f"operations.kill_payments={ops.get('kill_payments')}",
        fact="payments enabled",
    )


def check_security(suite: Suite, t: Target) -> None:
    g = "SECURITY"
    suite.expect_json(g, "auth/me anonymous", request("GET", f"{t.api}/auth/me", timeout=20), (401,), fact="auth 401")

    dev = str(uuid.uuid4())
    signin = request(
        "POST",
        f"{t.api}/auth/signin",
        headers={"X-Device-Id": dev},
        body={"provider": "google", "id_token": "qa-invalid-token", "device_id": dev},
        timeout=30,
    )
    suite.expect_json(g, "signin rejects bad token", signin, (401,), fact="signin 401")

    suite.expect_json(g, "history needs identity", request("GET", f"{t.api}/history", timeout=20), (401,), fact="history 401")
    suite.expect_json(g, "stats needs identity", request("GET", f"{t.api}/stats", timeout=20), (401,), fact="stats 401")

    # Admin surface: the point is that it never answers 200. Which rejection you get depends
    # on whether ADMIN_API_KEY is configured (403 Forbidden) or unset (503 not configured).
    # /admin/grant is probed with no target at all, so even a hypothetical auth bypass could
    # only 400 — the probe cannot mint sparks for anyone.
    for path, method in (
        ("/admin/config", "GET"),
        ("/admin/stats", "GET"),
        ("/admin/lookup", "GET"),
        ("/admin/host-app-catalog-flags", "GET"),
        ("/admin/grant", "POST"),
    ):
        resp = request(method, f"{t.api}{path}", timeout=20)
        suite.expect_json(
            g,
            f"admin {path} rejects",
            resp,
            (401, 403, 503),
            fact="admin locked" if path == "/admin/config" else "",
        )

    suite.expect_json(g, "system/info locked", request("GET", f"{t.api}/system/info", timeout=20), (401, 403), fact="system/info 403")

    # SPEC-ADS: the ad-reward endpoint is a trust-the-client stub. It must stay locked until
    # server-side verification replaces it, or it is farmable free sparks.
    suite.expect_json(g, "ad-reward locked", request("POST", f"{t.api}/tokens/ad-reward", body={}, timeout=20), (403,), fact="ad-reward 403")

    suite.expect_json(
        g, "room create needs device", request("POST", f"{t.api}/room/create", body={"game_type": "quiz"}, timeout=20), (400,), fact="room needs device"
    )
    suite.expect_json(
        g,
        "revelry bridge needs token",
        request("GET", f"{t.api}/integrations/revelry/games", timeout=20),
        (401,),
        fact="bridge 401",
    )

    evil = request("GET", f"{t.api}/health", headers={"Origin": "https://evil.example.com"}, timeout=20)
    suite.record(
        g,
        "CORS rejects unknown origin",
        "access-control-allow-origin" not in evil.headers,
        detail=f"reflected: {evil.headers.get('access-control-allow-origin')}",
        fact="CORS closed",
    )
    own = request("GET", f"{t.api}/health", headers={"Origin": t.api}, timeout=20)
    suite.record(
        g,
        "CORS allows own origin",
        own.headers.get("access-control-allow-origin") == t.api,
        detail=f"reflected: {own.headers.get('access-control-allow-origin')} for origin {t.api}",
        fact="CORS allowlist",
    )


def check_flags(suite: Suite, t: Target, public_cfg: Optional[dict], device_id: str) -> None:
    g = "FLAGS"
    if public_cfg is None:
        suite.record(g, "config/public", False, detail="could not read /config/public")
        return
    flags = public_cfg.get("feature_flags") or {}
    ops = public_cfg.get("operations") or {}
    models = public_cfg.get("ai_models") or {}
    h = {"X-Device-Id": device_id}

    suite.record(
        g,
        "flags present",
        all(k in flags for k in ("gifting_enabled", "achievements_enabled", "referral_enabled", "ads_enabled")),
        detail=f"flags={flags}",
        fact=" ".join(
            f"{k.replace('_enabled', '')}={str(flags.get(k)).lower()}"
            for k in ("gifting_enabled", "achievements_enabled", "referral_enabled", "ads_enabled")
        ),
    )

    # SPEC-ADS: ads_enabled must stay false until SSV lands, everywhere.
    suite.record(
        g, "ads locked off", flags.get("ads_enabled") is False, detail=f"ads_enabled={flags.get('ads_enabled')}"
    )

    # A flag that disagrees with its endpoint is worse than a flag that is off: the UI shows
    # a feature the backend refuses (or hides one it would serve).
    for flag, path, method, body in (
        ("achievements_enabled", "/achievements", "GET", None),
        ("gifting_enabled", "/tokens/gift", "POST", {"amount": 0}),
        ("referral_enabled", "/referral/code", "GET", None),
    ):
        resp = request(method, f"{t.api}{path}", headers=h, body=body, timeout=20)
        on = bool(flags.get(flag))
        ok = (resp.status != 503) if on else (resp.status == 503)
        suite.record(
            g,
            f"{flag} matches {path}",
            ok and resp.is_json,
            detail=f"flag={on}, {path} -> {resp.status} {resp.content_type} {resp.text[:90]}"
            + ("" if ok else "  (503 means the backend refuses a feature the flag advertises, or vice versa)"),
        )

    for key in ("maintenance", "kill_switch", "kill_generate"):
        suite.record(g, f"operations.{key} off", ops.get(key) is False, detail=f"{key}={ops.get(key)}")

    suite.record(
        g,
        "model pinned",
        models.get("provider") == "gemini"
        and models.get("free_model") == EXPECTED_MODEL
        and models.get("paid_model") == EXPECTED_MODEL,
        detail=f"ai_models={models}",
        fact=f"model {models.get('free_model')}",
    )

    promo = ((public_cfg.get("pricing") or {}).get("promo")) or {}
    expires = promo.get("expires")
    if expires:
        try:
            when = datetime.fromisoformat(str(expires).replace("Z", "+00:00"))
            suite.record(
                g,
                "promo not expired",
                when > datetime.now(timezone.utc),
                detail=f"promo {promo.get('id')!r} expired {expires} but is still advertised in /config/public",
                fact=f"promo {promo.get('id')}",
                warn_only=True,
            )
        except ValueError:
            suite.record(g, "promo expiry parses", False, detail=f"unparsable expires={expires!r}", warn_only=True)


# --------------------------------------------------------------------------- deep (websocket)


def ws_url(api: str, path: str) -> str:
    return api.replace("https://", "wss://").replace("http://", "ws://") + path


async def recv_typed(ws, want: set[str], *, timeout: float = 10.0) -> Optional[dict]:
    """Read until a message of an interesting type arrives. Never bare recv() on a loop —
    a missing broadcast otherwise blocks forever (SPEC-TESTING §6)."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            raw = await asyncio.wait_for(ws.recv(), timeout=max(0.2, deadline - time.monotonic()))
        except asyncio.TimeoutError:
            return None
        except Exception:  # noqa: BLE001 — server-side close is a legitimate outcome
            return None
        try:
            msg = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if not want or msg.get("type") in want:
            return msg
    return None


async def room_is_gone(websockets_mod, t: Target, code: str) -> bool:
    """A player socket into a closed room is answered with ERROR 'Room not found'. Used to
    *prove* cleanup rather than assume it — a leaked room squats against MAX_ROOMS=50, which
    real hosts share."""
    try:
        async with websockets_mod.connect(
            ws_url(t.api, f"/ws/{code}/{uuid.uuid4()}"),
            additional_headers={"Origin": t.api},
            open_timeout=15,
            close_timeout=5,
        ) as ws:
            msg = await recv_typed(ws, {"ERROR", "JOINED_ROOM", "ROOM_STATE"}, timeout=6)
            if msg is None:
                return False
            return msg.get("type") == "ERROR" and "not found" in str(msg.get("message", "")).lower()
    except Exception:  # noqa: BLE001 — a refused handshake also means the room is gone
        return True


async def check_games_deep(suite: Suite, t: Target, games: list[dict], device_id: str, verbose: bool) -> None:
    """Every catalog game: room creates, its runtime lobby is reachable by an authenticated
    organizer, and its minimum-player gate refuses to start (before charging). Then the room
    is cancelled and verified gone.

    Deliberate boundary: this does NOT start all 38 games. Starting costs COST_ROOM each, so
    a full start sweep would burn ~380 sparks across ~14 minted wallets and hold 38 rooms
    against the shared MAX_ROOMS cap. The gate assertion already proves the engine was
    constructed and the room is live, and the playthrough below proves the start path end to
    end on one game. Use --play <game_id> to start a specific game instead.
    """
    g = "GAMES (deep)"
    try:
        import websockets  # noqa: PLC0415 — optional: only --deep needs it
    except ImportError:
        suite.record(g, "websockets available", False, detail="pip install websockets (repo .venv has it)")
        return

    headers = {"X-Device-Id": device_id}
    created: list[tuple[str, str]] = []  # (game_id, room_code)
    by_type_seen: dict[str, str] = {}

    for entry in games:
        gid, gtype = entry.get("id"), entry.get("game_type")
        label = f"{gid}"
        room = request("POST", f"{t.api}/room/create", headers=headers, body={"game_type": gtype}, timeout=40)
        if not suite.expect_json(g, f"{label} room create", room, (200,)):
            continue
        code = (room.body or {}).get("room_code")
        token = (room.body or {}).get("organizer_token")
        if not code or not token:
            suite.record(g, f"{label} room payload", False, detail=f"body={room.text[:120]}")
            continue
        created.append((gid, code))
        by_type_seen.setdefault(gtype, gid)

        try:
            async with websockets.connect(
                ws_url(t.api, f"/ws/{code}/{uuid.uuid4()}?organizer=true"),
                additional_headers={"Origin": t.api},
                open_timeout=20,
                close_timeout=5,
            ) as ws:
                await ws.send(json.dumps({"type": "AUTH", "token": token}))
                hello = await recv_typed(ws, {"ROOM_CREATED", "ORGANIZER_SYNC", "ERROR"})
                lobby_ok = bool(hello) and hello.get("type") in ("ROOM_CREATED", "ORGANIZER_SYNC")
                suite.record(
                    g, f"{label} lobby", lobby_ok, detail=f"organizer first frame: {hello}"
                )

                if lobby_ok and gtype not in GATE_EXEMPT_GAME_TYPES:
                    await ws.send(json.dumps({"type": "START_GAME"}))
                    reply = await recv_typed(ws, {"ERROR", "GAME_STARTING", "INSUFFICIENT_SPARKS"})
                    gated = bool(reply) and reply.get("type") == "ERROR" and bool(
                        GATE_MESSAGE_RE.search(str(reply.get("message", "")))
                    )
                    suite.record(
                        g,
                        f"{label} min-player gate",
                        gated,
                        detail=f"START_GAME with an empty lobby answered: {reply}",
                    )
                elif lobby_ok:
                    suite.skip(g, f"{label} min-player gate", "quiz starts solo by design")

                await ws.send(json.dumps({"type": "CANCEL_GAME"}))
                await recv_typed(ws, {"ROOM_CLOSED"}, timeout=5)
        except Exception as exc:  # noqa: BLE001
            suite.record(g, f"{label} lobby", False, detail=f"websocket error: {exc}")

        if verbose:
            print(f"    · {gid:<18} room {code}")

    # Prod hygiene is part of the contract, not an afterthought: prove every room this run
    # created is gone, so the sweep cannot squat against MAX_ROOMS.
    leaked = [f"{gid}/{code}" for gid, code in created if not await room_is_gone(websockets, t, code)]
    suite.record(
        g,
        "rooms cleaned up",
        not leaked,
        detail=f"still alive after CANCEL_GAME: {leaked}",
        fact=f"{len(created)} games: create · lobby · gate · closed",
    )
    dedup = len(created) - len(by_type_seen)
    note = f"{len(by_type_seen)} distinct runtimes behind {len(created)} catalog entries swept"
    if dedup:
        note += (
            f" — {dedup} share a runtime with another entry (the occasion Bingo decks are frontend"
            " content over game_type=bingo, so their decks are covered by e2e, not here)"
        )
    suite.note(note)


async def check_playthrough(suite: Suite, t: Target, games: list[dict], game_id: str, verbose: bool) -> None:
    """Start one game for real, with QA-prefixed synthetic players, and assert the spark
    debit. Uses its own freshly minted wallet so the sweep's wallet stays unspent."""
    g = "GAMES (deep)"
    e = "ECONOMY"
    try:
        import websockets  # noqa: PLC0415
    except ImportError:
        suite.record(g, "playthrough", False, detail="websockets not importable")
        return

    entry = next((x for x in games if x.get("id") == game_id), None)
    if entry is None:
        suite.record(g, f"playthrough {game_id}", False, detail="not in catalog")
        return
    gtype = entry.get("game_type")
    min_players = int(((entry.get("config_schema") or {}).get("players") or {}).get("min") or 1)

    device_id = str(uuid.uuid4())
    h = {"X-Device-Id": device_id}
    before = request("GET", f"{t.api}/tokens/balance", headers=h, timeout=30)
    start_balance = (before.body or {}).get("balance")
    cost_room = (before.body or {}).get("cost_room")
    suite.note(f"playthrough wallet {device_id} ({game_id}), opening balance {start_balance}")

    room = request("POST", f"{t.api}/room/create", headers=h, body={"game_type": gtype}, timeout=40)
    if not suite.expect_json(g, f"playthrough {game_id} room", room, (200,)):
        return
    code, token = (room.body or {}).get("room_code"), (room.body or {}).get("organizer_token")

    players: list = []
    try:
        organizer = await websockets.connect(
            ws_url(t.api, f"/ws/{code}/{uuid.uuid4()}?organizer=true"),
            additional_headers={"Origin": t.api},
            open_timeout=20,
            close_timeout=5,
        )
        await organizer.send(json.dumps({"type": "AUTH", "token": token}))
        hello = await recv_typed(organizer, {"ROOM_CREATED", "ERROR"})
        if not suite.record(
            g, f"playthrough {game_id} organizer", bool(hello) and hello.get("type") == "ROOM_CREATED",
            detail=f"first frame: {hello}",
        ):
            await organizer.close()
            return

        for i in range(max(2, min_players)):
            pws = await websockets.connect(
                ws_url(t.api, f"/ws/{code}/{uuid.uuid4()}"),
                additional_headers={"Origin": t.api},
                open_timeout=20,
                close_timeout=5,
            )
            players.append(pws)
            await pws.send(json.dumps({"type": "JOIN", "nickname": f"QA-P{i + 1}", "avatar": "🧪"}))
            joined = await recv_typed(pws, {"JOINED_ROOM", "ERROR"})
            if not suite.record(
                g, f"playthrough {game_id} join QA-P{i + 1}",
                bool(joined) and joined.get("type") == "JOINED_ROOM",
                detail=f"JOIN answered: {joined}",
            ):
                break

        await organizer.send(json.dumps({"type": "START_GAME"}))
        started = await recv_typed(organizer, {"GAME_STARTING", "ERROR", "INSUFFICIENT_SPARKS", "QUESTION"}, timeout=20)
        ok_start = bool(started) and started.get("type") in ("GAME_STARTING", "QUESTION")
        suite.record(g, f"playthrough {game_id} start", ok_start, detail=f"START_GAME answered: {started}")

        if ok_start:
            first = started if started.get("type") == "QUESTION" else None
            if first is None:
                await organizer.send(json.dumps({"type": "NEXT_QUESTION"}))
                first = await recv_typed(organizer, {"QUESTION", "ERROR"}, timeout=20)
            suite.record(
                g,
                f"playthrough {game_id} first playable screen",
                bool(first) and first.get("type") == "QUESTION" and bool(first.get("question")),
                detail=f"first round broadcast: {str(first)[:160]}",
                fact=f"{game_id} played to first round",
            )

            after = request("GET", f"{t.api}/tokens/balance", headers=h, timeout=30)
            end_balance = (after.body or {}).get("balance")
            suite.record(
                e,
                "room debit",
                isinstance(end_balance, int)
                and isinstance(start_balance, int)
                and start_balance - end_balance == cost_room,
                detail=f"{start_balance} -> {end_balance}, expected -{cost_room}",
                fact=f"room debit {cost_room}",
            )

        await organizer.send(json.dumps({"type": "CANCEL_GAME"}))
        await recv_typed(organizer, {"ROOM_CLOSED"}, timeout=6)
        await organizer.close()
    except Exception as exc:  # noqa: BLE001
        suite.record(g, f"playthrough {game_id}", False, detail=f"websocket error: {exc}")
    finally:
        for pws in players:
            try:
                await pws.close()
            except Exception:  # noqa: BLE001
                pass

    suite.record(
        g,
        f"playthrough {game_id} room closed",
        await room_is_gone(websockets, t, code),
        detail=f"room {code} still answers after CANCEL_GAME",
        fact="room closed",
    )


def check_generate_idempotency(suite: Suite, t: Target) -> None:
    """Same Idempotency-Key must return the same content and must not double-charge.
    Generation is charged lazily (settled when the content becomes a playable room), so this
    spends no sparks — but it does spend an LLM call, hence --deep only."""
    g = "ECONOMY"
    device_id = str(uuid.uuid4())
    key = str(uuid.uuid4())
    h = {"X-Device-Id": device_id, "Idempotency-Key": key}
    body = {"prompt": f"QA regression harmless ocean facts {int(time.time())}", "difficulty": "easy", "num_questions": 5}

    before = request("GET", f"{t.api}/tokens/balance", headers={"X-Device-Id": device_id}, timeout=30)
    opening = (before.body or {}).get("balance")

    first = request("POST", f"{t.api}/quiz/generate", headers=h, body=body, timeout=180)
    if not suite.expect_json(g, "generate", first, (200,), fact="LLM generate"):
        return
    quiz_id = (first.body or {}).get("quiz_id")
    second = request("POST", f"{t.api}/quiz/generate", headers=h, body=body, timeout=180)
    suite.record(
        g,
        "generate idempotent",
        (second.body or {}).get("quiz_id") == quiz_id and bool(quiz_id),
        detail=f"first={quiz_id} second={(second.body or {}).get('quiz_id')}",
        fact="idempotent retry",
    )
    after = request("GET", f"{t.api}/tokens/balance", headers={"X-Device-Id": device_id}, timeout=30)
    suite.record(
        g,
        "generate does not pre-charge",
        (after.body or {}).get("balance") == opening,
        detail=f"{opening} -> {(after.body or {}).get('balance')} (charge settles on room start)",
        fact="no pre-charge",
    )


# --------------------------------------------------------------------------- main


def repo_commit() -> str:
    try:
        out = subprocess.run(
            ["git", "-C", str(REPO_ROOT), "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return out.stdout.strip() or "unknown"
    except Exception:  # noqa: BLE001
        return "unknown"


def main() -> int:
    parser = argparse.ArgumentParser(description="LocalPlay L5 prod/gamma regression suite")
    parser.add_argument("--target", choices=sorted(TARGETS), default="gamma")
    parser.add_argument(
        "--deep",
        action="store_true",
        help="also create+cancel a room for every catalog game, play one game, and check generation idempotency",
    )
    parser.add_argument("--play", default="quiz", help="game id to play through in --deep (default: quiz)")
    parser.add_argument(
        "--games",
        default="",
        help="comma-separated catalog ids to sweep in --deep instead of the whole catalog "
        "(e.g. --games impostor,quiz for a targeted prod check)",
    )
    parser.add_argument("--no-play", action="store_true", help="in --deep, skip the playthrough (spends no sparks)")
    parser.add_argument("--skip-generate", action="store_true", help="in --deep, skip the LLM generation checks")
    parser.add_argument("--verbose", "-v", action="store_true", help="print every individual check")
    args = parser.parse_args()

    t = TARGETS[args.target]
    started = time.monotonic()
    suite = Suite()

    # One synthetic wallet for the read-mostly checks and the free room sweep. UUID-shaped or
    # tokens.get_device_id() rejects it and every wallet assertion silently tests nothing.
    device_id = str(uuid.uuid4())
    assert UUID_RE.match(device_id)

    if args.target == "local":
        suite.note(
            "local target assumes scripts/dev-local.sh with a built frontend and a reachable "
            "config.json — without those, the SPA, legal-page and remote-config checks fail truthfully"
        )

    cfg = request("GET", f"{t.api}/config/public", timeout=30)
    public_cfg = cfg.body if (cfg.status == 200 and cfg.is_json and isinstance(cfg.body, dict)) else None
    if public_cfg is None:
        suite.record("INFRA", "config/public", False, detail=f"{cfg.status} {cfg.content_type} {cfg.text[:120]}")
    else:
        suite.record("INFRA", "config/public", True, fact="remote config")

    check_infra(suite, t)
    games = check_catalog(suite, t, public_cfg)
    check_economy(suite, t, device_id, public_cfg)
    check_payment_rails(suite, t, device_id, public_cfg)
    check_security(suite, t)
    check_flags(suite, t, public_cfg, device_id)

    if args.deep:
        if games:
            wanted = [x.strip() for x in args.games.split(",") if x.strip()]
            sweep = [x for x in games if x.get("id") in wanted] if wanted else games
            unknown = sorted(set(wanted) - {x.get("id") for x in games})
            if unknown:
                suite.record("GAMES (deep)", "--games ids exist", False, detail=f"not in catalog: {unknown}")
            asyncio.run(check_games_deep(suite, t, sweep, device_id, args.verbose))
            if args.no_play:
                suite.skip("GAMES (deep)", "playthrough", "--no-play")
                suite.skip("ECONOMY", "room debit", "--no-play")
            else:
                asyncio.run(check_playthrough(suite, t, games, args.play, args.verbose))
        else:
            suite.record("GAMES (deep)", "catalog available", False, detail="catalog unreadable, cannot sweep games")
        if args.skip_generate:
            suite.skip("ECONOMY", "generate idempotent", "--skip-generate")
        else:
            check_generate_idempotency(suite, t)
    else:
        suite.skip("GAMES (deep)", "game sweep", "run with --deep")

    header = [
        f"REVELRY GAMES · {t.name} REGRESSION · {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC",
        f"target: {t.api}   repo commit: {repo_commit()}   mode: {'deep' if args.deep else 'read-mostly'}",
        f"synthetic device: {device_id}   nicknames: QA-*",
    ]
    return suite.report(header=header, elapsed=time.monotonic() - started, verbose=args.verbose)


if __name__ == "__main__":
    raise SystemExit(main())
