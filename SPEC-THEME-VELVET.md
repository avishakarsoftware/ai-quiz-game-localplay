# LocalPlay Velvet Theme Redesign Spec

## Overview

Replace the current "game show purple" aesthetic with **Velvet** — a late-night lounge theme with midnight purple, neon magenta, electric mint, and warm cream text. This is primarily a frontend change. Backend APIs and WebSocket message contracts should stay unchanged; a small frontend-only `INTRO` presentation state is allowed.

The redesign also introduces a proper **TV host surface** (reworked SpectatorPage) alongside the existing phone player and organizer views.

Design reference: `marketing/claude-design-1/` — specifically `src/screens.jsx`, `src/styles.css`, and `src/data.jsx`.

Important: the marketing prototype is visual guidance, not production code. Recreate the intent inside LocalPlay's existing React/TypeScript structure, accessibility patterns, route model, auth/payment UX, and game state machines. Do not copy prototype-only fake games, demo data, URLs, or timing assumptions into production unless the current backend supports them.

## Implementation Principles

- Preserve current product behavior first: quiz and WMLT must remain playable from organizer, player, and spectator views.
- Ship this as a design-system migration plus screen-by-screen restyle, not as a rewrite of gameplay logic.
- Keep visual density appropriate to each surface: player phone screens are direct controls, organizer screens are operational controls, spectator screens are TV presentation.
- Maintain mobile safe areas, installable PWA behavior, and IONOS `/quiz/` base path.
- Keep all text legible at current supported breakpoints. Validate narrow phones, desktop organizer, and 1280×720 TV.
- Avoid adding backend persistence or new WebSocket messages as part of this theme work.

---

## Phase 1: Theme System

### CSS Variable Contract

Add the Velvet token set in `index.css`, then keep a compatibility layer for the existing variable names while the screen migration is in progress. The current app references `--bg-primary`, `--accent-primary`, `--glass-bg`, `--text-tertiary`, and similar names in many components and Tailwind arbitrary values. Removing them up front will create invisible text and broken colors.

```css
:root {
  /* Surfaces */
  --bg:         #0A0612;
  --bg-2:       #14091F;
  --paper:      #1A0F2A;

  /* Text */
  --ink:        #F8EBD9;
  --ink-2:      #E5D7C2;
  --ink-mute:   rgba(248, 235, 217, 0.45);

  /* Dividers */
  --rule:       rgba(248, 235, 217, 0.10);
  --rule-2:     rgba(248, 235, 217, 0.35);

  /* Primary action */
  --accent:     #FF2E7A;
  --accent-ink: #1A0612;

  /* Semantic colors */
  --olive:      #6DFFE6;   /* correct / success — electric mint */
  --plum:       #B57AFF;   /* category / info — lilac */
  --gold:       #FFC76B;   /* highlight / warning */

  /* Elevation */
  --shadow: 0 0 40px -10px rgba(255,46,122,0.35), 0 20px 60px rgba(0,0,0,0.5);

  /* Typography */
  --font-display: 'Bricolage Grotesque', sans-serif;
  --font-body:    'Hanken Grotesk', sans-serif;
  --font-mono:    'JetBrains Mono', monospace;

  /* Temporary compatibility aliases. Delete only after rg confirms no usage. */
  --bg-primary: var(--bg);
  --bg-secondary: var(--bg-2);
  --bg-tertiary: rgba(248, 235, 217, 0.08);
  --bg-elevated: var(--paper);
  --bg-gradient: none;
  --glass-bg: var(--paper);
  --glass-border: var(--rule);
  --glass-blur: blur(0px);
  --accent-primary: var(--accent);
  --accent-secondary: var(--plum);
  --accent-success: var(--olive);
  --accent-warning: var(--gold);
  --accent-danger: var(--accent);
  --text-primary: var(--ink);
  --text-secondary: var(--ink-2);
  --text-tertiary: var(--ink-mute);
  --text-quaternary: rgba(248, 235, 217, 0.28);
  --separator: var(--rule);
}
```

Exit criterion for removing aliases:

```bash
rg "var\\(--(bg-primary|bg-secondary|bg-tertiary|bg-elevated|bg-gradient|glass-bg|glass-border|glass-blur|accent-primary|accent-secondary|accent-success|accent-warning|accent-danger|text-primary|text-secondary|text-tertiary|text-quaternary|separator)" frontend/src
```

Remove an alias only when the search no longer finds production usage.

### Background Treatment

The page background uses two broad radial gradient washes instead of the current solid purple. Keep them subtle; they should read as ambient lighting, not decorative orbs.

```css
body {
  font-family: var(--font-body);
  color: var(--ink);
  background:
    radial-gradient(ellipse 80% 60% at 20% 0%, rgba(255,46,122,0.15) 0%, transparent 60%),
    radial-gradient(ellipse 80% 60% at 80% 100%, rgba(109,255,230,0.10) 0%, transparent 60%),
    var(--bg);
}
```

TV surface gets additional blooms:

```css
.tv-surface::before {
  content: '';
  position: absolute;
  inset: 0;
  background:
    radial-gradient(ellipse 60% 50% at 20% 30%, rgba(255,46,122,0.20) 0%, transparent 70%),
    radial-gradient(ellipse 50% 40% at 85% 75%, rgba(109,255,230,0.12) 0%, transparent 70%);
  pointer-events: none;
}
```

Phone surface:

```css
.phone-surface {
  background:
    radial-gradient(ellipse 90% 50% at 50% 10%, rgba(255,46,122,0.20) 0%, transparent 70%),
    var(--bg);
}
```

### Font Loading

Preferred implementation: self-host font files under `frontend/public/fonts/` and define `@font-face` in `index.css` so the PWA remains stable and avoids a third-party runtime dependency. If self-hosting is not done in the first implementation pass, Google Fonts may be used temporarily in `index.html`, but track a follow-up to self-host before release.

Temporary Google Fonts option:

```html
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:wght@400;600;700&family=Hanken+Grotesk:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
```

### Variable Migration Map

| Old variable | New variable | Notes |
|---|---|---|
| `--bg-primary` (#46178F) | `--bg` (#0A0612) | Much darker |
| `--bg-secondary` | `--bg-2` (#14091F) | |
| `--bg-elevated` | `--paper` (#1A0F2A) | Card backgrounds |
| `--accent-primary` (#6C5CE7) | `--accent` (#FF2E7A) | Purple → hot magenta |
| `--accent-secondary` (#A29BFE) | `--plum` (#B57AFF) | |
| `--accent-success` (#26DE81) | `--olive` (#6DFFE6) | Green → electric mint |
| `--accent-warning` (#FF9F43) | `--gold` (#FFC76B) | |
| `--accent-danger` (#FF6B6B) | `--accent` (#FF2E7A) | Danger uses accent in Velvet |
| `--text-primary` (#FFFFFF) | `--ink` (#F8EBD9) | White → warm cream |
| `--text-secondary` | `--ink-2` (#E5D7C2) | |
| `--text-tertiary` | `--ink-mute` | |
| `--glass-bg` | `--paper` | No more glassmorphism |
| `--glass-border` | `--rule` | |
| `--separator` | `--rule` | |

### What Gets Deprecated

- Glassmorphism as a dominant visual language (`backdrop-filter: blur`, semi-transparent white panels). A very subtle overlay is allowed only for drawer/backdrop readability.
- The current purple-heavy `--bg-gradient`.
- Direct use of old token names in components. Keep aliases during migration, then remove once all references are converted.
- System font stack as the primary brand typography. Keep native fallbacks after Hanken/Bricolage/JetBrains.
- Colored answer buttons (red/blue/yellow/green). Replace with unified dark cards and neutral letter glyph badges.
- `ANSWER_STYLES` as a visual source of truth. Do not delete it until all components/tests stop importing it; instead introduce an answer-label helper (`A/B/C/D`) and migrate callers.
- Existing `@keyframes` in `index.css`: audit each. Keep functional animations (timer pulse, score pop), replace decorative ones with Velvet equivalents, remove unused.

---

## Phase 2: Shared Components

### `<Avatar>`

Emoji rendered inside a disc. Current code likely renders emoji inline; this needs a proper component.

```tsx
type AvatarProps = {
  player: { name?: string; nickname?: string; avatar?: string; hue?: number };
  size?: number;       // default 32
  you?: boolean;       // accent ring + glow
  fallbackText?: string;
};
```

**Rendering:**
- Round `<span>` with `width`/`height` = size, `border-radius: 50%`
- Background: `var(--bg-2)`
- Emoji child `<span>` at ~62% of disc size
- If no emoji exists, fall back to initials derived from `nickname`, `name`, or `fallbackText`
- Include an accessible label for the player name when the avatar is not purely decorative
- Default ring: `box-shadow: 0 0 0 1.5px var(--accent), 0 0 16px rgba(255,46,122,0.35)`
- "You" ring: `box-shadow: 0 0 0 2px var(--accent), 0 0 24px rgba(255,46,122,0.65)`

**Size chart:**

| Context | Size |
|---|---|
| Lobby player chips | 26px |
| WMLT player grid (phone) | 32px |
| WMLT player grid (TV) | 48px |
| Leaderboard rows (phone) | 28px |
| Leaderboard rows (TV) | 36px |
| Phone lobby self-avatar | 80px |
| Podium 2nd/3rd | 64px |
| Podium 1st | 88px |
| Awards strip | 28px |

### `<PlayerChip>`

Avatar + name pill. Used in lobby rosters and inline references.

```tsx
type PlayerChipProps = {
  player: { name?: string; nickname?: string; avatar?: string };
  you?: boolean;
};
```

**Rendering:**
- `display: inline-flex`, `align-items: center`, `gap: 8px`
- `padding: 6px 14px 6px 6px`
- `border: 1px solid var(--rule-2)`, `border-radius: 100px`
- If `you`: `background: var(--accent)`, `color: var(--accent-ink)`
- Avatar at 26px
- Name: `font-weight: 500`, `font-size: 14px`
- Entry animation: `lp-fade-in` class (opacity 0→1, translateY 4→0, 400ms ease), staggered by 60ms per player

### `<TimerRing>` (existing — restyle)

The component already exists at `components/TimerRing.tsx`. Update the styling:

- Stroke colors:
  - Normal (>10s): `var(--accent)` (#FF2E7A)
  - Warning (≤10s): `var(--gold)` (#FFC76B)
  - Danger (≤5s): `var(--accent)` with pulse animation
- Track (background circle): `var(--rule)` (10% white)
- Center number: `font-family: var(--font-mono)`, color `var(--ink)`
- Sizes: 80px (phone default), 120px (TV question), 140px (TV pictionary/taboo)

### Answer Cards

Replace the current colored answer buttons (`.answer-red`, `.answer-blue`, etc.) with a unified card style. Use semantic class names that do not conflict with native answer elements, for example `.answer-card` and `.answer-glyph`; keep `.answer` only if implementation confirms no existing CSS or tests depend on it.

```css
.answer-card {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 18px 22px;
  font-size: 18px;
  font-weight: 500;
  background: #1F1430;
  border: 1px solid rgba(255, 255, 255, 0.10);
  border-radius: 14px;
  color: var(--ink);
  cursor: pointer;
  transition: background 0.15s;
}
.answer-card:hover { background: #261837; }

/* Glyph badge (A, B, C, D) */
.answer-glyph {
  width: 28px;
  height: 28px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 6px;
  font-size: 14px;
  font-weight: 600;
  font-family: var(--font-mono);
  background: rgba(255, 255, 255, 0.08);
  color: var(--ink);
  border: 1px solid rgba(255, 255, 255, 0.1);
  flex-shrink: 0;
}

/* States */
.answer-card.selected {
  outline: 2px solid var(--accent);
  outline-offset: -2px;
}
.answer-card.correct {
  background: rgba(109, 255, 230, 0.16);
  border-color: var(--olive);
  color: var(--olive);
  box-shadow: 0 0 24px rgba(109, 255, 230, 0.30);
}
.answer-card.correct .answer-glyph {
  background: var(--olive);
  color: var(--bg);
}
.answer-card.wrong { opacity: 0.35; }
```

**Phone answer cards:** `font-size: 16px`, `padding: 14px 16px`
**TV answer cards:** `font-size: 26px`, `padding: 24px 32px`, glyph `44px × 44px`

### Buttons

Replace current `.btn-primary` and `.btn-secondary`:

```css
.btn-primary {
  background: var(--accent);
  color: var(--accent-ink);
  border-radius: 100px;      /* pill */
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  font-size: 13px;
  box-shadow: 0 0 0 1px var(--accent), 0 0 24px rgba(255,46,122,0.4);
  border: none;
}

.btn-ghost {
  background: transparent;
  color: var(--ink);
  border: 1px solid var(--rule-2);
  border-radius: 100px;      /* pill */
}
```

### Typography Utility Classes

Three utility classes used throughout the design:

```css
/* Mono-spaced labels, meta text, section headers */
.eyebrow {
  font-family: var(--font-mono);
  font-size: 11px;
  letter-spacing: 0.16em;
  text-transform: uppercase;
  color: var(--ink-mute);
}

/* Display headings — Bricolage Grotesque for Velvet */
.display {
  font-family: var(--font-display);
  font-weight: 600;
  letter-spacing: -0.03em;
  color: var(--ink);
}

/* Tabular numbers — keeps scores/timers aligned */
.num {
  font-variant-numeric: tabular-nums;
  font-feature-settings: 'tnum';
}
```

### Horizontal Rule

```css
.hr {
  height: 1px;
  background: var(--rule);
  width: 100%;
}
.hr-ink {
  height: 1px;
  background: var(--rule-2);
  width: 100%;
}
```

### Progress Bar

```css
.progress {
  height: 2px;
  background: rgba(255, 255, 255, 0.08);
  border-radius: 1px;
  overflow: hidden;
}
.progress-fill {
  height: 100%;
  background: var(--accent);
  transition: width 0.1s linear;
}
```

### Cards

```css
.card {
  background: var(--paper);
  border: 1px solid var(--rule-2);
  border-radius: 14px;
  box-shadow: var(--shadow);
}
```

---

## Phase 3: Phone Surfaces

All phone screens use a shared layout shell:

```
PhoneHeader (eyebrow nav bar)
  Content area (flex: 1, scrollable)
  Bottom action area (fixed padding)
```

### PhoneHeader

```tsx
// Replaces the current in-component headers
<div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', padding: '20px 24px 8px' }}>
  <span className="eyebrow">{left}</span>
  <span className="eyebrow">{right}</span>
</div>
```

### Phone: Join Screen

**Current:** Room code input, nickname, team, avatar picker. Hero icon + gradient title.

**Velvet:** Same fields, restyle with:
- Remove `.hero-icon` (72px gradient circle) — replace with a large display title
- Title: `font-family: var(--font-display)`, `font-size: 42px`, `line-height: 1`
- Input fields: `background: var(--paper)`, `border: 1px solid var(--rule-2)`, `border-radius: 12px`, `color: var(--ink)`, `font-size: 16px`
- Join button: `.btn-primary` pill style
- Avatar picker: keep emoji grid, update background/border colors to Velvet tokens

### Phone: Lobby

**Current:** Shows "Waiting for host…" with player count and list.

**Velvet:**
- PhoneHeader: left="LocalPlay", right="ROOM {code}"
- Center: Avatar (80px, you=true), eyebrow "You're in", display title (42px): "Hi, {name}" with name in italic accent color
- Body text (15px, ink-mute): "Waiting for the room to fill up…"
- Horizontal rule
- Eyebrow: "· {count} player(s) in the room"
- Player chips: flex wrap, gap 6px, staggered `lp-fade-in`
- Bottom: eyebrow with pulse animation "· · · waiting for host"

### Phone: Intro (3-2-1 Countdown)

**Current:** Not a distinct screen — game just starts.

**Velvet (new screen):**
- PhoneHeader: left="{GAME TYPE}", right="ROOM {code}"
- Center: eyebrow "Get ready · Q{round} of {total}"
- Giant number: `font-size: 200px`, `line-height: 1`, steps through "3" → "2" → "1" → "Go." at 1s intervals
- "Go." is italic

### Phone: Quiz Question

**Current:** Question card + 4 colored answer buttons + power-up bar + timer bar.

**Velvet:**
- PhoneHeader: left="TRIVIA · Q{n}/{total}", right="{remaining}s" (mono, num)
- Progress bar (2px): `padding: 0 24px 16px`
- Question: `padding: 8px 24px 16px`, eyebrow "· {topic}", display text (22px, line-height 1.2)
- Answer grid: flex column, gap 10px, padding 8px 24px 16px
  - Each: `.answer-card` (16px font, 14px 16px padding) with `.answer-glyph`
  - Selected: outline 2px accent
  - Revealing: `.correct` (mint glow) / `.wrong` (opacity 0.35)
  - Player's choice: eyebrow "· your pick"
- Power-ups (if not revealing): padding 0 24px 20px, flex gap 8px
  - Two `.btn-ghost` pills: "2× points", "50 / 50" (13px, padding 10px 12px)
- Result (if revealing): text-center, eyebrow "· Correct ·" or "· Wrong ·"
  - Display num (36px): "+ {points}" in olive (correct) or ink-mute (wrong)

### Phone: WMLT Voting

**Current:** Statement + player voting grid + vote button.

**Velvet:**
- PhoneHeader: left="MOST LIKELY · {n}/{total}", right="{remaining}s"
- Progress bar
- Statement: eyebrow "· Statement", display text (22px)
- Player grid: 2 columns, gap 10px
  - Each: flex gap 10px, padding 10px, background paper, border 1px rule-2, border-radius 10px
  - Avatar 32px, name 14px
  - If voted for: border/outline accent
  - If self: opacity 0.4
- Bottom: `.btn-primary` full width "Cast vote"

### Phone: Leaderboard

**Current:** LeaderboardBarChart (Recharts horizontal bars) with auto-advance timer.

**Velvet:**
- PhoneHeader: left="STANDINGS", right="Q{n} / {total}"
- Top section (text-center):
  - Eyebrow "Your position"
  - Display (96px, accent): "#{rank}"
  - Display num (28px): score
  - Eyebrow: "+ {last_round} this round · climbed {delta} spot(s)"
- Standings list: flex column, gap 8px
  - Per-player row: flex gap 10px, padding 10px 12px, border 1px, border-radius 10px
  - If me: background accent, color accent-ink, border accent
  - Else: background paper, color ink, border rule
  - Eyebrow num (24px width): rank
  - Avatar 28px
  - Name (15px, weight 500)
  - Score (margin-left auto, 18px, mono)
- Bottom: eyebrow with pulse "· · · next question loading"

### Phone: Podium

**Current:** Podium bars (1st/2nd/3rd), remaining leaderboard, team standings, superlatives, Play Again button.

**Velvet:**
- PhoneHeader: left="FINAL · {GAME}", right="GAME OVER"
- Result section (text-center):
  - Eyebrow "You finished"
  - Display (110px, accent): "#{rank}"
  - Display num (30px): score
- Podium: grid 3 columns, gap 8px
  - Per-position: padding 12px, border 1px, border-radius 10px
  - 1st: border/bg accent, color accent-ink
  - 2nd/3rd: border/bg paper, color ink
  - Avatar (36px), display num (22px): "I"/"II"/"III", name (13px, weight 600)
- Awards: flex column, gap 6px
  - Per-award: flex gap 10px, padding 8px 12px, border 1px rule, border-radius 8px
  - Eyebrow label, name (14px, weight 500), display num (accent): "+ {points}"
- Buttons: flex gap 8px
  - `.btn-ghost` flex 1: "Recap"
  - `.btn-primary` flex 2: "Play again"

---

## Phase 4: TV Surface (SpectatorPage Rework)

The current SpectatorPage is a simplified view. Rework it into a proper TV host surface at 1280×720 target resolution.

### TV Layout Shell

```
TVHeader (eyebrow nav with game info + room code)
  Content area (flex: 1)
```

**TVHeader:**
- `padding: 32px 56px 0`
- Flex space-between, baseline
- Left: eyebrow with "LocalPlay", "·", game name, round/question info (gap 24px)
- Right: eyebrow "ROOM {code}" (letter-spacing 0.2em)

### TV: Library (Game Selection)

This is a new screen for when the TV is waiting / no game selected.

Implementation note: the current production backend only supports `quiz` and `wmlt`. The library may visually preview future games as disabled/coming-soon cards, but selectable cards must be limited to supported `GameType` values until the backend implements the new games.

- Header: eyebrow row with "LocalPlay", session info, host name, spark count
- Title: display (80px): "Pick a game" ("game" italic accent)
- Eyebrow: "· Six rooms, all played locally…"
- Game grid: 3 columns, gap 16px
  - Per card: border 1px rule-2, background paper, padding 20px, border-radius 4px
  - Chapter number eyebrow, optional badge chip
  - Display name (36px), tagline (14px, ink-2)
  - Footer: eyebrow player count + pace, display arrow (20px, italic, accent) "→"

Current supported cards:

| Game | ID | Enabled |
|---|---|---|
| Trivia | `quiz` | Yes |
| Most Likely To | `wmlt` | Yes |
| Pictionary | `pictionary` | Disabled / Coming soon |
| Taboo | `taboo` | Disabled / Coming soon |
| Whispers | `whispers` | Disabled / Coming soon |
| Bluff | `fibbage` or future backend id | Disabled / Coming soon |

### TV: Lobby

- TVHeader
- Grid: 2 columns (main + sidebar), gap 48px, padding 40px 56px
- **Left column:**
  - Eyebrow: "· Round one starts when host is ready"
  - Display (84px, line-height 0.96): "Join" (italic accent)
  - Step 01/02 instructions (17px, ink-2)
  - Horizontal rule
  - Room code: display (88px, mono, letter-spacing 0.04em)
  - Player count: display num (88px, accent)
- **Right column:**
  - QR code box: background paper, padding 24px, border 1px ink, shadow. QR at 220px
  - Player roster: eyebrow header, player chips with staggered animation

### TV: Intro (3-2-1)

- TVHeader with round/total
- Center: eyebrow "Question XX of YY"
- Display (280px, line-height 0.85): step label ("Three", "Two", "One", "Begin.")
- "Begin." is italic
- Eyebrow: "{topic} · 4 options · 15 seconds"

### TV: Quiz Question

- TVHeader
- Topic strip: eyebrow "· Topic · {topic}", display (56px, line-height 1.05, max-width 900px)
- TimerRing (120px, stroke 5), eyebrow "{answered} of {total} answered"
- Progress bar (padding 24px 56px 0)
- Answer grid: 2×2, gap 16px, font-size 26px, padding 24px 32px
  - answer-glyph: 44px × 44px, font-size 20px
  - Correct: mint glow, "+ {points} pts to leaders" eyebrow
  - Wrong: opacity 0.35

### TV: WMLT Voting

- TVHeader
- Display statement (72px, line-height 1.0, letter-spacing -0.03em)
- TimerRing (120px), eyebrow "{voted} / {total} voted"
- Player grid: 8 columns, gap 12px
  - Per-player card: padding 16px 8px, border 1px rule-2, border-radius 12px, background paper
  - Avatar 48px, name 15px, eyebrow "+ vote"

### TV: Leaderboard

- TVHeader
- Header: eyebrow "· After question {n}", display "Standings." (64px)
- Standings: flex column, gap 12px
  - Per-player: flex row, gap 18px
  - Rank (eyebrow, 36px width), Avatar (36px)
  - Name (18px, weight 500), score (display num 28px), delta (eyebrow, olive if positive)
  - Progress bar: height 6px, border-radius 3px, width = score/max * 100%, transition 0.6s ease
  - 1st place bar: background accent; others: background ink

### TV: Podium

- TVHeader
- Header (text-center): eyebrow "· Final standings · {n} of {total} complete", display (64px): "{winner} takes the crown" (name italic accent)
- Podium: grid 3 columns, gap 24px, align-end, max-width 900px, ordered [silver, gold, bronze]
  - Avatar (88px 1st, 64px others)
  - Display name (28px), display score (48px 1st, 36px others, accent)
  - Podium bar: height [320, 220, 160]px
    - 1st: background accent, color accent-ink
    - 2nd: background ink, color bg
    - 3rd: background ink-2, color bg
    - Display Roman numeral (32px), border-radius 2px
- Awards strip: grid 4 columns, gap 12px, border-top 1px rule
  - Eyebrow title, Avatar 28px + name (15px, weight 500), eyebrow detail (9px)

---

## Phase 5: Animations

### Entry Animation

```css
@keyframes lp-fade-in {
  from { opacity: 0; transform: translateY(4px); }
  to   { opacity: 1; transform: translateY(0); }
}
.lp-fade-in {
  animation: lp-fade-in 400ms ease both;
}
```

Lobby player chips: stagger by `animation-delay: ${index * 60}ms`.

### Pulse Animation

```css
@keyframes lp-pulse {
  0%, 100% { opacity: 0.5; }
  50%      { opacity: 1; }
}
.lp-pulse {
  animation: lp-pulse 2s ease-in-out infinite;
}
```

Used for "waiting for host" and "next question loading" text.

### Leaderboard Bars

TV leaderboard progress bars grow from 0 to target width:
- `transition: width 0.6s ease-out`

### Podium Reveal

TV podium reveals positions 3rd → 2nd → 1st with ~300ms delay between each:
- Keep existing `revealPhase` logic in PodiumScreen
- Awards strip cross-fades in after all three positions

### Answer Reveal

- Wrong answers: `transition: opacity 0.3s ease` to 0.35
- Correct answer: `transition: all 0.3s ease` to mint glow state
- Points chip: fade in after 200ms delay

### Countdown

Intro screen: number transitions at 1s ticks. Each number scales in (optional):
- `transform: scale(1.1) → scale(1)` over 200ms

### Reduced Motion

Add a global reduced-motion policy:

```css
@media (prefers-reduced-motion: reduce) {
  *,
  *::before,
  *::after {
    animation-duration: 0.001ms !important;
    animation-iteration-count: 1 !important;
    scroll-behavior: auto !important;
    transition-duration: 0.001ms !important;
  }
}
```

For gameplay-critical moments, prefer replacing motion with static state changes rather than hiding information. Timer countdowns and score changes must still be visible.

---

## Phase 6: Screen-by-Screen Migration Checklist

### Organizer Screens

| Current Component | File | Changes |
|---|---|---|
| GameSelectScreen | `components/organizer/GameSelectScreen.tsx` | Restyle cards with Velvet tokens. Add new game entries as games are built. Replace emoji hero icon with display title. |
| PromptScreen | `components/organizer/PromptScreen.tsx` | Restyle inputs, character counter, generate button with Velvet tokens. |
| MLTPromptScreen | `components/organizer/MLTPromptScreen.tsx` | Same as PromptScreen — restyle with Velvet tokens. |
| LoadingScreen | `components/organizer/LoadingScreen.tsx` | Restyle loading rings with accent/plum/olive colors. |
| ReviewScreen | `components/organizer/ReviewScreen.tsx` | Restyle question cards, edit fields with Velvet tokens. |
| MLTReviewScreen | `components/organizer/MLTReviewScreen.tsx` | Same as ReviewScreen. |
| ImageGenerationScreen | `components/organizer/ImageGenerationScreen.tsx` | Restyle with Velvet tokens. |
| LobbyScreen | `components/organizer/LobbyScreen.tsx` | Major rework: QR container, room code display, player chips, lock toggle. Match TV lobby right-column style. |
| GameQuestionScreen | `components/organizer/GameQuestionScreen.tsx` | Restyle question card, answer grid, timer, progress bar. Use new answer card style. |
| LeaderboardScreen | `components/organizer/LeaderboardScreen.tsx` | Replace Recharts bar chart with Velvet leaderboard list. Update timer bar. |
| PodiumScreen | `components/organizer/PodiumScreen.tsx` | Major rework: new podium bars, awards strip, play-again button. |

### Player Screens

| Screen State | File | Changes |
|---|---|---|
| JOIN | `pages/PlayerPage.tsx` | Restyle join form. Replace hero icon. Velvet input fields + pill button. |
| LOBBY | `pages/PlayerPage.tsx` | New layout: centered self-avatar, player chips, "waiting" pulse. |
| INTRO (optional) | `pages/PlayerPage.tsx` | Add intro countdown state between LOBBY and QUESTION only if it does not reduce answer time. 3-2-1 display. |
| QUESTION | `pages/PlayerPage.tsx` | New answer cards (no color coding). Glyph badges. Power-up pills. |
| WAITING | `pages/PlayerPage.tsx` | Restyle with Velvet tokens. |
| RESULT | `pages/PlayerPage.tsx` | Points display in olive/ink-mute. Eyebrow correct/wrong. |
| PODIUM | `pages/PlayerPage.tsx` | New podium grid, awards list, play-again buttons. |
| RECONNECTING | `pages/PlayerPage.tsx` | Restyle with Velvet tokens. |
| GAME_IN_PROGRESS | `pages/PlayerPage.tsx` | Restyle with Velvet tokens. |

### TV / Spectator Screens

| Screen | File | Changes |
|---|---|---|
| LOBBY | `pages/SpectatorPage.tsx` | Full rebuild: 2-column grid with QR + room code + player roster. |
| QUESTION | `pages/SpectatorPage.tsx` | Full rebuild: topic strip, TimerRing, 2×2 answer grid with reveal. |
| LEADERBOARD | `pages/SpectatorPage.tsx` | Full rebuild: standings list with progress bars. |
| PODIUM | `pages/SpectatorPage.tsx` | Full rebuild: podium bars + awards strip. |
| LIBRARY (new) | `pages/SpectatorPage.tsx` | New: game catalog grid when no game is active. |
| INTRO (optional) | `pages/SpectatorPage.tsx` | Round countdown with giant display number, subject to the same timing guardrails as PlayerPage. |

### Global Components

| Component | File | Changes |
|---|---|---|
| SettingsDrawer | `components/SettingsDrawer.tsx` | Restyle drawer background, toggles, auth buttons with Velvet tokens. |
| TokenBadge | `components/TokenBadge.tsx` | Restyle pill colors. Use ink/accent instead of purple/red/orange. |
| SparkCoin | `components/SparkCoin.tsx` | Update sparkle colors to match Velvet palette (accent, gold, olive). |
| ErrorModal | `components/ErrorModal.tsx` | Restyle with paper/ink/accent. |
| BonusSplash | `components/BonusSplash.tsx` | Update colors: gold → `var(--gold)`, burst particles to accent/gold/olive. |
| Fireworks | `components/Fireworks.tsx` | Update color palette to Velvet: accent, olive, gold, plum, ink. |
| LeaderboardBarChart | `components/LeaderboardBarChart.tsx` | Replace Recharts with simple CSS bars matching TV leaderboard style. Or keep Recharts but update colors. |
| MaintenanceOverlay | `components/MaintenanceOverlay.tsx` | Restyle with Velvet tokens. |
| AnnouncementBanner | `components/AnnouncementBanner.tsx` | Restyle with Velvet tokens. |
| SignInNudge | `components/SignInNudge.tsx` | Restyle with Velvet tokens. |
| AnimatedNumber | `components/AnimatedNumber.tsx` | No visual change needed — just ensure it uses `var(--font-mono)` for numbers. |
| CastButton | `components/CastButton.tsx` | Restyle icon/button with Velvet tokens. |

---

## Implementation Order

1. **Token foundation** — Add Velvet tokens plus compatibility aliases in `index.css`. Load fonts, preferably self-hosted. Verify current screens remain readable before deeper refactors.
2. **Shared primitives** — Build `<Avatar>`, `<PlayerChip>`, `.eyebrow`, `.display`, `.num`, `.answer-card`, `.answer-glyph`, `.btn-ghost`, and restyle existing button classes without changing behavior.
3. **Answer migration** — Migrate quiz answer rendering away from `ANSWER_STYLES` shapes/colors to letter glyph badges. Keep `ANSWER_STYLES` exported until all imports/tests are gone.
4. **Phone core path** — Restyle JOIN, LOBBY, QUESTION, WAITING/RESULT, LEADERBOARD, PODIUM in `PlayerPage.tsx`.
5. **Organizer control surfaces** — Restyle GameSelect, Prompt, MLT prompt, Loading, Review, MLT review, ImageGeneration, Lobby, Question, Leaderboard, Podium. Keep host controls clear and operational.
6. **Spectator TV surface** — Rework SpectatorPage LOBBY, QUESTION, LEADERBOARD, PODIUM as the polished TV view.
7. **Optional INTRO state** — Add local presentation countdown only after the core restyle is stable and only if timing does not steal answer time. See the INTRO section below.
8. **Global components** — SettingsDrawer, TokenBadge, SparkCoin, ErrorModal, BonusSplash, Fireworks, AnnouncementBanner, MaintenanceOverlay, SignInNudge, CastButton.
9. **Animation pass** — Add subtle fade/pulse/bar/podium motion, respecting reduced-motion preferences.
10. **Cleanup** — Remove unused old token aliases, answer color classes, keyframes, and any compatibility code only after `rg` and tests confirm no references.

---

## INTRO State Machine Change

This is the only allowed state-machine change in this redesign, and it is optional. Both PlayerPage and SpectatorPage may add an `INTRO` presentation state between `LOBBY` and `QUESTION`, but it must not reduce real answer time or require backend timing changes.

**Current flow:**
```
GAME_STARTING → stay in LOBBY → first QUESTION arrives → QUESTION state
```

**New flow:**
```
GAME_STARTING → INTRO state (3-2-1 countdown, ~2.5s) → first QUESTION arrives → QUESTION state
```

Implementation guardrails:
- On `GAME_STARTING` message: transition to `INTRO` instead of staying in `LOBBY`
- INTRO screen runs a local countdown (`3` -> `2` -> `1` -> `Go.`)
- When the first `QUESTION` message arrives, transition to `QUESTION` regardless of countdown progress (the backend is the source of truth for timing)
- No backend changes needed — `GAME_STARTING` is already sent
- If the backend sends `QUESTION` immediately enough that users lose visible answer time, skip or shorten the intro rather than delaying question rendering.
- Respect `prefers-reduced-motion`: show a static "Get ready" screen or skip the countdown.

Add `'INTRO'` to the `PlayerState` and spectator state types.

---

## Organizer Page: Relationship to TV Surface

The OrganizerPage currently serves as both the host control panel AND the "big screen" during gameplay (GameQuestionScreen, LeaderboardScreen, PodiumScreen). The design prototype shows the TV surface as a separate, presentation-focused view.

For this redesign:
- The **OrganizerPage** keeps its control function: game setup, room management, next/end buttons
- The **SpectatorPage** becomes the polished TV presentation surface
- During gameplay, the OrganizerPage shows a simplified version of the game state (question + controls), while the SpectatorPage shows the full TV treatment
- The OrganizerPage screens (GameQuestionScreen, LeaderboardScreen, PodiumScreen) should be restyled with Velvet tokens but don't need the full TV layout — they're control surfaces, not presentation surfaces

This means the Organizer and TV views diverge more than they do today. The Organizer is for the host's phone/laptop; the TV is for the room's screen.

## Implementation Acceptance Criteria

Before merging the theme implementation:

- `npm run build` and `npm test` pass in `frontend/`.
- Backend tests still pass if any shared types or route assumptions changed.
- Existing quiz flow works on phone player, organizer, and spectator: join -> lobby -> question -> answer -> result/leaderboard -> podium.
- Existing WMLT flow works on phone player, organizer, and spectator.
- Google/Apple sign-in controls remain visible and usable in SettingsDrawer.
- Token badge, purchase modal/error modal, maintenance overlay, and announcement banner remain readable.
- IONOS `/quiz/` build loads with the correct base path and no broken asset URLs.
- Playwright or manual screenshot coverage includes: narrow phone, desktop organizer, 1280x720 spectator, and a long-question/long-answer quiz. The committed Playwright suite currently covers the DrawingGame organizer prompt screen on desktop and mobile, including fixed-control overlap and no horizontal overflow.
- No text overlaps fixed controls, safe-area notches, or the settings/spark badges.
- `rg "var\\(--text-quaternary|var\\(--bg-tertiary|answer-red|answer-blue|answer-yellow|answer-green" frontend/src` is either clean or every remaining hit is intentionally covered by a compatibility alias.
- `prefers-reduced-motion` still leaves gameplay state clear.

---

## What This Spec Does NOT Cover

- New game implementations (Pictionary, Taboo, Whispers, Bluff) — those have their own game-specific screens built when the games are built. The theme system supports them.
- Backend API or WebSocket protocol changes.
- Theme switching — this spec ships Velvet as the only theme. Multi-theme support can be added later by wrapping variables in `[data-theme="velvet"]` selectors.
- Drawing canvas for Pictionary — separate component, separate spec.
- Recharts dependency decision — the LeaderboardBarChart currently uses Recharts. This can either be replaced with pure CSS bars (matching the TV leaderboard spec) or kept with updated colors. Decide during implementation.
- Long-term generated-content persistence, Cloud Run readiness, or multi-instance room state.
