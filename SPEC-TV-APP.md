# SPEC-TV-APP — the TV as the party's home, not its second screen

Status: **MVP slice implemented locally (2026-07-28): derived `tv_capability` catalog metadata,
`tv_availability()` helpers, `/catalog` exposure, and a D-pad-friendly `/tv` launcher shell.**
Native Fire TV/Google TV packaging, TV-origin room creation/control, and real companion unlock
sync are still the next implementation slice. Avi's framing: install the app on the TV *instead of*
a phone, because that suits local play better. This is a different product from the
TV-as-spectator-display we already ship; `/tv/:code` remains the legacy spectator shortcut.
Owner: Avi. Live status: DEPLOY.md's ledger after deploy.

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

**A TV with no phones in the room can be a real, servable product.** This is the most important
finding in this spec, and it comes from two implementation facts:

- Most games ship playable default content (`default_content_available`) or can fall back to a
  curated pack. AI/custom text entry is a setup enhancement, not always a blocker.
- **Housie/Bingo on a TV is excellent with zero phones** — the TV calls numbers, players use *paper
  tickets*. That is how housie has always been played. Same for Musical Chairs (TV plays and stops
  the music) and several prompt/discussion games.

Important implementation boundary: the **current web runtime** still treats many games as
phone-controller rooms for scoring/input. The TV shell's `companion_mode: "none"` means "eligible
for the TV-primary/no-companion adaptation", not that every existing room screen has already been
rewired to remote-only control.

So availability is a function of **how many player devices are currently connected**, computed live:

| Tier | Devices | What unlocks | Examples |
|---|---|---|---|
| **0** | TV + remote only | Prompt/caller/discussion games. TV is the quizmaster; humans self-organise. No per-player scoring. | Housie, Bingo (+ occasion decks), Musical Chairs, Would You Rather, Never Have I Ever, This or That, Hot Takes, Story Chain, Two Truths |
| **1** | + one phone | Pass-and-play (private role reveals), typed AI topics, a comfortable host controller | Impostor, Odd Question, AI Quiz with a custom topic |
| **2** | + a phone each | Individually-scored games, per-player input | Quiz proper, Drawing, Poker, Acronym, Survey Says |

Photo games are **not** a fourth tier — no number of companion phones makes the TV able to host
them, because the *host* needs the camera. They are `tv_capability.hostable: false` /
`companion_mode: "phone_host"` and get the phone hand-off in §4b.

**Tiles must un-grey live as phones join.** A guest scanning the QR should visibly unlock games on
the TV. That teaches the whole model without a word of explanation, and it is the single most
valuable piece of feedback in the product.

## 3. Declaring capability (data model)

**Implementation refinement (2026-07-28): derive first, override narrowly.** The first draft used
per-entry `tv_requires` fields. That is too easy to let drift across 38+ games, and we have already
been burned by catalog drift. The implementation should derive a `tv_capability` object from
existing catalog metadata (`interaction`, `runtime_type`, `supports_images`,
`supports_ai_generation`, `default_content_available`, and `config_schema.players.min`) with a tiny
explicit override list for exceptions like `photo_clue`.

The public catalog shape should be:

```python
"tv_capability": {
    "hostable": True,                 # false only when TV lacks a host capability, e.g. camera
    "companion_mode": "none",         # none | shared_phone | per_player_phone | phone_host
    "min_companion_devices": 0,
    "private_screen": False,
    "text_input_for_customization": False,
    "reason_chip": "",               # computed user-facing chip when unavailable
}
```

`tv_requires` from the earlier draft folds into `companion_mode` + `min_companion_devices`.
Availability remains computed live from connected devices; catalog metadata describes what the
game needs, not whether it is playable in this particular room.

Add this to every catalog entry via a backend derivation step. **Derived availability wherever
possible, narrow override lists only for true capability exceptions** — three separate hardcoded
lists shipped the occasion bingos broken (see BACKLOG), so hidden per-screen allowlists are banned.

```python
# backend/tv_catalog.py — derived per entry
def derive_tv_capability(entry: dict) -> dict:
    ...
```

Shipped implementation:

- `backend/tv_catalog.py` derives the object above for every catalog entry.
- `PHONE_HOST_GAME_IDS = {"photo_clue"}` is the narrow non-TV-hostable override.
- `TV_REMOTE_ONLY_RUNTIMES` is an explicit product policy list for games with a viable
  TV-primary/no-companion adaptation. This list is allowed because it is a policy tier, not a
  duplicated catalog.
- Pass-and-play is derived from `interaction == "pass_and_play"` and requires one shared phone.
- Per-player games derive `min_companion_devices` from `config_schema.players.min`.

Availability is then computed, not stored:

```python
def tv_availability(entry: dict, connected_devices: int) -> dict:
    """Returns {playable, hostable, reasons[]}.

    `hostable: False` short-circuits — no device count fixes it, so the caller shows the
    phone hand-off sheet (§4b) rather than a join QR. Otherwise `reasons` lists the unmet
    companion needs, which map to user-facing copy.
    """
```

A companion `tv_playable_now(catalog, connected_devices)` powers the grid. Guard tests must assert
every launchable catalog entry has a derived `tv_capability`, and that every `supports_images` game
has been audited for hostability rather than treating image display as camera capture.

## 4. Two different kinds of "you can't play this", and two different answers

This distinction is the heart of the TV UX, and conflating the two produces the wrong prompt in
both cases. A game can be unavailable for two structurally different reasons:

| | **Unlockable** | **Not TV-hostable** |
|---|---|---|
| Meaning | TV *can* run it; the room just needs more devices | The TV can **never** run it — hosting it needs a phone capability the TV lacks |
| Declared by | `tv_capability` companion need unmet (§3) | `tv_capability.hostable: false` (§3) |
| Fix | Somebody scans and joins | Host plays it on their phone instead |
| Primary CTA | **Web join QR** — `/join/{code}`, no install | **App-store QR** — get the app on your phone |
| Why | Guests have never needed an install; a download would add friction to a solved problem | The TV is only a signpost here. The host is going to *leave* the TV to play, and the app is the thing worth having |

`tv_capability.hostable: false` is the narrow case: the **host** needs a camera or a capture
surface, not just a bigger screen. `photo_clue` is the clear member (host-side photo capture; a TV
has no camera). Games that merely *display* images (`quiz`, the bingo family) are fine — the TV is
the ideal display for those. **Audit every `supports_images` game against this before shipping**;
the flag is not a proxy for it.

### 4a · The unlock sheet (Unlockable)

```
┌──────────────────────────────────────────────┐
│  Impostor                                    │
│  Needs one phone to pass around              │
│      ▄▄▄▄▄▄▄   Scan with any phone           │
│      █ QR  █   games.revelryapp.me/join/HY2  │
│      ▀▀▀▀▀▀▀                                 │
│  No app needed — it opens in the browser.    │
│  ‹ Back to games                             │
└──────────────────────────────────────────────┘
```

### 4b · The "play on your phone" sheet (Not TV-hostable)

```
┌──────────────────────────────────────────────┐
│  Photo Clue                                  │
│  This one needs a phone camera —             │
│  play it on the Revelry Games app.           │
│                                              │
│   ▄▄▄▄▄▄▄            ▄▄▄▄▄▄▄                 │
│   █ QR  █            █ QR  █                 │
│   ▀▀▀▀▀▀▀            ▀▀▀▀▀▀▀                 │
│   App Store          Google Play             │
│                                              │
│  Your sparks work on both — sign in with     │
│  the same account.                           │
│                                              │
│  ‹ Back to games                             │
└──────────────────────────────────────────────┘
```

Two deliberate copy choices. It names the *reason* ("needs a phone camera") rather than saying
unsupported. And it reassures about **sparks carrying over**, because a host who has bought sparks on
the TV account will otherwise assume a phone install means paying twice — `tokens.get_wallet_id`
resolves to `user_id` when signed in, so it is genuinely the same wallet (§6).

**Strategic note — this is a funnel, not a dead end.** A host who found you on Fire TV (an uncrowded
store) gets pushed to install the *mobile* app for the games the TV can't run. TV distribution
feeding mobile installs is exactly the direction that's currently stalled at 0 installs, so this
sheet is worth building well rather than treating as an error state.

### 4c · Greyed tiles stay focusable

Do not skip unavailable tiles with the D-pad — a host needs to land on one and learn why. Skipping
them makes the app feel broken. Each carries a **reason chip**, not just dimming:

| Reason | Chip |
|---|---|
| `companion_mode: "shared_phone"` | "Needs 1 phone to pass around" |
| `companion_mode: "per_player_phone"` | "Needs phones to join" / "Needs a phone each" |
| `text_input_for_customization` | "Needs a phone to type" |
| `hostable: false` / `companion_mode: "phone_host"` | "Play on your phone" |

## 5. Screen inventory + flows

**S1 · Home / game grid** (D-pad primary surface; shipped as `/tv`)
- Row 1: **"Play now"** — only Tier-0-satisfied games, so a host with no phones has an obvious start.
- Row 2+: categories, including greyed tiles with reason chips.
- Persistent header: room code + a small QR once a room exists; connected-device count ("2 phones joined").
- A **"What can I play now?"** toggle filters to currently-playable.

**S2 · Unlock sheet** (§4a) and **S2b · Play-on-your-phone sheet** (§4b) — shipped as modal sheets.
The v1 phone-host sheet links to the mobile web join surface until final store URLs are configured.

**S3 · Room / lobby** (next slice)
- Giant QR + room code, readable across a room.
- Live joined list. Each new phone re-evaluates the grid.
- "Start" is enabled per the game's own minimum.

**S4 · In-game** — `SpectatorPage`'s existing views, TV-safe (§7). `/tv/:code` still goes here.

**S5 · Sign-in (optional, deferred)** — device-code pairing so sparks reach the TV (§6).

### Flow A — zero phones (must work)
1. Open app → S1 → "Play now" row → Housie.
2. Next slice: TV creates the room itself, goes straight to calling numbers with the auto-caller.
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
1. **Done:** Derived `tv_capability` on every launchable catalog entry + `tv_availability()` /
   `tv_playable_now()` helpers.
2. **Next:** TV creates rooms. Today only the organizer calls `POST /room/create`. Add a TV-origin path
   returning `{room_code, tv_token}`.
3. **Next:** Claim-host handshake. First phone to join a TV-created room becomes controller; later joiners
   are players. Needs a guard so a guest can't silently steal control mid-party.
4. **Next:** Short TTL for unclaimed TV rooms — a TV that creates rooms nobody claims will burn the
   `MAX_ROOMS` cap. Reuse the occupancy-qualified TTL work.
5. **Next:** Expose `connected_devices` in room sync so the TV can re-evaluate the grid live.

**7b · Frontend (TV shell)**
6. **Done:** `TvHomePage` — D-pad grid, focus model per §8, "Play now" filter, reason chips,
   search, and capability filters.
7. **Done:** `TvUnlockSheet` equivalent inside `TvHomePage` — §4, web-join QR primary.
8. **Next:** `TvRoomScreen` — giant QR + live joined list.
9. **Next:** TV-safe pass on `SpectatorPage`: 5% overscan margins, larger type, no hover states,
   no scrollbars.

**7c · Packaging**
10. Fire TV first (least friction): leanback manifest flags, TV banner, Amazon Appstore listing.
11. Google TV second, same codebase.

**7d · Tests**
- **Done:** Every launchable catalog entry receives a derived `tv_capability` (guard test).
- **Done:** `tv_availability` truth table across the no-phone/shared-phone/per-player/phone-host
  tiers.
- **Done:** A shared-phone tile appears when `connected_devices` increases in the TV shell.
- **Done:** Greyed tiles remain focusable because they are rendered as buttons, not skipped.
- **Done:** An **Unlockable** game's sheet shows the **web join URL**.
- **Done:** A **`tv_capability.hostable: false`** game's sheet explains the phone-camera handoff.
- **Next:** Replace the phone-host web QR with configured App Store / Google Play QR URLs and
  mention sparks carrying over once production store URLs are final.
- **Next:** Live WebSocket/device-count test once `TvRoomScreen` exists.

## 8. D-pad focus model (explicit, so it isn't invented per screen)

- Grid: 4 columns on 1080p, 5 on 4K. Left/Right within a row, Up/Down between rows, wrapping at ends.
- **Greyed tiles are focusable** (§4).
- `BACK` closes a sheet, then returns to the grid, then prompts before exit.
- Focus ring must be visible at 3 metres: 4px accent outline + scale, never colour alone.
- Long-press/`MENU` on a tile opens Rules (the metadata already exists).
- No element requires hover, right-click, or a text caret on the TV surface.

## 9. Deliberately out of scope for v1

Photo games hosted directly on TV, voice input, Tizen/webOS/tvOS/Roku, TV-store billing, casting
*from* the TV, per-player TV profiles.

## 10. Open questions for Avi

- **Un-signed-in TV**: free sparks per TV device (farmable) vs sign-in required to host (friction)?
- **Is Housie-on-TV-with-paper-tickets worth leading the store listing with?** It's the clearest
  "you need nothing but this TV" story, and it's a genuinely traditional way to play.
- **Rank against other install-getting work.** This is a marketing bet, not a feature bet. The
  question is whether a Fire TV listing beats the same effort spent elsewhere — currently unknown.
- **Store QR URLs:** confirm final App Store / Google Play URLs before replacing the v1 mobile-web
  handoff in the `phone_host` sheet.
