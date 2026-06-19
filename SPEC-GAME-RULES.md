# LocalPlay Game Rules Surface Spec

Status: Implementation-ready
Last updated: June 19, 2026

## Goal

Every LocalPlay game should expose concise, consistent rules before play starts. Hosts should be able to read rules before choosing or creating a game. Players should be able to read the same rules from the join/lobby screen while waiting for the host. Revelry and other host-app surfaces should receive the same rules from LocalPlay catalog metadata so copy does not drift.

This is a cross-game platform feature, not a new game runtime.

## Product Requirements

Rules must be:

- Short enough for mobile reading.
- Structured consistently across games.
- Specific to the actual configured game when possible.
- Safe for hidden-role games: never reveal private role assignments or strategy-specific secrets.
- Available without creating a room.
- Available in a room/lobby after the host creates a room.
- Available in embedded Revelry game picker surfaces through catalog metadata.

Rules should answer:

1. What is the objective?
2. How many players are needed or recommended?
3. What physical setup is needed, if any?
4. How does a round or turn work?
5. How do scoring and winning work?
6. What should players keep private?
7. What should late joiners know?

## Rules Schema

Add a shared `rules` object to each `GAME_CATALOG` entry.

```json
{
  "rules": {
    "version": 1,
    "title": "Mafia Rules",
    "summary": "Find the Mafia before they outnumber the town.",
    "player_count": {
      "min": 5,
      "recommended": "7-15",
      "max": 50
    },
    "sections": [
      {
        "id": "objective",
        "title": "Objective",
        "items": [
          "Town wins by eliminating all Mafia.",
          "Mafia wins when they equal or outnumber the living Town."
        ]
      },
      {
        "id": "flow",
        "title": "How it works",
        "items": [
          "Everyone gets a secret role on their phone.",
          "At night, every player gets a private prompt so action roles are hidden socially.",
          "During the day, players discuss and vote to eliminate one person."
        ]
      },
      {
        "id": "privacy",
        "title": "Keep private",
        "items": [
          "Do not show your role screen unless the host explicitly allows it.",
          "Mafia should coordinate quietly through their private prompts."
        ]
      }
    ],
    "host_notes": [
      "Best with a host who can explain the first night.",
      "Works better when players can read their phones privately."
    ],
    "player_notes": [
      "Read your role carefully before the first night.",
      "You can lie, bluff, and accuse, but keep it playful."
    ],
    "physical_setup": [
      "Players should sit or stand where they can talk as a group."
    ],
    "late_join_policy": "Late joiners can spectate until the next game unless the runtime explicitly supports mid-game joins."
  }
}
```

Required fields:

- `version`
- `title`
- `summary`
- `sections`

Optional fields:

- `player_count`
- `host_notes`
- `player_notes`
- `physical_setup`
- `late_join_policy`
- `variants`

Section ids should use this standard set where applicable:

- `objective`
- `players`
- `setup`
- `flow`
- `scoring`
- `winning`
- `privacy`
- `late_join`
- `tips`

## Backend Implementation

Add rules metadata to the static catalog in `backend/main.py`.

Expose rules through existing catalog responses:

- `GET /catalog`
- `GET /integrations/revelry/party-games/resolve`
- Any saved/prepared content response that already includes catalog game metadata.

No database migration is required for the MVP. Rules are static metadata attached to game types. Saved custom content may override display title/theme, but it should not override base game rules in MVP.

Backend validation:

- Catalog serializer should pass through `rules`.
- Host-app policy must not strip `rules`.
- Rules must be JSON-serializable and reasonably small.

Suggested helper:

```py
def game_rules(game_type: str) -> dict:
    ...
```

This can start as direct catalog lookup and move to a dedicated registry if `GAME_CATALOG` becomes too large.

## Frontend Implementation

Add a reusable `GameRulesModal` component.

Host game picker:

- Each game card gets a small rules/info button.
- Tapping the card still selects/creates the game.
- Tapping rules opens the modal and does not select the game.
- Modal shows title, summary, player count, sections, host notes, and physical setup.

Standalone player lobby:

- Waiting players see a `Rules` button before the host starts.
- Button uses the current room's `game_type` and catalog rules.
- If room-specific config changes rules-relevant text later, the sync payload can include a `rules_override`, but MVP uses base rules.

Organizer lobby:

- Host sees `Rules` near the start button.
- For hidden-role/complex games, rules should remain available after game start from menu/help, but MVP can limit to pre-start surfaces.

Spectator/TV:

- Optional in MVP. Later, spectator can show a QR-friendly "How this game works" panel before start.

Embedded Revelry:

- Revelry party hub cards should render a `Rules` affordance from LocalPlay catalog metadata when present.
- If Revelry does not implement the affordance yet, LocalPlay's embedded hub should still show it for LocalPlay-owned screens.

## UX Guidelines

- Rules modal should not be a long document. Prefer bullets.
- Use compact headings and 16-18px body text on mobile.
- Avoid tutorial tone that explains obvious app controls.
- Hidden-role games must clearly tell players what stays private.
- Physical games must clearly say what is needed outside the phone.
- Ambient games must explain whether late joins are supported.

## Initial Coverage

Add rules metadata for every catalog game:

- AI Quiz
- Baby Bingo
- Bingo
- Bluff
- Chit Pull
- Common Ground
- Drawing Game
- Emoji Charades
- Fact or Fiction
- Find Someone Who
- Housie
- Mafia
- Most Likely To
- Musical Chairs
- Odd One Out
- Party Quests
- Rebus Rush
- Story Chain
- Timeline Twist
- Two Truths and a Lie
- Who Am I?

## Testing

Backend:

- Catalog includes `rules` for every launchable game.
- Rules survive host-app catalog policy filtering.
- Revelry party-games resolve includes rules for enabled games.
- Rules schema has required fields for every game.

Frontend:

- Host can open rules from game picker without selecting the game.
- Player can open rules from lobby before start.
- Organizer can open rules from lobby before start.
- Modal closes cleanly and does not disrupt socket state.
- Mobile viewport does not clip modal actions.

Playwright:

- Open game picker, open rules for Mafia, verify objective/privacy sections.
- Create a Housie room, join as player, open rules in lobby.
- Resolve Revelry embedded hub, verify at least one card exposes rules metadata or a rules affordance.

## Rollout

Phase 1:

- Add backend catalog metadata and schema tests.
- Add LocalPlay host picker modal.
- Add organizer/player lobby modal.

Phase 2:

- Add rules affordance to embedded Revelry hub.
- Add room-config-aware rule overrides for games such as Musical Chairs mode, Bingo card shape, and Mafia role mix.

Phase 3:

- Add post-start help access from the menu for complex games.
- Add localized rules copy if LocalPlay becomes multilingual.

## Open Decisions

- Whether rules copy should live entirely in backend catalog metadata or in a frontend registry with backend schema checks.
- Whether Revelry should render LocalPlay rules itself or open LocalPlay embedded modal.
- Whether room-specific rules overrides are needed before production rollout, or only after we see confusion in playtests.
