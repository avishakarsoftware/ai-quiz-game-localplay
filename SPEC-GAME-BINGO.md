# LocalPlay Custom Bingo Game Spec

## Overview

Add **Bingo** as a standalone LocalPlay game card built on the existing Bingo-family engine.

Housie remains the classic 90-ball / Tambola ruleset with 3x9 tickets. Bingo is a separate, customizable 5x5 game where hosts can create themed decks using text, phrases, emoji, and images. The first implementation should reuse the Housie caller/claim/runtime concepts where they fit, but Bingo should feel like its own game in the catalog and setup flow.

```text
Engine family: bingo
Game type: bingo
Future preset catalog ids: baby_bingo, wedding_bingo, holiday_bingo, office_bingo, emoji_bingo, image_bingo, photo_bingo
Backend engine: bingo_engine.py
Frontend display name: Bingo
```

## Rollout Constraint

The first implementation is **gamma-only**.

Rules:

- Do not expose Bingo in production catalog, production frontend, or Revelry production.
- Any database/schema changes required for Bingo must be applied only to gamma objects, such as `games_gamma_*`.
- Production `games_*` schema and production runtime behavior must remain untouched unless a later explicit production rollout is requested.
- Prefer reusing existing gamma media tables and generated-content structures before adding new schema.
- If new schema is required, add a gamma migration/script or gamma SQL section first; keep production SQL unchanged in the same implementation pass.
- Local development can support Bingo for testing, but deploy/release gating should keep the feature gamma-only.

## Product Decision

Bingo should be a **separate game** from Housie.

Shared mechanics:

- Host/caller draws items from a deck.
- Players receive unique boards/cards.
- Players mark matching cells.
- Players claim prize patterns.
- Server validates claims and broadcasts winners.
- Organizer and spectator screens show latest call, call history, claims, and winners.

Separate product expectations:

- Housie uses classic 1-90 numeric tickets, 3 rows x 9 columns, and Tambola prize names.
- Bingo uses customizable 5x5 boards, optional free center, themed text/image cells, and patterns such as line, corners, and blackout.
- Baby Bingo and other event games are easier to discover as their own cards, but should reuse the Bingo runtime and setup model.

## Goals

- Add `bingo` as a first-class standalone `GameType`.
- Let hosts create customizable text, phrase, emoji, and image Bingo games.
- Support templates so hosts can start quickly.
- Support Baby Bingo as a near-follow-up preset using the same runtime.
- Keep the first implementation process-local and compatible with the current VM/WebSocket deployment.
- Reuse existing Housie `BINGO_*` message concepts where practical.
- Support host-provided image deck items in the MVP using the shared LocalPlay media layer.

## Non-Goals For MVP

- No Revelry/host-app exposure until standalone Bingo has setup, runtime, result summary, and tests.
- No AI generation in the first slice unless it falls out cheaply from existing content generation patterns.
- No player photo submission in MVP.
- No image moderation or image AI validation in MVP.
- No AI image generation in MVP. Image deck items come from host upload or already-existing media assets.
- No paid ticketing, gambling, betting, cash prizes, or raffle mechanics.
- No public marketplace of Bingo templates.
- No long-term persistent Bingo template library in the first runtime slice unless it reuses existing generated content storage cleanly.

## Accepted MVP Decisions

- Minimum players: `2`, matching Housie.
- Winner policy: one winner per prize pattern in MVP.
- Claim mode default: casual, `claim_requires_latest_call = false`.
- Strict claims: supported as a setup flag if cheap, but not the default.
- Baby Bingo: not required in the base Bingo implementation, but the setup/template model must make it a small follow-up.
- Image support: included in MVP.
- Revelry exposure: disabled for MVP.
- Auto-caller: manual caller only for the first pass unless Housie auto-caller reuse is trivial and low-risk.

## Game Types And Catalog Model

Current standalone catalog shows:

```ts
{
  id: "bingo",
  runtimeType: "bingo",
  title: "Bingo",
  description: "Create a custom Bingo board with your own words, phrases, or party moments."
}
```

Preset cards are separate catalog ids with the same runtime:

```ts
{
  id: "baby_bingo",
  runtimeType: "bingo",
  ruleset: "baby_bingo",
  defaultTemplate: "baby_shower_gifts",
  title: "Baby Bingo"
}
```

This mirrors quiz variants: separate visible cards, shared runtime.

Backend room creation should use `game_type = "bingo"` for MVP. Presets can pass `ruleset` and `template_id` inside the Bingo setup content rather than creating new backend runtime types immediately.

Implemented preset behavior:

- `baby_bingo` appears as its own standalone catalog card when Bingo is enabled.
- Selecting Baby Bingo opens the Bingo setup screen with title `Baby Bingo`, free center enabled, casual claim rules, and a ready-made 25-item baby shower deck.
- Starting the preset still creates a normal `bingo` setup and room; no new backend runtime type is introduced.
- Baby Bingo remains disabled for Revelry/host-app mode until the generic Bingo bridge contract is deliberately enabled.

Because the rollout is gamma-only, catalog exposure should be gated by environment/config. Production builds and production `/catalog` responses must not show `bingo` until an explicit production rollout.

## MVP Gameplay

### Setup

Host configures:

- Game title.
- Template or blank custom deck.
- Deck items: editable words, short phrases, emoji, or image items.
- Board size: 5x5 only for MVP.
- Free center: on by default.
- Free center label: default `FREE`.
- Prize patterns:
  - First Line
  - Four Corners
  - Blackout
- Caller mode:
  - Manual for MVP.
  - Auto can reuse Housie later.
- Claim rule:
  - Casual mode: claim whenever pattern is complete.
  - Strict mode: pattern must become true on the latest called item.

Recommended MVP defaults:

```json
{
  "layout": "bingo_5x5_free",
  "free_center": true,
  "free_center_label": "FREE",
  "patterns": ["first_line", "four_corners", "blackout"],
  "caller_mode": "manual",
  "claim_requires_latest_call": false
}
```

### Deck Requirements

For MVP text Bingo:

- Minimum 24 unique playable items when free center is enabled.
- Minimum 25 unique playable items when free center is disabled.
- Maximum 120 deck items.
- Item display text should be 1-40 characters after trimming.
- Duplicate items should be merged case-insensitively.
- Empty lines are ignored.
- Deck order in setup is editable, but runtime call order is shuffled by the server.

For MVP image Bingo:

- Image deck items require a display label.
- Image files must be uploaded through the existing signed LocalPlay media upload flow.
- Runtime cards use stable app-controlled media references, preferably `/media/{asset_id}`.
- Image items count toward the same minimum deck size as text items.
- Mixed decks are allowed: a single game can include text, emoji, and image cells.
- If an image asset is still pending or failed, the setup screen must block room creation or remove that item before save/start.
- Players and spectators must see the image plus label/alt text where space allows.

### Player Flow

1. Player joins the room.
2. When the host starts, the server generates a unique Bingo card for each player.
3. Player sees their card.
4. Host calls items one at a time.
5. Player marks matching cells manually.
6. Player taps a claim button when they complete a prize pattern.
7. Server validates the claim against that player's card and called items.
8. Winners are announced across organizer, player, and spectator surfaces.

### Organizer / Spectator Flow

Organizer sees:

- Latest called item.
- Call Next button.
- Undo Last Call, blocked after claims that depend on the latest call. The server publishes `can_undo_last_call` in caller sync/call/claim messages so the organizer UI can disable Undo when a claim has locked the latest call. If Undo is used while auto-caller is running, the server pauses auto before rewinding; the host must explicitly resume auto.
- Called item history.
- Prize pattern status.
- Winner/claim log.
- End Game.

Spectator sees:

- Latest called item in large type.
- Called history / recent calls.
- Winners.
- Player count.

For custom Bingo, a full called board is not required because the deck can be arbitrary. Show a recent-call rail and searchable/list-like called history instead of a 1-90 grid. Image calls should show a thumbnail and label.

## Card Shape

```ts
export interface BingoCell {
  kind: "text" | "emoji" | "image" | "free";
  item_id?: string;
  value: string;
  display: string;
  label?: string;
  image_asset_id?: string;
  image_url?: string;
  alt_text?: string;
  row: number;
  col: number;
}

export interface BingoCard {
  id: string;
  player_id: string;
  player_name: string;
  layout: "bingo_5x5_free" | "bingo_5x5";
  rows: Array<Array<BingoCell>>;
}
```

Free center cell:

```json
{
  "kind": "free",
  "value": "free",
  "display": "FREE",
  "row": 2,
  "col": 2
}
```

## Setup Content Shape

```json
{
  "game_title": "Baby Shower Bingo",
  "ruleset": "custom",
  "layout": "bingo_5x5_free",
  "free_center": true,
  "free_center_label": "FREE",
  "deck": [
    {
      "id": "item_1",
      "kind": "text",
      "value": "diapers",
      "display": "Diapers"
    }
  ],
  "patterns": [
    {
      "id": "first_line",
      "label": "First Line",
      "description": "Any complete row, column, or diagonal"
    },
    {
      "id": "four_corners",
      "label": "Four Corners",
      "description": "All four corner cells"
    },
    {
      "id": "blackout",
      "label": "Blackout",
      "description": "Every non-free cell",
      "terminal": true
    }
  ],
  "caller_mode": "manual",
  "claim_requires_latest_call": false
}
```

## Prize Patterns

MVP patterns:

| Pattern | Meaning |
|---|---|
| `first_line` | Any complete row, column, or diagonal |
| `four_corners` | Four corner cells marked/called |
| `blackout` | Every non-free cell marked/called |

Later:

- `two_lines`
- `postage_stamp`
- custom pattern templates

Non-terminal patterns award to the first valid server claim. Terminal patterns such as Blackout keep a final claim window open after the first valid terminal claim on the latest call; other players can still claim the same terminal pattern if their board also completed on that same call. Claim buttons should display the prize and claimant names rather than a generic "Claimed" label.

## Image Bingo Phase

Image support is part of the gamma MVP. It should use the shared media asset layer from `SPEC-IMAGE-GAMES.md`.

Image deck item:

```json
{
  "id": "item_12",
  "kind": "image",
  "value": "baby_bottle",
  "display": "Baby Bottle",
  "image_asset_id": "asset_uuid",
  "image_url": "/media/asset_uuid",
  "alt_text": "A baby bottle"
}
```

Rules:

- Image assets must be app-controlled URLs or `/media/{asset_id}`.
- Host uploads must go through signed LocalPlay upload endpoints.
- AI-generated images are out of scope for MVP.
- Uploaded images must have labels/alt text for accessibility and fallback display.
- If upload safety, metadata, or display behavior is not reliable enough on gamma, block image item save/start rather than silently creating broken boards.
- Production media/schema behavior must not be changed for this gamma MVP unless a shared code path already safely supports it.

## Baby Bingo Preset

Baby Bingo should be a catalog preset on top of Bingo.

Initial templates:

- Baby Shower Gifts
- Baby Items
- Baby Predictions

Example Baby Shower Gifts deck:

```text
Diapers
Wipes
Onesie
Pacifier
Bottle
Blanket
Stroller
Car Seat
Baby Monitor
Teether
Booties
Bib
Rattle
Swaddle
Crib Sheet
Bath Toys
Baby Book
Stuffed Toy
Burp Cloths
Diaper Bag
Changing Pad
High Chair
Night Light
Baby Shampoo
```

The host should be able to edit every item before room creation.

## Backend Implementation Plan

Add or extend `backend/bingo_engine.py` with:

- `DEFAULT_BINGO_PATTERNS`
- `sanitize_bingo_deck`
- `sanitize_bingo_patterns`
- `default_bingo_game`
- `generate_bingo_card`
- `create_bingo_call_deck`
- `validate_bingo_claim`
- image item validation helpers that accept only app-controlled media URLs/assets

Add runtime support:

- `game_type = "bingo"` accepted by room creation.
- Store temporary setup content in `bingo_games` with timestamps and ownership.
- Add `/bingo/create`, `/bingo/{bingo_id}`, `/bingo/{bingo_id}` update routes if needed for MVP.
- Reuse existing media upload/finalize APIs for image deck items; do not add production schema unless explicitly needed.
- Reuse `BINGO_CALL_NEXT`, `BINGO_UNDO_LAST_CALL`, `BINGO_CLAIM`, `BINGO_SYNC`, `BINGO_COMPLETE`.
- `BINGO_SYNC` and `BINGO_CALL` include `can_undo_last_call`; accepted claim broadcasts also include the updated value so organizer controls immediately disable after a locking claim.
- Broadcast `game_type: "bingo"` so frontend can choose Bingo card/called-list rendering instead of Housie 1-90 rendering.

Suggested room internals can reuse existing Housie fields initially:

```py
room.housie_deck
room.housie_called
room.housie_tickets
room.housie_winners
room.housie_claimed_patterns
```

Longer term, rename these to neutral `bingo_*` fields after both Housie and Bingo are stable. Do not block the MVP on that refactor.

## Frontend Implementation Plan

Add:

- `bingo` to `GameType`.
- `runtimeType: "bingo"` to game mode config.
- `BingoSetupScreen`.
- Generic Bingo card component for 5x5 cells.
- Generic called-list component for text/image calls.
- Image deck item controls: upload, replace, remove, label, and upload status.

Organizer flow:

- Selecting Bingo opens setup.
- Setup creates a Bingo content id.
- Room creation passes `game_type = "bingo"` and `bingo_id`.
- Runtime screen reuses the Housie caller shell where possible but renders Bingo copy and called-list UI.
- Setup must validate the deck has enough ready items before room creation.

Player flow:

- On `BINGO_SYNC` with `game_type = "bingo"`, render 5x5 Bingo card.
- Allow marking cells locally.
- Claim buttons use the setup's selected patterns.
- Image cells render through the shared `GameImage` component or a Bingo-specific wrapper around it.

Spectator flow:

- On `game_type = "bingo"`, show latest item, recent called items, winners, and player count.
- Do not render the Housie 1-90 called grid.

## Testing Plan

Backend unit tests:

- Deck sanitization trims, dedupes, and enforces minimum size.
- Image deck item validation rejects non-app-controlled URLs and pending/failed assets.
- 5x5 card generation places a free center and 24 playable cells.
- Generated cards contain no duplicate items.
- First Line validates rows, columns, and diagonals.
- Four Corners validates only literal corners.
- Blackout ignores the free center.
- Strict latest-call mode rejects stale claims.
- Casual claim mode accepts completed patterns even if the latest call did not complete the pattern.

Backend API tests:

- `/bingo/create` accepts a valid custom text deck.
- `/bingo/create` accepts valid image deck items backed by ready media assets.
- `/room/create` accepts `game_type = "bingo"` with `bingo_id`.
- Starting a Bingo room creates player cards.
- Invalid decks return 422.

Frontend tests:

- Game select shows Bingo.
- Setup validates minimum deck item count.
- Setup supports image upload/remove/label states.
- Setup can load a Baby Bingo template once preset cards are added.
- Player card marks cells without layout shift.
- Claim buttons show awarded claimants; non-terminal awarded claims disable, while terminal claims can remain available during the final claim window.

## Rollout

1. Ship standalone gamma-only Bingo with custom text/emoji/image deck items.
2. Add Baby Bingo preset card using the same runtime.
3. Add more templates: Wedding Bingo, Birthday Bingo, Holiday Bingo, Office Bingo.
4. Add AI text deck generation.
5. Add Image/Photo Bingo-specific cards after media pipeline hardening beyond basic host-upload cells.
6. Expose Bingo-family games to Revelry only after host-app session/content/result contracts and e2e tests are in place.
7. Promote to production only after an explicit production rollout decision and any required production schema migration.
