import { expect, test, type Browser, type Page } from '@playwright/test';
import fs from 'node:fs/promises';
import path from 'node:path';
import {
  closePlayers,
  createRoomViaApi,
  joinPlayers,
  liveDeviceId,
  openOrganizerFromRoom,
  startLobbyGame,
} from './liveGameHarness';

/**
 * Store screenshot capture — BREADTH tour.
 *
 * `store-screenshots.spec.ts` sells the quiz flow end-to-end. It does not sell the
 * catalog: a shopper sees one game and assumes the app is one game. This spec plays a
 * handful of *visually distinct* games on prod and shoots each one live, so the store
 * listing can show that 33 games ship in the box.
 *
 * Run (same env as the main store spec):
 *   PLAYWRIGHT_BASE_URL=https://games.revelryapp.me \
 *   LIVE_API_BASE_URL=https://gamesapi.revelryapp.me \
 *   STORE_SHOTS=1 npx playwright test e2e/store-breadth.spec.ts --project chromium-desktop --workers=1
 *
 * Optional: BREADTH_TARGETS=app-store/iphone-6.7 limits to one store target while iterating.
 *
 * Each game is best-effort and isolated: a game that changes its start flow degrades to
 * "no shot for that game" instead of failing the other games. Every shot is still size-
 * asserted, so a wrong-sized image is a hard failure rather than a silent store rejection.
 */

const MARKETING = path.resolve(process.cwd(), '../marketing');

interface Target {
  dir: string;
  label: string;
  viewport: { width: number; height: number };
  dsf: number;
  expect: { width: number; height: number };
}

const ALL_TARGETS: Target[] = [
  { dir: 'app-store/iphone-6.7', label: 'iPhone 6.7"', viewport: { width: 430, height: 932 }, dsf: 3, expect: { width: 1290, height: 2796 } },
  { dir: 'app-store/ipad-12.9', label: 'iPad 12.9"', viewport: { width: 1024, height: 1366 }, dsf: 2, expect: { width: 2048, height: 2732 } },
  { dir: 'play-store/phone', label: 'Play phone', viewport: { width: 360, height: 720 }, dsf: 3, expect: { width: 1080, height: 2160 } },
  { dir: 'play-store/tablet-10', label: 'Play 10" tablet', viewport: { width: 800, height: 1280 }, dsf: 2, expect: { width: 1600, height: 2560 } },
];

const only = process.env.BREADTH_TARGETS?.split(',').map((s) => s.trim()).filter(Boolean);
const TARGETS = only?.length ? ALL_TARGETS.filter((t) => only.includes(t.dir)) : ALL_TARGETS;

/**
 * The tour. `players` is the game's real minimum — starting below it leaves the Start
 * button disabled and the shot never happens. `shootPlayer` picks the phone POV (better
 * for games whose host screen is just a scoreboard); otherwise we shoot the host.
 */
interface Tour {
  gameType: string;
  name: string;          // output file stem, prefixed with its index
  players: string[];
  shootPlayer: boolean;
  settleMs?: number;     // some games need time to reach a screen worth showing
}

const TOUR: Tour[] = [
  // Drawing: the HOST screen is just "Drawer: Leo / Clue: ____" over black. The player
  // screen is where the canvas and tools live, so shoot that and give the round time to open.
  { gameType: 'drawing', name: 'drawing', players: ['Maya', 'Leo', 'Ada'], shootPlayer: true, settleMs: 9000 },
  // Housie is deliberately NOT in the tour: the host calls numbers manually, so an
  // unattended run sits on "Waiting for first call / 0 numbers called" no matter how long
  // it settles (verified at 16s). It needs host-driven calls before it photographs well.
  { gameType: 'poker', name: 'poker', players: ['Maya', 'Leo', 'Ada'], shootPlayer: true },
  { gameType: 'would_you_rather', name: 'would-you-rather', players: ['Maya', 'Leo'], shootPlayer: true },
  { gameType: 'acronym', name: 'acronym', players: ['Maya', 'Leo'], shootPlayer: true },
  // Alternates, so the final 10 can be curated from more than the bare minimum.
  { gameType: 'find_someone', name: 'find-someone', players: ['Maya', 'Leo'], shootPlayer: true, settleMs: 6000 },
  { gameType: 'emoji_story', name: 'emoji-story', players: ['Maya', 'Leo'], shootPlayer: true },
];

async function shoot(page: Page, target: Target, name: string): Promise<string> {
  const dir = path.join(MARKETING, target.dir);
  await fs.mkdir(dir, { recursive: true });
  const file = path.join(dir, `${name}.png`);
  await page.screenshot({ path: file, animations: 'disabled' });
  // Stores reject off-size images; assert rather than discover it in review.
  const { width, height } = await page.viewportSize()!;
  expect({ width: width * target.dsf, height: height * target.dsf }).toEqual(target.expect);
  return file;
}

async function newPage(browser: Browser, target: Target): Promise<Page> {
  const context = await browser.newContext({
    viewport: target.viewport,
    deviceScaleFactor: target.dsf,
    isMobile: target.viewport.width < 700,
    hasTouch: target.viewport.width < 700,
  });
  return context.newPage();
}

/**
 * Join a player AT THE STORE VIEWPORT. The harness `joinPlayers` uses the default
 * viewport, which is right for filler players but wrong for the one we photograph —
 * shooting it produces an off-size image that fails the size assertion.
 */
async function joinPlayerAtTarget(
  browser: Browser,
  target: Target,
  roomCode: string,
  nickname: string,
): Promise<Page> {
  const page = await newPage(browser, target);
  await page.goto(`/join/${roomCode}`);
  await page.getByPlaceholder('Your nickname').fill(nickname);
  await page.getByRole('button', { name: 'Join' }).click();
  await expect(page.getByRole('heading', { name: "You're in!" })).toBeVisible({ timeout: 20_000 });
  return page;
}

test.describe('store breadth tour', () => {
  test.skip(!process.env.STORE_SHOTS, 'set STORE_SHOTS=1 to capture');
  test.setTimeout(15 * 60_000);

  for (const target of TARGETS) {
    test(`breadth — ${target.label}`, async ({ browser, request }) => {
      const captured: string[] = [];
      const skipped: string[] = [];

      for (const [i, game] of TOUR.entries()) {
        const stem = `${String(i + 8).padStart(2, '0')}-${game.name}`;
        let host: Page | undefined;
        let hero: Page | undefined;
        let players: Awaited<ReturnType<typeof joinPlayers>> = [];
        try {
          const deviceId = liveDeviceId(`breadth-${game.gameType}`);
          const room = await createRoomViaApi(request, deviceId, { game_type: game.gameType });

          host = await newPage(browser, target);
          await openOrganizerFromRoom(host, room);

          // The photographed player joins at target size; the rest just fill the room.
          const [heroName, ...fillerNames] = game.players;
          hero = game.shootPlayer
            ? await joinPlayerAtTarget(browser, target, room.roomCode, heroName)
            : undefined;
          players = await joinPlayers(
            browser,
            room.roomCode,
            game.shootPlayer ? fillerNames : game.players,
          );
          await startLobbyGame(host, game.players.length);

          // No universal "game started" selector across 33 engines — settle, then shoot.
          const subject = hero ?? host;
          await subject.waitForTimeout(game.settleMs ?? 4000);
          captured.push(await shoot(subject, target, stem));
        } catch (err) {
          skipped.push(`${game.gameType}: ${(err as Error).message.split('\n')[0]}`);
        } finally {
          await closePlayers(players).catch(() => {});
          await hero?.context().close().catch(() => {});
          await host?.context().close().catch(() => {});
        }
      }

      // Never let a partial tour read as a complete one.
      console.log(`[breadth ${target.label}] captured ${captured.length}/${TOUR.length}`);
      captured.forEach((f) => console.log(`  ✓ ${path.relative(MARKETING, f)}`));
      skipped.forEach((s) => console.log(`  ✗ ${s}`));
      expect(captured.length, `no games captured for ${target.label}`).toBeGreaterThan(0);
    });
  }
});
