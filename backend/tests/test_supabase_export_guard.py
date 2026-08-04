"""Guard the three-place sync behind the Supabase backend override (REVIEW-2026-08 §D1).

Making a db function behave differently on Supabase requires THREE edits:
    1. the db.py (SQLite) implementation,
    2. the supabase_db.py implementation,
    3. the function's name in db.py's _SUPABASE_EXPORTS list.

Forget #3 and nothing errors: prod (DB_BACKEND=supabase) silently runs the SQLite implementation
against the container's EPHEMERAL disk — plausible return values, data written to a file that
vanishes on the next deploy. The referral wrappers came within one review of shipping exactly this
way. test_runtime_db_guard.py guards backend *selection*; this file guards override *completeness*.

Each assertion here has been mutation-tested (name removed from the list / bogus name added /
sensitive function added without wiring) to confirm it actually fails.
"""
import re
from pathlib import Path

import supabase_db

BACKEND = Path(__file__).resolve().parent.parent


def _exports() -> list[str]:
    """The _SUPABASE_EXPORTS names, read statically — the block only executes under
    DB_BACKEND=supabase, so importing db in the test env never runs it."""
    text = (BACKEND / "db.py").read_text()
    block = re.search(r"_SUPABASE_EXPORTS = \[(.*?)\]", text, re.S)
    assert block, "_SUPABASE_EXPORTS list not found in db.py — if it was renamed, update this guard"
    return re.findall(r'"([^"]+)"', block.group(1))


# Rule for the supabase_db side: underscore-prefixed functions are private helpers called only
# by the exported functions in the same module ( _sb, _first, row mappers, …) — they never need
# wiring. Every NON-underscore function is part of the override surface and MUST be exported.
# The one deliberately-exported underscore name (_utc_date_str) is covered by the existence test.
# Note this exemption cannot hide a dangerous db.py-side helper: the sensitive-tables test below
# scans underscore names too (it is what forced _credit_in_txn into the allowlist).

# db.py functions that touch wallet/user/money tables but are deliberately SQLite-only.
# Every entry needs a reason. Adding a name here is a decision, not a default.
_SQLITE_ONLY = {
    # Internal credit helper called only inside db.py's own BEGIN IMMEDIATE transactions;
    # the Supabase equivalent lives inside the SQL RPC bodies (credit path is atomic there).
    "_credit_in_txn",
    # Pure date helper (no I/O); flagged only because callers pass it into referral queries.
    "_utc_midnight_epoch",
    # Referral daily cap counting for the SQLite path. On Supabase the cap is enforced INSIDE
    # the redeem_referral RPC (returns status='cap_reached'), so no override is needed.
    "count_referrals_today",
}

_SENSITIVE_TABLES = re.compile(
    r"\b(wallets|token_transactions|users|entitlements|device_usage|deleted_accounts)\b"
)


def test_every_exported_name_exists_in_supabase_db():
    """A typo'd or stale export name raises AttributeError at prod startup — catch it here,
    on SQLite CI, with a message that says what to fix."""
    missing = [n for n in _exports() if not hasattr(supabase_db, n)]
    assert not missing, (
        f"_SUPABASE_EXPORTS names {missing} do not exist in supabase_db.py. "
        "Prod startup (DB_BACKEND=supabase) would crash with AttributeError. "
        "Implement them in supabase_db.py or remove them from the list."
    )


def test_every_supabase_override_is_wired_into_the_export_list():
    """The deadly direction: an override implemented in supabase_db.py but absent from the list
    is silently IGNORED — prod keeps executing SQLite code against the ephemeral container disk."""
    text = (BACKEND / "supabase_db.py").read_text()
    defined = set(re.findall(r"^def ([A-Za-z][A-Za-z0-9_]*)\(", text, re.M))
    unwired = sorted(defined - set(_exports()))
    assert not unwired, (
        f"supabase_db.py defines {unwired} but _SUPABASE_EXPORTS (db.py) does not list them, so "
        "on DB_BACKEND=supabase these overrides never take effect and the SQLite implementation "
        "runs against the container's ephemeral disk instead. Add them to _SUPABASE_EXPORTS, or to "
        "_SUPABASE_INTERNAL in this test with a reason if they are genuinely private helpers."
    )


def test_sensitive_db_functions_are_overridden_or_explicitly_exempt():
    """Any db.py function whose body touches wallet/user/money tables must be either overridden on
    Supabase or consciously exempted above. A new economy function that skips the list writes user
    balances to a file that evaporates on the next deploy."""
    text = (BACKEND / "db.py").read_text()
    funcs: dict[str, list[str]] = {}
    current = None
    for line in text.splitlines():
        m = re.match(r"def ([A-Za-z_][A-Za-z0-9_]*)\(", line)
        if m:
            current = m.group(1)
            funcs[current] = []
        elif current is not None:
            funcs[current].append(line)

    touching = {
        name for name, body in funcs.items()
        if _SENSITIVE_TABLES.search("\n".join(body)) and name != "init_db"
    }
    unaccounted = sorted(touching - set(_exports()) - _SQLITE_ONLY)
    assert not unaccounted, (
        f"db.py functions {unaccounted} touch wallet/user/money tables but are neither in "
        "_SUPABASE_EXPORTS nor in this test's _SQLITE_ONLY allowlist. If they must behave "
        "differently on Supabase, implement + export the override; if the SQLite implementation is "
        "genuinely correct for both backends, add the name to _SQLITE_ONLY here WITH A REASON."
    )
