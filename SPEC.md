# LocalPlay System Spec

This document describes the system as it exists now. It is intended as a baseline for planning new games and platform upgrades.

For the forward-looking LocalPlay platform vision, including the future Revelry integration boundary, see `SPEC-PLATFORM.md`.

## Product

LocalPlay, currently surfaced publicly as **Revelry Games**, is an AI-powered party game platform. A host creates or selects game content, creates a room, shares a room code or join URL, and players join from their phones. Gameplay happens in real time over WebSockets, with an optional spectator/TV surface.

The platform currently supports:

- `quiz`: AI-generated, imported, or manually authored multiple-choice trivia.
- Quiz runtime variants: `rebus`, `emoji_charades`, `fact_fiction`, `timeline`, and `odd_one_out`.
- `wmlt`: "Who's Most Likely To" voting rounds.
- `drawing`: rotating drawer/guesser rounds with live canvas sync.
- `musical_chairs`: standalone elimination rounds where music/visual rhythm stops and players race to tap.
- Standalone custom quiz authoring and saved quiz packs.
- Host-app/party-scoped authoring and game setup through the Revelry Games hub.

The system uses shared room, player, team, token, media, and WebSocket infrastructure. Game-specific rules are handled by `room.game_type` branches in backend and frontend code while the platform is still single-server and deliberately simple.

Launch readiness baseline:

- Standalone hosts can choose a game, create content, review it, create a room, share a join link/QR, run the game, and play again without falling into dead-end screens.
- Standalone **My Quizzes** is scoped to the current LocalPlay wallet/session and must not show Revelry party-scoped content or images.
- Host-app launches must hide standalone economy/account/library chrome unless explicitly allowed by the host-app context.
- All user-facing labels should treat the app as a multi-game surface, not as "Revelry Quiz".
- The standalone game picker is a catalog, not a long vertical list: show all available games by default, include search, and filter with the product categories **All**, **Quiz/Trivia**, **Creative**, and **Bingo/Housie**. Do not include a generic "Social" category because all LocalPlay games are social by design. Games that support AI-generated setup/content should show a small sparkle marker after the game name.
- Backend-served SPA and service worker routing must never allow API routes to be fulfilled by cached app shell HTML.
- PWA prompts should improve continuity without interrupting gameplay: update prompts are allowed globally, while install and notification prompts are standalone-first and suppressed in Revelry/host-app embedded surfaces.

## Architecture

### Backend

The backend is a FastAPI app.

Key files:

- `backend/main.py`: REST API routes, room creation, content storage, imports/exports, auth/payment/history routes.
- `backend/socket_manager.py`: WebSocket room lifecycle, player join/reconnect, organizer control messages, game state transitions, scoring.
- `backend/config.py`: centralized environment variables and constants.
- `backend/db.py`: persistence facade for wallets, users, checkout/webhook/idempotency data.
- `backend/supabase_db.py`: Supabase/PostgREST implementation used by deployed prod/gamma.
- `backend/tokens.py`: spark wallet and token economy.
- `backend/quiz_engine.py`: LLM generation and validation for quiz content.
- `backend/mlt_engine.py`: LLM generation and validation for WMLT content.
- `backend/drawing_engine.py`: LLM generation and validation for drawing prompts.
- `backend/musical_chairs_engine.py`: setup validation, round counts, tap ranking, and elimination helpers for Musical Chairs.
- `backend/image_engine.py`: optional Stable Diffusion image generation for quiz questions.
- `backend/auth.py`: Google/Apple sign-in and session handling.
- `backend/remote_config.py`: remote config for provider/model/operation flags.

### Frontend

The frontend is React + TypeScript + Vite.

Key files:

- `frontend/src/pages/OrganizerPage.tsx`: host state machine and WebSocket client.
- `frontend/src/pages/PlayerPage.tsx`: player join, game, result, reconnect, and podium flows.
- `frontend/src/pages/SpectatorPage.tsx`: spectator and TV room-code entry/playback surface.
- `frontend/src/pages/PartyHubPage.tsx`: Revelry/host-app party-scoped games hub.
- `frontend/src/pages/RevelryAuthoringPage.tsx`: host-app quiz authoring entry point.
- `frontend/src/components/organizer/GameSelectScreen.tsx`: game picker.
- `frontend/src/components/organizer/PromptScreen.tsx`: quiz generation prompt.
- `frontend/src/components/organizer/MLTPromptScreen.tsx`: WMLT generation prompt.
- `frontend/src/components/organizer/DrawingPromptScreen.tsx`: drawing prompt setup.
- `frontend/src/components/organizer/MusicalChairsSetupScreen.tsx`: standalone Musical Chairs timing/music setup.
- `frontend/src/components/organizer/MusicalChairsGameScreen.tsx`: Musical Chairs host controls.
- `frontend/src/components/organizer/CustomQuizEditor.tsx`: manual custom quiz authoring.
- `frontend/src/components/organizer/ReviewScreen.tsx`: quiz review/edit before room creation.
- `frontend/src/components/organizer/MLTReviewScreen.tsx`: WMLT review/edit before room creation.
- `frontend/src/components/organizer/DrawingReviewScreen.tsx`: drawing prompt review/edit before room creation.
- `frontend/src/components/organizer/LobbyScreen.tsx`: host room lobby.
- `frontend/src/components/organizer/GameQuestionScreen.tsx`: host active-round display.
- `frontend/src/components/organizer/LeaderboardScreen.tsx`: quiz leaderboard between rounds.
- `frontend/src/components/organizer/PodiumScreen.tsx`: final results.
- `frontend/src/components/PwaPrompts.tsx`: install, notification opt-in, and service-worker update prompts.
- `frontend/src/gameModes.ts`: standalone and host-app-visible game catalog metadata.
- `frontend/src/types.ts`: shared frontend types.

### Production Topology

Production deployment is documented in `DEPLOY.md`.

Current production shape:

```text
Users -> games.revelryapp.me (IONOS CDN/static hosting) -> React/Vite frontend
      -> gamesapi.revelryapp.me (GCP VM)                 -> FastAPI backend + WebSockets + optional frontend
      -> gamesapi-gamma.revelryapp.me (GCP VM)           -> FastAPI backend + WebSockets + frontend
```

Production URLs:

- Frontend: `https://games.revelryapp.me/`
- Backend API + SPA fallback: `https://gamesapi.revelryapp.me`
- Gamma full stack: `https://gamesapi-gamma.revelryapp.me`
- Player join: `https://games.revelryapp.me/join`
- Spectator/TV: `https://games.revelryapp.me/spectator`
- Cast App ID: `1BC9ACD8`

Backend hosting:

- GCP Compute Engine VM.
- Dockerized FastAPI backend.
- Nginx terminates HTTPS and proxies API and WebSocket requests to the backend.
- Let's Encrypt certificates are managed with Certbot.
- Production container: `games-backend` on `127.0.0.1:8000`, using Supabase `games_*` tables for durable state.
- Gamma container: `games-backend-gamma` on `127.0.0.1:8004`, using Supabase `games_gamma_*` tables for durable state.
- Canonical LocalPlay VM home: `/home/revelry-games`.
- Older backup containers named `revelry-platform` and `revelry-gamma` may exist on the VM; the LocalPlay deploy script does not manage them.

Frontend hosting:

- Static Vite build uploaded under the IONOS `games/` directory.
- SPA routing is handled by `.htaccess` at the IONOS game root.

Backend-served frontend:

- FastAPI can also serve a built Vite frontend from `FRONTEND_DIST_DIR`, default `/app/static`.
- When `/app/static/index.html` exists, `/` and browser routes such as `/join` and `/spectator` return the app shell.
- Known API prefixes still return API JSON/errors and are not swallowed by the SPA fallback.
- Missing `/assets/*` files return JSON 404 instead of `index.html`.
- This mode is for gamma, backend preview, and future container-hosted staging. IONOS remains the public production frontend.
- The deploy script packages this mode with `./scripts/deploy-gcp.sh --with-frontend` or `./scripts/deploy-gcp.sh --gamma --with-frontend`.
- Docker images are built for `linux/amd64` because the GCP VM is AMD64, including when deploying from Apple Silicon.

Production notes:

- Ollama and Stable Diffusion are not expected to be available on the production VM.
- Production should use cloud AI providers, primarily Gemini.
- The frontend is built with `VITE_BASE_PATH=/`, `VITE_API_URL=https://gamesapi.revelryapp.me`, and `VITE_WEB_URL=https://games.revelryapp.me/`.

## Runtime Configuration

Backend config is centralized in `backend/config.py`.

Important settings:

- LLM providers:
  - `DEFAULT_PROVIDER`, default `gemini`.
  - `GEMINI_MODEL`, default `gemini-2.5-flash-lite`.
  - `GEMINI_PREMIUM_MODEL`, default `gemini-2.5-flash-lite`.
  - `OLLAMA_MODEL`, `OLLAMA_URL`, `ANTHROPIC_MODEL`.
- Server:
  - `HOST`, `PORT`, `ALLOWED_ORIGINS`, `FRONTEND_DIST_DIR`.
- Persistence:
  - `DB_BACKEND`, default `sqlite`.
  - `TABLE_PREFIX`, default `games_`; gamma must use `games_gamma_`.
  - `SUPABASE_URL`, `SUPABASE_SERVICE_KEY`, `SUPABASE_ANON_KEY`, `SUPABASE_TIMEOUT_SECONDS`.
  - Supabase settings are inert unless `DB_BACKEND=supabase`.
- Rate limits:
  - `RATE_LIMIT_WINDOW`, `RATE_LIMIT_MAX_REQUESTS`.
  - `DAILY_QUIZ_LIMIT`.
  - `MAX_LLM_CALLS_PER_HOUR`.
  - `WS_RATE_LIMIT_PER_SEC`.
  - `MAX_WS_MESSAGE_SIZE`.
- Game:
  - `DEFAULT_TIME_LIMIT`.
  - `DEFAULT_NUM_QUESTIONS`.
  - `MIN_QUESTIONS`, `MAX_QUESTIONS`.
  - `MAX_PLAYERS_PER_ROOM`.
  - `MIN_WMLT_PLAYERS`.
  - `ROOM_TTL_SECONDS`.
  - `ORGANIZER_RECONNECT_GRACE_SECONDS`, default 600 seconds. This protects live rooms from being closed immediately when the host phone locks, backgrounds the browser, or briefly loses connectivity.
  - `QUIZ_TTL_SECONDS`.
- Economy:
  - `COST_GENERATE`.
  - `COST_ROOM`.
  - `SIGNUP_BONUS_TOKENS`.
  - `DAILY_BONUS_TOKENS`.
  - `TOKEN_PACK_AMOUNT`.

### Request Headers

The platform uses shared API headers from the frontend fetch wrapper.

Important headers:

- `X-Device-Id`: stable device identifier for wallet/device context.
- `X-Platform`: `web`, `ios`, or `android` when available.
- `X-App-Version`: app version when available.
- `X-Build`: build number when available.
- `X-Idempotency-Key` or `Idempotency-Key`: used on generation requests to avoid duplicate charges/results on retry.

The backend CORS configuration explicitly allows these headers.

## Persistence

The implemented system supports SQLite and Supabase for durable state:

- Users and provider identities.
- Spark wallets and token transactions.
- Checkout/webhook idempotency.
- Legacy entitlements and free-usage tracking.
- Pending token pickup after checkout return.

Local development defaults to SQLite. Deployed production and gamma use Supabase:

- Production: `DB_BACKEND=supabase`, `TABLE_PREFIX=games_`.
- Gamma: `DB_BACKEND=supabase`, `TABLE_PREFIX=games_gamma_`.

The planned Supabase migration is specified in `SPEC-SUPABASE-MIGRATION.md`. It uses the existing VibePix Supabase project as a shared database, with table/RPC prefixes to avoid collisions:

- Production: `games_`.
- Gamma: `games_gamma_`.

The Supabase objects have been created in the shared project. Gamma and production have both been cut over and smoke-tested. SQLite files remain useful for local development and rollback backups during the initial rollout window.

## Content Model

Generated game content is stored in memory in `backend/main.py` for immediate room creation. Durable custom/saved content is stored through the DB facade.

Quiz storage:

- `quizzes: Dict[str, dict]`
- `quiz_timestamps: Dict[str, float]`
- `quiz_images: Dict[str, Dict[int, str]]`
- Saved custom quiz packs use `*_quiz_packs` and `*_quiz_questions`.
- Question image metadata uses `*_media_assets`; image files live on IONOS.

WMLT storage:

- `mlt_scenarios: Dict[str, dict]`
- `mlt_timestamps: Dict[str, float]`

Drawing storage:

- `drawing_games: Dict[str, dict]`
- `drawing_timestamps: Dict[str, float]`

Host-app/party setup storage:

- Current WMLT, Drawing, and Revelry gamma Housie party setups reuse `*_generated_content` with scoped owner ids such as `revelry:party:{party_id}`.
- Revelry party quiz authoring reuses quiz-pack storage under the same party-scoped ownership pattern.
- A richer generic content table remains backlog for future games that need collaboration, search, versioning, richer media, or cross-party reuse.

Ownership:

- `content_owners: Dict[str, str]`
- Content ids are mapped to wallet ids.
- Update, delete, export, and image-generation actions require matching ownership.
- Host-app content is scoped by host app and external container/party id and must not appear in standalone LocalPlay libraries.

Eviction:

- `_evict_old_content()` removes expired content and trims storage to `MAX_QUIZZES`.
- Content used by active rooms is not evicted.
- Quiz, WMLT, and Drawing generated content use the same TTL constant unless a game-specific retention rule is added.

## Game Types

Frontend game types are defined in `frontend/src/types.ts`:

```ts
export type QuizVariantGameType = 'rebus' | 'emoji_charades' | 'fact_fiction' | 'timeline' | 'odd_one_out';
export type GameType = 'quiz' | 'wmlt' | 'drawing' | 'housie' | 'bingo' | QuizVariantGameType;
```

The frontend catalog in `frontend/src/gameModes.ts` maps visible game ids to runtime types:

- `quiz`, `rebus`, `emoji_charades`, `fact_fiction`, `timeline`, and `odd_one_out` use the quiz runtime.
- `wmlt` uses the WMLT runtime.
- `drawing` uses the Drawing runtime.
- `housie` uses the 90-ball Bingo-family runtime.
- `bingo` uses the configurable 5x5 Bingo-family runtime.

Backend room creation accepts runtime game types:

- `quiz`
- `wmlt`
- `drawing`
- `housie`
- `bingo`

Unsupported game types are rejected by `RoomCreateRequest.validate_game_type`.

Host-app mode applies an additional catalog gate. A game must be returned as launchable by `GET /catalog?host_app=...` before it appears in the host-app hub or menus. Standalone-only variants can remain visible in standalone LocalPlay while hidden from Revelry until their bridge contract is complete.

Host-app game availability must be remotely controllable so enabling or disabling a game for Revelry does not require a new LocalPlay release. The code-backed catalog remains the maximum capability set: it declares which games can safely support host-app mode, which creation/start/edit surfaces exist, and which runtime/result contracts are implemented. Remote config or a small durable catalog-flags table is the operational switchboard: it can hide a game, expose it on gamma only, enable it for a party/account allowlist, or toggle features such as content creation, quick start, AI prompt generation, custom photos, and payments. Remote configuration must never enable a game that the code catalog does not declare host-app-compatible.

Implementation-ready availability model:

- Add a backend module, tentatively `backend/host_app_catalog_policy.py`, that loads host-app game policy, merges it with the static `GAME_CATALOG`, and returns effective catalog entries for host-app requests.
- Store policy in Supabase/PostgREST as `{TABLE_PREFIX}host_app_catalog_flags` or in the existing remote config service. Prefer the table if operators need per-game edits without replacing a whole JSON blob.
- If using a table, create columns: `id`, `environment`, `host_app`, `game_id`, `enabled`, `status`, `allowlist_party_ids` JSON array, `allowlist_external_user_ids` JSON array, `rollout_percentage`, `capability_overrides` JSON object, `notes`, `updated_by`, `updated_at`. Add a unique constraint on `(environment, host_app, game_id)`.
- `capability_overrides` may contain only known boolean capability keys: `can_create_content`, `can_edit_content`, `can_quick_start`, `supports_ai_generation`, `supports_images`, `payments_enabled`, `embedded_authoring_supported`, and future reviewed host-app capabilities.
- Policy lookup inputs are `environment`, `host_app`, `game_id`, and optional context for allowlists: `external_container_id` / party id and `external_user_id`.
- Merge algorithm:
  1. Start with the static code catalog entry.
  2. Drop the entry if `host_app_supported` is false or `supported_host_apps` does not contain the requested host app.
  3. Load matching policy for `(environment, host_app, game_id)`.
  4. In production, drop the entry if no matching policy exists or `enabled` is not true. In gamma/dev, missing policy may fall back to static metadata only when the static entry is explicitly marked host-app-supported.
  5. If `enabled` is false, return no launchable entry; optionally return a `planned`/`disabled` entry only when the caller requested planned catalog cards.
  6. If allowlists are present, expose the game only when the party id or actor id is listed.
  7. If `rollout_percentage` is set, hash a stable key such as `{host_app}:{external_container_id || external_user_id}:{game_id}` into 0-99 and expose only below the threshold.
  8. Compute every effective capability as static capability AND policy capability. Remote policy can turn supported capabilities off or selectively on only when the static catalog already supports them.
  9. Set `launchable = enabled && status in ("live", "gamma") && required effective capabilities are present`.
- Cache policy briefly, around 30-60 seconds, and fail closed on malformed policy in production. Log enough detail for operators without leaking secrets or party/user private data.
- Add an operator path to update policy without deploy: either an admin-only API, a small CLI/script that writes the table, or documented SQL snippets. Changes should become visible after cache expiry.
- Include a kill switch path that sets `enabled = false` for one `(environment, host_app, game_id)` and removes it from host-app catalogs immediately after cache expiry while leaving standalone LocalPlay unaffected.
- `GET /catalog?host_app=...` must be the only source used by host-app surfaces. Frontend hub code should not have separate hardcoded allow/deny lists except for defensive rendering of unknown capabilities.
- Tests should cover static capability gating, remote disable, gamma/prod differences, allowlisted exposure, rollout hashing, feature-flag intersection, malformed policy, unsupported game ids being ignored, and kill-switch behavior.

Revelry content callbacks must treat safe `payload.content` metadata as a first-class prepared-game mirror source. `content.created` and `content.updated` callbacks include top-level host-app/container/content ids plus a safe summary object with `localplay_content_id`, `game_type`, `title`, `status`, item/question count, optional thumbnail, and time limit. They must never include raw prompts, questions, answers, options, full media paths, provider prompts, launch tokens, or participant secrets. After signature and envelope validation, Revelry may fetch LocalPlay metadata to confirm or enrich, but a fetch failure must not skip the prepared-game mirror update when safe `payload.content` is present. Versioned updates move the visible prepared setup pointer to the new `content_id` rather than creating a duplicate visible card.

Bingo-family games are a separate runtime family rather than quiz variants. `SPEC-GAME-BINGO-HOUSIE.md` defines the reusable Bingo/Housie engine. Housie is implemented for standalone LocalPlay and Revelry gamma with server-generated tickets, manual/auto number calling, server-side claim validation, and spectator called-board sync. Configurable standalone Bingo is implemented with text/emoji/number/image-shaped deck items, 5x5 cards, optional free center, template/manual/AI-text setup, and host-reviewed generated items. Baby Bingo / dedicated word / emoji / image / photo Bingo remain later named rulesets on the same engine.

### Musical Chairs

`musical_chairs` is a standalone-first runtime family, not a quiz variant. `SPEC-GAME-MUSICAL-CHAIRS.md` defines the implementation-ready MVP. A host configures gameplay mode plus timing/music mode, creates a room, and starts with at least 3 connected players. Physical mode is the default: LocalPlay starts/stops rounds randomly while players use real chairs, then the host selects who is out. Digital mode uses phone taps: the stop signal opens a grab window, players tap once, and the slowest/no-tap player is eliminated automatically. MVP built-in mode provides server-randomized stop timing plus visual rhythm; procedural Web Audio is a later phase. Revelry/host-app launch remains deferred until a bridge contract is added and tested.

## LLM Generation Pattern

Generation engines follow the same pattern:

1. Build a system prompt.
2. Wrap the user prompt/theme in boundary markers.
3. Call the selected provider.
4. Extract JSON from the provider response.
5. Validate required fields.
6. Sanitize all user-visible text.
7. Return structured content.

Provider support:

- Ollama
- Gemini
- Claude

Gemini handling includes:

- Header auth for Gemini models.
- Query-param API key for models that require it.
- `responseMimeType: application/json` when supported by the selected model.
- Structural filtering of Gemini `part.thought` response parts.
- Regex fallback stripping of `<think>` / `<thinking>` blocks.

### Quiz Content Shape

Quiz generation returns:

```json
{
  "quiz_title": "string",
  "questions": [
    {
      "id": 1,
      "text": "Question text",
      "options": ["A", "B", "C", "D"],
      "answer_index": 0,
      "image_prompt": "Image generation prompt"
    }
  ]
}
```

Validation requires:

- `questions` exists and is a non-empty list.
- Each question has `id`, `text`, `options`, `answer_index`.
- Options count is either 2 or 4.
- `answer_index` is an integer within option bounds.

After provider output passes validation and sanitization, the backend shuffles every 4-option multiple-choice question and rewrites `answer_index` to match the shuffled correct answer. This prevents LLM ordering bias where the correct answer is usually option A. Two-option questions are not shuffled; Fact/Fiction questions keep the exact `["True", "False"]` order.

Quiz API responses strip `answer_index` before returning quiz data to clients except export/import and server-internal room data.

### WMLT Content Shape

WMLT generation returns:

```json
{
  "game_title": "string",
  "statements": [
    {
      "id": 1,
      "text": "Who is most likely to forget their passport?"
    }
  ]
}
```

Validation requires:

- `statements` exists and is a non-empty list.
- Each statement has `id` and non-empty `text`.

### Drawing Content Shape

Drawing generation returns:

```json
{
  "game_title": "string",
  "prompts": [
    {
      "id": 1,
      "text": "birthday cake",
      "aliases": ["cake"],
      "difficulty": "easy"
    }
  ]
}
```

Validation requires:

- `prompts` exists and is a non-empty list.
- Each prompt has `id` and non-empty `text`.
- Difficulty, if present, is one of `easy`, `medium`, or `hard`.

## REST API

### System

- `GET /system/info`
  - Requires admin key.
  - Returns local IP information.

### Providers

- `GET /providers`
  - Returns provider availability for Ollama, Gemini, and Claude.

### Quiz

- `POST /quiz/generate`
  - Requires `X-Device-Id`.
  - Requires enough balance for `COST_GENERATE`; the debit is deferred until the generated quiz is successfully accepted into a room or room reset.
  - Supports idempotency through `X-Idempotency-Key` or `Idempotency-Key`.
  - Body:
    - `prompt`
    - `difficulty`
    - `num_questions`
    - `provider`
    - `mode`, optional quiz variant such as `rebus` or `fact_fiction`.
  - Returns:
    - `quiz_id`
    - `quiz` with answers stripped.

- `GET /quiz/{quiz_id}`
  - Returns quiz with answers stripped.

- `PUT /quiz/{quiz_id}`
  - Requires authenticated wallet ownership.
  - Updates quiz title and questions.

- `DELETE /quiz/{quiz_id}/question/{question_id}`
  - Requires authenticated wallet ownership.
  - Deletes a question.
  - Cannot delete the last question.

- `POST /quiz/generate-images`
  - Requires authenticated wallet ownership.
  - Generates one or all question images using Stable Diffusion.

- `GET /quiz/{quiz_id}/image/{question_id}`
  - Returns generated PNG image bytes.

- `GET /quiz/{quiz_id}/export`
  - Requires ownership.
  - Returns full quiz including answers.

- `POST /quiz/import`
  - Requires authentication.
  - Validates and stores imported quiz.

### Saved Quiz Packs

- `GET /quiz-packs`
  - Lists saved custom quiz packs for the current wallet/session.
  - Must not include host-app/party-scoped packs unless the request is made through a valid host-app context.

- `POST /quiz-packs`
  - Saves a custom quiz pack for the current wallet/session.

- `GET /quiz-packs/{pack_id}`
  - Returns pack metadata and quiz payload for editing/review.

- `DELETE /quiz-packs/{pack_id}`
  - Deletes a saved custom quiz pack owned by the current wallet/session.

- `POST /quiz-packs/{pack_id}/materialize`
  - Produces a temporary runtime `quiz_id` from a saved pack so the normal room/review flow can start.
  - Frontend copy should say "Preparing Quiz", not "Generating Quiz".

### Stable Diffusion

- `GET /sd/status`
  - Returns whether image generation backend is available.

### WMLT

- `POST /mlt/generate`
  - Requires `X-Device-Id`.
  - Requires enough balance for `COST_GENERATE`; the debit is deferred until the generated setup is successfully accepted into a room or room reset.
  - Supports idempotency through `X-Idempotency-Key` or `Idempotency-Key`.
  - Body:
    - `prompt`
    - `difficulty`, used as WMLT vibe.
    - `num_rounds`
    - `provider`
  - Returns:
    - `scenario_id`
    - `game`

- `GET /mlt/{scenario_id}`
  - Returns generated WMLT game.

- `PUT /mlt/{scenario_id}`
  - Requires authenticated wallet ownership.
  - Updates title and statements.

- `DELETE /mlt/{scenario_id}/statement/{statement_id}`
  - Requires authenticated wallet ownership.
  - Deletes a statement.
  - Cannot delete the last statement.

- `GET /mlt/{scenario_id}/export`
  - Requires ownership.

- `POST /mlt/import`
  - Requires authentication.
  - Validates and stores imported WMLT game.

### Drawing

- `POST /drawing/generate`
  - Requires `X-Device-Id`.
  - Requires enough balance for `COST_GENERATE`; the debit is deferred until the generated setup is successfully accepted into a room or room reset.
  - Supports idempotency through `X-Idempotency-Key` or `Idempotency-Key`.
  - Body:
    - `prompt`
    - `difficulty`, used as drawing prompt vibe.
    - `num_prompts`
    - `provider`
  - Returns:
    - `drawing_id`
    - `game`

- `GET /drawing/{drawing_id}`
  - Returns generated Drawing game.

- `PUT /drawing/{drawing_id}`
  - Requires authenticated wallet ownership.
  - Updates title and prompts.

- `POST /drawing/import`
  - Requires authentication.
  - Validates and stores imported Drawing game.

### Catalog And Host-App Integration

- `GET /catalog`
  - Returns LocalPlay game metadata, launchability, creation capabilities, and host-app gating information.

- `/integrations/revelry/*`
  - LocalPlay-side bridge for Revelry party hub, authoring links, launch tokens, content CRUD, session status/results, and callbacks.
  - Detailed contract lives in `SPEC-REVELRY-INTEGRATION.md`.
  - External apps must use LocalPlay APIs; they must not read/write LocalPlay Supabase tables directly.

### Rooms

- `POST /room/create`
  - Requires device/wallet context.
  - Does not charge sparks; game-start charge happens over WebSocket.
  - Body:
    - `game_type`
    - `time_limit`
    - `quiz_id` for quiz.
    - `mlt_id` for WMLT.
    - `drawing_id` for Drawing.
  - Returns:
    - `room_code`
    - `organizer_token`

- `WS /ws/{room_code}/{client_id}`
  - Query params:
    - `organizer=true` for host.
    - `spectator=true` for spectator.

### History

- `GET /history`
  - Requires authentication.
  - Returns completed games for the current wallet.

- `GET /history/{room_code}`
  - Requires ownership.
  - Returns detailed game history.

### Auth And Payments

The backend also includes routes for:

- `POST /auth/signin`
- `GET /auth/me`
- `POST /checkout/create`
- `POST /webhook/stripe`

Token and checkout details are handled through `tokens.py`, `db.py`, and Stripe configuration.

## Room Model

`Room` lives in `backend/socket_manager.py`.

Important fields:

- `room_code`
- `quiz`
  - Generic game content payload. Used for both quiz and WMLT.
- `content_id`
- `game_type`
- `time_limit`
- `organizer_token`
- `players`
- `organizer`
- `spectators`
- `state`
- `current_question_index`
- `question_start_time`
- `answered_players`
- `connections`
- `timer_task`
- `previous_leaderboard`
- `wallet_id`
- `disconnected_players`
- `answer_log`
- `teams`
- `power_ups`
- `player_tokens`
- `bonus_questions`
- `locked`
- `votes`
- `show_votes`
- `mlt_round_history`
- `current_drawer_index`
- `drawing_ops`
- `drawing_guess_log`
- `drawing_correct_guessers`

Room states:

- `LOBBY`
- `INTRO`
- `QUESTION`
- `LEADERBOARD`
- `PODIUM`

The field name `current_question_index` is used for quiz questions, WMLT statements, and Drawing prompts.

## WebSocket Security

Shared rules:

- Origin validation is based on configured allowed origins.
- Organizer sockets must send first-frame `AUTH` with `organizer_token`.
- Message size is capped by `MAX_WS_MESSAGE_SIZE`.
- Per-client message rate is capped by `WS_RATE_LIMIT_PER_SEC`.
- Malformed JSON is rejected.
- Organizer privilege is tied to the current organizer client id.

Player join validation:

- Nicknames are stripped of HTML tags and control characters.
- Nicknames must be 1 to `MAX_NICKNAME_LENGTH` characters.
- Team names are sanitized and capped.
- Avatars are capped by `MAX_AVATAR_LENGTH`.
- Duplicate nickname takeover requires a matching session token.
- New joins are blocked if the room is locked or no longer in `LOBBY`.

Reconnection:

- Mid-game player disconnects preserve score, rank, streak, avatar, and answered state.
- Session tokens prevent nickname hijacking.
- Organizer disconnect starts a short cleanup grace period.
- Organizer reconnect receives a full room sync.

## WebSocket Protocol

### Organizer Messages To Server

- `AUTH`
  - First message required for organizer sockets.
  - Fields:
    - `token`

- `START_GAME`
  - Allowed from `LOBBY`.
  - Charges `COST_ROOM`.
  - Locks room.
  - WMLT validates minimum player count before charging.
  - Drawing validates minimum player count before charging.
  - Sets state to `INTRO`.
  - Broadcasts `GAME_STARTING`.

- `NEXT_QUESTION`
  - If state is `QUESTION`, ends current round.
  - If state is `INTRO` or `LEADERBOARD`, starts next round.

- `SET_TIME_LIMIT`
  - Allowed from `LOBBY`, `LEADERBOARD`, or `PODIUM`.
  - Time must be 5 to 60 seconds.

- `SET_SHOW_VOTES`
  - WMLT only.
  - Controls whether vote breakdown is exposed.

- `END_QUIZ`
  - Ends active game and broadcasts `PODIUM`.

- `RESET_ROOM`
  - Allowed from `PODIUM`.
  - Validates new content id and ownership.
  - Charges `COST_ROOM`.
  - Resets room while keeping connected players.

- `TOGGLE_LOCK`
  - Allowed from `LOBBY`.
  - Broadcasts room lock status.

### Player Messages To Server

- `JOIN`
  - Fields:
    - `nickname`
    - `team`
    - `avatar`
    - `session_token`

- `ANSWER`
  - Quiz only.
  - Fields:
    - `answer_index`

- `VOTE`
  - WMLT only.
  - Fields:
    - `voted_for`

- `DRAW_OP`
  - Drawing only.
  - Sent by the current drawer.
  - Fields:
    - `op`: stroke, clear, or undo payload.

- `GUESS`
  - Drawing only.
  - Sent by guessers.
  - Fields:
    - `guess`

- `USE_POWER_UP`
  - Quiz only.
  - Fields:
    - `power_up`: `double_points` or `fifty_fifty`.

### Server Messages To Clients

Common:

- `ERROR`
- `PING`
- `ROOM_CREATED`
- `JOINED_ROOM`
- `RECONNECTED`
- `PLAYER_JOINED`
- `PLAYER_LEFT`
- `PLAYER_DISCONNECTED`
- `PLAYER_RECONNECTED`
- `ORGANIZER_DISCONNECTED`
- `HOST_RECONNECTED`
- `ROOM_CLOSED`
- `ROOM_RESET`
- `ROOM_LOCK_STATUS`
- `GAME_STARTING`
- `QUESTION`
- `TIMER`
- `QUESTION_OVER`
- `PODIUM`

Quiz-specific:

- `ANSWER_COUNT`
- `ANSWER_RESULT`
- `POWER_UP_ACTIVATED`

WMLT-specific:

- `VOTE_COUNT`
- `VOTE_CONFIRMED`

Drawing-specific:

- `DRAW_OP`
- `GUESS_RESULT`
- `GUESS_ACCEPTED`
- `GUESS_LOG`

Spectator sync:

- `SPECTATOR_SYNC`

Organizer sync:

- `ORGANIZER_RECONNECTED`

## Quiz Gameplay

### Round Start

When `start_question()` runs for quiz:

1. Current round index increments.
2. Previous leaderboard is stored.
3. `answered_players` is cleared.
4. Per-question power-up state is cleared.
5. State becomes `QUESTION`.
6. The current question is broadcast without `answer_index`.
7. Timer starts after optional bonus splash delay.

Quiz `QUESTION` payload includes:

- `question`
- `question_number`
- `total_questions`
- `time_limit`
- `is_bonus`

### Answering

Players send `ANSWER` with `answer_index`.

Scoring:

- Correct answer base points are time-based: 100 to 1000.
- Bonus rounds double base points.
- Streak multipliers come from `STREAK_THRESHOLDS`.
- `double_points` power-up doubles awarded points once.
- Wrong answer resets streak and awards 0 points.

Power-ups:

- `double_points`: marks next correct answer for double points.
- `fifty_fifty`: removes up to two wrong options from the player view.

### Round End

Round ends when all active players answer or timer expires.

Server broadcasts `QUESTION_OVER`:

- `answer`
- `leaderboard`
- `previous_leaderboard`
- `is_final`

## WMLT Gameplay

### Start Constraint

WMLT requires at least `MIN_WMLT_PLAYERS` players.

### Round Start

When `start_question()` runs for WMLT:

1. Current round index increments.
2. Previous leaderboard is stored.
3. `answered_players` is cleared.
4. `votes` is cleared.
5. State becomes `QUESTION`.
6. Current statement and player list are broadcast.
7. Timer starts after optional bonus splash delay.

WMLT `QUESTION` payload includes:

- `statement`
- `question_number`
- `total_questions`
- `time_limit`
- `is_bonus`
- `game_type: "wmlt"`
- `players`

### Voting

Players send `VOTE` with `voted_for`.

Rules:

- Vote target must be an active or disconnected player nickname.
- Each player may vote once per round.
- The server tracks `room.votes` as `voter -> target`.
- The server sends `VOTE_CONFIRMED` to the voter.
- The organizer receives `VOTE_COUNT`.

### Round End

Round ends when all active players vote or timer expires.

Vote tally:

- Votes are tallied by target nickname.
- All players tied for the most votes are winners.
- Unanimous means one winner received all votes and more than one vote exists.

Scoring:

- Players who voted for a winner receive 500 base points.
- Bonus rounds double base points.
- Unanimous rounds add 200 points.
- Streak multipliers apply to repeated majority votes.
- Most-voted winners receive an additional 100 points if they are active players.
- Non-voters and voters outside the winning set lose streak.

Server broadcasts WMLT `QUESTION_OVER`:

- `game_type: "wmlt"`
- `statement`
- `votes`, hidden if `show_votes` is false.
- `round_podium`
- `winner`
- `winners`
- `winner_votes`
- `unanimous`
- `show_votes`
- `leaderboard`
- `previous_leaderboard`
- `is_final`
- `is_bonus`

### WMLT Superlatives

At podium time, WMLT may include:

- Most Likely To Everything
- Narcissist Award
- Mind Reader
- Most Controversial

Superlatives are calculated from `mlt_round_history`.

## Drawing Gameplay

### Start Constraint

Drawing requires at least `MIN_DRAWING_PLAYERS` players.

### Round Start

When `start_question()` runs for Drawing:

1. Current round index increments.
2. Previous leaderboard is stored.
3. `answered_players` is cleared.
4. `drawing_ops` and guess logs are cleared.
5. The next drawer is selected.
6. State becomes `QUESTION`.
7. The drawer receives the full prompt text and aliases.
8. Guessers and spectators receive safe public drawing state.
9. Timer starts after optional intro/splash delay.

Drawing `QUESTION` payload includes:

- `game_type: "drawing"`
- `drawing_prompt`, with hidden answer fields only for the drawer.
- `drawer`
- `drawing_ops`
- `question_number`
- `total_questions`
- `time_limit`
- `is_bonus`

### Drawing And Guessing

The drawer sends `DRAW_OP` messages. The backend rate-limits draw operations, trims sync payloads to `MAX_DRAW_OPS_PER_SYNC`, and broadcasts accepted operations to players and spectators.

Guessers send `GUESS` messages. The backend normalizes guesses against prompt text and aliases, confirms accepted guesses, and tracks correct guessers for the round.

### Round End

Round ends when the timer expires or the organizer advances.

Server broadcasts Drawing `QUESTION_OVER`:

- `game_type: "drawing"`
- `prompt`
- `drawer`
- `correct_guessers`
- `leaderboard`
- `previous_leaderboard`
- `is_final`
- `is_bonus`

## Frontend Organizer State Machine

Organizer states:

- `SELECT_GAME`
- `PROMPT`
- `QUIZ_VARIANT_PROMPT`
- `CUSTOM_QUIZ`
- `QUIZ_LIBRARY`
- `MLT_PROMPT`
- `DRAWING_PROMPT`
- `LOADING`
- `REVIEW`
- `MLT_REVIEW`
- `DRAWING_REVIEW`
- `GENERATING_IMAGES`
- `ROOM`
- `QUESTION`
- `LEADERBOARD`
- `PODIUM`

Game select:

- Host chooses from `frontend/src/gameModes.ts`.
- The standalone picker renders a responsive searchable catalog. Category filters are **All**, **Quiz/Trivia**, **Creative**, and **Bingo/Housie**; games with AI setup/generation are visually marked with a sparkle after the title.
- Quiz and quiz variants go through quiz prompt/review or custom quiz authoring.
- WMLT goes to `MLT_PROMPT` and `MLT_REVIEW`.
- Drawing goes to `DRAWING_PROMPT` and `DRAWING_REVIEW`.
- **My Quizzes** opens `QUIZ_LIBRARY`; starting a saved pack materializes it and enters normal review.
- Home/menu navigation must reset safely from setup, loading, review, library, and terminal states.
- Entering a new organizer state or switching game type must reset page scroll to the top so setup/review screens never open partially scrolled from the previous catalog or editor position.

Generation:

- Quiz calls `/quiz/generate`.
- WMLT calls `/mlt/generate`.
- Drawing calls `/drawing/generate`.
- Successful generation moves to review.
- Provider-picking UI is a local/gamma diagnostic affordance only. Production standalone and production backend-served surfaces must hide raw provider selectors such as "Google AI"; production still uses the configured backend/default provider and remote config.
- AI Quiz, quiz variants, and Drawing prompt screens must include a consistent back control positioned with the header/icon area so hosts can return to the game catalog without using the global menu.
- AI-generated setup screens must keep visible vertical separation between count selectors and the final generate action. The primary action should not visually attach to the last selector row.
- `402`, `429`, and `503` are surfaced in an error modal.
- In host-app party hub mode, prompt-list setup games such as WMLT and Drawing may call `/integrations/revelry/party-games/prompts/generate` with a party-scoped token. Generated prompts populate the editable setup form and are not persisted until the host saves the setup.

Review:

- Quiz and quiz-variant review use the shared `ReviewScreen`.
- Generated quiz-variant review titles should show the stable game name first, for example **Odd One Out**, and place the generated topic/theme, for example **Animal Kingdom**, in a smaller subtitle.
- The **Show Answers** toggle belongs with the lower review actions near room creation, not in the header.
- Player preview answer choices must use a stable badge/text grid with clear row boundaries so answer labels and copy align for every quiz-family game and wrap cleanly on mobile.
- When **Show Answers** is active, the review screen must make the state visible with an answer-key indicator, active toggle styling, and an unmistakable correct-answer row. It should be obvious even on mirrored host screens.
- Button groups, including **My Quizzes** empty/library footer actions, must keep visible spacing between adjacent buttons on desktop and mobile.
- WMLT and Drawing review should place timer/round controls before the editable content list and use the shared clock label and time preset styling.

Room creation:

- Calls `/room/create`.
- Sends `quiz_id`, `mlt_id`, or `drawing_id` based on `gameType`.
- Standalone review/setup components must invoke the room creation callback with no browser event argument, for example `onClick={() => onCreateRoom()}`. Passing `onClick={onCreateRoom}` is unsafe because React forwards the click event into the optional content override slot used by reset/play-again flows, which can prevent `/room/create` from being sent.
- Explicit content-id overrides are reserved for code-owned reset/play-again/materialized-content paths, never raw DOM events.
- Opens organizer WebSocket with `organizer=true`.
- Sends first-frame `AUTH`.

Game start:

- Plays start sound.
- Sends `SET_SHOW_VOTES` for WMLT.
- Sends `START_GAME`.
- Sends `NEXT_QUESTION`.

Round progression:

- Server `QUESTION` moves host to `QUESTION`.
- `ANSWER_COUNT` and `VOTE_COUNT` update progress.
- Drawing `DRAW_OP`, `GUESS_LOG`, and `GUESS_ACCEPTED` update live drawing/guess state.
- `QUESTION_OVER` moves host to `LEADERBOARD`.
- `PODIUM` moves host to final results.

Play again:

- The final results screen should expose two separate host actions across all game types.
- `Play Again` reuses the current content id, sends `RESET_ROOM`, keeps connected players in the same room, and returns the host to the lobby.
- `Choose Another Game` intentionally leaves the current content path. In standalone mode it returns to game select while keeping the room/socket available so the next content can reset the existing room. In host-app mode it returns to the party-scoped LocalPlay/Revelry Games hub instead of standalone game select.
- If no reusable content id/socket is available, `Play Again` may fall back to the same behavior as `Choose Another Game`.
- `RESET_ROOM` validates the content id, charges the room-start cost, clears round-specific state, and broadcasts `ROOM_RESET` so players return to lobby with the same room code.
- Dead socket cleanup is a shared room-lifecycle rule for all games. If `ROOM_RESET`, a lobby broadcast, a per-player runtime sync, or a drawing question broadcast discovers a dead player socket, the server removes that player and emits a corrected `PLAYER_LEFT` / `PLAYER_DISCONNECTED` roster update. The organizer's displayed player count must match the server roster used by start-game minimum-player checks.
- Before any minimum-player-gated game starts, the server probes/prunes dead player sockets and then evaluates the minimum-player rule. This applies to WMLT, Drawing, Housie, Bingo, and future games with player-count requirements.
- Revelry replacement starts must close the superseded runtime room and notify old sockets before exposing the newer session as the party's active game. Superseded/cancelled/expired sessions must not later be overwritten as completed by stale runtime callbacks.
- Durable Revelry session rows are not sufficient proof that a LocalPlay runtime room still exists. On party workspace resolve, launch-token mint/resolve, session status, and replacement checks, LocalPlay must reconcile `lobby` / `active` / `paused` sessions against the in-memory runtime room map. If the session points to a missing room after a deploy/restart or cleanup, mark it `expired`, set `joinable = false`, use `closed_reason = "runtime_unavailable"` when not simply past expiry, and stop presenting it as the party's active game. Hosts should then be able to start a fresh game without replacement confirmation.
- Bingo-family undo availability is server authoritative. `BINGO_SYNC`, `BINGO_CALL`, and claim broadcasts should expose `can_undo_last_call`; organizer UI disables Undo when false. Undo is allowed only while calling is active, at least one item has been called, and no accepted claim was validated at or after the latest call index. If Undo is performed while the auto-caller is running, the server pauses auto before rewinding the call.

## Frontend Player State Machine

Player states:

- `JOIN`
- `LOBBY`
- `QUESTION`
- `WAITING`
- `RESULT`
- `PODIUM`
- `RECONNECTING`
- `GAME_IN_PROGRESS`

Join:

- Player enters room code, nickname, optional team, and avatar.
- Session info is stored in `sessionStorage` under `localplay_session`.
- Saved sessions auto-rejoin after refresh.

Quiz round UI:

- Displays question text, optional image, timer, progress, answer options, streak, bonus, and power-ups.
- Sends `ANSWER`.
- Waits for `ANSWER_RESULT`.

WMLT round UI:

- Displays statement, timer, and player voting grid.
- Sends `VOTE`.
- Waits for `VOTE_CONFIRMED`.

Drawing round UI:

- Current drawer sees the secret prompt and drawing canvas.
- Guessers see the live canvas, guess input, and accepted guess feedback.
- Sends `DRAW_OP` from the drawer and `GUESS` from guessers.
- Spectator/TV shows public canvas, drawer, timer, and safe round state.

Results:

- Quiz result shows correctness, points, rank, and leaderboard.
- WMLT result shows winner(s), vote count, majority feedback, and vote podium.
- Drawing result shows prompt, drawer, correct guessers, points, rank, and leaderboard.

Podium:

- Shows final rankings and team rankings.
- Shows WMLT superlatives when present.
- Waits for host to reset/start another game.

## Token Economy

Spark costs:

- Generate content: `COST_GENERATE`, currently 1 spark.
- Start a game: `COST_ROOM`, currently 10 sparks.

Bonuses and packs:

- Signup bonus: `SIGNUP_BONUS_TOKENS`, currently 20.
- Daily bonus: `DAILY_BONUS_TOKENS`, currently 10.
- Paid token pack: `TOKEN_PACK_AMOUNT`, currently 110.

Billing:

- Stripe Checkout is used for web purchases.
- Native iOS requests are blocked from Stripe checkout and directed to in-app purchase.
- Stripe webhook events are deduplicated in SQLite.

Important behavior:

- Generation endpoints preflight-check balance, but generated content is charged only when it first becomes playable through `/room/create` or a room reset. If room creation/reset fails, no generation spark is taken.
- Room creation is otherwise free.
- Game start and room reset charge room-start sparks.
- iOS native clients are blocked from Stripe checkout by `/checkout/create`; native iOS purchases are expected to use in-app purchase paths when implemented.

### Historical Monetization Context

Older docs describe an entitlement-based "Party Pass" model with free-game counters and premium JWTs. The current codebase has moved to the spark/token economy:

- `backend/tokens.py` is active.
- `frontend/src/hooks/useTokenBalance.ts` is active.
- `rollback_economy.md` describes reverting from token economy back to entitlement economy and should be treated as an emergency rollback note, not the current product model.
- `docs/monetization_plan.md` contains useful historical design rationale around idempotency, platform headers, kill switches, SQLite persistence, and native-store compliance, but its entitlement state machine is not the current implementation.

## Security And Sanitization

Input sanitization:

- User prompts strip control characters and HTML tags.
- Prompt validators reject common prompt-injection phrases.
- Nicknames and team names strip HTML tags and control characters.
- LLM output strips HTML tags and control characters.

Prompt injection defense:

- User topics/themes are wrapped in boundary markers.
- System prompts state that user text is subject matter only, not instructions.

LLM output defense:

- JSON is parsed and structurally validated.
- User-visible generated text is sanitized and length-capped.
- Gemini thought parts are filtered.
- `<think>` and `<thinking>` blocks are stripped.

WebSocket defense:

- Organizer auth token required.
- Message size limit.
- Per-client message rate limit.
- Origin validation.
- Session tokens protect nickname ownership.

Ownership:

- Generated content is associated with wallet id.
- Mutating and exporting content requires ownership.

## Authentication And Persistence

Current auth support exists in `backend/auth.py`, `backend/db.py`, and `backend/main.py`.

Current behavior:

- `POST /auth/signin` accepts provider, id token, and device id.
- Supported providers are `google` and `apple`.
- `GET /auth/me` returns the current signed-in user and token status.
- Sign-in migrates in-memory game history entries from the device wallet id to the signed-in user id.
- Token/wallet status is resolved through the current spark economy.

Historical context:

- `docs/auth_persistence_plan.md` describes the intended Phase 2 identity model using provider subject id rather than email.
- Parts of that document refer to the older entitlement/free-tier model and should not be treated as current code behavior.
- The durable architectural idea is still relevant: provider `sub` is the stable identity key, email is display-only, and cross-device recovery depends on authenticated user identity.

## Testing

Testing commands are documented in `README.md` and the Makefile.

Common commands:

- `make test`: backend unit and integration tests (excludes e2e and websocket integration).
- `make test-e2e`: end-to-end tests that call live LLM generation. These tests still use an `@requires_ollama` skip guard, so local Ollama must be running even if generation is configured to use another provider.
- `make test-all`: all tests.
- `make lint`: frontend TypeScript type check.
- `make build`: frontend production build.
- `cd frontend && npm run test:e2e`: Playwright UX/regression coverage for organizer, player, spectator/TV, custom quiz authoring, saved quiz library, and Revelry party hub surfaces.
- `cd frontend && npm test -- --run ...`: targeted Vitest component/unit coverage.

The backend test suite includes API validation, game logic, WebSocket flows, power-ups, reconnection, bonus rounds, team leaderboard, token economy, auth, and thinking-leak defense. The exact count may drift over time.

Launch-readiness checks should include:

- Desktop and mobile screenshots of the standalone game catalog, menu, each setup/review flow, lobby, player join, and TV/spectator entry.
- Saved quiz library flow: list, start, prepare copy, review, Home return, edit, delete.
- Host-app flow: party hub, create game, save setup, start saved game, replacement confirmation, lobby, player join, completion, return.
- Host-app callback mirror flow: save or update party-scoped quiz, WMLT, and Drawing content; verify `content.created` / `content.updated` safe `payload.content` can update the prepared-games mirror even if follow-up metadata fetch fails.
- Service worker/API check: `/quiz-packs`, `/media`, `/catalog`, `/integrations`, and game API routes return API responses, not cached HTML.

## Native / Capacitor

The frontend includes Capacitor/iOS scaffolding.

Known notes:

- `frontend/ios/App/CapApp-SPM/README.md` is generated Capacitor Swift Package Manager scaffolding and says not to modify it manually.
- Native iOS checkout must avoid Stripe and use in-app purchase paths.
- The organizer page adjusts join URL generation when running under Capacitor.
- Historical plans mention secure storage for native device/session tokens; current code should be checked before relying on a specific native storage implementation.

## Current Boundaries And Constraints

The platform intentionally does not have a plugin system or generic game engine.

Current extensibility pattern:

- Add a generation engine per game.
- Add REST endpoints under a namespaced prefix.
- Add storage and ownership for that game content.
- Extend room creation by `game_type`.
- Add WebSocket branches in `socket_manager.py`.
- Add frontend game type, prompt/review screens, player round UI, and organizer result UI.

Known pressure points:

- `socket_manager.py` contains both shared infrastructure and game-specific rules.
- `Room.quiz` is a generic content field despite the quiz-specific name.
- `current_question_index`, `QUESTION`, `QUESTION_OVER`, and related message names are reused for non-quiz games.
- In-memory generated content and in-memory game history do not survive backend restarts.
- Adding many games by direct branching will make socket and page state machines increasingly large.

These are current design facts, not necessarily defects. They should guide any upgrade plan.

## Known Residual Backlog

Historical review notes were consolidated into this section and the platform spec. Items here are not necessarily urgent, but they are useful checks when touching nearby code.

- **Auth error specificity:** `/auth/signin` currently returns `401 Invalid or expired ID token` for several backend failures, including missing `JWT_SECRET`. Split provider-token verification failures from LocalPlay session creation/config failures so the UI and logs point to the real cause.
- **Sign-in wallet merge verification:** A newly signed-in gamma user showed `0 sparks`. Verify whether guest sparks should merge into the signed-in wallet in all flows, including existing-user re-sign-in and repeated merge rejection paths.
- **Signed-in balance refresh:** After sign-in, confirm the header spark balance refreshes from the signed-in session and does not keep stale guest-wallet state.
- **Show answers control:** The organizer/player "show answers" UI currently appears to do nothing. Trace the intended answer-reveal state, WebSocket message, and client rendering path, then add regression coverage.
- **Apple web sign-in regression coverage:** Apple sign-in has been verified on gamma and the IONOS production frontend. Manual smoke coverage is documented in `DEPLOY.md`; add browser automation later if we can provide stable test account/session handling for provider popups.
- **Provider sign-in diagnostics:** Add a narrow admin/debug view or structured log event for sign-in attempts that reports provider, origin, audience, verification stage, and sanitized failure reason without logging tokens.
- **Auth config startup checks:** Startup currently warns on short `JWT_SECRET`, but missing `JWT_SECRET` is fatal for sign-in. Add a deployment/startup warning that explicitly says Google/Apple sign-in is disabled when `JWT_SECRET`, `GOOGLE_CLIENT_ID`, or Apple audience config is absent.
- **LocalPlay/Revelry session boundary:** Document and test that LocalPlay sessions are independent from the main Revelry app even if Google Cloud/Firebase infrastructure is shared.
- **Google OAuth branding:** Google currently shows the main Revelry OAuth app name during sign-in because the web client lives in the main `revelryapp` Google Cloud project. If the user-facing label must say "Revelry Games" without changing the main Revelry app name, create a separate Google Cloud project/OAuth brand for Revelry Games and move the LocalPlay web client there.
- **Ephemeral generated content strategy:** Decide whether generated quiz/WMLT content should remain process-memory only, be temporarily persisted with a short TTL, or be stored another way. This is about restart/multi-instance resilience, not a product requirement to save every generated quiz forever. Do not implement long-term generated-content storage until retention, cleanup, ownership, and user-facing value are clear.
- **Spectator lifecycle:** `SpectatorPage` has reconnect/backoff handling and cleanup guards, but spectator reconnect behavior should be regression-tested when changing room join/leave UI. In particular, verify reconnect still works after manually leaving one spectator room and joining another in the same mounted page.
- **Spectator/player client-id collision:** Spectators and players use different client id prefixes, so real collisions are unlikely. Still, room cleanup paths should avoid assuming a `client_id` can only ever belong to one connection map.
- **Reset-room tests:** Older tests once sent `RESET_ROOM` with inline `quiz_data`; current backend expects a valid `content_id`. Keep reset-room tests aligned with the content-id flow.
- **Remote config announcement shape:** Historical review notes called out partial normalization of announcement entries. If remote config banners are expanded, normalize `type`, `dismissible`, and defaults explicitly.
- **Quick play polish:** Add one-tap quick play for games that can start from default/template content, especially Drawing and WMLT. Current setup-first behavior is safer, but too slow for some live party moments.
- **TV/cast polish:** Chromecast support is fragile as a primary user story. Use one shared game link with a clear **Join to Play** / **Join to Watch** choice, keep `/tv/{room_code}` as a reliable typed-TV fallback, and add a host-facing helper that opens/copies the spectator watch URL before platform casting. Browser Cast/Screen Mirroring mirrors the current tab, so hosts should cast the watch tab, not the organizer controls. Backlog first-class Chromecast/Google Cast, Apple TV/AirPlay, and platform receiver support as native-cast enhancements rather than the only TV path.
- **Result sharing polish:** Add shareable result cards/thumbnails and a "one more round" path from completed games.
- **Late join policy:** Decide and implement per-game late-join behavior after a game starts: spectate, join with missed-round penalty, or block until next round.
- **Push notifications:** Current PWA prompt only requests browser permission. Add real push subscriptions, notification preferences, and event triggers for game-start/result-ready after the product copy and native/web ownership are settled.

## Upgrade Backlog

### Hosting Strategy

LocalPlay currently fits a single-server deployment best.

Decision:

- Keep LocalPlay on a server for now.
- Do not move to Cloud Run or another autoscaled multi-instance platform until traffic or ops needs justify the state-management work.

Rationale:

- Active rooms live in process memory through `socket_manager.rooms`.
- WebSocket connection objects live in process memory.
- Generated quiz/WMLT content is stored in process memory.
- Game history is currently in process memory.
- Reconnect behavior assumes the room still exists on the same backend process.
- This architecture is simple and appropriate while LocalPlay is still expanding its game catalog and gameplay loops.

Cloud Run notes for later:

- Cloud Run supports WebSockets.
- WebSockets are treated as long-running HTTP requests and are subject to Cloud Run request timeouts.
- Cloud Run can scale to multiple instances, but LocalPlay's current in-memory room model is not safe across instances.
- Session affinity may reduce reconnect issues, but it should not be treated as a correctness guarantee.
- A first Cloud Run deployment could work with `min-instances=1`, `max-instances=1`, and a long request timeout, but that would mostly reproduce the single-server model with different ops tradeoffs.

Required work before multi-instance hosting:

- Decide the generated game content strategy: process memory only, temporary TTL persistence, or another shared active-content store.
- Decide whether completed game history has product value. Persist it only if needed for user history, analytics, support, or multi-instance correctness.
- Decide where live room state belongs, likely Redis/Memorystore, Firestore, Cloud SQL, or another shared store.
- Add a broadcast/routing strategy for WebSocket events if one room can span instances.
- Make reconnect safe when a client lands on a different backend instance.
- Revisit cleanup semantics so room TTL and organizer disconnect cleanup work across instances.
- Add deployment tests for reconnects, room creation, game start, and podium flow under instance restarts.

Recommended migration order:

1. Keep the current server deployment while adding games.
2. Decide whether generated content and completed game history need temporary persistence, long-term persistence, or no persistence.
3. Externalize live room state only when multi-instance scaling is actually needed.
4. Add shared pub/sub or room routing for WebSocket fanout.
5. Move to autoscaled infrastructure after the state model is no longer process-local.

### Backend-Served SPA Status

Repo implementation and VM rollout are complete:

- `frontend/src/config.ts` supports empty `VITE_API_URL` for same-origin API and WebSocket traffic.
- `backend/main.py` conditionally serves the SPA when a frontend build is present and remains API-only when it is absent.
- `backend/Dockerfile` includes a `static/` directory in the image.
- `scripts/deploy-gcp.sh --with-frontend` builds and packages `frontend/dist` into the backend image.
- `scripts/deploy-gcp.sh --gamma --with-frontend` targets a separate gamma container, VM port, env file, and data directory.
- `scripts/deploy-gcp.sh --bootstrap-vm --skip-build` creates `/home/revelry-games`, env files, and prod/gamma data and backup directories.
- The deploy script builds images with `--platform linux/amd64` for the AMD64 GCP VM.
- Backend tests cover root behavior, SPA fallback, API 404 protection, missing static assets, and path traversal.
- The frontend service worker must bypass backend API prefixes in same-origin builds, including `/quiz-packs`, `/media`, `/catalog`, `/integrations`, `/drawing`, and the core game/auth/payment prefixes. API requests must never be fulfilled with cached SPA HTML.

Current deployed infrastructure:

- `gamesapi.revelryapp.me` proxies to `games-backend` on `127.0.0.1:8000`.
- `gamesapi-gamma.revelryapp.me` proxies to `games-backend-gamma` on `127.0.0.1:8004`.
- Both containers are deployed with the backend-served SPA bundle.
- `/home/revelry-games/app/.env` is production env; `/home/revelry-games/app/.env.gamma` is gamma env.
- Production data lives in `/home/revelry-games/revelry-data`; gamma data lives in `/home/revelry-games/revelry-data-gamma`.
- Production env should include `TRUST_PROXY_HEADERS=true`, `https://gamesapi.revelryapp.me`, the IONOS PWA origin, and the native/local origins the app can launch from: `capacitor://localhost`, `http://localhost`, `https://localhost`, `http://localhost:9200`, and `http://127.0.0.1:9200`.
- Gamma env should include `CHECKOUT_RETURN_URL=https://gamesapi-gamma.revelryapp.me/`, `TRUST_PROXY_HEADERS=true`, gamma origin plus local dev origins in `ALLOWED_ORIGINS`, and test Stripe keys before checkout testing.
- AI model defaults can be overridden by both VM env and remote `config.json`. Keep `GEMINI_MODEL=gemini-2.5-flash-lite`, `GEMINI_PREMIUM_MODEL=gemini-2.5-flash-lite`, production `REMOTE_CONFIG_URL=https://games.revelryapp.me/config.json`, and gamma `REMOTE_CONFIG_URL=https://gamesapi-gamma.revelryapp.me/config.json`. Free and premium generation intentionally use the same Flash Lite model.
- Prod and gamma envs must set a strong `JWT_SECRET`; provider sign-in can verify a valid Google/Apple token but still fail if the backend cannot mint the app session JWT.
- Prod and gamma envs must set the browser auth client IDs used for backend token verification: `GOOGLE_CLIENT_ID=458966837298-9hjencou1ag2o17ln06iuuj86j5p8igj.apps.googleusercontent.com`, `APPLE_CLIENT_ID=me.revelryapp.quiz.web`, and `APPLE_CLIENT_IDS=me.revelryapp.quiz.web,me.revelryapp.quiz`.
- Google OAuth Web Client authorized JavaScript origins must include every SPA host: `https://games.revelryapp.me`, `https://gamesapi.revelryapp.me`, `https://gamesapi-gamma.revelryapp.me`, `http://localhost:5173`, `http://localhost:9200`, and `http://127.0.0.1:9200`.
- Apple Sign in with Apple Service ID `me.revelryapp.quiz.web` must allow `games.revelryapp.me`, `gamesapi.revelryapp.me`, and `gamesapi-gamma.revelryapp.me` with matching `https://...` return URLs.
- Browser sign-in is direct Google Identity Services / Apple Sign-In, not Firebase Auth. The provider returns an ID token, the LocalPlay backend verifies it, and the backend mints a LocalPlay session JWT.
- A successful signed-in state is visible in the menu as **Signed in**, account/email prefix, and a **Sign Out** button.
- LocalPlay sessions are independent from the main Revelry app session even if Google Cloud/Firebase project infrastructure is shared.
- Verified browser sign-in: Google on gamma; Apple on gamma and IONOS production. Production Google is configured on the IONOS bundle and production backend and should be manually smoke-tested after auth/OAuth changes.

### PWA Prompts And Updates

The frontend is installable as a PWA and registers `frontend/public/sw.js` from `frontend/index.html`.

Implemented behavior:

- The service worker bypasses all API prefixes and known backend API hostnames. It caches static app assets and the offline fallback only.
- Host-app/iframe surfaces skip service-worker registration. Standalone surfaces register `sw.js` from the app root, derived from the manifest path, so nested routes do not accidentally request a route-relative service-worker URL and receive cached SPA HTML.
- New service-worker installs wait rather than taking over immediately. The app receives a `localplay-sw-update` event and shows a **New version ready** prompt.
- Choosing **Refresh** posts `SKIP_WAITING` to the waiting worker and reloads after `controllerchange`.
- Standalone web surfaces can show an install prompt when the browser fires `beforeinstallprompt`.
- Standalone web surfaces can show a notification opt-in prompt. The browser permission dialog is only requested after the user taps **Enable**.
- Revelry/host-app surfaces suppress install and notification prompts because Revelry is the party shell. They may still show update prompts so stale game code can be refreshed.
- Prompt dismissals are stored in localStorage and should remain lightweight; do not use them for security state.

Product rules:

- Do not interrupt active rounds with forced reloads. The update prompt copy should encourage refreshing between rounds.
- Do not ask for notification permission on first paint. Ask only through a user-facing LocalPlay prompt.
- Notification permission by itself is not a push subscription. Real game-start/result notifications need a later push-subscription backend and host-app/native strategy.
- Installed PWAs still use the origin from which they were installed; auth, CORS, remote config, and service-worker bypass rules must include backend-served prod/gamma origins and the IONOS origin as applicable.

Operational follow-up:

- Keep IONOS as the public production frontend unless a later product/deployment decision changes the URL strategy.
- For every backend deploy, use `./scripts/deploy-gcp.sh --with-frontend` for production and `./scripts/deploy-gcp.sh --gamma --with-frontend` for gamma unless intentionally testing API-only mode.
- After deploys, run `make test-remote-prod` or `make test-remote-gamma`. These cover `/health`, provider/config, SPA root, auth guards, iOS checkout guard, live generation, idempotent retry, and token balance. Manually smoke Google/Apple browser sign-in and Stripe checkout as described in `DEPLOY.md`.

### Product Boundary

LocalPlay is a separate app/platform. It may later integrate with Revelry accounts or let Revelry users launch and play LocalPlay games, but the current system should be treated as LocalPlay first.

Backlog:

- Clean up docs and user-facing labels that imply LocalPlay and Revelry are the same product.
- Keep legacy deployment/package names documented where they are real operational facts.
- Keep the Revelry integration boundary aligned with `SPEC-REVELRY-INTEGRATION.md`: Revelry is launcher/pointer/results surface; LocalPlay owns authoring, media, lobby, gameplay, and results.

## Markdown Document Currentness

The repository contains several Markdown files with different freshness levels:

- `SPEC.md`: current baseline spec for the codebase as inspected.
- `README.md`: broadly useful for quick start, feature list, project structure, and test commands; branding and provider defaults may be older.
- `DEPLOY.md`: useful production deployment reference. It is operationally specific and should be verified before executing commands.
- Historical `REVIEW_STATUS_TABLE_2026-03-21.md`: reviewed and consolidated into `SPEC.md`; the standalone scratch file is not required.
- `rollback_economy.md`: emergency rollback note from token economy back to entitlement economy. Not current product behavior.
- `docs/monetization_plan.md`: historical monetization architecture for an entitlement/party-pass model. Useful for rationale, but not the current economy.
- `docs/auth_persistence_plan.md`: historical auth plan. Useful identity guidance, but some entitlement references are stale.
- `frontend/README.md`: default Vite template README, not project-specific.
- `frontend/ios/App/CapApp-SPM/README.md`: generated Capacitor note, not project architecture.
