# SPEC-GAME-ODD-ONE-OUT — asymmetric-prompt social deduction

Status: **Spec + engine being built 2026-07-27.** Live status: DEPLOY.md's env-status ledger.

## 1. Why this game and not another prompt deck

The catalog has 33 games but only **two** information shapes:

- **Symmetric prompt** — everyone sees the same thing and answers it (all 10 generic-prompt games,
  WYR, NHIE, Acronym, Caption Contest, Survey Says, Two Truths…).
- **Hidden role with private night actions** — Mafia, and only Mafia (min 6 players).

Nothing sits between them, and the gap is the most reliably funny party format there is: *everyone
answers what looks like the same question, one person got a different one, and the group has to work
out who.* It plays at 3 players (Mafia needs 6), needs no moderator, and every answer is public — so
unlike Mafia there is no dead time and nobody is eliminated.

It is also cheap to make good: the fun comes from prompt *pairs*, which is content, not code.

## 2. Shape of a round

1. **Assign.** One player is secretly the odd one out. Everyone else gets the *majority prompt*;
   the odd one gets the *minority prompt* — same shape, different answer space.
   > Majority: "Name something you'd take to a beach." Minority: "Name something you'd take to a gym."
2. **Answer.** Everyone submits one short text answer. Nobody sees anyone else's until all are in
   (or the host reveals).
3. **Accuse.** All answers are shown attributed to their author, and every player votes for who they
   think had the different prompt. A player cannot vote for themselves.
4. **Score + reveal.** The odd one is revealed along with both prompts — the reveal is the payoff,
   and showing both prompts is what makes the round *legible* in hindsight.

## 3. Scoring — deliberately asymmetric

| Outcome | Points |
|---|---|
| Non-odd player votes correctly | `ODD_CORRECT_VOTE` (2) |
| Odd one is **not** caught by a majority | `ODD_SURVIVES` (3) to the odd one |
| Odd one **is** caught | 0 to the odd one |
| Odd one votes for a non-odd player who received the most votes | `ODD_MISDIRECT` (1) bonus |

"Caught" means *strictly more than half* of the eligible voters named them. A plurality is not
enough — with 5 players a 2-vote plurality catching someone would make the odd one's job nearly
impossible and the game stops being fun.

The misdirect bonus exists so the odd one has something to *do* during the vote instead of waiting.

## 4. Rotation, not randomness

The odd one is chosen by **rotating through the player list**, not by random draw per round. Random
selection means someone can plausibly never be the odd one across a short game — which is the whole
point of playing. Rotation is also what makes the game fair to screenshot and to test.

Late joiners are appended to the rotation, so they get a turn without disrupting the order.

## 5. States

`ASSIGNED → ANSWERING → VOTING → REVEAL → (next round | PODIUM)`

- A player who joins mid-round is seated for the **next** round; they cannot answer or vote in the
  round already underway (they'd have seen the answers).
- A player who leaves mid-round has their answer and votes retained; if the **odd one** leaves, the
  round still resolves — their absence must not wedge the game.

## 6. Guardrails

- **Minimum 3 players.** At 2 the vote is trivial (you can't vote for yourself, so there's one
  option). The engine refuses to start below the minimum rather than producing a degenerate round.
- Answers are `clean_text`-sanitized through `engine_common` like every other engine (HTML tags and
  control characters stripped), capped at a short length — this is a one-line answer, not an essay.
- Self-votes are rejected, not silently reassigned.
- Duplicate submissions from the same player **overwrite** rather than stack; a double-tap must not
  become two answers.
- The minority prompt is **never** sent to a non-odd player, and the majority prompt is never sent to
  the odd one. This is the one leak that would destroy the game, so `public_state` is viewer-scoped
  and covered by a test that asserts a non-odd viewer cannot see the minority prompt anywhere in
  their payload.

## 7. Content

Prompt pairs ship as a curated deck. Each entry is `{id, majority, minority}`, and the pair must be
close enough that a single answer is ambiguous — "beach vs gym" works, "beach vs tax return" does
not, because the odd one is caught instantly and the round is over.

The deck is the tuning surface: if playtesting says a pair is too easy or too hard, that's a content
edit, not a code change.

## 8. Not in v1

- AI-generated prompt pairs (the curated deck ships first; the authoring path already exists for
  other games and can follow).
- Multiple odd ones per round.
- Images/photos as answers (the media layer exists, but text keeps v1 honest and fast).

## 9. Integration status — engine done, socket/frontend NOT wired

**The engine and catalog entry are committed (`93feb599`) and fully tested (30 tests). The game is
NOT playable yet** — `socket_manager` has no `odd_one_out` branch, so creating a room of this type
will not start a round. It is `status: "gamma"` in the catalog but must not be offered to hosts
until the wiring below lands.

### Why this was stopped rather than half-done

`socket_manager.py` carries **~48 touchpoints** for a comparable game (measured against
`would_you_rather`), including hardcoded game-type tuples repeated in ~12 places with *different*
semantics — one gates the podium/summary path, one gates the valid `new_game_type` on reset, several
gate the "simple round" reconnect/sync shape. They are not interchangeable, so they can't be
collapsed into one constant without reading each. A partially-wired game is worse than an unwired
one: it appears in the catalog and fails at start time.

### Wiring checklist (verified line references as of `93feb599`)

1. **Import** engine functions with an `ooo_` prefix, near the `would_you_rather_engine` import
   (~L179).
2. **`Room.__init__`** (~L375) and **`reset_for_new_game`** (~L503): `self.ooo_config` /
   `self.ooo_state`.
3. **`total_rounds()`** (~L563) → `config["total_rounds"]`.
4. **Public game state** (~L614) → `ooo_public_state(...)`.
5. **START_GAME** (~L1494): build initial state; refuse below `MIN_ODD_ONE_OUT_PLAYERS` with a
   host-visible error rather than starting a degenerate round.
6. **Message handlers**: player `OOO_ANSWER` / `OOO_VOTE` (~L2662 block); organizer
   `OOO_START_VOTING` / `OOO_REVEAL` / `OOO_NEXT_ROUND` (~L1722 block).
7. **Membership tuples** — add `odd_one_out` to each after reading its purpose: ~L1118, L1318,
   L1623, L1640, L1855, L1899, L2161, L2280.
8. **Reset** (~L1948): `validate_config({})` branch.
9. **Podium** → `record_game_completion` already handles it once the podium path includes the type.

### Do this test-first

Model on an existing socket test (`test_ws_flow.py` / `test_mafia_socket.py`) and write the flow
test *before* the wiring, so "wired correctly" has a definition. The per-viewer prompt scoping is
the thing most likely to break in translation: assert over the wire that a non-odd player's payload
never contains the minority prompt.

### Related debt this exposed

Adding game #35 requires touching ~12 hardcoded tuples with no compiler or test forcing you to find
them all — a missed one is a silent runtime gap. The catalog already knows each game's
`runtime_type`; deriving these sets from it (per distinct purpose, not one merged set) would make new
games cheap and correct by construction. Tracked in BACKLOG.
