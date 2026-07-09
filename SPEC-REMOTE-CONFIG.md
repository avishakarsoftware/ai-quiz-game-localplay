# SPEC-REMOTE-CONFIG — Server-driven config & feature flags

Status: **Frontend already built; this spec adds a backend endpoint + schema extension** (2026-07-07)
Owner: Avi
Related: `frontend/src/hooks/useRemoteConfig.ts`, `frontend/src/types/remoteConfig.ts`, `frontend/public/config.json`, `backend/config.py` (`REMOTE_CONFIG_URL`)

---

## 0. What already exists (do not rebuild)

A complete **frontend** remote-config system:
- `useRemoteConfig` fetches `${BASE_URL}config.json` with localStorage cache + TTL (`cache_ttl_seconds`),
  merge-with-defaults (crash-proof), foreground refresh on tab visibility, and a `force_config_refresh`
  escape hatch.
- `RemoteConfig` schema covers: `operations` (maintenance, kill_switch, kill_generate, kill_payments,
  min_supported_version), `pricing` (+ promo block), `feature_flags` (show_upgrade_button,
  enable_image_generation), `announcements`. Consumed by `MaintenanceOverlay`, `AnnouncementBanner`,
  pricing/promo UI.
- `config.py` has `REMOTE_CONFIG_URL` (unused hook) and the promo mirrors `PROMO_ID`.

**Today the config is a static file** (`public/config.json`, shipped to IONOS). There is **no backend
endpoint** and **no game-catalog / spark-cost control** in the schema.

## 1. Gaps this spec closes

1. **Backend `GET /config/public`** — a server-owned config source so config can change without a frontend
   redeploy, and so native builds (which bundle their own `config.json`) can opt into a live source.
2. **Schema extension** — add `enabled_game_types` (catalog gating) and `economy` (tunable spark costs) +
   `ads_enabled` / `referral_enabled` flags, wired to real behavior.

## 2. Backend `GET /config/public`

- Reads a JSON file from the data dir: `${DATA_DIR}/remote_config.json` (path via
  `REMOTE_CONFIG_FILE`, default under the existing SQLite data dir). **In-memory cache** with a short TTL
  (e.g. 30s) + mtime check so edits are picked up without restart.
- **Safe defaults:** any missing key falls back to `config.py` constants (`COST_ROOM`, `COST_GENERATE`,
  the current game-enable flags, etc.). A missing/unparseable file ⇒ return the all-defaults object (never
  500). This mirrors the frontend's merge-with-defaults so both ends are crash-proof.
- Response shape is a **superset** of the existing `RemoteConfig` (so the frontend keeps working if pointed
  here) plus:
  ```jsonc
  {
    "enabled_game_types": ["quiz","wmlt","drawing", ...],   // null/absent ⇒ all enabled
    "economy": { "cost_room": 10, "cost_generate": 1 },
    "feature_flags": { ..., "ads_enabled": false, "referral_enabled": true }
  }
  ```
- Cheap, unauthenticated (public read), rate-limited by IP. No secrets in it.

**No admin write endpoint in v1** — the file is edited on the server (like `.env`). A future
`POST /config` (admin-gated) is noted, not built. *(If added during impl, log it.)*

## 3. Frontend extension

- Extend `RemoteConfig` type + `DEFAULT_CONFIG` + `mergeWithDefaults` with the new fields (all optional,
  defaulted). **Keep the static-file fetch working**; optionally allow the fetch URL to be the backend
  endpoint via an env (`VITE_CONFIG_URL`) that defaults to `${BASE_URL}config.json` (backward compatible).
- **Game-catalog gating:** `GameSelectScreen` filters the offered games by `enabled_game_types` when present
  (absent ⇒ show all). Complements the existing `ENABLE_BINGO`.
- `ads_enabled` / `referral_enabled` gate those features' UI (ties into SPEC-ADS / SPEC-REFERRAL).

## 4. Config / env
| Var | Default | Notes |
|---|---|---|
| `REMOTE_CONFIG_FILE` | `${data}/remote_config.json` | server-side config file |
| `REMOTE_CONFIG_CACHE_SECONDS` | 30 | in-memory cache TTL |
| `VITE_CONFIG_URL` (frontend) | `${BASE_URL}config.json` | deployed backend/IONOS/native builds point at backend `/config/public` so backend-authoritative flags such as `referral_enabled` are respected |

## 5. Testing
- `backend/tests/test_remote_config.py`: missing file ⇒ defaults (200, no throw); valid file ⇒ merged over
  defaults; partial file ⇒ only provided keys override; mtime change busts the cache; response is a superset
  containing economy + enabled_game_types.
- Frontend: `mergeWithDefaults` fills the new fields; `GameSelectScreen` hides a game absent from
  `enabled_game_types` and shows all when the field is absent.

## 6. Files touched
- `backend/config.py` (REMOTE_CONFIG_FILE, cache secs), `backend/remote_config.py` (new: load+cache+merge)
  or inline, `backend/main.py` (`GET /config/public`), `backend/tests/test_remote_config.py`.
- `frontend/src/types/remoteConfig.ts` (+fields), `frontend/src/hooks/useRemoteConfig.ts` (merge + optional
  URL env), `GameSelectScreen` (catalog gating), tests.
