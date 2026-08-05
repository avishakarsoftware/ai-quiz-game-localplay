"""Abuse guards (REVIEW-2026-08 S2): signup-bonus IP allowance + per-wallet LLM quota.

The economics before these: any fresh UUID in X-Device-Id earned SIGNUP_BONUS_TOKENS, and each
spark funds an LLM call — so minting device ids converted directly into a drain on the shared
hourly LLM budget. The global cap bounded the dollar cost but let one farmer DoS generation
for every real user.
"""
import uuid

import pytest

import config
import db
import tokens

# Captured at module-import time, i.e. BEFORE any fixture runs — conftest's autouse
# fund_test_wallet monkeypatches tokens.ensure_wallet to a no-op for the general suites,
# and these tests need the real implementation.
_REAL_ENSURE_WALLET = tokens.ensure_wallet


@pytest.fixture(autouse=True)
def reset_guard_state(monkeypatch):
    tokens._signup_grants_by_ip.clear()
    tokens.set_request_client_ip("")
    monkeypatch.setattr(tokens, "ensure_wallet", _REAL_ENSURE_WALLET)
    yield
    tokens._signup_grants_by_ip.clear()
    tokens.set_request_client_ip("")


def _fresh(prefix: str = "") -> str:
    return str(uuid.uuid4())


class TestSignupBonusIpAllowance:
    def test_grants_stop_after_the_ip_limit_but_wallets_still_created(self, monkeypatch):
        monkeypatch.setattr(config, "SIGNUP_BONUS_IP_DAILY_LIMIT", 3)
        tokens.set_request_client_ip("198.51.100.7")

        balances = [tokens.ensure_wallet(_fresh())["balance"] for _ in range(5)]
        # first 3 creations from this IP get the grant, the rest are created grantless
        assert balances[:3] == [config.SIGNUP_BONUS_TOKENS] * 3
        assert balances[3:] == [0, 0], (
            "wallets past the allowance must still exist (nobody is blocked from playing) "
            "but must not carry the farmable grant"
        )

    def test_returning_devices_do_not_consume_the_allowance(self, monkeypatch):
        """The gate spends quota only on CREATION. A returning device polling its balance all
        evening must not eat its party's allowance — that regression would silently zero the
        grant for every late-arriving guest."""
        monkeypatch.setattr(config, "SIGNUP_BONUS_IP_DAILY_LIMIT", 2)
        tokens.set_request_client_ip("198.51.100.8")

        first = _fresh()
        tokens.ensure_wallet(first)                 # consumes 1 of 2
        for _ in range(10):
            tokens.ensure_wallet(first)             # existing wallet: no consumption
        assert tokens.ensure_wallet(_fresh())["balance"] == config.SIGNUP_BONUS_TOKENS, (
            "the second allowance unit must still be available after repeat visits"
        )

    def test_other_ips_unaffected(self, monkeypatch):
        monkeypatch.setattr(config, "SIGNUP_BONUS_IP_DAILY_LIMIT", 1)
        tokens.set_request_client_ip("198.51.100.9")
        tokens.ensure_wallet(_fresh())
        assert tokens.ensure_wallet(_fresh())["balance"] == 0  # ip exhausted

        tokens.set_request_client_ip("203.0.113.5")
        assert tokens.ensure_wallet(_fresh())["balance"] == config.SIGNUP_BONUS_TOKENS

    def test_no_ip_context_allows(self, monkeypatch):
        """Internal callers and tests have no request context; the gate must fail open —
        misfiring on internal paths would be worse than the farming it prevents."""
        monkeypatch.setattr(config, "SIGNUP_BONUS_IP_DAILY_LIMIT", 1)
        tokens.set_request_client_ip("")
        for _ in range(3):
            assert tokens.ensure_wallet(_fresh())["balance"] == config.SIGNUP_BONUS_TOKENS

    def test_zero_limit_disables_the_gate(self, monkeypatch):
        monkeypatch.setattr(config, "SIGNUP_BONUS_IP_DAILY_LIMIT", 0)
        tokens.set_request_client_ip("198.51.100.10")
        for _ in range(5):
            assert tokens.ensure_wallet(_fresh())["balance"] == config.SIGNUP_BONUS_TOKENS


class TestPerWalletLlmQuota:
    def test_one_wallet_cannot_drain_the_global_pool(self, monkeypatch):
        import main
        monkeypatch.setattr(config, "MAX_LLM_CALLS_PER_WALLET_PER_HOUR", 3)
        monkeypatch.setattr(config, "MAX_LLM_CALLS_PER_HOUR", 100)
        main._llm_calls_by_wallet.clear()
        main._llm_call_timestamps.clear()

        hog = "wallet-hog"
        assert [main._check_llm_budget(hog) for _ in range(3)] == [True] * 3
        assert main._check_llm_budget(hog) is False, "4th call in the hour must be refused"
        # the hog's refusals must not have consumed global budget for others
        assert main._check_llm_budget("wallet-other") is True
        assert len(main._llm_call_timestamps) == 4  # 3 hog + 1 other; refusal recorded nothing

    def test_no_wallet_id_checks_global_only(self, monkeypatch):
        import main
        monkeypatch.setattr(config, "MAX_LLM_CALLS_PER_WALLET_PER_HOUR", 1)
        monkeypatch.setattr(config, "MAX_LLM_CALLS_PER_HOUR", 100)
        main._llm_calls_by_wallet.clear()
        main._llm_call_timestamps.clear()
        assert all(main._check_llm_budget() for _ in range(5))

    def test_zero_disables_per_wallet_cap(self, monkeypatch):
        import main
        monkeypatch.setattr(config, "MAX_LLM_CALLS_PER_WALLET_PER_HOUR", 0)
        monkeypatch.setattr(config, "MAX_LLM_CALLS_PER_HOUR", 100)
        main._llm_calls_by_wallet.clear()
        main._llm_call_timestamps.clear()
        assert all(main._check_llm_budget("w") for _ in range(10))
