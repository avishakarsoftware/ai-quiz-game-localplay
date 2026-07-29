# SPEC-TV-APP — the TV as the party's home, not its second screen

Status: **Implementation-ready spec, not built (2026-07-28).** Avi's framing: install the app on the
TV *instead of* a phone, because that suits local play better. This is a different product from the
TV-as-spectator-display we already ship. Owner: Avi. Live status: DEPLOY.md's ledger once anything ships.

## 1. The reframe, and why it's the right one

We already support TV as a **secondary display**: `SpectatorPage` (live at
`games.revelryapp.me/spectator`), Chromecast with a registered receiver (`VITE_CAST_APP_ID`
`1BC9ACD8`), and a `CastButton`. That serves a host who already has the app on their phone.

TV-**primary** inverts it:

| | Phone-primary (today) | TV-primary |
|---|---|---|
| Who installs | Every host, on their phone | **Once per household**, on the TV |
| Room code lives | On the host's phone, shown around | **On a 55" screen everyone can see** |
| Discovery | App Store, brutally crowded | **TV stores, far less crowded** |
| Social focus | A phone in someone's hand | The screen the room already faces |

The distribution argument is the strongest one, and it addresses the real bottleneck: **0 installs**
as of 2026-07-28.

## 2. The capability tiers — the core of the design

**A TV with no phones in the room is a real, servable product.** This is the most important finding
in this spec, and it comes from two verified facts:

- **32 of 38 games ship playable default content** (`default_content_available && !supports_ai_generation`).
  Only 6 need a typed AI topic.
- **Housie/Bingo on a TV is excellent with zero phones** — the TV calls numbers, players use *paper
  tickets*. That is how housie has always been played. Same for Musical Chairs (TV plays and stops
  the music) and Find Someone Who (printed cards).

So availability is a function of **how many player devices are currently connected**, computed live:

| Tier | Devices | What unlocks | Examples |
|---|---|---|---|
| **0** | TV + remote only | Prompt/caller/discussion games. TV is the quizmaster; humans self-organise. No per-player scoring. | Housie, Bingo (+ occasion decks), Musical Chairs, Would You Rather, Never Have I Ever, This or That, Hot Takes, Story Chain, Two Truths |
| **1** | + one phone | Pass-and-play (private role reveals), typed AI topics, a comfortable host controller | Impostor, Odd Question, AI Quiz with a custom topic |
| **2** | + a phone each | Individually-scored games, per-player input | Quiz proper, Drawing, Poker, Acronym, Survey Says |
| **2+cam** | + camera | Photo games | Photo Clue |

**Tiles must un-grey live as phones join.** A guest scanning the QR should visibly unlock games on
the TV. That teaches the whole model without a word of explanation, and it is the single most
valuable piece of feedback in the product.

## 3. Declaring capability (data model)

Add to each catalog entry. **Derived availability, never a hardcoded id list** — three separate
hardcoded lists shipped the occasion bingos broken (see BACKLOG), so this is a hard rule.

```python
# backend/game_catalog.py — per entry
"tv_requires": {
    "player_devices": 0,        # phones needed to PLAY at all (0 = TV+remote is enough)
    "private_screen": False,    # secret roles → needs at least one passed phone
    "text_input": False,        # AI topic / free text → needs a phone keyboard
    "camera": False,            # photo capture
},
```

Availability is then computed, not stored:

```python
def tv_availability(entry: dict, connected_devices: int, has_camera: bool) -> dict:
    """Returns {playable: bool, reasons: [str]}. Reasons are user-facing copy keys."""
```

A companion `tv_playable_now(catalog, connected_devices)` powers the grid. A guard test must assert
every catalog entry declares `tv_requires`, so a new game cannot silently default to "playable".

## 4. The greyed-tile experience

**Greyed tiles stay focusable.** Do not skip them with the D-pad — a host needs to be able to land
on a game and learn *why* it's unavailable. Skipping them makes the app feel broken.

Each unavailable tile shows a **reason chip**, not just dimming:

| Reason | Chip |
|---|---|
| `player_devices` unmet | "Needs 1 phone" / "Needs a phone each" |
| `private_screen` | "Needs 1 phone to pass around" |
| `text_input` | "Needs a phone to type" |
| `camera` | "Needs a phone camera" |

Selecting a greyed tile opens the **Unlock sheet**:

```
┌──────────────────────────────────────────────┐
│  Impostor                                    │
│  Needs one phone to pass around              │
│                                              │
│      ▄▄▄▄▄▄▄   Scan with any phone           │
│      █ QR  █   games.revelryapp.me/join/HY2  │
│      ▀▀▀▀▀▀▀                                 │
│                                              │
│  No app needed — it opens in the browser.    │
│                                              │
│  ── Want the app? ──                         │
│  [small App Store QR]  [small Play QR]       │
│                                              │
│  ‹ Back to games                             │
└──────────────────────────────────────────────┘
```

**The primary QR is the WEB JOIN URL, not an app store.** Verified: `/join/{code}` returns 200 and
works in any mobile browser — guests have never needed an install. Leading with an app-store QR
would add a download, an account, and a store round-trip to a problem solved by opening a link. The
store QRs stay as a small secondary affordance for people who *want* the app.

Copy rule: say what it needs and how to get there. Never "unsupported".

## 5. Screen inventory + flows

**S1 · Home / game grid** (D-pad primary surface)
- Row 1: **"Play now"** — only Tier-0-satisfied games, so a host with no phones has an obvious start.
- Row 2+: categories, including greyed tiles with reason chips.
- Persistent header: room code + a small QR once a room exists; connected-device count ("2 phones joined").
- A **"What can I play now?"** toggle filters to currently-playable.

**S2 · Unlock sheet** — §4.

**S3 · Room / lobby**
- Giant QR + room code, readable across a room.
- Live joined list. Each new phone re-evaluates the grid.
- "Start" is enabled per the game's own minimum.

**S4 · In-game** — `SpectatorPage`'s existing views, TV-safe (§7).

**S5 · Sign-in (optional, deferred)** — device-code pairing so sparks reach the TV (§6).

### Flow A — zero phones (must work)
1. Open app → S1 → "Play now" row → Housie.
2. TV creates the room itself, goes straight to calling numbers with the auto-caller.
3. Guests use paper tickets; the remote pauses/advances.
4. Podium on the TV. **No phone touched the party at any point.**

### Flow B — one phone arrives
1. S1 → Impostor is greyed, "Needs 1 phone to pass around".
2. Select it → Unlock sheet → host scans the web QR.
3. Their phone joins; **the tile un-greys on the TV in real time**.
4. Start. TV shows `GroupScreenFrame` phases; the passed phone handles `PrivacyGate` role reveals.
   TV is the table centre, phone is the secret-holder — better than either alone.

### Flow C — full party
Every guest scans; Tier-2 games un-grey; the TV is the shared display and phones are controllers.
This is today's product with the TV promoted from optional to default.

## 6. Monetization — TV-store billing is dodged entirely

`tokens.get_wallet_id` already resolves to `user_id` when signed in, else `device_id`. **Sparks
follow the account, not the device.** So: host buys on their phone (Stripe and mobile IAP are both
live), signs in once on the TV, TV spends the same wallet. No Amazon IAP, no Google Play Billing for
TV, no extra store revenue share.

Open decision (§10): what an **un-signed-in** TV gets. A per-TV-device signup bonus is farmable
across factory resets; requiring sign-in to host is safer but adds first-run friction.

## 7. Implementation plan

**7a · Backend**
1. `tv_requires` on every catalog entry + `tv_availability()` / `tv_playable_now()` helpers, derived.
2. **TV creates rooms.** Today only the organizer calls `POST /room/create`. Add a TV-origin path
   returning `{room_code, tv_token}`.
3. **Claim-host handshake.** First phone to join a TV-created room becomes controller; later joiners
   are players. Needs a guard so a guest can't silently steal control mid-party.
4. **Short TTL for unclaimed TV rooms** — a TV that creates rooms nobody claims will burn the
   `MAX_ROOMS` cap. Reuse the occupancy-qualified TTL work.
5. Expose `connected_devices` in room sync so the TV can re-evaluate the grid live.

**7b · Frontend (TV shell)**
6. `TvHomeScreen` — D-pad grid, focus model per §8, "Play now" row, reason chips.
7. `TvUnlockSheet` — §4, web-join QR primary.
8. `TvRoomScreen` — giant QR + live joined list.
9. TV-safe pass on `SpectatorPage`: 5% overscan margins, larger type, no hover states, no scrollbars.

**7c · Packaging**
10. Fire TV first (least friction): leanback manifest flags, TV banner, Amazon Appstore listing.
11. Google TV second, same codebase.

**7d · Tests**
- Every catalog entry declares `tv_requires` (guard test).
- `tv_availability` truth table across all four tiers.
- A tile un-greys when `connected_devices` increases (the live-unlock behaviour).
- Greyed tiles remain focusable.
- The unlock sheet's primary QR is the **web join URL**, not a store URL.

## 8. D-pad focus model (explicit, so it isn't invented per screen)

- Grid: 4 columns on 1080p, 5 on 4K. Left/Right within a row, Up/Down between rows, wrapping at ends.
- **Greyed tiles are focusable** (§4).
- `BACK` closes a sheet, then returns to the grid, then prompts before exit.
- Focus ring must be visible at 3 metres: 4px accent outline + scale, never colour alone.
- Long-press/`MENU` on a tile opens Rules (the metadata already exists).
- No element requires hover, right-click, or a text caret on the TV surface.

## 9. Deliberately out of scope for v1

Photo games on TV, voice input, Tizen/webOS/tvOS/Roku, TV-store billing, casting *from* the TV,
per-player TV profiles.

## 10. Open questions for Avi

- **Un-signed-in TV**: free sparks per TV device (farmable) vs sign-in required to host (friction)?
- **Is Housie-on-TV-with-paper-tickets worth leading the store listing with?** It's the clearest
  "you need nothing but this TV" story, and it's a genuinely traditional way to play.
- **Rank against other install-getting work.** This is a marketing bet, not a feature bet. The
  question is whether a Fire TV listing beats the same effort spent elsewhere — currently unknown.
