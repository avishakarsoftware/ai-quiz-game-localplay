# SPEC-ANALYTICS — Product analytics (PostHog)

Status: **Frontend already built; this spec adds backend capture + identify wiring + build-script baking** (2026-07-07)
Owner: Avi
Related: `SPEC-IAP.md` (purchase events), `SPEC-REFERRAL.md`, `SPEC-ADS.md`, `frontend/src/utils/analytics.ts`

---

## 0. What already exists

- `posthog-js@^1.352.0` is a dependency. `frontend/src/utils/analytics.ts` exposes `initAnalytics()`,
  `track(event, props)`, `identify(id, props)` — all **no-op unless `VITE_POSTHOG_KEY` is set**.
- `initAnalytics()` runs at boot (`main.tsx`). ~23 events already fire (`game_started`, `game_completed`,
  `room_created`, `signed_in`, `tokens_purchased`, `checkout_started`, `paywall_hit/shown`,
  `get_sparks_clicked`, `config_loaded`, `*_generated`, …).
- `analytics.ts` has its **own** `getPlatform()` (web/pwa/native). **Do not** collapse it into
  `utils/platform.ts` (payment helper) — intentionally separate.

## 1. Gaps this spec closes

1. **`identify()` is never called** — events aren't tied to a wallet/user, so per-user funnels & retention
   are impossible. Wire `identify(walletId)` once the wallet id is known (sign-in + first balance fetch).
2. **Keys not baked into builds** — `VITE_POSTHOG_KEY`/`VITE_POSTHOG_HOST` are not injected by
   `cap-build.mjs` (native) or `ionos-build.mjs` (web), so analytics can never turn on in shipped builds.
3. **No backend analytics** — server-authoritative events (IAP credit via `/webhook/revenuecat`, referral
   grants, ad rewards, daily bonus) have no capture path. Client events can't see these truthfully.
4. **A few economy events missing** — no explicit `spark_earned{source}` / `spark_spent{reason}`.

## 2. Non-goals

- No autocapture / heatmaps beyond what posthog-js already does. No PII beyond the opaque wallet id
  (UUID/user_id — already non-identifying). No session-recording policy change.

## 3. Backend capture (`backend/analytics.py`, net-new)

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

**Server events to emit:**
| Event | Where | Key props |
|---|---|---|
| `iap_purchase_credited` | `/webhook/revenuecat` INITIAL_PURCHASE success | store, sku, sparks |
| `iap_refund` | webhook REFUND/CANCELLATION | store, sku, sparks_clawed |
| `web_purchase_credited` | Stripe webhook credit | sku, sparks |
| `spark_earned` | daily bonus / ad reward / referral grant | source, amount, (streak) |
| `referral_redeemed` | `/referral/redeem` | (referrer/referee are distinct_ids) |

## 4. Frontend changes

- **`identify` wiring:** call `identify(walletId)` in the sign-in success path and in the token-balance
  hook once a wallet id resolves (guard so it only fires once per id). Include `{signed_in: bool}`.
- **New events:** `spark_earned{source}` where the client learns of a credit (daily bonus grant in
  `/tokens/balance`, referral redeem success); `spark_spent{reason}` is better emitted server-side (§3) —
  keep client ones only where the client is the source of truth.
- **Build baking:** add `VITE_POSTHOG_KEY` + `VITE_POSTHOG_HOST` passthrough to `cap-build.mjs` and
  `ionos-build.mjs` (read from env; omit → analytics stays disabled). Never hardcode a key.

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
- Frontend: `analytics.track` already no-ops without init — add a test that `identify` no-ops pre-init and
  passes the id through post-init (mock posthog).

## 7. Rollout

Ship code (no-op without keys). Later: set `POSTHOG_API_KEY` on gamma/prod `.env`, `VITE_POSTHOG_KEY` in the
build env, redeploy. **Needs the user:** a PostHog project + write key.

## 8. Files touched
- `backend/analytics.py` (new), `backend/config.py` (keys), `backend/main.py` (emit in webhooks + economy),
  `backend/tests/test_analytics.py` (new).
- `frontend/src/utils/analytics.ts` (identify guard helper if needed), sign-in + balance-hook call sites,
  `frontend/scripts/cap-build.mjs`, `frontend/scripts/ionos-build.mjs`.
