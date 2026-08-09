# SPEC: First-Party Grace — free rooms for a host's first evening

**Status: BUILT 2026-08-04 (REVIEW-2026-08 P1, option "first-party grace"). Hardened 2026-08-08 to require a signup-bonus ledger proof. Gamma only; production promotion remains user-gated.**

## Why

The economy paywalled a brand-new host at ~game 2: signup grant 20 ⚡, room 10 ⚡. The 402
arrived **mid-party, friends watching** — the worst moment in the product to ask for money, and
it monetized failure (an error modal) instead of success. Grace moves the ask to *after* a great
first party.

## Behavior

- A wallet's **first room ever** opens a grace window: `PARTY_GRACE_HOURS` (default **6**) of
  **free rooms**, capped at `PARTY_GRACE_MAX_ROOMS` (default **10**). Generation still costs
  sparks (1 ⚡) — a new host's 20 ⚡ covers a full evening of quizzes.
- After the window (or cap): normal spark pricing. Wallets that ever **paid** for a room are
  ineligible — veterans don't get a surprise free evening.
- Eligibility requires a positive signup proof: the wallet must have received a `signup_bonus`
  ledger row. Wallets that are created grantless after the per-IP signup allowance is exhausted
  can still join/play, but they cannot be minted into free first-party host rooms.
- **Grace identity survives sign-in** (added 2026-08-09): `merge_wallet` moves balance only, so
  `db.migrate_grace_proofs` (called from `auth.signin` beside the merge) carries the three proofs
  device→user as zero-amount marker rows: signup proof (else signing in before the first game
  silently cost a new host their free party), the open window verbatim with original timestamps
  (no deadline reset, no double allowance), and `spend_room` veteran history (else sign-in
  laundered a veteran into a fresh free evening). Idempotent; runs even when the balance merge
  no-ops on a drained wallet.
- `PARTY_GRACE_HOURS=0` disables the feature entirely.

### Known interaction with the per-IP signup allowance — deliberate, worth watching

Grace eligibility depends on the signup grant, and that grant is capped per IP per day
(`SIGNUP_BONUS_IP_DAILY_LIMIT`, default 20 — REVIEW-2026-08 S2). So the 21st **new host** from one
IP in a day gets the daily bonus only (10 ⚡, exactly `COST_ROOM`) and no grace: one game, then the
paywall. Measured on a live stack — wallets #1–20 came back `balance=30/available`, #21+
`balance=10/ineligible`.

This is the intended trade (it is what bounds room-farming by minted device ids, since grace needs
no sparks), and 20 first-time hosts sharing an IP in one day is implausible at current scale. But it
is a real degradation for a venue/dorm/office behind one NAT, so:
- **the throwaway test harnesses set `SIGNUP_BONUS_IP_DAILY_LIMIT=0`** — a single-IP harness minting
  ~76 wallets is precisely what the limiter cannot reason about; leaving it on failed 37 of 76
  all-games tests in CI;
- if real users ever report "I only got one free game", raise the limit rather than weakening the
  grace proof — the proof is what stops the farm.

## Mechanics (no schema change)

- State lives in the ledger: each free room writes a zero-amount `grace_room` row;
  the window anchors on the oldest one. `db.party_grace_state / has_room_spend /
  has_signup_bonus / record_grace_room` on both backends (export-guard enforced).
- The charge seam is `tokens.spend_room` — covers **both** socket-layer sites (game start +
  room reset) without touching socket_manager.
- `/tokens/balance` now carries `party_grace: {state: available|active|expired|ineligible,
  until, rooms_used}`.
- `PartyGraceBanner` on the game catalog: "Your first party's on us…" before the first room,
  live deadline while active, **nothing** for expired/ineligible (no dead promises).
- Analytics: `grace_room_used` (room_number) — the question this feature must answer is
  whether grace hosts convert after the party.

## Testing

`backend/tests/test_party_grace.py` (10): free evening well past the old paywall point, window
expiry, room cap, broke-host-post-cap 402, veteran ineligibility, grantless-wallet ineligibility,
kill switch, status lifecycle/read-only-ness. `backend/tests/test_abuse_guards.py` also verifies
that the signup IP allowance and grace compose correctly: after the per-IP grant allowance is
exhausted, a newly created grantless wallet cannot start free rooms. Frontend:
`PartyGraceBanner.test.tsx` (5) incl. old-backend fail-silent. conftest pins
`PARTY_GRACE_HOURS=0` so the other 1,400+ tests keep pre-grace expectations. Visual baselines
updated (banner on catalog); all-games passes with grace active.

## Rollout

Ships dark-by-default? **No — active by default** (`PARTY_GRACE_HOURS=6`); disable per-env with
`PARTY_GRACE_HOURS=0` if needed. Gamma first, watch `grace_room_used` vs `paywall_hit` and
post-party purchases.
