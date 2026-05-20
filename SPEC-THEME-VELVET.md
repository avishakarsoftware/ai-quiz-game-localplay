# LocalPlay Velvet Theme Redesign Spec

## Overview

Replace the current "game show purple" aesthetic with **Velvet** — a late-night lounge theme with midnight purple, neon magenta, and electric mint. This is a frontend-only change. No backend, WebSocket protocol, or API changes.

The redesign also introduces a proper **TV host surface** (reworked SpectatorPage) alongside the existing phone player and organizer views.

Source of truth: `marketing/claude-design-1/` — specifically `src/screens.jsx`, `src/styles.css`, and `src/data.jsx`.

---

## Phase 1: Theme System

### CSS Variable Contract

Replace the current variables in `index.css` with the Velvet token set. The old variables (`--bg-primary`, `--accent-primary`, `--glass-bg`, etc.) are replaced entirely — no backward compatibility needed.

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
}
```

### Background Treatment

The page background uses radial gradient blooms instead of the current solid purple:

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

Add to `index.html` `<head>`:

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

### What Dies

- Glassmorphism (`backdrop-filter: blur`, semi-transparent white backgrounds)
- `--bg-gradient` radial purple gradient
- `--bg-tertiary`, `--bg-elevated`, `--glass-blur`, `--text-quaternary` (no Velvet equivalents)
- System font stack (replaced with Hanken Grotesk / Bricolage Grotesque)
- Colored answer buttons (red/blue/yellow/green) → unified dark cards with glyph badges
- `ANSWER_STYLES` in `types.ts` (the `bg`, `shape`, and `className` fields): replace with letter glyphs (A/B/C/D) in neutral `.answer-glyph` badges. The shapes (▲/◆/●/■) and per-answer color classes (`answer-red`, `answer-blue`, etc.) are no longer used.
- 31 existing `@keyframes` in `index.css`: audit each. Keep functional animations (timer pulse, score pop), replace decorative ones (glow, shimmer) with Velvet equivalents, remove unused.

---

## Phase 2: Shared Components

### `<Avatar>`

Emoji rendered inside a disc. Current code likely renders emoji inline; this needs a proper component.

```tsx
type AvatarProps = {
  player: { name: string; avatar: string; hue?: number };
  size?: number;       // default 32
  you?: boolean;       // accent ring + glow
};
```

**Rendering:**
- Round `<span>` with `width`/`height` = size, `border-radius: 50%`
- Background: `var(--bg-2)`
- Emoji child `<span>` at ~62% of disc size
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
  player: { name: string; avatar: string };
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

Replace the current colored answer buttons (`.answer-red`, `.answer-blue`, etc.) with a unified card style:

```css
.answer {
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
.answer:hover { background: #261837; }

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
.answer.selected {
  outline: 2px solid var(--accent);
  outline-offset: -2px;
}
.answer.correct {
  background: rgba(109, 255, 230, 0.16);
  border-color: var(--olive);
  color: var(--olive);
  box-shadow: 0 0 24px rgba(109, 255, 230, 0.30);
}
.answer.correct .answer-glyph {
  background: var(--olive);
  color: var(--bg);
}
.answer.wrong { opacity: 0.35; }
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
  - Each: `.answer` card (16px font, 14px 16px padding) with `.answer-glyph`
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

- Header: eyebrow row with "LocalPlay", session info, host name, spark count
- Title: display (80px): "Pick a game" ("game" italic accent)
- Eyebrow: "· Six rooms, all played locally…"
- Game grid: 3 columns, gap 16px
  - Per card: border 1px rule-2, background paper, padding 20px, border-radius 4px
  - Chapter number eyebrow, optional badge chip
  - Display name (36px), tagline (14px, ink-2)
  - Footer: eyebrow player count + pace, display arrow (20px, italic, accent) "→"

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
| INTRO (new) | `pages/PlayerPage.tsx` | Add intro countdown state between LOBBY and QUESTION. 3-2-1 display. |
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
| INTRO (new) | `pages/SpectatorPage.tsx` | New: round countdown with giant display number. |

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

1. **CSS variable swap** — Replace all variables in `index.css`. Load Google Fonts. Remove glassmorphism. Test that nothing is invisible/unreadable.
2. **Avatar component** — Build `<Avatar>` with size prop and "you" ring.
3. **PlayerChip component** — Build `<PlayerChip>` using Avatar.
4. **Answer cards** — Replace colored answer buttons with unified `.answer` card style.
5. **Buttons** — Update `.btn-primary` and add `.btn-ghost`. Pill shapes, uppercase, glow.
6. **Eyebrow utility** — Add `.eyebrow` class.
7. **Phone Join/Lobby** — Restyle with new components.
8. **Phone Question + Result** — New answer cards, power-up pills, result display.
9. **Phone Leaderboard** — Replace Recharts with standings list.
10. **Phone Podium** — New podium grid + awards + play again.
11. **Phone Intro** — Add 3-2-1 countdown state.
12. **Organizer screens** — GameSelect, Prompt, Review, Lobby, Question, Leaderboard, Podium.
13. **TV Lobby** — 2-column grid with QR + roster.
14. **TV Question** — Topic strip, TimerRing, 2×2 grid.
15. **TV Leaderboard** — Standings with progress bars.
16. **TV Podium** — Bars + awards strip.
17. **TV Intro** — Giant countdown.
18. **TV Library** — Game catalog grid (when games are ready).
19. **Animation pass** — lp-fade-in, leaderboard bar growth, podium reveal, countdown.
20. **Global components** — SettingsDrawer, TokenBadge, SparkCoin, ErrorModal, BonusSplash, Fireworks.

---

## INTRO State Machine Change

The only state machine change in this redesign. Both PlayerPage and SpectatorPage need an `INTRO` state between `LOBBY` and `QUESTION`.

**Current flow:**
```
GAME_STARTING → stay in LOBBY → first QUESTION arrives → QUESTION state
```

**New flow:**
```
GAME_STARTING → INTRO state (3-2-1 countdown, ~2.5s) → first QUESTION arrives → QUESTION state
```

Implementation:
- On `GAME_STARTING` message: transition to `INTRO` instead of staying in `LOBBY`
- INTRO screen runs a local 3-step countdown (3 → 2 → 1 → "Go." at 1s ticks)
- When the first `QUESTION` message arrives, transition to `QUESTION` regardless of countdown progress (the backend is the source of truth for timing)
- No backend changes needed — `GAME_STARTING` is already sent

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

---

## What This Spec Does NOT Cover

- New game implementations (Pictionary, Taboo, Whispers, Bluff) — those have their own game-specific screens built when the games are built. The theme system supports them.
- Backend changes — none needed.
- WebSocket protocol changes — none needed.
- Theme switching — this spec ships Velvet as the only theme. Multi-theme support can be added later by wrapping variables in `[data-theme="velvet"]` selectors.
- Drawing canvas for Pictionary — separate component, separate spec.
- Recharts dependency decision — the LeaderboardBarChart currently uses Recharts. This can either be replaced with pure CSS bars (matching the TV leaderboard spec) or kept with updated colors. Decide during implementation.
