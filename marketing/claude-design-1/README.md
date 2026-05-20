# Handoff: LocalPlay Redesign

A premium party-games living room — TV host + mobile player surfaces, multi-game library, five aesthetic directions to choose from.

---

## About the Design Files

The files in this bundle are **design references created in HTML** — visual prototypes built with React + Babel showing the intended look, layout, copy, and behaviour of the redesign.

They are **not production code to copy directly**. The task is to **recreate these designs in LocalPlay's existing codebase** (React + TypeScript + Vite, based on the `src/` folder structure observed: `src/pages/PlayerPage.tsx`, `src/types.ts`, `src/components/`, `src/context/`, `src/hooks/`, etc.), using its established patterns, theme tokens, and conventions.

Where the prototype invents component primitives (`<Avatar>`, `.answer`, `.btn-primary`, etc.), map them to whatever the real codebase already uses; only fall back to the prototype's CSS if no equivalent exists.

---

## Fidelity

**High-fidelity (hifi).** Exact colours, type, spacing, copy, and motion are specified throughout. The interactive loop in `LocalPlay Redesign.html` is the source of truth for screen states and transitions. Recreate the UI pixel-perfectly using the codebase's existing libraries and patterns.

---

## What's in the design

### Surfaces

1. **TV host view** — 1280 × 720, rendered in a browser fullscreen / Chromecast context. Big-screen typography, room code + QR, leaderboards, podiums. URL pattern: `localplay.fm/tv/<code>`.
2. **Phone player view** — iPhone-class (≈390 × 740 viewport inside Safari). Per-player control surface: lobby, answer input, hit/skip buttons, personal podium card.

The two surfaces are **synced** by room code (`PLAY42` in the demo) — every screen has a TV component **and** a phone component for the same phase of the same game.

### Game library

Six games (existing two + four new). The chapter Roman numerals and glyphs are decorative; carry whatever IDs the backend already uses.

| ID | Name | Status | Pace | Players | Tagline |
|---|---|---|---|---|---|
| `quiz` | Trivia | existing | 6–8 min | 2–30 | Bring-your-own-topic AI quiz |
| `wmlt` | Most Likely To | existing | 4–6 min | 3–12 | Vote on each other, no wrong answers |
| `pictionary` | Pictionary | **New** | 8–12 min | 3–12 | Draw on your phone, group guesses |
| `taboo` | Taboo | **New** | 5 min | 4–10 | Get your team to say the word — without saying it |
| `whispers` | Whispers | **New** | 6 min | 4–12 | Pass a phrase down the chain. Watch it mutate. |
| `fibbage` | Bluff | Soon | 10 min | 3–12 | Write a fake answer. Fool everyone. |

### Game phases (state machine)

Every game runs through the same phase sequence; the per-game `asking`/`revealing` screens differ, the rest are shared.

```
lobby → intro (3-2-1) → asking → revealing → leaderboard → (next round, or) podium
```

| Phase | Duration (demo) | TV | Phone |
|---|---|---|---|
| `lobby` | until host starts | Big room code, QR, joining player chips streaming in | Avatar, name, "Waiting…" |
| `intro` | 2.5 s | Round counter, large 3-2-1 countdown | "Get ready" |
| `asking` | 15 s | Question/prompt, answer grid, ring timer | Per-game input (see below) |
| `revealing` | 4 s | Correct answer highlighted, +pts animation | Right/wrong card, points earned |
| `leaderboard` | 5 s | Horizontal bar chart, top of table, delta arrows | Your rank, your score |
| `podium` | until exit | Three-step podium, four awards | Personal card, awards earned, "Play again" |

### Per-game asking/revealing differences

- **Trivia** — 4 answer cards (A/B/C/D), one correct. Phone has 4 large tappable tiles + power-up bar (`double_points`, `fifty_fifty`).
- **Most Likely To** — single statement, 8 player tiles to vote on. Phone shows an 8-tile player grid; "Cleo" is the demo's pre-selected vote.
- **Pictionary** — TV shows the live drawing canvas with the drawer's name; phone shows live guesses streaming with a hit/miss indicator and a text input. The drawer's phone shows the word + tools.
- **Taboo** — Big word (e.g. `TELESCOPE`), five forbidden tags below. Phone has HIT / SKIP / NEXT buttons.
- **Whispers** — TV reveals the chain message-by-message. Phone shows your turn to read & retell. The example chain is in `src/data.jsx` → `WHISPERS_PHRASE`.

---

## Five aesthetic directions (themes)

The prototype ships **five complete themes**, switchable via the Tweaks panel. The real product will ship **one** — pick (or let the user pick) and lift its tokens into the existing theme system.

Each theme overrides the same CSS-variable contract:

```css
--bg / --bg-2 / --paper       /* surfaces */
--ink / --ink-2 / --ink-mute  /* text */
--rule / --rule-2             /* dividers */
--accent / --accent-ink       /* primary action */
--olive / --plum / --gold     /* secondaries (correct / category / highlight) */
--shadow                      /* signature elevation */
--font-display / --font-body / --font-mono
```

### A · Salon — editorial premium
Warm cream paper, terracotta accent, Newsreader serif headlines.

| Token | Value |
|---|---|
| `--bg` | `#F4EEE4` |
| `--bg-2` | `#EBE2D2` |
| `--paper` | `#FBF7EF` |
| `--ink` | `#1A1714` |
| `--ink-2` | `#3A3328` |
| `--ink-mute` | `#8A7C66` |
| `--rule` | `#D6CBB8` |
| `--accent` | `#B95536` (terracotta) |
| `--accent-ink` | `#FFFCF6` |
| `--olive` | `#586A3B` |
| `--plum` | `#6E3F4D` |
| `--gold` | `#C99641` |
| Display | Newsreader 400, tight tracking |
| Body | Hanken Grotesk |
| Mono | JetBrains Mono |
| Shadow | `0 1px 0 rgba(26,23,20,0.06), 0 12px 32px -16px rgba(26,23,20,0.18)` |
| Buttons | 6 px radius, solid ink primary |
| Cards | 1 px hairline border, paper fill |

### B · Velvet — late-night lounge
Midnight purple + neon magenta/mint. Bricolage Grotesque display.

| Token | Value |
|---|---|
| `--bg` | `#0A0612` |
| `--bg-2` | `#14091F` |
| `--paper` | `#1A0F2A` |
| `--ink` | `#F8EBD9` |
| `--accent` | `#FF2E7A` (hot magenta) |
| `--olive` | `#6DFFE6` (mint — used for "correct") |
| `--plum` | `#B57AFF` |
| `--gold` | `#FFC76B` |
| Background | Page has two radial-gradient blooms (top-left magenta, bottom-right mint) |
| Buttons | Pill (`border-radius: 100px`), uppercase, neon glow shadow |
| Cards | 14 px radius, dark fill, 10 % white inner border |

### C · Playground — confident pop
Paper white, chunky black borders, coral + electric blue. Bricolage Grotesque display.

| Token | Value |
|---|---|
| `--bg` | `#F2EEE5` |
| `--paper` | `#FFFFFF` |
| `--ink` | `#0A0B0E` |
| `--accent` | `#FF4D2D` (coral) |
| `--olive` | `#2D5BFF` (electric blue) |
| `--gold` | `#D6FF3F` (lime, used for "correct") |
| Background | Polka-dot pattern: `repeating-radial-gradient(circle at 0 0, transparent 0 38px, var(--bg-2) 38px 39px)` |
| Borders | 2–2.5 px solid ink everywhere |
| Buttons | 12 px radius, `box-shadow: 4px 4px 0 var(--ink)` (offset hard shadow) |
| Avatars | Player-hue fill with hard 2.5 px ink border |

### D · Arcade — CRT cabinet (new)
Near-black + neon green, scanlines, all-mono terminal type.

| Token | Value |
|---|---|
| `--bg` | `#07080C` |
| `--bg-2` | `#0E1119` |
| `--paper` | `#12161F` |
| `--ink` | `#E8FFE3` |
| `--accent` | `#38FF6B` (neon green) |
| `--plum` | `#FF3FE0` (hot pink secondary) |
| `--gold` | `#00E0FF` (cyan tertiary) |
| Display / Body / Mono | **All** JetBrains Mono |
| Background | Two-pixel scanline overlay + vignette + soft top bloom |
| Borders | 1 px hairline ringed in accent on focus, phosphor glow on highlight |
| Buttons | Square (radius 0), uppercase mono, double-glow shadow |

### E · Garden — botanical zine (new)
Sage paper, dusty rose, deep-forest ink. Newsreader display like Salon but softer mood.

| Token | Value |
|---|---|
| `--bg` | `#EEF2E6` |
| `--bg-2` | `#DEE6D0` |
| `--paper` | `#F8FAF1` |
| `--ink` | `#1F2E22` |
| `--accent` | `#C8506D` (dusty rose) |
| `--olive` | `#5A7A3E` (moss — used for "correct") |
| `--plum` | `#8B5E96` (iris) |
| `--gold` | `#D9A441` (honey) |
| Display | Newsreader serif |
| Buttons | Pill (`999px`), gentle rose primary |
| Cards | 14 px radius, sage hairline, no hard shadows |

---

## Avatars — emoji system (matches existing `src/types.ts`)

The redesign **uses the existing `AVATAR_EMOJIS` palette unchanged** (56 emoji, see `src/types.ts`). The prototype shows them rendered as **disc tiles** sized 24 – 88 px depending on context, with the emoji glyph filling ~62 % of the disc.

- Lobby chips: 26 px disc
- Player grid (Most Likely To): 48 px
- Mid-question hit/skip rows: 24 px
- Leaderboard rows: 36 px
- Podium 1st place: 88 px, 2nd/3rd: 64 px
- Awards strip: 28 px

**"You" indicator** — never swap the disc fill (it would hide the emoji). Instead, render a 2 px outer ring + glow in the theme's `--accent` colour.

Per-player hue (used only by Playground theme as the disc background) lives next to the player in app state. Demo roster + hues in `src/data.jsx` → `PLAYERS`.

---

## Component spec

### `<Avatar>` (`src/screens.jsx`)
```ts
type Props = {
  player: { name: string; avatar: string; hue: number };
  size?: number;       // default 32
  you?: boolean;       // adds the highlight ring
};
```
Inside: a round `<span class="av">`, emoji glyph as a child `<span class="av-emoji">`, screen-reader-only `<span class="visually-hidden">{name}</span>`. Sets `--av-pg-bg: oklch(72% 0.18 <hue>)` inline so Playground theme can read it.

### `<PlayerChip>` (`src/screens.jsx`)
Pill containing an avatar + name. Used in lobby player rosters and inline references.

### `<TimerRing>` (`src/screens.jsx`)
Circular SVG progress ring. Used on every `asking` TV screen. Props: `progress` (0 – 1), `size`, `stroke`, `label`.

### `.answer` (CSS, in `src/styles.css`)
The answer-card primitive. Variants: default, `:hover`, `.correct`, `.wrong` (faded). Each theme overrides — see `src/styles.css` for exact values. Layout: flex row, `gap: 16`, `padding: 18 22`, `font-size: 18`, font weight 500.

### `.btn-primary` / `.btn-ghost`
- Salon: 6 px radius, solid ink fill.
- Velvet: pill, magenta fill, neon glow.
- Playground: 12 px radius, coral fill, offset hard shadow.
- Arcade: square, mono uppercase, phosphor glow.
- Garden: pill, dusty rose, no shadow.

### `.progress`
2 – 8 px bar. Playground uses an 8 px bar with 2 px ink border. Arcade uses 2 px with phosphor glow on the fill. Filled width = `progress * 100%`.

---

## Screens — detailed inventory

Each screen has a TV component and a phone component (15 screens × 2 surfaces = 30 React components). All live in `src/screens.jsx`.

| TV component | Phone component | Used for | Props |
|---|---|---|---|
| `TVLibrary` | — | Pre-game home (host browses games) | — |
| `TVLobby` | `PhoneLobby` | Room code, QR, joining players | `code`, `joined` |
| `TVIntro` | `PhoneIntro` | 3-2-1 round countdown | `round`, `total`, `progress` |
| `TVQuiz` | `PhoneQuiz` | Trivia question | `phase`, `progress`, `answers` |
| `TVWmlt` | `PhoneWmlt` | Most Likely To prompt + voting | `phase`, `progress`, `answers` |
| `TVPictionary` | `PhonePictionary` | Drawing canvas + guesses | `phase`, `progress` |
| `TVTaboo` | `PhoneTaboo` | Big word + forbidden tags | `phase`, `progress` |
| `TVWhispers` | `PhoneWhispers` | Chain reveal | `phase`, `progress` |
| `TVLeaderboard` | `PhoneLeaderboard` | Mid-game standings | — |
| `TVPodium` | `PhonePodium` | Final result + awards | — |

The phase-to-component routing is in `src/app.jsx` → `PhaseScreen()`. Use it as the spec for how the app should switch screens on phase transitions.

---

## Interactions & motion

- **Lobby player chips** stream in with a 60 ms-staggered `lp-fade-in` (`opacity 0 → 1, translateY 4px → 0` over 400 ms ease).
- **Intro countdown** counts 3 → 2 → 1 at 1 s ticks.
- **Asking phase**: timer ring fills clockwise. As each player answers, the "X of N answered" counter increments and their hit row fades in.
- **Revealing**: incorrect cards drop to `.wrong` (opacity 0.32 – 0.45 depending on theme); correct card animates to its theme's "correct" treatment (Salon → olive fill, Velvet → mint glow, Playground → lime fill, Arcade → phosphor glow, Garden → moss fill). Points push to the leaders with a `+pts` chip.
- **Leaderboard bars** grow from left to width `score / max * 100%` over ~600 ms ease-out.
- **Podium** reveals 3rd → 2nd → 1st (~300 ms apart); awards strip cross-fades in after.

Timings are encoded in `src/data.jsx` → `PHASE_DURATIONS`. Use them as a starting point, not gospel.

---

## State

The prototype's simulation hook (`useGameSim` in `src/data.jsx`) is **demo-only** — it auto-loops phases on a timer. In production, the host's screen and each player's screen subscribe to the same realtime room state.

Minimum state shape the screens need:

```ts
type RoomState = {
  code: string;                          // 'PLAY42'
  phase: 'lobby'|'intro'|'asking'|'revealing'|'leaderboard'|'podium';
  game: 'quiz'|'wmlt'|'pictionary'|'taboo'|'whispers'|'fibbage';
  round: { number: number; total: number };
  players: Array<{ name: string; avatar: string; hue: number; score: number; rank: number; delta: number }>;
  prompt: object;                        // shape varies per game — see src/data.jsx
  answers: Record<string, { choice: number; time: number }>;  // by player name
  timer: { startedAt: number; durationMs: number };           // → progress = (now - startedAt) / durationMs
};
```

Per-player additional state for the phone surface: `me: PlayerInfo`, `powerUps: { double_points: bool; fifty_fifty: bool }` (matches existing `src/types.ts → PowerUps`).

---

## Design tokens — consolidated

### Spacing scale (from observed CSS)
`4, 6, 8, 10, 12, 14, 16, 18, 20, 22, 24, 28, 32, 36, 40, 48, 60, 80, 88` px. Use multiples of 4 throughout.

### Radii
- 0 (Arcade), 4, 6 (Salon), 8, 12 (Playground), 14 (Velvet, Garden cards), 100 / 999 (pills), 50 % (avatars).

### Type scale
- Display: 28, 36, 48, 64, 88, 96 px
- Body: 14, 15, 16, 17, 18 px
- Eyebrow / mono labels: 10, 11, 12 px, tracking 0.12 – 0.16 em, uppercase
- Numerals: always `font-variant-numeric: tabular-nums` (`.num` class)

### Fonts (Google Fonts — already loaded in the prototype `<head>`)
- Newsreader (Salon, Garden display)
- Hanken Grotesk (all body)
- Bricolage Grotesque (Velvet, Playground display)
- JetBrains Mono (all mono; Arcade uses it everywhere)

---

## Files in this bundle

| File | Purpose |
|---|---|
| `LocalPlay Redesign.html` | Root document — wires React, fonts, and all `src/` modules together. |
| `src/app.jsx` | Top-level `App` — intro panel, prototype stage, design canvas, Tweaks panel. Phase-to-component routing lives in `PhaseScreen`. |
| `src/data.jsx` | Player roster (with emoji avatars + hues), game catalog, sample question data per game, demo leaderboard/podium scores, awards, and the `useGameSim` simulation hook. |
| `src/screens.jsx` | All 30 screen components (TV + phone for every phase × game), plus `<Avatar>`, `<PlayerChip>`, `<TimerRing>`, `<FauxQR>`. **Most of the design fidelity lives here.** |
| `src/styles.css` | All five theme blocks, layout primitives, button / card / answer / progress variants per theme. |
| `src/design-canvas.jsx` | The pan/zoom canvas at the bottom of the page comparing themes side-by-side (prototype scaffolding — not needed in production). |
| `src/tweaks-panel.jsx` | The floating Tweaks panel (prototype scaffolding — not needed in production). |
| `src/ios-frame.jsx` | iPhone bezel for the phone preview (prototype scaffolding). |
| `src/browser-window.jsx` | Browser chrome around the TV preview (prototype scaffolding). |

To open the prototype: serve the folder over HTTP (the JSX uses Babel standalone at runtime) and open `LocalPlay Redesign.html`. The interactive loop runs automatically; the Tweaks toggle in the toolbar lets you switch theme, game, and phase.

---

## Implementation order — suggested

1. **Decide on the theme** (or expose theme switching, if that's part of the product). Lift its tokens into the existing CSS-variable system.
2. **Avatar primitive** — confirm the existing one renders the emoji at all the sizes listed above; if it currently does monograms (the previous design did), update it.
3. **Phase router** — wire `RoomState.phase + RoomState.game` to the right screen component pair, matching `PhaseScreen` in `src/app.jsx`.
4. **Build the shared phases first** (`lobby`, `intro`, `leaderboard`, `podium`) — they're identical across all games.
5. **Then per-game** (`asking` + `revealing`) — Trivia and Most Likely To exist already; Pictionary, Taboo, Whispers are new.
6. **Wire timer / progress** to the realtime room state's `startedAt + durationMs`.
7. **Motion pass** — the staggered fades, ring fills, podium reveal sequence.

---

## Open questions / decisions for the team

- **Which theme(s) ship?** All five are production-quality CSS; product/brand picks.
- **Realtime layer** — is the existing socket message format rich enough to deliver the new game types' prompts (Pictionary stroke data, Taboo forbidden tags, Whispers chain)?
- **Drawing canvas** — Pictionary needs a touch-friendly drawing surface on the phone + a live-rendering canvas on the TV. The prototype only shows the visual treatment, not the input pipeline.
- **Power-ups** — the prototype shows `double_points` and `fifty_fifty` as visible chips on the phone Quiz screen until the player picks. Confirm the power-up roster is unchanged.
