# Where the test coverage actually is — measured 2026-08-09

Analysis only; nothing in the repo was changed to produce it. Every number below came from running
the tooling, not from reading code and guessing. Reproduce with the commands in each section.

Context: this was measured hours after prod moved from `b0c1fc03` (2 weeks stale) to `1179b530`,
and after CI started emitting `coverage.xml` — which, until this document, nobody had opened.

---

## 1. The headline: we test the database we don't run

```bash
cd backend && source venv/bin/activate
python -m pytest tests/ -q --ignore=tests/test_e2e.py --cov=. --cov-report=term
```

| Module | Stmts | Miss | Cover | Note |
|---|---:|---:|---:|---|
| `db.py` (SQLite) | 918 | 116 | **87%** | **not used in production** |
| `supabase_db.py` (Postgres/REST) | 488 | 343 | **30%** | **holds every real wallet** |
| `socket_manager.py` | 4585 | 1878 | 59% | the game engine |
| `main.py` | 4012 | 1075 | 73% | 106 endpoints |
| `quiz_engine.py` | 337 | 142 | 58% | |
| `auth.py` | 106 | 0 | 100% | |
| `tokens.py` | 107 | 1 | 99% | |
| `share.py` | 70 | 1 | 99% | |
| `remote_config.py` | 78 | 4 | 95% | |
| `room_snapshot.py` | 110 | 14 | 87% | |
| **TOTAL** | **31642** | **5562** | **82%** | flattering average hiding the split above |

**82% total is misleading.** The two DB backends are near-mirror implementations, and the coverage
is inverted with respect to risk: the SQLite path (local dev only) is at 87%, the Supabase path
(production, real money) at 30%.

### 33 functions in `supabase_db.py` have never executed once

Ranked by untested lines. Money- and identity-critical ones are marked.

| Function | Untested | |
|---|---|---|
| `find_or_create_user` | 19/20 | 💰 identity |
| `migrate_grace_proofs` | 15/16 | 💰 written 2026-08-09; **only the SQLite path was ever tested** |
| `save_quiz_pack` | 12/13 | |
| `check_idempotency` | 10/11 | 💰 **the webhook replay guard** |
| `save_game_content` | 10/11 | |
| `create_entitlement` | 8/9 | 💰 IAP audit marker |
| `lookup_by_user` | 7/8 | support runbook |
| `get_or_create_referral_code` | 7/8 | |
| `get_share_snapshot` | 7/9 | |
| `get_wallet_stats` | 7/8 | |
| `list_host_app_catalog_flags` | 7/8 | |
| `finalize_media_asset` | 7/8 | |
| `update_game_session` | 7/8 | |
| `find_restorable_entitlement` | 6/7 | 💰 **/purchases/restore** |
| `check_and_grant_daily_bonus` | 6/7 | 💰 grants sparks daily |
| `get_quiz_pack` | 6/7 | |
| `admin_grant_tokens` | 5/6 | 💰 **the support remediation path** |
| `admin_lookup_wallet` | 5/6 | support runbook |

…plus 15 more. Note `migrate_grace_proofs`: every test that "verified grace" on 2026-08-09 exercised
SQLite. Its Postgres implementation has been touched only by one live gamma probe.

**Why this is the top priority:** `test_postgres_parity.py` and a real Postgres service in CI
already exist, so effort goes into tests rather than scaffolding, and the target is measurable
(a coverage number). Writing tests cannot break production.

---

## 2. `socket_manager.py` — a *different* kind of gap

```bash
python -m pytest tests/ -q --ignore=tests/test_e2e.py --cov=socket_manager --cov-report=json:/tmp/cov.json
```

**Zero functions are >75% uncovered**, despite 1,878 uncovered lines. So the gap is not missing
features — it is missing **branches**: error paths, reconnection, organizer drop/reclaim, room
reset, teams, spectator, snapshot-restore under load. Precisely the paths that ruin a live party
and that no unit test naturally reaches.

**Sequencing consequence, and it is the important one in this document:** the REVIEW-2026-08 A1
refactor (decompose the 6.7k-line god class into per-game adapters) is **not safe at 59% branch
coverage**. Build the scenario harness first; the refactor becomes verifiable afterwards. Doing it
in the other order risks breaking live games with no test to catch it.

---

## 3. Seven games never reach a podium in any backend test

Derived by intersecting the 38-game catalog against test files that assert `PODIUM` / `GAME_OVER` /
`final_scores`:

`desert_island` · `holiday_bingo` · `memory_lane` · `musical_chairs` · `one_word_vibes` ·
`road_trip_bingo` · `wedding_bingo`

31 of 38 do have a full-round test. Also note what `e2e/all-games.spec.ts` actually asserts: the
lobby disappears, the screen is not the crash screen, not the picker, not blank (>40 chars), no
uncaught page errors. That is **"the game starts and isn't visibly broken"** — deliberately, since
38 engines share no positive selector. It does **not** verify scoring, round progression, or podium
correctness through the UI. "75/76 passing" means 75 games *launch*, not 75 games *play correctly*.

---

## 4. Frontend: never measured, and the biggest file is untested

`@vitest/coverage-v8` is **not installed** — there has never been a frontend coverage number.

Proxy measurement (is a component's name mentioned in any test file — generous, since being
*named* is not being *covered*):

- Components ≥150 lines: **40**
- Never named in any test: **14**
- Lines in those: **5,779 of 17,371 (33%)**

Untested large components include:

| Lines | File |
|---:|---|
| **3,174** | `src/pages/OrganizerPage.tsx` ← **largest file in the repo, in no test at all** |
| 250 | `src/components/GenericPromptGame.tsx` |
| 250 | `src/components/passplay/ImpostorGame.tsx` |
| 228 | `src/components/organizer/BingoSetupScreen.tsx` |

`OrganizerPage` is the host's entire experience — room creation, every game's host view, the
paywall triggers. 399 frontend tests exist and none of them touch it.

---

## 5. No concurrency or load testing whatsoever

`MAX_ROOMS = 50`, a single uvicorn process, rooms held in memory. No test starts more than a couple
of rooms at once; nothing measures WebSocket fan-out. **The real ceiling of one VM is unknown** —
which means the room-sharding plan in CLAUDE.md is un-costed: nobody can say whether it is needed at
100 users or 10,000.

Related unknown: **zero real purchases have ever completed** (858 wallets, 0 purchases, live Stripe
keys). The money path is verified only synthetically.

---

## PROGRESS — items 1 and 2 done (2026-08-09, later the same day)

`supabase_db.py`: **30% → 82%**, via a real PostgREST + Postgres harness
(`backend/tests/postgrest_harness.py`, `scripts/parity-stack.sh`). 60 new tests across four suites:
money rails, races, economy features (gifting/referrals/achievements/restore/account lifecycle) and
the content layer (packs, media, sessions, share cards, settings, admin). Now gated in CI by the
`backend-supabase-rest` job, which re-runs the race suite five times because races are probabilistic.

**Two production bugs found, both fixed:**
1. `credit_purchase` **raised** on a concurrent duplicate payment. The RPC's own duplicate check
   passes in both racers and the `*_purchase_once` unique index rejects the loser with SQLSTATE
   23505. Money was never at risk, but the raise became a 500 to Stripe/RevenueCat → retry of an
   already-credited payment → after ~3 days Stripe disables the endpoint. Reproduced ~3 times in 8
   runs; now mapped to the idempotent `(True, balance)` result, matching what BOTH backends return
   for a sequential replay (measured, not assumed).
2. `migrate_grace_proofs` (written hours earlier) **duplicated the grace window** under concurrent
   sign-ins — check-then-insert, which two racers both pass. Fixed with a new `claim_once()`
   primitive on both backends, built on `request_log`'s PRIMARY KEY so the *database* picks the
   winner. No migration needed. SQLite's `credit_purchase` was checked and is safe (`BEGIN
   IMMEDIATE` serializes it).

Also confirmed by the harness, worth keeping: allowed `game_sessions.status` values are
`lobby|active|paused|complete|expired|cancelled|superseded` — note **`complete`, not `completed`**
(the app writes the legal value); `game_id` is a column distinct from `game_type`, and
`game_content_has_sessions` filters on `game_id`; `admin_lookup_wallet` returns
`{"wallet": …, "transactions": …}` while `get_admin_stats` returns a flat dict (main.py does the
nesting); `finalize_media_asset` stores the size in a `bytes` column.

Remaining from the list below: items 3 (socket_manager scenario coverage — still the prerequisite
for A1), 4 (load harness), 5 (frontend coverage).

## Recommended order for a large token budget

1. **Postgres parity expansion** — `supabase_db` 30% → 85%+ against the real Postgres in CI.
   Highest value per token: worst coverage exactly where the money is, harness already exists,
   measurable target, cannot break prod. Expect it to surface real divergences between the two
   backends.
2. **Adversarial money-rail audit on that layer.** `supabase_db` does read-modify-write where
   SQLite uses `BEGIN IMMEDIATE`. Untested: two concurrent spends of one wallet, webhook replay
   during partial failure, refund-after-spend. Real dollars, real races.
3. **`socket_manager` scenario coverage** (§2) plus the seven missing full-round games (§3).
   Prerequisite for A1 — see §2.
4. **Load harness** (§5) to find the single-VM ceiling and cost the sharding decision.

Deliberately *not* recommended for this budget: the A1/F1 god-file decompositions (high tokens,
high risk, unsafe before #3, days after a prod deploy), and the TV/ads builds (large, speculative,
no install base yet).
