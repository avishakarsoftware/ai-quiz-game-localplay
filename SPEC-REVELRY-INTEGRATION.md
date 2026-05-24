# LocalPlay Revelry Integration Spec

Status: Gamma bridge plus party-scoped quiz authoring implemented; production hardening remains

Last updated: 2026-05-23

## Purpose

This document is the LocalPlay-side contract for integrating with the separate Revelry app.

Revelry's app-side integration plan lives in:

`/Users/Avi/Desktop/dev/antigravity/revelryapp/SPEC-LOCALPLAY-INTEGRATION.md`

`SPEC-PLATFORM.md` remains the broad LocalPlay platform strategy. This spec is narrower: the concrete LocalPlay work needed so Revelry can launch, embed, and summarize LocalPlay games without copying game logic into Revelry.

## Boundary

LocalPlay owns:

- game catalog metadata
- game setup and AI content generation
- game sessions and live room runtime
- party-scoped host-app game workspace surfaces such as "Revelry Games"
- WebSockets, reconnects, timers, scoring, and results
- standalone LocalPlay host/player UX
- embeddable launch routes for trusted host apps

Revelry owns:

- party identity and lifecycle
- host/cohost/helper/guest roles
- party membership, RSVP, guest list, and display names
- Games tab UX, party-scoped entry links, and launch authorization
- party-scoped entitlement/payment decisions
- displaying, mirroring, and posting completed result summaries

The bridge owns:

- signed handoff validation
- creating/resuming a LocalPlay session from external context
- returning tokenless launch routes
- opening a party-scoped LocalPlay "Revelry Games" hub
- synchronizing safe prepared-game/session/result metadata
- delivering lifecycle/result callbacks back to Revelry for feed/memory updates
- exposing normalized result summaries
- iframe/open-in-new-tab compatibility

Product framing: Revelry is ingress into a LocalPlay party-scoped game area. It can show mirrored cards and entry points, but authoring, room creation, lobby, gameplay, and results execution happen inside LocalPlay surfaces opened with Revelry party context.

## Current LocalPlay State

LocalPlay still uses the existing room runtime internally:

```text
POST /room/create
WS   /ws/{room_code}/{client_id}
```

`POST /room/create` returns a `room_code` and `organizer_token`. The organizer token is a live control credential and must not be exposed in guest URLs or stored in Revelry as a durable launch URL.

The Revelry bridge is implemented on gamma on top of that runtime:

```text
GET  /catalog?host_app=revelry
POST /integrations/revelry/sessions
POST /integrations/revelry/sessions/{session_id}/launch-token
GET  /integrations/revelry/sessions/{session_id}
GET  /integrations/revelry/sessions/{session_id}/results
POST /integrations/revelry/party-games-link
GET  /integrations/revelry/party-games/resolve
GET  /integrations/revelry/party-workspace
POST /integrations/revelry/party-games/authoring-link
POST /integrations/revelry/party-games/start
POST /integrations/revelry/content/authoring-link
GET  /integrations/revelry/content/authoring-token/resolve
POST /integrations/revelry/content
GET  /integrations/revelry/content/{content_id}
PUT  /integrations/revelry/content/{content_id}
GET  /sessions/{session_id}/organizer
GET  /sessions/{session_id}/join
GET  /sessions/{session_id}/spectate
GET  /revelry/games
GET  /revelry/author
```

Current limitations and follow-up work:

- rooms live in process memory
- participant persistence remains deferred; session metadata is durable
- quiz-only LocalPlay-hosted authoring/content APIs are implemented by reusing durable quiz-pack storage scoped to `revelry:party:{external_container_id}`
- the party-scoped "Revelry Games" hub is implemented for list/create/edit/start quiz flows
- host-app launch chrome is hidden on `/revelry/*` and tokenized/embedded organizer/player/spectator launch URLs; deeper brand-specific polish remains iterative
- organizer gameplay renders the live WebSocket `QUESTION` payload, because Revelry-launched organizer sessions may not have the original quiz object in browser state
- host-app media upload paths sanitize synthetic owner ids such as `revelry:party:{party_id}` before signing IONOS paths; raw colons or other unsafe wallet characters must never appear in `storage_path`
- callbacks are best-effort signed HTTP delivery when `REVELRY_CALLBACK_URL` is configured; polling remains the recovery path
- result summaries exist but should be hardened as richer game variants are added

## Phase Plan

### Phase 0: Safe MVP Bridge

Goal: let Revelry prove the Games tab flow without baking LocalPlay internals into Revelry.

Minimum LocalPlay work:

1. Add the generic durable `game_sessions` slice needed for integration state; defer participant persistence until gameplay identity needs it.
2. Add `GET /catalog?host_app=revelry` with launchability metadata.
3. Add origin/frame allowlist for Revelry hosts.
4. Add stable embeddable launch routes that do not expose long-lived organizer credentials.
5. Add a short-lived launch token exchange for organizer/player/spectator scope.
6. Add a service-only endpoint that wraps current room creation and writes the durable session record.
7. Enforce one active game per `host_app` + `external_container_id`, with host-confirmed replacement.
8. Return a normalized response with `session_id`, `room_code`, `launch_routes`, joinability state, and a safe feed-card payload.
9. Add a polling status/result endpoint with safe result summaries.
10. Add a party-scoped "Revelry Games" hub link and workspace sync endpoint so Revelry and LocalPlay show the same prepared games, active session, and results for a party.

Phase 0 may still run gameplay in the existing in-memory `Room`, but the external contract should talk about `session_id`, not raw room internals. Durable session records are required for status polling, friendly expired/superseded states, one-active-game enforcement, and result summaries.

### Phase 1: Session-First Integration

Goal: make LocalPlay sessions first-class product objects.

Add:

- persistent `GameSession` table/model
- `/integrations/revelry/sessions`
- `/sessions/{session_id}`
- `/sessions/{session_id}/organizer`
- `/sessions/{session_id}/join`
- `/sessions/{session_id}/spectate`
- `/integrations/revelry/sessions/{session_id}/results`
- normalized result persistence
- optional `postMessage` bridge events

### Later

- expanded catalog metadata backed by server configuration/content
- party-aware recommendations
- multi-brand copy/style hints
- multi-instance realtime state if traffic requires it

## LocalPlay API Contract

### Generic Host-App Contract

LocalPlay integrations should use a generic host-app model internally. Revelry is adapter one.

The API may expose Revelry-specific routes for MVP:

```text
POST /integrations/revelry/party-games-link
GET  /integrations/revelry/party-workspace
POST /integrations/revelry/sessions
```

Core persisted records and service code should use generic fields:

- `host_app`
- `external_container_type`
- `external_container_id`
- `external_container_title`
- `external_user_id`
- `external_guest_id`
- `display_name`
- `avatar_url`
- `role`
- `capabilities`
- `return_url`

This keeps LocalPlay reusable for future apps without changing gameplay code. For Revelry, `external_container_type` is usually `party` and `external_container_id` is the Revelry party id.

### Create Revelry Session

```text
POST /integrations/revelry/sessions
Authorization: Bearer <service token or signed handoff token>
```

Request:

```json
{
  "handoff_token": "jwt",
  "game_type": "quiz",
  "settings": {
    "time_limit": 30,
    "vibe": "party"
  },
  "replace_session_id": "previous_lp_session_uuid_or_null",
  "replacement_confirmed": false,
  "external_context": {
    "host_app": "revelry",
    "external_container_type": "party",
    "external_container_id": "party_uuid",
    "external_container_title": "Ava's Birthday",
    "party_type": "birthday",
    "brand_key": "revelry",
    "host_user_id": "revelry_user_uuid",
    "return_url": "https://app.revelryapp.me/parties/party_uuid"
  },
  "actor": {
    "external_user_id": "revelry_user_uuid",
    "external_guest_id": null,
    "display_name": "Avi",
    "avatar_url": "https://media.revelryapp.me/avatar.jpg",
    "role": "host",
    "capabilities": ["manage_games", "operate_game", "moderate_players"]
  }
}
```

Response:

```json
{
  "session_id": "lp_session_uuid",
  "room_code": "ABC123",
  "status": "lobby",
  "joinable": true,
  "feed_card": {
    "title": "Birthday Quiz",
    "body": "Ava started a LocalPlay quiz.",
    "action_label": "Join game"
  },
  "launch_routes": {
    "organizer": {
      "url": "https://gamesapi.revelryapp.me/sessions/lp_session_uuid/organizer?embed=1",
      "path": "/sessions/lp_session_uuid/organizer",
      "scope": "organizer"
    },
    "player": {
      "url": "https://gamesapi.revelryapp.me/sessions/lp_session_uuid/join",
      "path": "/sessions/lp_session_uuid/join",
      "scope": "player"
    },
    "spectator": {
      "url": "https://gamesapi.revelryapp.me/sessions/lp_session_uuid/spectate",
      "path": "/sessions/lp_session_uuid/spectate",
      "scope": "spectator"
    }
  },
  "expires_at": "2026-05-22T01:00:00Z"
}
```

Rules:

- Validate handoff before creating organizer-capable sessions.
- Do not return raw `organizer_token`.
- Return stable tokenless launch routes that can be iframe-embedded or opened externally.
- Short-lived `launch_token` values may be returned or minted separately for immediate launch, but external apps must not persist tokenized URLs.
- Enforce one active LocalPlay session per host-app/container context.
- If the host already has an active LocalPlay session for the same container, Revelry should warn the host before requesting a replacement session.
- Replacement requests must use `replace_session_id` plus `replacement_confirmed = true`.
- `replace_session_id` is a LocalPlay `session_id`; host-app adapters that expose their own session ids must resolve them before calling LocalPlay.
- When the host confirms replacement, LocalPlay must create the replacement first and only then mark `replace_session_id` as `superseded`, or perform both changes atomically.
- Failed replacement creation must not close or supersede the existing active session.
- If LocalPlay cannot create a session, return a structured error.
- `launch_routes` includes absolute `url` values for immediate use and may include stable `path` values for persistence; external apps should treat `path` + `scope` as the canonical persisted metadata when available.

Suggested error codes:

```text
invalid_handoff
expired_handoff
forbidden_scope
unsupported_game_type
payment_required
service_unavailable
```

If an active session already exists and replacement is not confirmed, return a structured conflict:

```json
{
  "error": "active_session_exists",
  "active_session_id": "lp_existing_session_uuid",
  "message": "A LocalPlay game is already active for this party."
}
```

### Session Lifecycle

Revelry hosts should be able to run only one active LocalPlay game at a time per party context. Generic host-app integrations should apply the same rule per `host_app` + `external_container_id`. This keeps room codes, embedded frames, result summaries, and guest links from drifting apart.

Lifecycle rules:

- `lobby`, `active`, and `paused` sessions count as active.
- Starting a new game for the same `host_app`, `external_container_id`, and managing actor requires confirmation from the managing host/cohost in the launching surface, whether that surface is Revelry or the LocalPlay party hub.
- After confirmation, the launching surface calls create session with replacement intent; LocalPlay creates the replacement first and only then marks the previous active session `superseded` and closes its organizer/player/spectator launch routes.
- If replacement creation fails, the previous active session remains active and joinable.
- Superseded sessions should return a friendly closed-game state, not a generic 404.
- Expired sessions should return clear UI copy, for example: "This game expired. Ask the host to start a new one."
- Cancelled or superseded sessions are no longer joinable and should not be selected by result polling unless explicitly requested.
- Completed sessions keep their result summaries attached to the Revelry party, but are no longer joinable.
- Abandoned Revelry-created lobby sessions remain joinable for 4 hours.
- Live sessions expire after 2 idle hours with no activity.
- Host/cohost can relaunch a fresh session from the same game setup when the game type supports it.

### Launch Routes

```text
GET /sessions/{session_id}/organizer?embed=1&launch_token=...
GET /sessions/{session_id}/join?embed=1&launch_token=...
GET /sessions/{session_id}/spectate?embed=1&launch_token=...
```

Route behavior:

- `organizer` requires organizer scope.
- `join` requires player scope or falls back to fast nickname entry if the session permits it.
- `spectate` requires spectator scope or a session-level spectator setting.
- Tokenless player/spectator routes are intentionally allowed for MVP when the caller already has the unguessable LocalPlay `session_id`, matching the existing "anyone with the room code can join" model. Revelry may still wrap these routes with its own URLs and mint player/spectator launch tokens on open.
- `embed=1` hides standalone marketing/app chrome and keeps only gameplay controls.
- `return_url` may be accepted for native/browser escape hatches.

Long-lived control credentials must not live in URLs. A URL launch token should be short-lived, preferably one-time use, and exchangeable for a LocalPlay runtime session token.
Organizer launch URLs are privileged because an organizer-scoped launch token can be exchanged for the room `organizer_token`; never put organizer launch URLs in feed cards, guest-visible pages, logs, or durable storage.

Persistence rules:

- Revelry should persist `session_id`, LocalPlay route type, and non-secret launch route metadata.
- Revelry should not persist URLs that include `launch_token`.
- Feed cards should use tokenless join/open routes or Revelry-owned URLs that mint a fresh launch token before redirecting/opening LocalPlay.
- If an iframe or external view is opened after the initial token expires, Revelry should call the launch-token endpoint again.
- Expired launch tokens must not close active gameplay after LocalPlay has exchanged them for runtime credentials.

### Launch Token Exchange

```text
POST /integrations/revelry/sessions/{session_id}/launch-token
Authorization: Bearer <service token or signed handoff token>
```

Request:

```json
{
  "scope": "player",
  "route": "join",
  "embed": true,
  "return_url": "https://app.revelryapp.me/party/party_uuid?tab=games",
  "guest_join_url": "https://app.revelryapp.me/party/party_uuid/games/join"
}
```

Response:

```json
{
  "launch_url": "https://gamesapi.revelryapp.me/sessions/lp_session_uuid/join?embed=1&launch_token=...",
  "launch_token_expires_at": "2026-05-22T00:05:00Z"
}
```

Rules:

- `scope` must be one of `organizer`, `player`, or `spectator`.
- `route` must match the requested scope: `organizer`, `join`, or `spectate`.
- `embed` controls whether `embed=1` is added to the returned URL.
- `return_url` is optional and must be validated against allowed Revelry origins before being reflected into a URL.
- `guest_join_url` is optional and is carried inside the launch token's `launch_context.display` for host-app organizer/spectator UI. Use this when Revelry wants LocalPlay to show a party-safe QR code on the lobby or TV surface.
- The returned `launch_url` is a just-in-time artifact and must not be persisted.
- `launch_token_expires_at` is LocalPlay's canonical response field; host-app wrapper APIs may rename it, but adapters must map it explicitly.
- The launch token should be short-lived and preferably one-time use.

### Session Status

```text
GET /integrations/revelry/sessions/{session_id}
Authorization: Bearer <service token>
```

Response:

```json
{
  "session_id": "lp_session_uuid",
  "room_code": "ABC123",
  "status": "active",
  "joinable": true,
  "closed_reason": null,
  "closed_message": null,
  "superseded_by_session_id": null,
  "launch_routes": {
    "organizer": {
      "url": "https://gamesapi.revelryapp.me/sessions/lp_session_uuid/organizer?embed=1",
      "path": "/sessions/lp_session_uuid/organizer",
      "scope": "organizer"
    },
    "player": {
      "url": "https://gamesapi.revelryapp.me/sessions/lp_session_uuid/join",
      "path": "/sessions/lp_session_uuid/join",
      "scope": "player"
    },
    "spectator": {
      "url": "https://gamesapi.revelryapp.me/sessions/lp_session_uuid/spectate",
      "path": "/sessions/lp_session_uuid/spectate",
      "scope": "spectator"
    }
  },
  "created_at": "2026-05-22T00:00:00Z",
  "started_at": "2026-05-22T00:10:00Z",
  "completed_at": null,
  "expires_at": "2026-05-22T04:00:00Z",
  "last_activity_at": "2026-05-22T00:15:00Z"
}
```

Status values:

```text
lobby
active
paused
complete
expired
cancelled
superseded
```

Closed sessions should return `joinable = false`, a stable `closed_reason`, and friendly `closed_message` suitable for organizer/player/spectator launch routes.
`completed_at` is LocalPlay's canonical completion timestamp; host apps should persist or explicitly map it in their own session records.
`last_activity_at`, `closed_reason`, and `closed_message` should be treated as first-class status metadata by external adapters.

### Result Summary

```text
GET /integrations/revelry/sessions/{session_id}/results
Authorization: Bearer <service token>
```

Response:

```json
{
  "session_id": "lp_session_uuid",
  "room_code": "ABC123",
  "status": "complete",
  "game_type": "quiz",
  "title": "Birthday Quiz",
  "custom_quiz_title": "Ava Trivia",
  "thumbnail_url": "https://gamesmedia.revelryapp.me/prod/custom-quiz/asset_uuid.jpg",
  "summary": "Ava won with 8 correct answers.",
  "feed_card": {
    "title": "Birthday Quiz results",
    "body": "Ava won with 8 correct answers.",
    "thumbnail_url": "https://gamesmedia.revelryapp.me/prod/custom-quiz/asset_uuid.jpg"
  },
  "players": [
    {
      "display_name": "Ava",
      "rank": 1,
      "score": 800,
      "highlights": ["fastest answer streak"]
    }
  ],
  "highlights": [
    "The final round changed the leaderboard."
  ],
  "completed_at": "2026-05-22T00:00:00Z"
}
```

Privacy rules:

- Do not expose raw per-question answers by default.
- Do not expose sensitive prompt text by default.
- Do not expose full custom quiz contents by default.
- Include image references only when they are public LocalPlay media URLs that are safe for party recap use.
- Keep the response suitable for host-approved feed/memory posting.
- Revelry decides whether to post the summary.

### Feed Integration

Revelry may use LocalPlay session metadata to create party feed cards. The feed is a Revelry product surface; LocalPlay provides canonical game state, tokenless launch routes, and summary payloads.

Feed rules:

- When a game starts, Revelry can add a party feed card with a join/open action using a Revelry-owned URL that mints or refreshes a LocalPlay launch token on demand.
- LocalPlay may suggest feed card text and an `action_label`, but Revelry owns the persisted `action_url`.
- Feed cards must not store or expose URLs containing `launch_token`.
- While a game is in `lobby` or `active`, feed cards should show a join/open action only if the session is still joinable.
- When a game is completed, Revelry can add or update a feed card with final results from the LocalPlay result summary.
- Cancelled, expired, or superseded games should not show a primary join action; they may show neutral copy such as "Game closed" or "Game expired".
- Host/cohost approval is required before posting a richer memory/feed recap that includes custom quiz images, generated highlights, or more detailed player results.
- Result feed cards should include only game type, game title, custom quiz title, top results, safe highlights, and optional safe public thumbnail/image references by default.
- LocalPlay should not decide final feed visibility. Revelry controls whether a card is party-only, host-only draft, or externally shareable.

### Catalog

LocalPlay should expose catalog metadata as part of the MVP so host apps do not hardcode stale game availability.

```text
GET /catalog?host_app=revelry
```

Response:

```json
{
  "games": [
    {
      "id": "quiz",
      "title": "AI Quiz",
      "short_description": "Generate a custom trivia game for your guests.",
      "category": "trivia",
      "min_players": 2,
      "max_players": 50,
      "estimated_minutes": 15,
      "thumbnail_url": "https://gamesmedia.revelryapp.me/prod/catalog/quiz.jpg",
      "supports_ai_generation": true,
      "supports_custom_content": true,
      "supports_manual_authoring": true,
      "supports_images": true,
      "supports_embed": true,
      "requires_content": true,
      "default_content_available": true,
      "embedded_authoring_supported": true,
      "min_questions": 3,
      "max_questions": 20,
      "supported_media": ["image/png", "image/jpeg", "image/webp"],
      "content_schema": {
        "type": "quiz",
        "question_types": ["multiple_choice", "true_false"],
        "supports_question_images": true
      },
      "config_schema": {
        "time_limit": {"min": 5, "max": 60, "default": 15}
      },
      "launchable": true,
      "status": "live",
      "party_types": ["birthday", "baby_shower", "wedding", "house_party"]
    }
  ]
}
```

Rules:

- Revelry should use the catalog to render available LocalPlay games.
- Catalog entries may define different defaults by game. Drawing Game uses `config_schema.time_limit.default = 30` and LocalPlay selects black as the initial drawing brush color. Revelry should pass an explicit `time_limit` only when the host changes it; otherwise LocalPlay applies the game-specific default.
- LocalPlay still validates every launch request server-side; catalog metadata is not authorization.
- Gamma and production catalogs may differ.
- `host_app` may filter availability, copy, thumbnails, and launchability.
- Status values may include `live`, `gamma`, `planned`, and `disabled`.
- Revelry should only enable launch actions for games where `launchable = true`.
- The Revelry-launched LocalPlay UI must only expose games returned as `launchable = true` for `GET /catalog?host_app=revelry`.
- If a quiz variant such as Rebus, Timeline, or Odd One Out should appear in Revelry, it must first be represented in the bridge contract with catalog metadata, accepted `game_type` or mode validation, content/session creation semantics, launch-token handling, status, and result summary support.
- Games not represented in the bridge contract must be hidden in Revelry-launched host-app mode even if they are available in standalone LocalPlay.
- Backlog games such as Bingo, Baby Bingo, and Housie may appear as `planned` if Revelry wants to show coming-soon cards.

### LocalPlay-Hosted Authoring And Play

Canonical product model: Revelry is the party launcher, pointer store, and result surface; LocalPlay is the game app. Revelry opens LocalPlay for authoring, lobby, gameplay, media upload, scoring, and results. Desktop may present LocalPlay in an iframe when it works well, but the contract must also work as fullscreen/open-external web and native app links/deep links.

LocalPlay owns game/content authoring, but when launched from Revelry or another host app the authoring UI must run in host-app-aware mode.

Principles:

- The standalone LocalPlay UI may be reused, but it must be constrained by the host app context, catalog response, actor capabilities, and authoring/session scope.
- Host-app authoring must not create standalone-only content that cannot be attached to a Revelry prepared setup or Revelry-managed session.
- Host-app authoring must not expose games or variants that are absent from `GET /catalog?host_app=revelry` or marked `launchable = false`.
- Host-app authoring must hide standalone LocalPlay navigation, login prompts, spark balances, spark paywalls, and unrelated account/library surfaces unless the host app explicitly launches a standalone LocalPlay flow.
- Content created from a Revelry launch is scoped to `host_app`, `external_container_id`, and the author/actor identity. Standalone LocalPlay content and host-app-scoped content must not be silently interchangeable.
- Custom quiz images remain in LocalPlay/IONOS media storage and are referenced by LocalPlay media asset ids or public LocalPlay media URLs.
- Result summaries may include custom quiz title and safe thumbnail, but not full quiz contents by default.
- Revelry stores pointer metadata only: prepared setup id, party id, LocalPlay `content_id`, LocalPlay `session_id`, title, safe thumbnail, question count, status, and result summary. Revelry must not store questions, answers, options, raw prompts, full media paths, or full game payloads.

#### Content Authoring API

Implementation endpoints:

```text
POST /integrations/revelry/content/authoring-link
POST /integrations/revelry/party-games/authoring-link
GET  /integrations/revelry/content/authoring-token/resolve
POST /integrations/revelry/content
GET  /integrations/revelry/content/{content_id}
PUT  /integrations/revelry/content/{content_id}
DELETE /integrations/revelry/content/{content_id}
DELETE /integrations/revelry/party-games/content/{content_id}
```

`POST /integrations/revelry/content/authoring-link` mints an edit-only token and URL for the LocalPlay-hosted authoring surface. LocalPlay is the only service that mints the browser `authoring_token`; Revelry calls this endpoint with service credentials and must not construct token-bearing LocalPlay authoring URLs itself.

Request:

```json
{
  "external_context": {
    "host_app": "revelry",
    "external_container_type": "party",
    "external_container_id": "party_uuid",
    "external_container_title": "Ava's Birthday",
    "party_type": "birthday",
    "brand_key": "revelry",
    "cover_image_url": "https://media.revelryapp.me/parties/party_uuid/cover.jpg",
    "accent_color": "#ff4f9a",
    "guest_join_url": "https://app.revelryapp.me/party/party_uuid/games/join"
  },
  "actor": {
    "external_user_id": "revelry_user_uuid",
    "display_name": "Avi",
    "role": "host",
    "capabilities": ["manage_games", "author_content"]
  },
  "game_type": "quiz",
  "draft_id": "revelry_prepared_setup_uuid_or_client_uuid",
  "content_id": "lp_content_uuid_when_editing",
  "return_url": "https://app.revelryapp.me/party/party_uuid?tab=games",
  "mode": "create"
}
```

Response:

```json
{
  "authoring_url": "https://gamesapi.revelryapp.me/revelry/author?authoring_token=...",
  "authoring_token_expires_at": "2026-05-23T21:00:00Z",
  "localplay_content_id": "lp_content_uuid_when_editing",
  "launch_context": {
    "mode": "host_app",
    "host_app": "revelry",
    "surface": "content_authoring"
  }
}
```

Rules:

- Requires service authorization from Revelry.
- Actor must include `author_content` or `manage_games`.
- `return_url` must match the allowlist for Revelry web, universal/app-link hosts, or explicitly allowed custom schemes.
- `draft_id` is stable across reopen/retry and is used for autosave recovery.
- `mode` is `create`, `edit`, or `duplicate`; `mode = edit` should include the existing `content_id` / `localplay_content_id`. Editing locked/used content must create a new version/content id.
- Token lifetime is 60 minutes. The authoring UI may refresh it through the same service-backed flow while the host remains active.
- The response must not include the shared integration secret. Browser clients receive only the short-lived LocalPlay `authoring_token` embedded in `authoring_url`.

When the user is already inside the LocalPlay party hub, the browser uses the validated LocalPlay `party_games_token` instead of a Revelry service credential:

```text
POST /integrations/revelry/party-games/authoring-link
```

```json
{
  "party_games_token": "...",
  "game_type": "quiz",
  "mode": "edit",
  "content_id": "lp_content_uuid"
}
```

This endpoint applies the same capability checks (`author_content` or `manage_games`) and returns the same `authoring_url` response shape. It exists so the LocalPlay hub can create/edit party-scoped content without exposing the Revelry shared secret to the browser.

`POST /integrations/revelry/content` request:

```json
{
  "external_context": {
    "host_app": "revelry",
    "external_container_type": "party",
    "external_container_id": "party_uuid",
    "external_container_title": "Ava's Birthday"
  },
  "actor": {
    "external_user_id": "revelry_user_uuid",
    "display_name": "Avi",
    "role": "host",
    "capabilities": ["manage_games", "author_content", "operate_game"]
  },
  "game_type": "quiz",
  "title": "Ava's Birthday Quiz",
  "content_id": "lp_content_uuid_when_editing",
  "content_payload": {
    "quiz": {
      "quiz_title": "Ava's Birthday Quiz",
      "questions": [
        {
          "id": 1,
          "text": "Where did Ava go to college?",
          "options": ["UCLA", "NYU", "UT Austin", "UW"],
          "answer_index": 2,
          "image_prompt": "",
          "image_url": "https://media.revelryapp.me/apps/localplay/gamma/...",
          "image_alt": "Ava wearing a graduation cap"
        }
      ]
    }
  }
}
```

Response:

```json
{
  "localplay_content_id": "lp_content_uuid",
  "content": {
    "localplay_content_id": "lp_content_uuid",
    "game_type": "quiz",
    "title": "Ava's Birthday Quiz",
    "status": "ready",
    "question_count": 10,
    "thumbnail_url": "https://media.revelryapp.me/apps/localplay/gamma/...",
    "updated_at": "2026-05-23T20:00:00Z",
    "action_requirements": {
      "start": ["operate_game"],
      "edit": ["author_content"],
      "delete": ["manage_games"]
    }
  },
  "workspace": {}
}
```

Rules:

- Server-to-server content API calls require the same service authorization model as session APIs.
- Browser-based authoring must not receive the shared integration secret. MVP uses a short-lived LocalPlay authoring token minted for the active actor, party container, game type, and optional draft/setup id.
- Browser authoring calls use the authoring token, not the Revelry service secret.
- LocalPlay validates `game_type` against the host-app catalog before accepting content.
- LocalPlay validates the payload against the catalog `content_schema` or `config_schema`.
- `image_url` and related media identifiers are LocalPlay internal/runtime fields. Embedded and standalone authoring UI must show image upload, preview, replace, remove, and alt text controls instead of asking hosts to paste or edit IONOS paths, CDN URLs, `/media` paths, asset ids, or storage backend names.
- LocalPlay stores host-app content ownership metadata so session creation can enforce same-container or allowed-author access.
- Revelry must use LocalPlay APIs for authoring and media; it must not write LocalPlay quiz, content, or media tables directly.
- Content create/update requests should eventually include an idempotency key or stable `draft_id` so browser refreshes, mobile webview reloads, and upload retries can recover without duplicating partial games. Current implementation relies on `content_id` for edit idempotency and the editor's local draft for unsaved create recovery.
- `GET /integrations/revelry/content/{content_id}` returns safe metadata by default. The LocalPlay authoring UI may request `include_payload=true` using an authoring token to load the full quiz for editing; Revelry should not persist that full payload.
- `DELETE /integrations/revelry/content/{content_id}` soft-deletes host-app-scoped content when called with service auth plus `external_container_id`, or with an authoring token scoped to the content.
- `DELETE /integrations/revelry/party-games/content/{content_id}` soft-deletes party-scoped content from the LocalPlay Revelry Games hub using `party_games_token`; the actor must have `manage_games`.
- Host-app content deletion sends a signed `content.deleted` callback with `status = deleted_by_host`, `content_id`, and top-level host-app/container context.
- Content statuses: `draft`, `ready`, `locked`, `deleted_by_host`, `expired`, `archived`.
- Validation errors use `422 invalid_content` with field paths such as `questions[2].options`.
- Duplicate idempotency keys returning the original response and stale update-version `409 edit_conflict` handling are backlog hardening items.
- AI-assisted authoring may use `source = ai` and include prompt/theme metadata, but it still returns a stable `content_id` before room creation.
- Manual custom quiz authoring should remain free because comparable products commonly include it. LocalPlay may monetize long-term saving/retention, larger libraries, larger media quotas, premium templates, AI assist, advanced branding, analytics, or cross-event reuse outside the Revelry-managed gameplay path.

LocalPlay persistence requirements:

- Store drafts/content in LocalPlay-owned tables, not Revelry tables. Current quiz implementation reuses `quiz_packs` / `quiz_questions` with owner wallet id `revelry:party:{external_container_id}`. A generic host-app content table should be added when additional editable game types need payloads that no longer fit the quiz-pack schema.
- Current required persisted fields for quiz content are `id`, `owner_wallet_id`, `title`, `status`, `question_count`, `deleted_at`, `created_at`, `updated_at`, and question rows. Future generic content should add `host_app`, `external_container_type`, `external_container_id`, `created_by_external_user_id`, `game_type`, `thumbnail_asset_id`, `draft_id`, `source`, `payload_version`, `locked_at`, `used_at`, `retention_expires_at`, and safe `metadata`.
- Required draft fields: `draft_id`, `host_app`, `external_container_id`, `actor_external_user_id`, `game_type`, `payload`, `autosave_version`, `editing_lock_actor_id`, `editing_lock_expires_at`, `expires_at`, `created_at`, and `updated_at`.
- Drafts expire 7 days after last edit. Saved party-scoped content expires 30 days after party end, or party start plus 48 hours plus 30 days when no end time exists.
- When content is used to start a session, set `used_at` / `locked_at`; future edits must duplicate/version rather than mutate that content id.
- Media asset rows must record content/draft ownership so unused draft images can be marked orphaned and cleaned up asynchronously.
- Retention cleanup should run as a scheduled LocalPlay job. For the current quiz-pack implementation, the job should soft-delete expired `revelry:party:{party_id}` quiz packs, mark expired drafts as `expired`, and enqueue orphaned IONOS media cleanup. Until the scheduled job exists, expired content remains hidden by UI/status rules but may remain in storage.

Common error responses:

```text
400 invalid_request
401 invalid_or_expired_authoring_token
403 insufficient_capability
404 content_not_found
409 edit_conflict
409 content_locked
410 content_expired
422 invalid_content
429 rate_limited
```

#### Session Creation With Authored Content

Revelry should create a session from authored content by passing:

```json
{
  "game_type": "quiz",
  "settings": {
    "content_id": "lp_content_uuid",
    "time_limit": 20
  },
  "external_context": {
    "host_app": "revelry",
    "external_container_id": "party_uuid"
  }
}
```

LocalPlay must validate:

- `content_id` exists and is `ready`.
- `content_id` belongs to the same `host_app` and compatible `external_container_id`, or the actor has an explicit capability to reuse it across containers.
- `game_type` on the session matches the authored content.
- The game is still `launchable` for `host_app = revelry`.
- The content payload can materialize a runtime room for the requested game type.

Avoid a path where a host creates content in embedded LocalPlay and then cannot create or attach a Revelry-managed room from it.

#### LocalPlay-Hosted Authoring Flow

MVP decision: manual quiz authoring happens before LocalPlay session creation in a LocalPlay-hosted authoring surface. Creating/editing prepared content does not close an active game. Revelry checks for an active LocalPlay session and shows the replacement warning only when the host taps Start on a prepared setup.

The preferred MVP flow is:

```text
Host opens Revelry Games tab
  -> Revelry fetches GET /api/games/catalog
  -> Host chooses a launchable catalog game
  -> Revelry opens LocalPlay-hosted authoring route with an authoring token and return_url
  -> Host creates/manual-edits/AI-generates content
  -> LocalPlay saves party-scoped content and redirects to return_url with localplay_content_id
  -> Revelry stores or updates a prepared game setup pointer
  -> Later, host taps Start on the prepared setup
  -> Revelry checks active session and gets replacement confirmation if needed
  -> Revelry creates the LocalPlay session with settings.content_id and replacement intent if needed
  -> Organizer launch token opens the normal LocalPlay lobby
```

Do not use the existing organizer route for pre-session authoring, because organizer launch currently requires a `session_id`. Add a separate content-authoring launch route such as:

```text
GET /revelry/author?authoring_token=...
```

The authoring token is only for editing. It lasts 60 minutes. Expiry does not delete saved content or affect gameplay; if the token expires during editing, LocalPlay asks the host to reopen from Revelry/the party hub. Token refresh and server-side draft recovery are backlog hardening items.

The authoring route must accept a validated `return_url`. When content is ready, LocalPlay redirects back with a compact handoff using canonical `localplay_content_id`, plus `game_type` and optional `prepared_setup_id`/`draft_id`. For native apps, Revelry should prefer universal/app links and may use a custom scheme fallback. LocalPlay must allowlist return origins/schemes, and Revelry must validate the returned `localplay_content_id` server-side before creating a session.

Canonical return shape:

```text
{return_url}&localplay_content_id=lp_content_uuid&game_type=quiz&draft_id=...&status=ready
```

`localplay_content_id` is the canonical return parameter. Do not use `content_id` in new return URLs; a temporary alias may be accepted only for backward compatibility during rollout.

If authoring is cancelled:

```text
{return_url}&draft_id=...&status=cancelled
```

The redirect must not include full content payloads, tokens, media paths, answers, or organizer credentials.

Native compatibility requirements:

- Revelry should pass universal/app-link `return_url` values where possible, for example `https://app.revelryapp.me/party/{party_id}?tab=games`.
- Custom schemes such as `revelry://party/{party_id}/games` may be supported as fallback, but must be allowlisted explicitly.
- LocalPlay authoring and launch URLs should be safe to open in a system browser, in-app browser, or Capacitor-style webview.
- Return handoff parameters are hints only. Revelry must verify party membership and fetch/validate LocalPlay content/session metadata server-side before storing pointers or starting a session.
- If an app link opens the Revelry native app after authoring, the app should resume the Games tab, refresh prepared setups from Revelry backend, and avoid trusting URL parameters as authoritative state.

Alternative later: create a non-joinable `setup`/`draft` session first, then author inside that session before opening player routes. That path requires session status, launch routes, replacement semantics, and cleanup rules for `setup` sessions; do not mix it into the MVP unless deliberately chosen.

For quick-start games with safe default content, LocalPlay may still create a lobby immediately.

#### Prepared Game Setups

Prepared game setups are Revelry-owned pointer records for LocalPlay content that can be started later. They let a host prepare one or more quizzes before the party without creating a live LocalPlay room.

Rules:

- Multiple prepared games are allowed per party.
- Only one active LocalPlay session is allowed per party at a time.
- Prepared games are visible only to host/cohost until started.
- Host/cohost can create, edit, delete, and start prepared games. Guests cannot author or start games.
- Revelry may show prepared game cards with two separate primary launch intents: **Start** and **Edit/Open**. Both are deep-link/open-in-LocalPlay actions from the user's perspective. Start asks LocalPlay to create or open the room from `settings.content_id` and then opens the LocalPlay organizer/lobby; Edit/Open uses the authoring-link API with `mode = edit` and opens LocalPlay authoring.
- Helpers remain view-only for MVP unless Revelry explicitly grants authoring capabilities later.
- Prepared content is party-scoped for MVP. A `content_id` created for one Revelry party cannot start a session in another party.
- Once a `content_id` has been used to start a session, it becomes immutable. Editing after use creates a new `content_id` or version, and Revelry updates the prepared setup pointer after save.
- Draft autosave survives 7 days since last edit.
- Free saved party content survives until 30 days after party end. If party end is unknown, use party start plus 48 hours, then 30 days.
- Deleting a prepared setup in Revelry detaches/hides the pointer and asks LocalPlay to mark the content `deleted_by_host`; IONOS media deletion happens asynchronously after a grace period.
- Images for expired/deleted drafts/content are marked orphaned/expired first and deleted later by cleanup. Completed game recap media should remain available through the result-retention window.
- MVP media limits: one image per question, 20 questions max, 5 MB per image, PNG/JPEG/WebP.
- Manual authoring ships first. AI assist may use the same LocalPlay-hosted surface later.

Suggested Revelry pointer fields:

```text
prepared_setup_id
party_id
game_type
localplay_content_id
title
thumbnail_url
question_count
status                  # draft, ready, locked, deleted_by_host, expired, archived
created_by
updated_by
created_at
updated_at
last_used_at
metadata jsonb          # safe display hints only
```

#### Party-Scoped "Revelry Games" Hub

When a user clicks a generic LocalPlay/Games entry point from Revelry, LocalPlay must not open the standalone LocalPlay catalog. It should open a party-scoped "Revelry Games" hub for the current `host_app = revelry` and `external_container_id`.

The hub is a LocalPlay-owned surface backed by the same party context as the Revelry Games tab. Revelry is ingress into this area and may mirror safe metadata, but LocalPlay owns the actual authoring/start/lobby/gameplay surfaces. The hub should show the party title, return action, active game state, prepared/saved party games, draft games, recent results, and the launchable catalog for that party. It should hide standalone LocalPlay navigation, sparks, wallet balances, paywalls, account prompts, unrelated libraries, and games not returned as launchable by the Revelry catalog.

Service endpoint to mint the hub link:

```text
POST /integrations/revelry/party-games-link
```

Request:

```json
{
  "external_context": {
    "host_app": "revelry",
    "external_container_type": "party",
    "external_container_id": "party_uuid",
    "external_container_title": "Ava's Birthday",
    "party_type": "birthday",
    "brand_key": "revelry"
  },
  "actor": {
    "external_user_id": "revelry_user_uuid",
    "display_name": "Avi",
    "role": "host",
    "capabilities": ["manage_games", "author_content", "operate_game"]
  },
  "return_url": "https://app.revelryapp.me/party/party_uuid?tab=games",
  "guest_join_url": "https://app.revelryapp.me/party/party_uuid/games/join",
  "preferred_display": "fullscreen",
  "display": {
    "link_label": "Open Ava's Birthday Games Hub on Revelry Games",
    "container_label": "Ava's Birthday",
    "container_image_url": "https://media.revelryapp.me/parties/party_uuid/cover.jpg",
    "accent_color": "#ff4f9a",
    "guest_join_url": "https://app.revelryapp.me/party/party_uuid/games/join",
    "guest_join_label": "Scan to join Ava's Birthday",
    "return_label": "Back to Revelry"
  }
}
```

Response:

```json
{
  "party_games_url": "https://gamesapi.revelryapp.me/integrations/revelry/games?party_games_token=...",
  "party_games_token_expires_at": "2026-05-23T21:00:00Z",
  "return_url": "https://app.revelryapp.me/party/party_uuid?tab=games",
  "display": {
    "link_label": "Open Ava's Birthday Games Hub on Revelry Games",
    "container_label": "Ava's Birthday",
    "container_image_url": "https://media.revelryapp.me/parties/party_uuid/cover.jpg",
    "accent_color": "#ff4f9a",
    "guest_join_url": "https://app.revelryapp.me/party/party_uuid/games/join",
    "guest_join_label": "Scan to join Ava's Birthday",
    "return_label": "Back to Revelry"
  }
}
```

Rules:

- Requires service authorization from Revelry. Browser/native clients must never receive the shared integration secret.
- The `party_games_token` is a short-lived exchange token. After exchange, LocalPlay issues a session-scoped runtime credential for the hub, authoring, and start actions.
- `guest_join_url` is optional but recommended for party/TV flows. It must be a Revelry-owned web URL, universal/app link, or allowed custom scheme that lets guests join or open the party's active game from Revelry. LocalPlay may render this URL as a QR code in host-app organizer/spectator surfaces; it must not replace authorization checks.
- `display.guest_join_url` overrides `external_context.guest_join_url` for presentation. `guest_join_label` is display copy only.
- LocalPlay validates `guest_join_url` with the same allowlist rules as `return_url`.
- The token must carry the normalized host-app launch context, actor capabilities, allowlisted `return_url`, and display policy.
- Party imagery/metadata in `display` is safe presentation context only. LocalPlay may use it for headers/cards, but Revelry remains authoritative for private party details.
- If the token expires before exchange, LocalPlay shows "Open this from Revelry again." Expiry after exchange must not interrupt authoring, lobby, or gameplay while runtime credentials remain valid.

LocalPlay hub route:

```text
GET /integrations/revelry/games?party_games_token=...
```

Expected hub behavior:

- Host/cohost sees prepared content for the party, including drafts, ready games, locked/used games, expired items when useful for recovery, and recent completed sessions.
- Guests see only active/joinable games and completed summaries that Revelry/LocalPlay mark visible to party members.
- Host/cohost can create, edit, delete, and start party-scoped games directly inside LocalPlay when granted `author_content` and/or `operate_game`.
- The primary hub entry can be labeled like "Open Ava's Birthday Games Hub on Revelry Games" and should use party-safe cover art/metadata when provided.
- Starting from the LocalPlay hub follows the same rules as starting from the Revelry Games tab: validate `settings.content_id`, enforce one active session per party, warn before replacement in the surface where Start was tapped, create the replacement before superseding the old session, and return safe launch/result metadata.
- Any game created in the hub remains party-scoped and must be visible later from the Revelry Games tab after sync. Do not save it only to a standalone LocalPlay library.
- Clicking a saved game without choosing Start should open the LocalPlay authoring/details surface for that party-scoped content, not create a live room.
- Host/cohost card actions must stay distinct, but both are LocalPlay launches from the user's perspective:
  - **Start** asks LocalPlay to materialize or open a room/session from `settings.content_id`, then deep-links/opens the organizer/lobby route.
  - **Edit/Open** mints an authoring link with `mode = edit` and the existing `localplay_content_id`, then deep-links/opens the LocalPlay authoring route.

Workspace sync endpoint for Revelry:

```text
GET /integrations/revelry/party-workspace?external_container_type=party&external_container_id=party_uuid
```

This service-authorized endpoint returns safe metadata only:

```json
{
  "external_context": {
    "host_app": "revelry",
    "external_container_type": "party",
    "external_container_id": "party_uuid",
    "external_container_title": "Ava's Birthday"
  },
  "catalog": [{ "game_id": "quiz", "launchable": true }],
  "prepared_content": [
    {
      "localplay_content_id": "lp_content_uuid",
      "game_type": "quiz",
      "title": "Ava's Birthday Quiz",
      "status": "ready",
      "thumbnail_url": "https://gamesmedia.revelryapp.me/gamma/...",
      "question_count": 12,
      "created_by": "revelry_user_uuid",
      "updated_at": "2026-05-23T20:45:00Z",
      "last_used_at": null,
      "action_requirements": {
        "start": ["operate_game"],
        "edit": ["author_content"],
        "delete": ["manage_games"]
      }
    }
  ],
  "active_session": null,
  "recent_results": []
}
```

Sync and callback rules:

- Revelry may call this endpoint when the Games tab opens, after returning from LocalPlay, after app resume, and after a LocalPlay hub start/edit action.
- Revelry stores or updates pointer metadata only. It must not store questions, answers, options, raw prompts, media paths, or full LocalPlay payloads.
- `party-workspace` is a service-level party snapshot, not an actor-personalized authorization response. It may include `action_requirements`, but Revelry must derive actor-specific `can_start`, `can_edit`, and `can_delete` from current party membership, role, and capabilities before rendering controls.
- LocalPlay should send signed callbacks for important changes so Revelry can update feed cards, prepared game cards, active-session state, and result summaries without waiting for user refresh. Polling/refresh remains the consistency fallback.
- Conflicts are resolved by LocalPlay content/session timestamps. Revelry should treat its prepared setup records as a mirror of LocalPlay party content, not as the authority for game internals.

### Revelry Callback Delivery

LocalPlay should support a service-to-service callback/webhook mechanism for Revelry. This is how a game played mostly inside LocalPlay still updates the Revelry party feed, Games tab, memories, and notifications.

Callback endpoint owned by Revelry:

```text
POST {revelry_callback_url}
```

LocalPlay receives the callback URL in integration configuration or session creation metadata. For security, prefer a configured allowlisted URL per environment rather than accepting arbitrary callback URLs from the browser.

Event envelope:

```json
{
  "event_id": "lp_evt_uuid",
  "event_type": "game.completed",
  "occurred_at": "2026-05-23T21:30:00Z",
  "host_app": "revelry",
  "external_container_type": "party",
  "external_container_id": "party_uuid",
  "session_id": "lp_session_uuid",
  "content_id": "lp_content_uuid",
  "idempotency_key": "game.completed:lp_session_uuid:v1",
  "payload": {
    "status": "complete",
    "result_summary": {}
  }
}
```

Recommended event types:

- `content.created`
- `content.updated`
- `content.deleted`
- `game.session_created`
- `game.started`
- `game.completed`
- `game.cancelled`
- `game.expired`
- `game.superseded`

Rules:

- Current implementation sends callbacks only when `REVELRY_CALLBACK_URL` is configured. `content.created` / `content.updated` / `content.deleted`, `game.session_created`, and `game.superseded` are sent from the API path; `game.started` and `game.completed` are sent from the room runtime. Cancellation/expiration callbacks are emitted when those state transitions happen.
- `occurred_at` must be an ISO 8601 UTC string ending in `Z`. Do not send Unix seconds in new LocalPlay callback code.
- Callbacks are signed with `REVELRY_INTEGRATION_SECRET`, the canonical shared Revelry integration secret. `REVELRY_CALLBACK_SECRET` may exist only as a temporary rotation alias or compatibility fallback and must not silently diverge from `REVELRY_INTEGRATION_SECRET` in normal gamma/prod configuration.
- LocalPlay signs `HMAC_SHA256("${timestamp}.${raw_body}")` and sends `X-LocalPlay-Event-Id`, `X-LocalPlay-Timestamp`, and `X-LocalPlay-Signature: sha256=...`; Revelry should reject replays and dedupe by event id.
- Callback payloads must contain safe metadata only. Do not include full quiz contents, answers, raw prompts, private media paths, organizer credentials, launch tokens, or participant secrets.
- Revelry owns whether to post feed/memory entries automatically, as drafts, or only after host approval.
- LocalPlay does best-effort delivery in the current implementation. It retries transient delivery failures, including Revelry HTTP `429` rate-limit responses and `5xx` errors, with short bounded backoff while preserving the same `event_id`, `idempotency_key`, and raw body for the retry attempt. Durable queued retry with long backoff remains backlog hardening; Revelry should poll `party-workspace` or session results on page open/app resume to recover missed callbacks.
- Callback failures must not block gameplay completion. They affect sync latency only.

## Handoff Token

Revelry should mint a short-lived signed JWT. LocalPlay validates it. LocalPlay should never use the Revelry app JWT directly as a runtime credential.

Suggested claims:

```json
{
  "iss": "revelry",
  "aud": "localplay",
  "typ": "localplay_launch",
  "jti": "uuid",
  "host_app": "revelry",
  "external_container_type": "party",
  "external_container_id": "party_uuid",
  "external_container_title": "Ava's Birthday",
  "brand_key": "revelry",
  "party_type": "birthday",
  "external_user_id": "uuid-or-null",
  "external_guest_id": "uuid-or-null",
  "display_name": "Avi",
  "avatar_url": "https://media.revelryapp.me/avatar.jpg",
  "role": "host",
  "capabilities": ["manage_games", "operate_game", "moderate_players"],
  "scope": "organizer",
  "game_type": "quiz",
  "return_url": "https://app.revelryapp.me/party/party_uuid?tab=games",
  "iat": 1770000000,
  "exp": 1770000600
}
```

Validation requirements:

- signature valid
- `iss = revelry`
- `aud = localplay`
- `typ = localplay_launch`
- `exp` is in the future
- `scope` matches the requested launch route
- required claims: `iss`, `aud`, `typ`, `jti`, `host_app`, `external_container_type`, `external_container_id`, `display_name`, `role`, `scope`, `capabilities`, `iat`, and `exp`
- optional context claims: `external_container_title`, `brand_key`, `party_type`, `external_user_id`, `external_guest_id`, `avatar_url`, `game_type`, and `return_url`
- sensitive host/cohost actions require explicit capabilities, not only role labels
- `jti` is checked for replay when practical

Secrets:

- Revelry owns `LOCALPLAY_INTEGRATION_SECRET` or the private signing key used to mint handoff tokens.
- LocalPlay owns `REVELRY_INTEGRATION_SECRET` or the public verification key used to validate Revelry handoff tokens.
- If symmetric HMAC is used, the two env vars contain the same secret value in their respective services.
- Keep prod and gamma secrets separate.
- Do not log full handoff tokens, launch tokens, organizer tokens, or service tokens.

Billing:

- Sessions created through `/integrations/revelry/sessions` use LocalPlay internal `billing_mode = host_app_managed`.
- Host-app-managed sessions must not grant LocalPlay signup bonuses to integration wallets.
- Host-app-managed sessions must not debit LocalPlay sparks or show LocalPlay spark/paywall prompts at game start.
- This is internal LocalPlay behavior and does not require a Revelry request-field change for Phase 0.

## External Context

Store only the context LocalPlay needs:

```json
{
  "host_app": "revelry",
  "external_container_type": "party",
  "external_container_id": "party_uuid",
  "external_container_title": "Ava's Birthday",
  "party_type": "birthday",
  "brand_key": "revelry",
  "host_user_id": "revelry_user_uuid",
  "return_url": "https://app.revelryapp.me/parties/party_uuid"
}
```

Do not duplicate Revelry's party model. Do not pass guest lists, contacts, invite metadata, private party notes, payment/subscription data, or broader profile data that LocalPlay does not need. Use external context for:

- launch/result correlation
- debugging
- party-aware copy or game recommendations
- result summary handoff

## Identity and Permissions

LocalPlay stores identity as session participant metadata. It should not build a global Revelry profile table or merge people across parties.

Identity rules:

- Logged-in users may include an opaque `external_user_id`.
- Anonymous guests may include an opaque `external_guest_id` or receive only a session-scoped `local_participant_id`.
- Gameplay state keys off `session_id` and `local_participant_id`.
- `external_container_id` scopes membership, host controls, feed cards, and result attachment.
- Cross-party identity, profile merging, and long-term guest recognition remain host-app responsibilities.

Permission rules:

- Preserve host/cohost role labels from the host app for audit and UI.
- Enforce capability flags rather than hard-coded role names.
- For MVP, host and cohost can share most gameplay controls.
- Destructive or session-replacing actions require an explicit `manage_games` capability.
- Live gameplay operation requires `operate_game`.
- Moderation actions require `moderate_players`.
- Sensitive organizer/cohost actions should use short-lived tokens or authority revalidation so host-app role changes can take effect during a live session.

## Origin, CORS, and Frame Policy

LocalPlay must allow Revelry origins for REST, WebSocket, and iframe embedding.

Initial allowlist:

```text
https://app.revelryapp.me
https://api.revelryapp.me
https://api-gamma.revelryapp.me
http://localhost:5173
http://localhost:5174
```

Future brand origins:

```text
https://rizzy.party
https://www.rizzy.party
https://pals.party
https://www.pals.party
```

Do not send `X-Frame-Options: DENY` or `SAMEORIGIN` on embeddable routes.

Recommended `frame-ancestors`:

```text
frame-ancestors 'self' https://app.revelryapp.me https://api.revelryapp.me https://api-gamma.revelryapp.me;
```

iframe routes should support:

```text
allow="fullscreen; clipboard-write"
referrerpolicy="strict-origin-when-cross-origin"
```

Avoid relying on third-party cookies. Use explicit launch/runtime tokens.

## Host-App Launch UX Rules

When launched from Revelry:

- hide standalone LocalPlay marketing chrome
- keep gameplay controls visible
- show only games/content actions that are valid for the current host-app catalog and actor capabilities
- keep authoring, room setup, lobby, and gameplay inside the same host-app session context
- provide a visible full-screen or open-external fallback
- provide a return path through allowlisted web URLs, universal/app links, or explicit custom schemes
- do not show standalone LocalPlay spark/paywall prompts, wallet balances, login prompts, or unrelated account/library navigation unless Revelry explicitly requests a standalone LocalPlay mode

Standalone LocalPlay can keep its own spark economy. Revelry-launched sessions should use LocalPlay internal `billing_mode = host_app_managed` or equivalent service authorization so the party does not see two payment systems.

Authoring and gameplay must establish runtime credentials that survive the short-lived handoff/launch token. Token expiry should not interrupt a host while they are writing questions, uploading images, reviewing AI-generated content, waiting in lobby, or playing.

### Frontend Launch Context Contract

LocalPlay frontend should derive a single `LaunchContext` from standalone app state, handoff tokens, launch tokens, or authoring tokens. Every top-level UI surface should use this context rather than checking raw query params directly.

Suggested shape:

```json
{
  "mode": "host_app",
  "host_app": "revelry",
  "brand_key": "revelry",
  "external_container_type": "party",
  "external_container_id": "party_uuid",
  "external_container_title": "Ava's Birthday",
  "party_type": "birthday",
  "role": "host",
  "capabilities": ["manage_games", "author_content", "operate_game"],
  "return_url": "https://app.revelryapp.me/party/party_uuid?tab=games",
  "billing_mode": "host_app_managed",
  "allowed_game_ids": ["quiz", "wmlt", "drawing"],
  "surface": "party_hub",
  "display": {
    "show_localplay_nav": false,
    "show_account_menu": false,
    "show_wallet": false,
    "show_paywalls": false,
    "show_library": false,
    "show_return_action": true,
    "container_label": "Ava's Birthday",
    "container_image_url": "https://media.revelryapp.me/parties/party_uuid/cover.jpg",
    "accent_color": "#ff4f9a",
    "link_label": "Open Ava's Birthday Games Hub on Revelry Games",
    "return_label": "Back to Revelry"
  }
}
```

Modes:

- `standalone`: normal LocalPlay app. Show LocalPlay nav/account/library, sparks, wallet balances, standalone catalog, standalone share/join flows, and LocalPlay save/library CTAs.
- `host_app`: launched from Revelry or another host app. Hide standalone economy/account/nav surfaces unless explicitly allowed. Show host-app context, return action, and only host-app catalog/actions.
- `diagnostic`: optional internal/debug mode; never use for normal Revelry users.

Surfaces:

- `party_hub`
- `authoring`
- `organizer`
- `player`
- `spectator`
- `results`

Revelry-specific UI policy:

- The `party_hub` surface is the LocalPlay-owned full-screen/embedded "Revelry Games" workspace for one party. It must never fall back to the standalone LocalPlay home/catalog when opened from Revelry with valid host-app context.
- Show `external_container_title` near the top of party hub/authoring/lobby/game surfaces, for example "Ava's Birthday".
- Use safe party display metadata such as `container_image_url`, `accent_color`, and `link_label` where available. Treat it as presentation only; do not depend on it for authorization or private party state.
- Show a clear return action using the validated `return_url`; use universal/app links where available.
- Hide sparks, wallet balances, LocalPlay checkout/paywalls, standalone login prompts, and unrelated LocalPlay library/account navigation.
- Hide unsupported standalone games and variants not present in `allowed_game_ids` / `GET /catalog?host_app=revelry`.
- Keep gameplay essentials visible: room code when useful, QR/join affordances, player list, start controls, moderation, timer/scoring, and spectator controls.
- Use host-app-aware share copy. Prefer Revelry-owned join/open URLs when sharing outside LocalPlay; raw `gamesapi.../join` URLs are acceptable for diagnostics but should not be the polished Revelry UX.
- In Revelry-launched organizer/spectator lobby or TV surfaces, render a QR code only when the launch context contains a validated `guest_join_url`. That QR should point to Revelry's party-aware guest join/open flow so guests can join from the party context. If no `guest_join_url` is provided, show neutral copy such as "Players can join from Revelry" and continue hiding the raw LocalPlay share URL/button.
- Preserve role labels for display, but gate actions by `capabilities`.
- If context is missing or invalid on a privileged surface, fail closed with a friendly "Open this from Revelry again" state rather than falling back to standalone organizer controls.

Implementation guidance:

- Backend token resolution should return the normalized launch context to the frontend along with any runtime credential.
- The frontend should store launch context only for the active browser session. Do not persist host-app role/capabilities indefinitely in localStorage.
- WebSocket `AUTH` / first sync should include enough context to keep server-side room behavior aligned with host-app billing and capabilities.
- Tests should cover standalone mode and Revelry mode so hiding sparks/nav does not regress standalone LocalPlay.

## MVP LocalPlay-Hosted Authoring Slice

Recommended first product slice:

1. Quiz manual authoring in LocalPlay-hosted host-app mode.
2. App-compatible authoring launch URL with authoring token, `draft_id`, and allowlisted `return_url`.
3. Save authored quiz content in LocalPlay and return canonical `localplay_content_id` to Revelry.
4. Store a Revelry prepared setup pointer without duplicating quiz content.
5. Start a Revelry-managed session later with `settings.content_id`.
6. Enter the normal LocalPlay lobby/gameplay flow with standalone economy/account chrome hidden.

Manual authoring ships first. Optional AI-generated quiz creation from Revelry party theme/title and host-provided prompt may follow on the same LocalPlay-hosted surface.

Rebus and other quiz variants should stay hidden from Revelry host-app authoring until promoted into the bridge contract. Promotion means catalog metadata, payload schema, accepted session `game_type` or mode, room materialization, launch-token handling, status, results, and feed-safe summaries are all implemented and tested.

Risks and gotchas:

- Content ownership can cross standalone and host-app contexts accidentally unless `host_app`, `external_container_id`, author identity, and reuse capabilities are stored and enforced.
- Creating content without a path to attach it to a Revelry prepared setup strands the host.
- Room creation from unsupported `game_type` or unsupported quiz variant creates broken organizer/player flows.
- Standalone wallet/economy/login/nav chrome leaking into Revelry-launched mode confuses hosts and can conflict with Revelry billing.
- Launch token expiry must not interrupt active authoring or gameplay after runtime credentials are established.
- Mobile/native behavior should default to open-external/fullscreen/app-link paths, especially for authoring forms and media upload.
- Host-app content APIs need idempotency or draft recovery so refreshes do not duplicate partially authored games.

## postMessage Events

Optional after Phase 0:

```text
LOCALPLAY_READY
LOCALPLAY_SESSION_STARTED
LOCALPLAY_SESSION_COMPLETE
LOCALPLAY_REQUEST_CLOSE
LOCALPLAY_HEIGHT_CHANGE
LOCALPLAY_OPEN_EXTERNAL
```

Rules:

- send only to trusted parent origins
- Revelry must validate `event.origin`
- messages are UI hints only
- backend result APIs remain the source of truth

## Environment Variables

LocalPlay:

```text
REVELRY_INTEGRATION_SECRET=<prod-or-gamma-secret>
REVELRY_LAUNCH_TOKEN_TTL_SECONDS=600
REVELRY_AUTHORING_TOKEN_TTL_SECONDS=3600
REVELRY_SESSION_LOBBY_TTL_SECONDS=14400
REVELRY_SESSION_IDLE_TTL_SECONDS=7200
REVELRY_CALLBACK_URL=<optional-revelry-callback-endpoint>
# Optional, temporary rotation-only alias. Keep unset in normal gamma/prod,
# or set to the same value as REVELRY_INTEGRATION_SECRET during planned rotation.
REVELRY_CALLBACK_SECRET=<temporary-rotation-alias-only>
PUBLIC_BASE_URL=https://gamesapi.revelryapp.me
ALLOWED_ORIGINS=https://gamesapi.revelryapp.me,https://app.revelryapp.me,https://api.revelryapp.me,https://api-gamma.revelryapp.me
```

Revelry:

```text
GAMES_ENGINE_URL=https://gamesapi.revelryapp.me
LOCALPLAY_INTEGRATION_SECRET=<matching-secret-or-private-key>
```

Gamma should use gamma URLs, a separate secret, and `PUBLIC_BASE_URL=https://gamesapi-gamma.revelryapp.me`.

## Testing

Implemented LocalPlay tests cover:

- valid handoff creates a session
- one-active-session replacement requires host confirmation
- launch-token minting and resolution
- stable `/sessions/{session_id}/organizer` redirect with token validation
- status polling returns joinability and launch metadata

Remaining focused tests to add:

- expired handoff is rejected
- wrong audience/issuer is rejected
- organizer launch rejects player-scoped token
- guest/player launch cannot receive organizer token
- Revelry origin is allowed for REST/WebSocket/frame embedding
- embedded launch hides standalone chrome
- result summary omits raw per-answer logs

Playwright smoke:

- Revelry-origin desktop/trusted iframe can load LocalPlay launch route
- WebSocket connects from desktop/trusted embedded context
- open-in-new-tab fallback works on mobile viewport
- session complete can be reflected through result endpoint

## Gamma Rollout

Roll out the integration on gamma first.

Current LocalPlay status: gamma is deployed from the callback retry/polish slice (`cbc218f` on 2026-05-23) and has passed direct smoke for health, config, catalog, session creation, launch-token generation, status polling, tokenless player launch redirect, party workspace, party hub link/resolve, host-app-managed billing wallet behavior, LocalPlay-hosted quiz authoring, start from saved `localplay_content_id`, WebSocket organizer/player play-through, completion, and result polling. Basic Revelry gamma end-to-end launch testing has worked for catalog, create session, organizer/player launch, and gameplay. Before each rollout or manual test pass, verify the deployed gamma container against the current repo HEAD because this spec intentionally does not act as the sole source of truth for deployed commit tracking. Deeper branded UX polish and production-scale callback durability remain required before production promotion.

Gamma acceptance checklist:

- Revelry gamma can create a LocalPlay session through the service endpoint.
- Organizer/player/spectator launch routes open against gamma LocalPlay.
- Desktop embedded launch works from Revelry gamma.
- Mobile join opens externally/fullscreen with a working fallback.
- One-active-game replacement warns in Revelry, then supersedes the old LocalPlay session only after confirmation.
- Expired, cancelled, and superseded launch routes show friendly closed-game states.
- Revelry gamma can poll status/results by `session_id`.
- Result summary omits raw answers and private custom quiz contents.
- Feed-card payloads are usable by Revelry but posting/visibility remains Revelry-owned.
- No standalone LocalPlay spark/paywall prompts appear in Revelry-managed sessions.
- Revelry gamma can mint an authoring link, create/edit a quiz with an image, return with `localplay_content_id`, refresh party workspace, and start the saved quiz.
- LocalPlay hub can create/edit/start party-scoped saved quizzes without exposing the Revelry service secret.
- If configured, signed callbacks reach Revelry for content/session events; LocalPlay signs `${timestamp}.${raw_body}` with `REVELRY_INTEGRATION_SECRET`, uses ISO UTC `occurred_at`, emits `content.deleted`, and retries `429` / transient `5xx` responses with short bounded backoff. If callbacks are unavailable, polling recovers state.

Do not promote to production until the gamma flow is playable end to end.

## Implementation Order

Recommended LocalPlay order:

1. Add config for Revelry integration origins/secrets. Done.
2. Add generic durable session schema and db facade methods. Done for `game_sessions`; participant persistence remains deferred.
3. Add catalog endpoint. Done.
4. Add handoff validation helper. Done for shared-secret bearer/JWT validation.
5. Add embeddable launch shell/chrome mode. Done for Revelry-launched `/revelry/*`, tokenized organizer/player/spectator surfaces, standalone economy chrome hiding, and raw LocalPlay share/join suppression in host-app lobby mode. Further brand-specific polish remains.
6. Add session wrapper around current `/room/create`. Done.
7. Add `POST /integrations/revelry/sessions`. Done.
8. Add safe one-active-game replacement handling. Done.
9. Add on-demand launch-token exchange. Done.
10. Add status/result polling endpoint. Done.
11. Add embedded host-app authoring mode for manual quiz content, including host-app content APIs and session creation via `settings.content_id`. Done for quiz content using party-scoped quiz packs.
12. Add signed callback/webhook delivery for content/session/result events, with polling as recovery. Done as best-effort delivery when callback env vars are configured, including short bounded retry for `429` and transient `5xx`; durable queued retry remains backlog.
13. Add postMessage events only where they improve embedded UX.

## Open Questions

- Decision: Phase 0 launch routes should use the backend-served LocalPlay frontend host (`https://gamesapi.revelryapp.me`, with gamma on `https://gamesapi-gamma.revelryapp.me`). This keeps the embedded MVP same-origin with LocalPlay REST/WebSocket runtime. After the flow is playable and stable, reconsider the public IONOS host (`https://games.revelryapp.me`) for cleaner open-external/shareable links.
- Decision: Mobile guest joins should default to open-external/fullscreen LocalPlay launch rather than an embedded Revelry iframe. Desktop web can use iframe by default, tablet can use iframe with an "Open full screen" fallback, and every surface should offer an open-external fallback if iframe loading or WebSockets fail.
- Decision: Revelry-launched sessions should be service-authorized for MVP and should not consume or display user-visible LocalPlay sparks. Standalone LocalPlay keeps its spark economy. Future Revelry entitlements may map to internal LocalPlay service accounting, but that should remain invisible to guests.
- Decision: Handoff and URL launch tokens are short-lived exchange credentials only. They must not terminate active gameplay after exchange. LocalPlay should issue session-scoped runtime credentials that remain valid for active gameplay, subject to idle expiration, cancellation, supersession, or role revocation.
- Decision: Revelry hosts can have only one active LocalPlay game at a time per party context. If a host starts a new game while another LocalPlay game is active, Revelry warns the host first; after confirmation, LocalPlay creates the replacement first and only then closes the previous session as `superseded`, or performs both changes atomically. Failed replacement creation must not close the existing active session.
- Decision: Abandoned Revelry-created lobby sessions remain joinable for 4 hours. Live sessions expire after 2 idle hours. Completed sessions preserve result summaries with the Revelry party but are no longer joinable. Cancelled sessions stop being joinable immediately. Host/cohost can relaunch from the same setup when supported.
- Decision: Result summaries should include game type, game title, custom quiz title, top results, safe highlights, and optional safe public thumbnail/image references visible to party members. They should not include raw per-question answers, sensitive prompt text, full custom quiz contents, or unapproved private uploads by default. Host/cohost approval is required before posting a richer recap to Revelry feed/memories.
- Decision: Revelry may create feed cards when games start and when results are finalized. LocalPlay provides `launch_routes`, joinability state, and result summaries; Revelry owns feed visibility, posting, editing, and external sharing.
- Decision: Revelry must not persist LocalPlay URLs containing `launch_token`. It should store `session_id` and tokenless route metadata, then mint or refresh short-lived launch tokens only when opening an iframe, external player view, organizer view, or spectator view.
- Decision: LocalPlay stores identity as session participant metadata. Logged-in users may include an opaque host-app `external_user_id`, but gameplay membership is scoped to `host_app`, `external_container_id`, and `session_id`. Anonymous guests receive only a session-scoped `local_participant_id` when no host-app guest id is provided. Cross-party identity and profile merging remain host-app responsibilities.
- Decision: LocalPlay preserves host/cohost role labels from the host app, but enforces capability flags rather than hard-coded role names. Host and cohost can share most gameplay controls for MVP. Destructive or session-replacing actions require `manage_games`.
- Decision: LocalPlay should receive only minimal host-app context: `host_app`, `external_container_type`, `external_container_id`, `external_container_title`, host user id, optional brand/theme/vibe hints, and optional `return_url`. The host app remains the source of truth for party/event data, guest lists, payments, and private metadata.
- Decision: LocalPlay integrations should use a generic host-app contract internally, with Revelry as the first adapter. The API may expose `/integrations/revelry/...` for MVP, but persisted records and core service code should use generic fields such as `host_app`, `external_container_type`, `external_container_id`, `external_user_id`, `role`, `capabilities`, and `return_url`.
- Decision: MVP should deliver a narrow Revelry-to-LocalPlay bridge on top of the generic durable session model: catalog, create session, enforce one active game, launch organizer/player/spectator, support embedded/open-external play, poll status/results, and return safe result summaries. Webhooks, full Cloud Run room persistence, richer feed automation, and deep analytics are deferred until the bridge is playable on gamma.
- Decision: Roll out on gamma first and do not promote to production until Revelry gamma can create, launch, play, supersede, expire, poll, and summarize a LocalPlay session end to end.
- Decision: Expose `GET /catalog` as part of the MVP. Revelry should use it to render available LocalPlay games, filtered by host app/environment where needed. LocalPlay still validates launch requests server-side. The catalog may include `live`, `gamma`, `planned`, or `disabled` status values, but Revelry should only enable launch for games LocalPlay marks `launchable`.
- Decision: Custom quiz authoring remains owned by LocalPlay. The MVP authoring path is LocalPlay-hosted prepared content: Revelry opens the authoring link, LocalPlay returns canonical `localplay_content_id`, Revelry stores a prepared setup pointer, and session creation passes `settings.content_id`. Do not add or revive a separate generic quiz/`quiz_pack_id` bypass for Revelry-launched custom quizzes.
- Decision: Reuse existing custom quiz tables for Revelry quiz content now. Existing quiz-pack tables already serve the non-Revelry custom quiz use case and can also support Revelry by scoping ownership to `revelry:party:<party_id>`, so the quiz authoring implementation should not be blocked on a new generic content-table migration. Add a generic host-app content table later when non-quiz editable game types need it.
- Decision: A generic Games/LocalPlay entry from Revelry opens a party-scoped LocalPlay "Revelry Games" hub, not standalone LocalPlay. The hub shows the same party prepared games, drafts, active session, recent results, and launchable catalog that Revelry mirrors in its Games tab, and host/cohost can start games from either surface.
- Decision: Embedded host-app authoring must run in host-app-aware mode. The UI may reuse standalone LocalPlay components, but it must hide unsupported games, standalone economy/account chrome, and standalone-only content paths. Authored content should be saved as LocalPlay host-app content and attached to the Revelry-managed session with `settings.content_id`.
- Decision: Rebus and other quiz variants stay hidden from Revelry-launched LocalPlay mode until explicitly promoted into the bridge contract with catalog metadata, content schema, room materialization, launch/status/results support, and feed-safe summaries.
- Decision: Manual custom quiz authoring should remain free. LocalPlay may delete free saved custom quizzes after a retention window and monetize long-term save/retention, larger libraries, media quotas, premium templates, AI assist, advanced branding, analytics, or cross-event reuse. This is a LocalPlay product/commerce feature, not a Revelry feature.
