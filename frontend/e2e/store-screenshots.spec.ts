import { expect, test, type Browser, type Page } from '@playwright/test';
import fs from 'node:fs/promises';
import path from 'node:path';
import {
  closePlayers,
  createRoomViaApi,
  deterministicQuiz,
  joinPlayers,
  liveDeviceId,
  openOrganizerFromRoom,
  postJson,
  startLobbyGame,
} from './liveGameHarness';

/**
 * Store screenshot capture — App Store + Google Play.
 *
 * Produces every listing screenshot at the exact pixel sizes both stores require
 * (see marketing/STORE_ASSETS.md: image px = viewport x deviceScaleFactor), writing
 * straight into marketing/app-store/... and marketing/play-store/....
 *
 * Run against PROD so the visible join URL is the real public domain:
 *   PLAYWRIGHT_BASE_URL=https://games.revelryapp.me \
 *   LIVE_API_BASE_URL=https://gamesapi.revelryapp.me \
 *   STORE_SHOTS=1 npx playwright test e2e/store-screenshots.spec.ts --project chromium-desktop --workers=1
 *
 * Rooms are created with fresh device ids (each gets the signup spark bonus, enough
 * for one room), so capturing costs nothing real. Screenshots are opaque PNGs — the
 * app is full-bleed on the Velvet background — which both stores require.
 */

// ESM: no __dirname. Resolve marketing/ from the repo root via cwd (playwright runs in frontend/).
const MARKETING = path.resolve(process.cwd(), '../marketing');

type Target = {
  dir: string;          // output directory (relative to marketing/)
  viewport: { width: number; height: number };
  dsf: number;          // deviceScaleFactor
  label: string;
  expect: { width: number; height: number };  // final image px, asserted
};

// Sizes straight from marketing/STORE_ASSETS.md.
const TARGETS: Target[] = [
  { dir: 'app-store/iphone-6.7', label: 'iPhone 6.7"', viewport: { width: 430, height: 932 }, dsf: 3, expect: { width: 1290, height: 2796 } },
  { dir: 'app-store/ipad-12.9', label: 'iPad 12.9"', viewport: { width: 1024, height: 1366 }, dsf: 2, expect: { width: 2048, height: 2732 } },
  { dir: 'play-store/phone', label: 'Play phone', viewport: { width: 360, height: 720 }, dsf: 3, expect: { width: 1080, height: 2160 } },
  { dir: 'play-store/tablet-10', label: 'Play 10" tablet', viewport: { width: 800, height: 1280 }, dsf: 2, expect: { width: 1600, height: 2560 } },
];

async function shoot(page: Page, target: Target, name: string) {
  const dir = path.join(MARKETING, target.dir);
  await fs.mkdir(dir, { recursive: true });
  const file = path.join(dir, `${name}.png`);
  // Viewport-sized (not fullPage) so the image is exactly the store's required px.
  await page.screenshot({ path: file, fullPage: false });
  const buf = await fs.readFile(file);
  // PNG header: width/height are big-endian uint32 at bytes 16..24.
  const width = buf.readUInt32BE(16);
  const height = buf.readUInt32BE(20);
  expect(width, `${target.dir}/${name} width`).toBe(target.expect.width);
  expect(height, `${target.dir}/${name} height`).toBe(target.expect.height);
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

/** Join a player at the STORE target viewport (harness joinPlayer uses the default
 *  project viewport, which would produce wrong-sized screenshots). */
async function joinPlayerAtTarget(browser: Browser, target: Target, roomCode: string, nickname: string): Promise<Page> {
  const page = await newPage(browser, target);
  await page.goto(`/join/${roomCode}`);
  await page.getByPlaceholder('Your nickname').fill(nickname);
  await page.getByRole('button', { name: 'Join' }).click();
  await expect(page.getByRole('heading', { name: "You're in!" })).toBeVisible({ timeout: 20_000 });
  return page;
}

test.describe('Store screenshots', () => {
  test.beforeEach(({}, testInfo) => {
    test.skip(process.env.STORE_SHOTS !== '1', 'Set STORE_SHOTS=1 to capture store screenshots (writes into marketing/).');
    test.skip(testInfo.project.name !== 'chromium-desktop', 'Capture runs once; viewports are set per-target inside the test.');
  });

  for (const target of TARGETS) {
    test(`capture ${target.label} (${target.expect.width}x${target.expect.height})`, async ({ browser, request }, testInfo) => {
      test.setTimeout(240_000);
      const captured: string[] = [];

      // --- 01 Catalog: the variety story. Lead with "Most Popular" so the marquee games
      // (AI Quiz, Most Likely To, Drawing) are on screen rather than an alphabetical
      // list starting at "Acronym Game" / "Baby Bingo".
      const catalog = await newPage(browser, target);
      await catalog.goto('/');
      await expect(catalog.getByRole('heading', { name: 'Choose a Game' })).toBeVisible({ timeout: 30_000 });
      const popular = catalog.getByRole('button', { name: 'Most Popular', exact: true });
      if (await popular.first().isVisible().catch(() => false)) {
        await popular.first().click();
        await catalog.waitForTimeout(500);
        // Clicking the chip scrolls it into view, which slices the filter row and hides the
        // "Choose a Game" heading. Put the page back at the top for the shot.
        await catalog.getByRole('heading', { name: 'Choose a Game' }).scrollIntoViewIfNeeded();
        await catalog.evaluate(() => window.scrollTo(0, 0));
      }
      await catalog.waitForTimeout(600); // let cards/animations settle
      captured.push(await shoot(catalog, target, '01-catalog'));

      // --- 07 Get Sparks: the IAP screen (Apple wants IAP visible; shows value + terms) ---
      await catalog.locator('[aria-label="Get Sparks"]').first().click();
      await expect(catalog.getByTestId('spark-purchase-modal')).toBeVisible({ timeout: 15_000 });
      await catalog.waitForTimeout(400);
      captured.push(await shoot(catalog, target, '07-get-sparks'));

      // --- 02 AI Quiz setup: the AI hook ---
      const setup = await newPage(browser, target);
      await setup.goto('/');
      await expect(setup.getByRole('heading', { name: 'Choose a Game' })).toBeVisible({ timeout: 30_000 });
      await setup.getByRole('button', { name: /AI Quiz/ }).click();
      await setup.waitForTimeout(600);
      captured.push(await shoot(setup, target, '02-quiz-setup'));
      await setup.context().close();

      // --- Live quiz room: lobby -> question -> podium ---
      const deviceId = liveDeviceId('store');
      const { quiz_id: quizId } = await postJson<{ quiz_id: string }>(
        request, '/quiz/import', { quiz: deterministicQuiz }, deviceId,
      );
      const room = await createRoomViaApi(request, deviceId, { game_type: 'quiz', quiz_id: quizId, time_limit: 60 });

      const host = await newPage(browser, target);
      await openOrganizerFromRoom(host, room);

      await expect(host.getByTestId('organizer-room-code')).toBeVisible({ timeout: 30_000 });

      // 06 Player join — "everyone joins from their own phone, no download". Captured from a
      // real join URL for this room, before filling anything in.
      const joinShot = await newPage(browser, target);
      await joinShot.goto(`/join/${room.roomCode}`);
      await expect(joinShot.getByPlaceholder('Your nickname')).toBeVisible({ timeout: 20_000 });
      await joinShot.waitForTimeout(500);
      captured.push(await shoot(joinShot, target, '06-player-join'));
      await joinShot.context().close();

      // Maya joins at the store viewport (her phone is what we screenshot);
      // Leo + Ada fill the room so the lobby/leaderboard look real.
      const maya = await joinPlayerAtTarget(browser, target, room.roomCode, 'Maya');
      const players = await joinPlayers(browser, room.roomCode, ['Leo', 'Ada']);
      try {
        await expect(host.getByTestId('organizer-player-count')).toHaveText('3', { timeout: 20_000 });

        // 03 Lobby — QR + room code ("everyone joins from their phone"). Shot *after* the
        // joins: an empty lobby reads "Waiting for players..." and sells nothing.
        await host.waitForTimeout(800);
        captured.push(await shoot(host, target, '03-lobby'));

        await startLobbyGame(host, 3);

        // 04 Gameplay — a live question on the player's own phone (the real player POV)
        await expect(maya.getByText(deterministicQuiz.questions[0].text)).toBeVisible({ timeout: 30_000 });
        await maya.waitForTimeout(600);
        captured.push(await shoot(maya, target, '04-gameplay'));

        // Answer through both questions so we land on a podium with a REAL winner.
        // (Clicking the first option scores 0 for everyone -> "It's a Tie!" 0/0/0, which
        // makes a terrible store screenshot.) Maya sweeps; Leo and Ada each take one.
        const answerPlan: Record<string, boolean[]> = {
          Maya: [true, true],   // 1st — clear winner
          Leo: [true, false],   // 2nd
          Ada: [false, true],   // 3rd
        };
        const pagesByName: Record<string, Page> = {
          Maya: maya,
          ...Object.fromEntries(players.map((p) => [p.nickname, p.page])),
        };

        // Scoring is speed-weighted, so simultaneous correct answers tie (978/978). Answer in
        // podium order with a gap between players so 1st/2nd/3rd are visibly distinct.
        const answerOrder = ['Maya', 'Leo', 'Ada'];

        for (let q = 0; q < deterministicQuiz.questions.length; q++) {
          const question = deterministicQuiz.questions[q];
          const correct = question.options[question.answer_index];
          const wrong = question.options.find((o) => o !== correct)!;
          for (const name of answerOrder) {
            const page = pagesByName[name];
            const choice = answerPlan[name]?.[q] ? correct : wrong;
            // Non-exact name match: the option button's accessible name carries more than
            // the option text. `exact: true` matches nothing -> no answers -> a 0/0/0 podium.
            const button = page.getByRole('button', { name: choice });
            await expect(button.first()).toBeEnabled({ timeout: 20_000 });
            await button.first().click();
            await page.waitForTimeout(1200); // widen the speed-bonus gap between players
          }
          await host.waitForTimeout(2500);

          // The host advances in two steps: reveal -> "Show Scores" -> leaderboard ->
          // "Next Question" / "Show Results" (final). Never match "End Game" loosely: it
          // cuts the quiz off after Q1 and the podium loses a question's worth of scores.
          const showScores = host.getByRole('button', { name: /Show Scores/ });
          if (await showScores.first().isVisible({ timeout: 15_000 }).catch(() => false)) {
            await showScores.first().click();
            await host.waitForTimeout(1200);
          }
          // The leaderboard button carries a countdown suffix, e.g. "Next Question (4)".
          const advance = host.getByRole('button', { name: /Next Question|Show Results/ });
          if (await advance.first().isVisible({ timeout: 15_000 }).catch(() => false)) {
            await advance.first().click().catch(() => {}); // may auto-advance on countdown
          }
          await host.waitForTimeout(1500);
        }

        // 05 Podium — the payoff. It must show a real winner: a "It's a Tie!" 0/0/0 board
        // is a broken-looking store screenshot, so assert rather than capture whatever.
        await expect(host.getByText(/Final Results/i).first()).toBeVisible({ timeout: 20_000 });
        await expect(host.getByText(/is the Champion!|wins!/i).first()).toBeVisible({ timeout: 10_000 });
        await expect(host.getByText(/It's a Tie!/i)).toHaveCount(0);
        await host.waitForTimeout(1200); // let confetti/animation land
        captured.push(await shoot(host, target, '05-podium'));
      } finally {
        await closePlayers(players);
        await maya.context().close();
        await host.context().close();
        await catalog.context().close();
      }

      testInfo.annotations.push({ type: 'captured', description: captured.map((f) => path.relative(MARKETING, f)).join(', ') });
      expect(captured.length).toBe(7);
    });
  }
});
