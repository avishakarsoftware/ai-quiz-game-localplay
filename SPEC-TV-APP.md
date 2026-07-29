# SPEC-TV-APP — the TV as the party's home, not its second screen

Status: **Product spec, not built (2026-07-28).** Avi's framing: install the app on the TV *instead
of* a phone, because that suits local play better. This spec takes that seriously and designs for
TV-primary, which is a different product from the TV-as-spectator-display we already ship.
Owner: Avi. Live status: DEPLOY.md's ledger once anything ships.

## 1. The reframe, and why it's the right one

We already support TV as a **secondary display**: `SpectatorPage` (live at
`games.revelryapp.me/spectator`) plus Chromecast with a registered receiver (`VITE_CAST_APP_ID`
`1BC9ACD8`) and a `CastButton`. That serves a host who already has the app on their phone.

TV-**primary** inverts it, and is a genuinely better fit for a living-room party:

| | Phone-primary (today) | TV-primary |
|---|---|---|
| Who installs | Every host, on their phone | **Once per household**, on the TV |
| Where the room code lives | On the host's phone, shown around | **On a 55" screen everyone can see** |
| Scanning the QR | Guests crowd round a phone | Everyone scans from their seat |
| Discovery | App Store, brutally crowded | **TV stores, far less crowded** |
| Social focus | A phone in someone's hand | The screen the room already faces |

The distribution argument is the strongest one, and it addresses the real bottleneck: **0 installs**
as of 2026-07-28. "Party games" on Fire TV / Google TV can get organic browse traffic that is
effectively unobtainable on mobile.

## 2. The role split (this is the whole design)

Three roles, and the good news is **two of them already exist as separate surfaces**:

| Role | Device | Status today |
|---|---|---|
| **Display + room owner** | The TV | `SpectatorPage` renders it; but it JOINS a room, it can't create one |
| **Controller (host)** | Host's phone | `OrganizerPage` already is exactly this |
| **Players** | Guests' phones | Already works — join by code, no install |

So TV-primary is **not** a rewrite. It is: let the TV create a room, and let a phone claim the host
controller role for it.

**The host's phone is the remote.** This is the key decision, and it dissolves the hardest problem
with TV apps (see §4). The TV never needs to be driven by a D-pad for anything but launching.

## 3. What the experience looks like

**First run (once per household)**
1. Install from the Fire TV / Google TV store. Open it.
2. TV shows a big **"Start a party"** and a game grid, D-pad navigable.
3. Optional: **"Sign in"** — shows a short code; the host signs in on their phone. This is how
   sparks reach the TV (see §4, monetization).

**Every party after that**
1. Host picks a game on the TV with the remote — or skips straight to step 2.
2. TV shows a **giant QR + room code**: *"Scan to join · or go to games.revelryapp.me and enter
   HY2HMO"*.
3. **First phone to scan becomes the host controller.** Their phone gets the OrganizerPage: game
   setup, start, next question, end. Everyone else joins as a player.
4. TV becomes the shared display for the whole party — questions, scores, reveals, podium.
5. Between games, the TV returns to the game grid and the room code persists.

**The pass-and-play combination (unexpectedly good)**
Impostor and the pass slate need a phone in hand, so TV-primary looks like a conflict. It isn't —
they **complement**: the TV shows the `GroupScreenFrame` phases (whose turn, the vote, the reveal)
while the single passed phone handles `PrivacyGate` role reveals. The TV becomes the table centre
and the phone stays the secret-holder. That is strictly better than either alone.

## 4. The hard parts, honestly

**Text input — the worst one.** Typing an AI quiz topic on a TV remote is miserable. Three options,
in order of preference:
1. **Phone as keyboard.** The host's phone already has the OrganizerPage; the topic prompt lives
   there. Costs nothing extra — it falls out of the role split.
2. **Curated topic tiles** on the TV for a no-phone path (you already have 38 games' worth of
   default content, so quick-start needs no typing at all).
3. Voice input. Platform-specific, do last or never.

**D-pad navigation.** `SpectatorPage` is 1,419 lines written for a passive display, so it needs no
focus management. The **game grid is the only D-pad surface** — that's the real scope of TV input
work, and it's small. Do NOT port `OrganizerPage` to the remote; that's what the phone is for.

**Monetization — and this is already solved.** TV billing (Amazon IAP, Google Play Billing for TV)
is a separate integration per store and a genuine tax. **We can skip it entirely:**
`tokens.get_wallet_id` already returns `user_id` when signed in, else `device_id` — so sparks follow
the *account*, not the device. The host buys on their phone (Stripe or mobile IAP, both live), signs
in on the TV once, and the TV spends from the same wallet. **No TV store billing, no new payment
rail, no extra store revenue share.** This is the single most important consequence of the existing
polymorphic wallet design.

**No camera on a TV.** `photo_clue` and any future photo game cannot be TV-hosted. Filter the TV
game grid by capability rather than hiding the games — the *players'* phones have cameras, so some
photo games may still work with the TV as display only. Decide per game; don't guess.

**Room ownership and abandonment.** A TV that creates rooms and never closes them will burn the
`MAX_ROOMS` cap. The occupancy-qualified lobby TTL already helps, but a TV-created room with nobody
claiming host needs its own short expiry.

## 5. Platform scope — do two, ignore four

| Target | Verdict |
|---|---|
| **Fire TV** | ✅ Do it. Android-based; the existing Capacitor APK is the starting point, Amazon Appstore accepts Android builds |
| **Google TV / Android TV** | ✅ Do it. Same codebase, needs a TV banner + leanback manifest bits |
| Samsung (Tizen) | ❌ Separate SDK, dev account, certification. A project in its own right |
| LG (webOS) | ❌ Same again, separate everything |
| Apple TV | ❌ No WebView — native rewrite |
| Roku | ❌ BrightScript only — full rewrite |

Two stores, one Android codebase. Everything else is a separate business decision, not an increment.

## 6. What's needed (the actual build)

Reusing what exists:
- ✅ `SpectatorPage` — the TV display, already built and live
- ✅ `OrganizerPage` — the phone controller, already built
- ✅ Player join by code — already built, no install for guests
- ✅ Cross-device wallet via sign-in — already built, dodges TV billing
- ✅ Capacitor Android build — the packaging starting point

New work:
1. **TV can create a room.** Today only the organizer does (`POST /room/create`). The TV needs to
   create-and-display, then hand the controller role to the first phone that claims it.
2. **A "claim host" handshake.** First scanner becomes controller; later scanners are players.
   Needs a guard so a guest can't silently steal control mid-party.
3. **A TV shell**: D-pad game grid, TV-safe margins, a device-code sign-in screen.
4. **TV-safe layout pass** on SpectatorPage — overscan margins, larger type, no hover states.
5. **Store packaging**: Fire TV + Android TV manifests, banners, leanback flags, two store listings.

## 7. MVP slice

1. Room creation from the TV + the claim-host handshake (backend + both surfaces).
2. TV shell with a D-pad game grid, defaulting to **quick-start games that need no typing**.
3. Device-code sign-in so sparks reach the TV.
4. Package for **Fire TV first** (least friction), one store listing, measure installs.
5. Only then consider Google TV, and only then anything else.

Deliberately out of scope for v1: photo games, voice input, Tizen/webOS/tvOS/Roku, TV-store billing.

## 8. Open questions for Avi

- **Does the TV need to work with no phone at all?** A fully remote-driven party (curated content
  only, no AI topics) is possible but constrains the product a lot. My instinct: no — the phone
  controller is a feature, not a compromise.
- **Who pays when the TV hosts?** The signed-in account. So an un-signed-in TV gets… what? Signup
  bonus sparks per TV device id is farmable across factory resets; requiring sign-in to host is
  safer but adds first-run friction.
- **Is this ahead of, or behind, getting 10 people playing on mobile?** This spec argues TV is a
  distribution *channel*, which makes it a marketing bet, not a feature bet. It should be ranked
  against other install-getting work, not against other features.
