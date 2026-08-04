import { expect, test, type APIRequestContext, type Browser, type Page } from '@playwright/test';
import fs from 'node:fs';
import { fileURLToPath } from 'node:url';
import {
  closePlayers,
  createRoomViaApi,
  deterministicBingoDeck,
  joinPlayers,
  liveDeviceId,
  openOrganizerFromRoom,
  postJson,
  type LivePlayer,
  type LiveRoom,
} from './liveGameHarness';

/**
 * THE canonical "every game is playable" suite (SPEC-TESTING §4, L3/L4).
 *
 * ## Why this file exists
 *
 * On 2026-07-28 the catalog held 38 games and 32 of them appeared in *some* e2e spec. The six with
 * none — baby_bingo, wedding_bingo, holiday_bingo, road_trip_bingo, odd_question, impostor — were
 * the six newest, and all three bugs that shipped that night (the occasion-bingo breakage, the
 * odd_one_out id collision, the Impostor room-create rejection) were invisible to 1269 backend
 * tests and 375 vitest tests. Hand-written per-game specs cannot fix that, because the failure mode
 * IS "nobody wrote the spec".
 *
 * So this suite is parameterised over `GET /catalog` at module load. There is no game list in this
 * file. Ship a 39th game and it is played on the next run without anyone editing a test.
 *
 * ## What it asserts, per catalog game
 *
 *   catalog · <id>   1. Rules metadata resolves — backend rules payload is well-formed AND the
 *                       frontend renders it (the picker's Rules modal shows the catalog title).
 *                    2. The game is reachable in the product: it has a picker tile.
 *   play · <id>      3. A room can be created for it.
 *                    4. Its minimum-player gate behaves (Start is refused below the minimum).
 *                    5. Its first playable screen renders — not an error, not a blank.
 *
 * Two tests rather than one so a failure is attributable at a glance: "rules/catalog broke for X"
 * and "X does not start" are different bugs with different owners. The catalog leg is free (no
 * room, no sparks); the play leg costs one room.
 *
 * ## Traps this suite already knows about (each cost real time once)
 *
 * - **Occasion bingos are VARIANTS.** `baby_bingo` is a catalog id whose `game_type` is `bingo`;
 *   `/room/create` with `game_type: "baby_bingo"` is correctly rejected. Rooms are therefore always
 *   created with `game.game_type`, never `game.id`. Their variant identity is the deck, which
 *   game-coverage.json supplies.
 * - **Impostor is pass-and-play.** Zero connected players by design; seats are typed by the host
 *   (SPEC-PASS-AND-PLAY §2). A start gate based on connected players would never fire, and there is
 *   no lobby or room code to wait for. Driven through the seat roster instead, with seat names
 *   generated from the catalog's own `config_schema.players.min`.
 * - **Housie/Bingo default to manual calling**, so an unattended run sits on "Waiting for first
 *   call" forever. The caller screen is still the real first playable screen, so the assertion is a
 *   "Call Next" button rather than a called number.
 * - **Per-game settle timing varies and there is no universal "game started" selector** across 38
 *   engines. The generic signal is therefore negative-space: the lobby is gone, no uncaught
 *   exception fired, the page is not blank. Games with a stable positive signal declare it.
 * - **A fresh device id per room** means a fresh wallet with the signup bonus, so no run can drain
 *   a wallet and report false failures (SPEC-TESTING §2, budget awareness). Nicknames are `QA-`
 *   prefixed so real analytics and support can identify synthetic actors.
 *
 * ## Running it
 *
 *   npm run test:e2e:all-games            # local: backend :9100 + vite :9200
 *   npm run test:e2e:all-games:gamma      # gamma (L4) — has all 38 games
 *
 * Never point this at prod: it creates a room per game. SPEC-TESTING §2/§3 own the prod path.
 */

// ---------------------------------------------------------------------------------------------
// Coverage registry — exceptions only. See game-coverage.json's own `_about`.
// ---------------------------------------------------------------------------------------------

interface ContentPlan {
  endpoint: string;
  body: Record<string, unknown> & { deck_prefix?: string };
  id_field: string;
  room_field: string;
}

interface GamePlan {
  content?: ContentPlan;
  room_body?: Record<string, unknown>;
  settle_ms?: number;
  expect_button?: string;
  expect_testid?: string;
}

interface CoverageRegistry {
  waivers: Record<string, { reason: string; revisit_when: string; still_asserted?: string }>;
  plans: Record<string, GamePlan>;
  defaults: { settle_ms: number; max_players: number };
}

const registry: CoverageRegistry = JSON.parse(
  fs.readFileSync(fileURLToPath(new URL('./game-coverage.json', import.meta.url)), 'utf8'),
);

// ---------------------------------------------------------------------------------------------
// The catalog IS the parameter list.
// ---------------------------------------------------------------------------------------------

interface CatalogRules {
  title?: string;
  summary?: string;
  sections?: Array<{ id: string; title: string; items: string[] }>;
  player_count?: { min?: number; recommended?: string };
}

interface CatalogGame {
  id: string;
  game_type: string;
  runtime_type?: string;
  title: string;
  interaction?: string;
  launchable?: boolean;
  config_schema?: { players?: { min?: number; max?: number } };
  rules?: CatalogRules;
}

/**
 * Where to ask for the catalog. Local dev serves the API and the SPA on different ports, gamma
 * serves both from one origin (backend-served SPA), so LIVE_API_BASE_URL falls back to the base URL.
 */
const apiBase = process.env.LIVE_API_BASE_URL || process.env.PLAYWRIGHT_BASE_URL || 'http://127.0.0.1:5173';

async function fetchCatalog(): Promise<CatalogGame[]> {
  const url = new URL('/catalog', apiBase).toString();
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`GET ${url} → ${response.status}. Is the backend up? (local: scripts/dev-local.sh)`);
  }
  const games = ((await response.json()) as { games: CatalogGame[] }).games || [];
  if (!games.length) throw new Error(`GET ${url} returned an empty catalog`);
  return games;
}

// Top-level await: frontend/package.json is `type: module`, so Playwright loads these specs as ESM.
// This is what makes per-game tests possible at all — Playwright's collection phase is synchronous,
// so the catalog has to be resolved before the `test()` calls run.
const CATALOG = (await fetchCatalog()).filter((game) => game.launchable !== false);

const PLAYER_POOL = [
  'QA-Ava', 'QA-Ben', 'QA-Cy', 'QA-Dee', 'QA-Eli', 'QA-Fay',
  'QA-Gus', 'QA-Hana', 'QA-Ivy', 'QA-Jai', 'QA-Kit', 'QA-Lou',
];

function minPlayers(game: CatalogGame): number {
  return Math.max(1, Number(game.config_schema?.players?.min ?? game.rules?.player_count?.min ?? 2));
}

function planFor(game: CatalogGame): GamePlan {
  return registry.plans[game.id] || {};
}

function settleMs(game: CatalogGame): number {
  return planFor(game).settle_ms ?? registry.defaults.settle_ms;
}

// ---------------------------------------------------------------------------------------------
// Shared assertions
// ---------------------------------------------------------------------------------------------

/**
 * "Not an error, not a blank" — the only signal that generalises across 38 engines.
 *
 * Positive per-engine selectors do not exist as a set (they are 38 different screens), so the
 * generic assertion is negative space plus a liveness floor. Games that DO have a stable positive
 * signal declare `expect_button`/`expect_testid` and get both.
 */
async function expectPlayableScreen(page: Page, game: CatalogGame, lobbyTestId: string, pageErrors: string[]) {
  // 1. The lobby (or seat roster) is gone — the engine took over the screen.
  await expect(page.getByTestId(lobbyTestId)).toBeHidden({ timeout: 40_000 });

  await page.waitForTimeout(settleMs(game));

  // 2. Not the crash screen.
  await expect(page.getByText('Something went wrong')).toHaveCount(0);
  // 3. Not bounced back to the picker (what an ERROR from the socket does).
  await expect(page.getByRole('heading', { name: 'Choose a Game' })).toHaveCount(0);
  // 4. No uncaught exception. A React subtree that threw renders as a blank region, not a 500 page,
  //    so this is the only way to see it.
  expect(pageErrors, `${game.id} raised uncaught page errors`).toEqual([]);

  // 5. Not blank. The floor is calibrated against the LEANEST real game screen, which is Drawing's
  //    host view — "Drawer: X / Clue: _ _ _" over black, ~110 characters including the spark chrome.
  //    An empty shell renders only the spark badge (~12 chars), so 40 separates them with room to
  //    spare. A higher floor fails on real screens (it did, on wmlt and drawing, at 120).
  const text = ((await page.locator('body').innerText()) || '').trim();
  expect(text.length, `${game.id} first screen looks blank: ${JSON.stringify(text.slice(0, 200))}`)
    .toBeGreaterThan(40);

  // 6. The engine's own signal, where one exists.
  const plan = planFor(game);
  if (plan.expect_button) {
    await expect(page.getByRole('button', { name: plan.expect_button })).toBeVisible({ timeout: 20_000 });
  }
  if (plan.expect_testid) {
    await expect(page.getByTestId(plan.expect_testid)).toBeVisible({ timeout: 20_000 });
  }
}

function trackPageErrors(page: Page): string[] {
  const errors: string[] = [];
  page.on('pageerror', (error) => errors.push(error.message));
  return errors;
}

/**
 * Create the room the way the product does: prepared content first (where the game needs it), then
 * `/room/create` with the catalog's `game_type` — never its `id`.
 */
async function createRoomForGame(request: APIRequestContext, game: CatalogGame, deviceId: string): Promise<LiveRoom> {
  const plan = planFor(game);
  const extra: Record<string, unknown> = { ...(plan.room_body || {}) };

  if (plan.content) {
    const body: Record<string, unknown> = { ...plan.content.body };
    if (typeof body.deck_prefix === 'string') {
      body.deck = deterministicBingoDeck(body.deck_prefix);
      delete body.deck_prefix;
    }
    const created = await postJson<Record<string, string>>(request, plan.content.endpoint, body, deviceId);
    const contentId = created[plan.content.id_field];
    expect(contentId, `${plan.content.endpoint} returned no ${plan.content.id_field}`).toBeTruthy();
    extra[plan.content.room_field] = contentId;
  }

  // Pass-and-play seats are derived from the catalog minimum, so a game that changes its minimum
  // does not need this file edited.
  if (game.interaction === 'pass_and_play') {
    const seats = PLAYER_POOL.slice(0, minPlayers(game));
    extra[`${game.game_type}_config`] = { seat_names: seats };
  }

  return createRoomViaApi(request, deviceId, { game_type: game.game_type, ...extra });
}

/**
 * Hand the room back (SPEC-TESTING §2: "Every created room must be ended or abandoned to its TTL").
 *
 * Not politeness — arithmetic. `MAX_ROOMS` is 50 and `ROOM_TTL_SECONDS` is 1800, so one 38-game run
 * leaves 38 rooms squatting for half an hour and the NEXT run reports 429 "Too many active rooms"
 * for two thirds of the catalog. Observed on the first local run of this suite.
 *
 * There is no REST endpoint for it, so this speaks the organizer socket directly: connect,
 * `AUTH` with the organizer token, `CANCEL_GAME` (socket_manager → close_room). Teardown never
 * fails a test — a leaked room is a slower next run, not a wrong verdict.
 */
async function releaseRoom(page: Page, room: LiveRoom) {
  const wsBase = apiBase.replace(/^http/, 'ws').replace(/\/$/, '');
  await page
    .evaluate(
      ({ wsBase: base, code, token }) =>
        new Promise<void>((resolve) => {
          const done = setTimeout(resolve, 5000);
          try {
            const socket = new WebSocket(`${base}/ws/${code}/qa-teardown?organizer=true`);
            socket.onopen = () => {
              socket.send(JSON.stringify({ type: 'AUTH', token }));
              setTimeout(() => socket.send(JSON.stringify({ type: 'CANCEL_GAME' })), 250);
              setTimeout(() => {
                socket.close();
                clearTimeout(done);
                resolve();
              }, 900);
            };
            socket.onerror = () => {
              clearTimeout(done);
              resolve();
            };
          } catch {
            clearTimeout(done);
            resolve();
          }
        }),
      { wsBase, code: room.roomCode, token: room.organizerToken },
    )
    .catch(() => {});
}

/** Dismiss the settings drawer, which otherwise swallows the Start click (see harness). */
async function clearOverlays(page: Page) {
  await page.evaluate(() => window.dispatchEvent(new CustomEvent('close-settings')));
  await page.keyboard.press('Escape').catch(() => {});
}

async function forceClick(page: Page, testId: string) {
  const button = page.getByTestId(testId);
  await button.scrollIntoViewIfNeeded();
  await button.evaluate((element) => (element as HTMLButtonElement).click());
}

// ---------------------------------------------------------------------------------------------
// Leg 1 — catalog: rules metadata resolves, and the game is reachable in the picker.
// ---------------------------------------------------------------------------------------------

test.describe('every catalog game · metadata', () => {
  test.describe.configure({ timeout: 90_000 });

  for (const game of CATALOG) {
    test(`catalog · ${game.id}`, async ({ page }) => {
      // (a) The backend's rules payload is well-formed. `rulesForGame` has a frontend fallback, so
      // asserting only the rendered modal would pass even with the catalog rules missing entirely.
      const rules = game.rules;
      expect(rules, `${game.id} has no rules metadata`).toBeTruthy();
      expect(rules!.title, `${game.id} rules have no title`).toBeTruthy();
      expect(rules!.summary, `${game.id} rules have no summary`).toBeTruthy();
      expect(rules!.sections?.length, `${game.id} rules have no sections`).toBeGreaterThan(0);
      for (const section of rules!.sections!) {
        expect(section.items.length, `${game.id} rules section "${section.id}" is empty`).toBeGreaterThan(0);
      }
      expect(rules!.player_count?.min, `${game.id} rules have no minimum player count`).toBeGreaterThan(0);

      await page.goto('/');
      await expect(page.getByRole('heading', { name: 'Choose a Game' })).toBeVisible({ timeout: 30_000 });

      // (b) The game is reachable in the product. This is the assertion the occasion bingos needed:
      // they were in the catalog and correct on the backend, but had fallen out of the picker.
      const card = page.getByTestId(`game-card-${game.id}`);
      await card.scrollIntoViewIfNeeded();
      await expect(card, `no picker tile for catalog game ${game.id}`).toBeVisible();
      await expect(card).toContainText(game.title);

      // (c) …and its rules survive the whole trip: catalog → /catalog → gameRules → modal.
      await card.getByRole('button', { name: 'Rules' }).click();
      await expect(page.locator('#game-rules-title')).toHaveText(rules!.title!, { timeout: 10_000 });
      await expect(page.getByRole('dialog')).toContainText(rules!.sections![0].title);
      await page.getByRole('button', { name: 'Close rules' }).click();
    });
  }
});

// ---------------------------------------------------------------------------------------------
// Leg 2 — play: a room can be created, the min-player gate behaves, the first screen renders.
// ---------------------------------------------------------------------------------------------

test.describe('every catalog game · plays', () => {
  test.describe.configure({ timeout: 180_000 });

  test.beforeEach(async ({}, testInfo) => {
    test.skip(
      testInfo.project.name !== 'chromium-desktop',
      'The play leg opens one browser context per player and runs desktop-only.',
    );
  });

  for (const game of CATALOG) {
    const waiver = registry.waivers[game.id];

    test(`play · ${game.id}`, async ({ page, browser, request }) => {
      // A waiver is a decision, not an omission: it still creates the room (so a broken
      // /room/create is caught) and only skips the play-through it cannot automate.
      const deviceId = liveDeviceId(`all-games-${game.id}`);
      const room = await createRoomForGame(request, game, deviceId);
      expect(room.roomCode).toMatch(/^[A-Z0-9]{6}$/);

      const pageErrors = trackPageErrors(page);
      try {
        if (waiver) {
          test.info().annotations.push({
            type: 'waiver',
            description: `${waiver.reason} (revisit: ${waiver.revisit_when})`,
          });
          await page.goto('/'); // teardown needs an allowed WebSocket origin
          test.skip(true, `WAIVED play-through — ${waiver.reason}`);
        }

        if (game.interaction === 'pass_and_play') {
          await playPassAndPlay(page, game, room, pageErrors);
        } else {
          await playWithPlayers(page, browser, game, room, pageErrors);
        }
      } finally {
        await releaseRoom(page, room);
      }
    });
  }
});

/**
 * Standard interaction: one phone per player.
 *
 * The gate is checked by joining one short of the minimum first — the cheap version (assert
 * disabled with a full room) proves nothing, because the button is enabled then anyway.
 */
async function playWithPlayers(
  page: Page,
  browser: Browser,
  game: CatalogGame,
  room: LiveRoom,
  pageErrors: string[],
) {
  const needed = minPlayers(game);
  expect(needed, `${game.id} needs more players than the suite will spin up`)
    .toBeLessThanOrEqual(registry.defaults.max_players);

  await openOrganizerFromRoom(page, room);
  const startButton = page.getByTestId('organizer-start-game');
  let players: LivePlayer[] = [];

  try {
    if (needed > 1) {
      players = await joinPlayers(browser, room.roomCode, PLAYER_POOL.slice(0, needed - 1));
      await expect(page.getByTestId('organizer-player-count')).toHaveText(String(needed - 1), { timeout: 30_000 });
      await clearOverlays(page);
      await expect(startButton, `${game.id} allows Start below its ${needed}-player minimum`).toBeDisabled();
    }

    players = players.concat(await joinPlayers(browser, room.roomCode, [PLAYER_POOL[needed - 1]]));
    await expect(page.getByTestId('organizer-player-count')).toHaveText(String(needed), { timeout: 30_000 });
    await clearOverlays(page);
    await expect(startButton, `${game.id} refuses Start at its own minimum`).toBeEnabled({ timeout: 15_000 });

    await forceClick(page, 'organizer-start-game');
    await expectPlayableScreen(page, game, 'organizer-room-code', pageErrors);
  } finally {
    await closePlayers(players).catch(() => {});
  }
}

/**
 * Pass-and-play interaction: ONE phone, zero sockets, host-typed seats (SPEC-PASS-AND-PLAY §1).
 *
 * There is no lobby and no room code here — `ROOM` renders the seat roster — so both the ready
 * signal and the start gate are different in kind, not just in timing.
 */
async function playPassAndPlay(page: Page, game: CatalogGame, room: LiveRoom, pageErrors: string[]) {
  const needed = minPlayers(game);
  await openOrganizerFromRoom(page, room, { readyLocator: '[data-testid="seat-roster"]' });

  const startButton = page.getByTestId('seat-start');

  // Type the roster the way a host does, rather than trusting the seats the room was created with.
  //
  // `SeatRosterSetup` seeds its names from `initialNames` in a `useState` INITIALISER, so seats that
  // arrive in the IMPOSTOR_SYNC after the component mounts are never adopted — the host sees blank
  // rows. That is a real (small) reconnect-path gap, filed separately; here it means seeded seats
  // cannot be relied on as the gate's starting point.
  //
  // Filling `needed - 1` seats and asserting Start is refused is the pass-and-play analogue of
  // joining one player short: the gate is seat count, not connected players, because pass-and-play
  // rooms have zero sockets by design (SPEC-PASS-AND-PLAY §1).
  for (let seat = 0; seat < needed - 1; seat += 1) {
    await page.getByTestId(`seat-input-${seat}`).fill(PLAYER_POOL[seat]);
  }
  await expect(startButton, `${game.id} allows Start below its ${needed}-seat minimum`).toBeDisabled();
  await page.getByTestId(`seat-input-${needed - 1}`).fill(PLAYER_POOL[needed - 1]);
  await expect(startButton, `${game.id} refuses Start at its own seat minimum`).toBeEnabled({ timeout: 15_000 });

  await clearOverlays(page);
  await forceClick(page, 'seat-start');
  await expectPlayableScreen(page, game, 'seat-roster', pageErrors);
}
