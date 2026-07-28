# Game Ideas

Brainstormed concepts for future Revelry Games. When a concept is ready for implementation, it graduates to its own `SPEC-GAME-*.md` file.

## Already Specced / Built

- **Quiz** (+ variants: Rebus, Emoji Charades, Fact/Fiction, Timeline, Odd One Out) — live
- **WMLT** (Who's Most Likely To) — live
- **Drawing** — live
- **Bingo / Housie** — specced, standalone implemented (`SPEC-GAME-BINGO-HOUSIE.md`)
- **Mafia** — draft spec (`SPEC-GAME-MAFIA.md`)
- **Musical Chairs** — draft spec (`SPEC-GAME-MUSICAL-CHAIRS.md`)
- **Who Am I?** — standalone implemented (`SPEC-GAME-WHO-AM-I.md`)
- **Chit Pull** — standalone implemented (`SPEC-GAME-CHIT-PULL.md`)

## Photo Games (2026-05-25)

Games that use the phone camera as a gameplay input. Photos upload via the existing IONOS media pipeline. AI validation/judging uses Gemini vision (multimodal).

### 1. Photo Charades / Strike a Pose
- Player gets a prompt ("Act out: a cat stuck in a tree")
- Takes a photo acting it out, shown on TV/spectator screen
- Other players guess the prompt (multiple choice or free text)
- AI vision model can auto-score how well the photo matches

### 2. Scavenger Hunt
- AI generates a list of things to find ("something red," "something older than you," "a circle")
- Players race to photograph matching items
- AI vision validates whether the photo actually matches
- Score by speed per item, or first to complete all wins

### 3. Meme Factory
- A photo is shown (player-taken or AI-generated)
- Everyone writes a caption
- Vote on the funniest — Apples-to-Apples energy
- Could also work with AI-generated absurd base images

### 4. Photo Telephone (Broken Picture Phone)
- Player 1 gets a prompt, takes a photo of it
- Player 2 sees only the photo, writes what they think it is
- Player 3 sees only that text, takes a new photo
- Chain continues, then the full chain is revealed — hilarious drift
- Telestrations with cameras — proven party format

### 5. Impostor Lens
- Everyone gets the same secret prompt ("photograph something cozy")
- One player gets a different secret prompt ("photograph something scary")
- All photos shown anonymously on TV — vote on who the impostor is
- Spyfall meets photography

### 6. Face Off
- Prompt: "make your angriest face" / "look like you just won the lottery"
- Everyone submits a selfie
- Vote on who nailed it best, or AI ranks them
- Dead simple, very funny in groups

## Pass-and-Play Games (2026-07-28)

One shared phone circulates so guests WITHOUT phones (kids, grandparents, dead batteries,
phones-away dinners) can play. Teens already play this way natively. Full interaction spec +
slate: **SPEC-PASS-AND-PLAY.md**. Flagship is **Impostor** (the real secret-word game — the id
was deliberately kept free when the odd-question game was renamed away from it). Slate: Impostor,
Paranoia, Hot Seat, Truth or Dare, Forehead Guess, Wavelength-ish; plus cheap pass modes for
chit_pull / never_have_i_ever / wmlt / two_truths.

