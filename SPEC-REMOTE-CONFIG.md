# SPEC-REMOTE-CONFIG — Server-driven config and feature flags

Status: **Implemented**, reconciled with source 2026-10-10. Public reads, durable admin
overrides, AI-model selection and frontend catalog/feature gates exist. Deployment state is
recorded in `DEPLOY.md`; this review changes local source only.

## Sources and precedence

`backend/remote_config.py` fetches JSON from `REMOTE_CONFIG_URL`. The legacy fallback derives
`/quiz/config.json` from the first `ALLOWED_ORIGINS` entry; use an explicit URL for another
hosting path. There is no `REMOTE_CONFIG_FILE` or mtime-based file reader.

- Backend fetch interval: 300 seconds; HTTP timeout: five seconds.
- Fetch/network/JSON failures and non-object payloads keep the last valid cached object;
  failed refreshes are retried after roughly one minute. A cold cache is an empty object.
- `app_settings.remote_config_overrides` stores a durable operator layer, deep-merged over the
  fetched object. Malformed stored values or settings-reader failures act as an empty layer.
- AI provider/free/paid model getters use the merged `ai_models` object with environment
  defaults. Startup tolerates a malformed `ai_models` value. Operator changes therefore affect
  actual generation, not just the public response.

## Public endpoint

`GET /config/public` is unauthenticated and returns the merged config augmented with:

```json
{
  "enabled_game_types": null,
  "economy": { "cost_room": 10, "cost_generate": 1 },
  "feature_flags": {
    "show_upgrade_button": true,
    "enable_image_generation": true,
    "ads_enabled": false,
    "referral_enabled": false,
    "gifting_enabled": false,
    "achievements_enabled": false
  }
}
```

The amounts above are examples of the current defaults; `config.COST_ROOM/COST_GENERATE`
remain authoritative. Referral, gifting and achievement flags reflect backend support and
Supabase activation flags. Ads remain false while verified ad fulfillment is unimplemented.
A malformed `feature_flags` value falls back to defaults without discarding other valid fields.
The endpoint has no dedicated IP rate limiter; do not claim otherwise.

`enabled_game_types` controls the standalone picker when it is a nonempty array; absent, null
or empty values leave its catalog unfiltered. This is presentation gating, not a server-side
runtime kill switch. `operations.kill_switch/kill_generate/kill_payments` control frontend
surfaces. Host-app launch authorization and game exposure use the separate catalog policy in
`SPEC-REVELRY-INTEGRATION.md`; config cannot add an unimplemented game.

## Admin endpoints

- `GET /admin/config`: returns `fetched`, `overrides`, `effective` and `source_url` separately.
- `PUT /admin/config` with `{ "overrides": { ... } }`: replaces the entire override layer.
- `DELETE /admin/config` or PUT with empty overrides: clears that layer.

All three require `Authorization: Bearer <ADMIN_API_KEY>` with constant-time comparison;
unconfigured admin access returns 503 and invalid credentials return 403. The override layer
is persisted in both storage backends. It does not write the fetched IONOS file or environment
variables. Migration `20260727T010000_app_settings{,_gamma}.sql` provides Supabase storage.

## Frontend

`useRemoteConfig` fetches `VITE_CONFIG_URL` or `${BASE_URL}config.json`, merges missing fields
with `DEFAULT_CONFIG`, and caches under `revelry_remote_config` in localStorage.

- Timeout: three seconds. Default/max cache TTL: 24 hours; a positive `cache_ttl_seconds`
  can shorten it. A fresh cache skips the network.
- Foreground visibility triggers the same cache-aware read; `force_config_refresh` in the
  current config bypasses cache. It cannot force a client to discover an unseen remote flag.
- Unknown/malformed announcement entries are dropped individually; they must not discard
  valid operational flags or valid neighboring announcements.
- IONOS/native build scripts point the hook at the backend `/config/public`; bundled/static
  config remains the default fallback for builds without that setting.
- Legacy single-pack `pricing` keys are ignored. Spark packs come from the product catalog and
  native store prices, with balance/spend amounts authoritative on the backend.

## Validation and remaining work

`test_remote_config.py`, `test_config_public.py` and `test_config_overrides.py` cover source URL,
last-good cache retention, malformed payloads, backend flags/economy, durable deep overrides,
admin authorization and model selection. `useRemoteConfig.test.ts` covers merge/cache/foreground
behavior and malformed announcements preserving kill switches.

Future work: a validated operator UI, server-side operational kill switches if required, and
shorter/explicit refresh policy for emergency changes. They are not implemented by the existing
frontend presentation flags.
