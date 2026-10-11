# SPEC-ANALYTICS — Product analytics (PostHog)

Status: **Implemented (frontend/backend capture, identity and build-script key baking)**, source reviewed 2026-10-10. Each surface is inert when its own PostHog key is absent. Build/runtime activation is recorded in `DEPLOY.md`; source inspection cannot establish that keys are unset in every deployed environment.
Owner: Avi
Related: `SPEC-IAP.md` (purchase events), `SPEC-REFERRAL.md`, `SPEC-ADS.md`, `frontend/src/utils/analytics.ts`

---

## 0. What already exists

- `posthog-js@^1.352.0` is a dependency. `frontend/src/utils/analytics.ts` exposes `initAnalytics()`,
  `track(event, props)`, `identify(id, props)`, `resetIdentity()` — all **no-op unless `VITE_POSTHOG_KEY` is set**.
- `initAnalytics()` runs at boot (`main.tsx`). ~23 events already fire (`game_started`, `game_completed`,
  `room_created`, `signed_in`, `tokens_purchased`, `checkout_started`, `paywall_hit/shown`,
  `get_sparks_clicked`, `config_loaded`, `*_generated`, …).
- `analytics.ts` has its **own** `getPlatform()` (web/pwa/native). **Do not** collapse it into
  `utils/platform.ts` (payment helper) — intentionally separate.

## 1. Implemented wiring and remaining gaps

- `AuthContext` identifies guests by device id and signed-in users by wallet/user id on session
  validation and sign-in. Sign-out, rejected sessions and failed sign-in reset the SDK identity
  before identifying the guest device, so later events are not attributed to the prior account.
- `cap-build.mjs` and `ionos-build.mjs` pass `VITE_POSTHOG_KEY/VITE_POSTHOG_HOST` into builds.
- `backend/analytics.py` provides bounded best-effort capture and retains references to background
  tasks. Web/IAP fulfillment, bonus, referral, gifting, badge and grace paths emit server events.
- `spark_earned` exists for bonus/referral/ad-stub paths. A general ledger-wide `spark_spent` event
  and client bonus animation telemetry remain follow-ups; do not describe them as implemented.
- Analytics are best-effort observations, not a transaction ledger. Distinct webhook event IDs
  for one payment can emit repeated analytics even though database credits are idempotent.

## 2. Non-goals

- Autocapture is explicitly disabled; pageview/pageleave capture is enabled. `initAnalytics` does not disable session recording; source inspection alone does not establish the project's remote recording settings. Explicit application event properties omit email and provider tokens, but the persistent wallet/device identifiers still identify a pseudonymous account.

## 3. Backend capture (`backend/analytics.py`, implemented)

Tiny, dependency-free (uses the already-present `httpx`). **No-op when `POSTHOG_API_KEY` unset.**

```
POSTHOG_API_KEY  = os.getenv("POSTHOG_API_KEY", "")           # project WRITE key ("phc_…")
POSTHOG_HOST     = os.getenv("POSTHOG_HOST", "https://us.i.posthog.com")
ANALYTICS_ENABLED = bool(POSTHOG_API_KEY)
```

- `async def capture(distinct_id: str, event: str, properties: dict | None = None) -> None` — POST to
  `${POSTHOG_HOST}/capture/` with `{api_key, event, distinct_id, properties:{...,$lib:"revelry-backend", env}}`.
  Wrap in try/except; **never raise into request handlers** (fire-and-forget via `asyncio.create_task` or
  awaited-but-swallowed). Short timeout (2s). Guard the whole thing behind `ANALYTICS_ENABLED`.
- `distinct_id` = wallet_id (user_id if signed in else device_id) so backend + frontend events unify on the
  same person.

**Implemented server events:**
| Event | Where | Key props |
|---|---|---|
| `iap_purchase_credited` | `/webhook/revenuecat` INITIAL_PURCHASE success | store, sku, sparks |
| `iap_refund` | webhook REFUND/CANCELLATION | store, sku, sparks_clawed |
| `web_purchase_credited` | Stripe webhook credit | sku, sparks |
| `spark_earned` | daily bonus / ad reward / referral grant | source, amount, (streak) |
| `referral_redeemed` | `/referral/redeem` | (referrer/referee are distinct_ids) |

## 4. Frontend contract

`initAnalytics()` runs at boot and no-ops without the build key. `track`, `identify` and
`resetIdentity` no-op before initialization. Platform telemetry remains separate from the strict
payment `web|ios|android` helper: analytics also distinguishes PWA/native fallback.

Auth-owned identity wiring avoids repeated balance-hook identification. `signed_out` is captured
before the SDK reset; later events use the device wallet. No email or provider token is sent as
an analytics identifier. Build helpers pass public project keys from their environment and do
not hardcode them.

## 5. Config / env (per environment)

| Var | Surface | Notes |
|---|---|---|
| `POSTHOG_API_KEY` | backend | project write key; unset ⇒ backend analytics off |
| `POSTHOG_HOST` | backend + frontend | default `https://us.i.posthog.com` |
| `VITE_POSTHOG_KEY` | frontend build | baked by cap/ionos build; unset ⇒ frontend analytics off |
| `VITE_POSTHOG_HOST` | frontend build | optional |

## 6. Testing

- `backend/tests/test_analytics.py`: `capture()` is a no-op (no HTTP) when key unset; when set, it builds the
  correct payload (monkeypatch httpx, assert URL/body); exceptions are swallowed (never propagate).
- `frontend/src/utils/__tests__/analytics.test.ts` checks no-op helpers before initialization. AuthContext regressions verify guest/user attribution, identity reset, sign-out, and rejected-session cleanup; the native recovery test also proves RevenueCat returns to the device wallet and balance refreshes.

## 7. Rollout

Activation, when required: set `POSTHOG_API_KEY` on gamma/prod `.env`, `VITE_POSTHOG_KEY` in the
build env, redeploy. Verify each deployed surface separately; frontend build keys and backend runtime keys are independent.

## 8. Files touched
- `backend/analytics.py` (new), `backend/config.py` (keys), `backend/main.py` (emit in webhooks + economy),
  `backend/tests/test_analytics.py` (new).
- `frontend/src/utils/analytics.ts` (guarded identity/reset helpers), auth and event call sites,
  `frontend/scripts/cap-build.mjs`, `frontend/scripts/ionos-build.mjs`.
