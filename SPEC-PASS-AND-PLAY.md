# SPEC-PASS-AND-PLAY — one shared phone, everyone plays

Status: **Product spec, not yet built (2026-07-28).** No code exists. This documents the
interaction model, the flagship game (Impostor — the id is deliberately kept free for it, see
SPEC-GAME-ODD-QUESTION's naming history), and the slate of candidates.
Owner: Avi. Live status: DEPLOY.md's ledger once anything ships.

## 1. Why this is a platform feature, not a game

Every existing game assumes **one phone per player** plus an optional host/TV screen. That
assumption silently excludes real party guests: kids, grandparents, people whose phone is dead,
dinner tables where phones are away, and — per Avi — **teens already play exactly this way**
(one phone circulating is the native mode of Impostor, Truth-or-Dare apps, Paranoia).

Pass-and-play inverts the model: **the room has one phone** (usually the host's), and the game is
built around handing it person to person. That needs a small set of shared UX primitives — not
per-game inventions:

| Primitive | What it does | Why it must be shared |
|---|---|---|
| **Seat list without devices** | Host types player names at setup; seats exist with no socket | Every pass game needs a roster; joining-by-QR is exactly what these players can't do |
| **Pass screen** | Full-screen "Pass the phone to **Maya** 🥭" between turns; nothing sensitive rendered | The privacy boundary between two players' hands |
| **Privacy gate** | "Tap and hold to reveal — make sure only you can see" → reveal → "Got it, hide & pass" | Secret roles/words die instantly without a deliberate reveal step |

**Refinement (2026-07-28, found while building Impostor):** "privacy is a UI gate, not a payload
filter" is right about per-VIEWER scoping (meaningless with one device) but wrong if read as
"always send everything". The client genuinely needs every role during the reveal pass, and
genuinely should not have the secret while the phone is face-up on a table. So disclosure is
scoped **by phase**, not by viewer: `public_state` ships a `roles` map only during the
gated reveal phase, and empties it for every face-up phase. Secrets travel exactly when a gate is
mounted to hold them. Pinned by `TestPhaseScopedDisclosure`.
| **Turn order engine** | Rotation with skip/insert (someone leaves the table) | Same logic every pass game repeats |
| **Group screen mode** | Some phases are face-up for the whole table (voting recap, timers, reveals) | The phone alternates between "secret hand" and "shared table centre" |

Existing plumbing that carries over unchanged: room creation/sparks, the host screen/Chromecast as
an optional shared display, game history/stats (`record_game_completion` — the host wallet
attribution model is *exactly* right here, since only the host has a device), share cards.

What does NOT carry over: WebSocket-per-player sync, reconnect/seat grace (there are no player
sockets), per-viewer payload scoping (privacy is physical, enforced by the privacy gate instead).
That's why this is cheaper than it looks — a pass game is nearly a single-client state machine.

## 2. Flagship: Impostor (the real one)

The teen-popular secret-word game. **This is why the `impostor` id was kept free.**

- Setup: host enters player names (3–12). Category chosen or AI-generated word pair.
- Everyone except one player is shown the **secret word** via the privacy gate; the impostor is
  shown "You are the IMPOSTOR — bluff!" (optionally a decoy category hint).
- Phone goes face-up on the table. In turn order, each player **says one word aloud** related to
  the secret word — vague enough not to tip the impostor, specific enough to prove they know it.
  The phone just shows whose turn it is (+ optional round timer).
- After N spoken rounds: discussion, then a **table vote** — tap the accused's name on the shared
  screen (or vote by pointing; the phone records the outcome).
- Reveal: impostor caught → word-knowers win; impostor survives *or* correctly guesses the secret
  word when caught → impostor wins (the classic comeback rule).
- Content = word pairs per category (secret word + near-miss decoy for the impostor variant),
  AI-generatable with the existing Gemini path; curated packs first, same policy as Odd Question.

Mechanically this shares DNA with `odd_question_engine` (hidden minority role, majority/minority
information, vote, strict-majority catch) — but the interaction layer is pass-and-play, and the
clues are spoken, not typed. Engine reuse is plausible; don't force it.

## 3. The slate (in rough build order)

| Game | One-liner | Why it fits pass-and-play |
|---|---|---|
| **Impostor** 🎭 | Everyone knows the word but one; spoken one-word clues; vote | The genre-defining phone-circle game; teens already know the rules |
| **Paranoia** 🤫 | Whisper a question, say the answer aloud, flip a coin to reveal the question | Literally built on selective information + one device |
| **Hot Seat** 🔥 | Phone picks a player + a question the table asks them | `chit_pull` engine is ~this already; pass mode is mostly UX |
| **Truth or Dare** 😈 | Classic, with AI-generated age-appropriate decks | Existing chit/deck machinery; the definitive sleepover game |
| **Forehead Guess** 🙃 | Hold the phone to your forehead, table gives clues | `who_am_i` content reused; needs tilt-to-answer natively later |
| **Wavelength-ish** 🌡️ | Psychic guesses where a hidden target sits on a spectrum; table debates | One screen alternating secret/shared; great mixed-age game |

Existing games that gain a cheap **pass mode** (same engine, new shell): `chit_pull`,
`never_have_i_ever` (show of hands instead of taps), `wmlt` (point at people), `two_truths`
(spoken statements, phone only tracks scores).

## 4. MVP slice (when this gets built)

1. The five primitives as shared components (`PassScreen`, `PrivacyGate`, seat-roster setup,
   turn engine, group-screen frame) — built once, themed Velvet.
2. **Impostor** as the first game on top of them, curated word packs only.
3. Catalog entry with a new `interaction: "pass_and_play"` field so the picker can badge these
   games ("One phone — no downloads for guests") — that badge is itself a selling point in a
   store listing: it's the answer to "what if my friends won't install anything?"
4. No per-player sockets, no reconnect logic, no per-viewer scoping — deliberately.

Open questions for Avi: age-rating implications of Truth-or-Dare content (IARC is already
Teen/PEGI-18 in places); whether pass-and-play rooms should cost fewer sparks (no server fan-out);
whether the host screen should mirror the group-screen phases to the TV.
