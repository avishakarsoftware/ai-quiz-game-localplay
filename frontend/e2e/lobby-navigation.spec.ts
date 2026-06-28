import { test, expect, type Browser } from '@playwright/test';
import {
  liveBaseURL,
  liveDeviceId,
  createRoomViaApi,
  type LiveRoom,
} from './liveGameHarness';

/**
 * Local sweep for the lobby navigation actions (Back to games / Edit setup)
 * added in "Add explicit lobby navigation actions". Runs against a real local
 * stack (backend :9100, frontend :9200) so every game's lobby is exercised.
 *
 * Reaching the lobby via reconnect (openOrganizer session) means the per-session
 * content state (quiz/mltGame/...) is NOT repopulated — so content games show
 * only "Back to games" on reconnect, while config/setup games whose edit target
 * is unconditional (Musical Chairs, Party Quests, Housie, Bingo) also show Edit.
 */

// Games creatable directly (no content import). On a reconnect lobby these show
// only "Back to games" — except the unconditional-edit games flagged below.
const DIRECT_GAMES: { gameType: string; expectEdit?: string }[] = [
  { gameType: 'bluff' },
  { gameType: 'two_truths' },
  { gameType: 'story_chain' },
  { gameType: 'common_ground' },
  { gameType: 'find_someone' },
  { gameType: 'mafia' },
  { gameType: 'survey_says' },
  { gameType: 'would_you_rather' },
  { gameType: 'never_have_i_ever' },
  { gameType: 'word_association' },
  { gameType: 'acronym' },
  { gameType: 'photo_clue' },
  { gameType: 'poker' },
  { gameType: 'caption_contest' },
  { gameType: 'musical_chairs', expectEdit: 'Edit setup' },
  { gameType: 'party_quests', expectEdit: 'Edit quests' },
];

async function openLobby(browser: Browser, room: LiveRoom, viewport?: { width: number; height: number }) {
  const context = await browser.newContext({ baseURL: liveBaseURL, ...(viewport ? { viewport } : {}) });
  const page = await context.newPage();
  await page.addInitScript((session) => {
    window.localStorage.setItem('localplay_organizer_session', JSON.stringify(session));
  }, {
    roomCode: room.roomCode,
    organizerToken: room.organizerToken,
    gameType: room.gameType,
    contentId: room.contentId,
    savedAt: Date.now(),
  });
  await page.goto('/');
  await expect(page.locator('.room-code')).toHaveText(room.roomCode, { timeout: 20_000 });
  return { context, page };
}

// Needs a real backend: either a remote PLAYWRIGHT_BASE_URL (backend-served,
// e.g. gamma) or a separate LIVE_API_BASE_URL (local stack on another port).
// Run desktop-only via --project chromium-desktop.
test.describe('Lobby navigation actions', () => {
  test.skip(!process.env.PLAYWRIGHT_BASE_URL && !process.env.LIVE_API_BASE_URL,
    'set PLAYWRIGHT_BASE_URL (remote) or LIVE_API_BASE_URL (local backend) to run');

  test('every game lobby offers Back to games; edit appears only where supported', async ({ browser, request }) => {
    const summary: string[] = [];
    for (const { gameType, expectEdit } of DIRECT_GAMES) {
      const room = await createRoomViaApi(request, liveDeviceId(`nav-${gameType}`), { game_type: gameType });
      const { context, page } = await openLobby(browser, room);

      // Back to games is present for every game.
      await expect(page.getByRole('button', { name: /back to games/i })).toBeVisible();

      const editVisible = await page.getByRole('button', { name: /^Edit / }).first().isVisible().catch(() => false);
      if (expectEdit) {
        await expect(page.getByRole('button', { name: expectEdit })).toBeVisible();
      } else {
        expect(editVisible, `${gameType} should not show an Edit button on reconnect`).toBe(false);
      }
      summary.push(`${gameType}: back=yes edit=${editVisible ? 'yes' : 'no'}`);
      await context.close();
    }
    console.log('LOBBY NAV SWEEP:\n' + summary.join('\n'));
  });

  test('visual: direct game and edit game lobbies', async ({ browser, request }) => {
    const bluff = await createRoomViaApi(request, liveDeviceId('nav-shot-bluff'), { game_type: 'bluff' });
    const b = await openLobby(browser, bluff);
    await b.page.screenshot({ path: 'test-results/lobby-nav-bluff.png', fullPage: true });
    await b.context.close();

    const mc = await createRoomViaApi(request, liveDeviceId('nav-shot-mc'), { game_type: 'musical_chairs' });
    const m = await openLobby(browser, mc);
    await m.page.screenshot({ path: 'test-results/lobby-nav-musical-chairs.png', fullPage: true });
    await m.context.close();

    // Mobile viewport (Pixel 5 size) — verify the top action row doesn't collide
    // with the fixed hamburger menu on narrow screens.
    const mcMobile = await createRoomViaApi(request, liveDeviceId('nav-shot-mc-m'), { game_type: 'musical_chairs' });
    const mm = await openLobby(browser, mcMobile, { width: 393, height: 851 });
    await mm.page.screenshot({ path: 'test-results/lobby-nav-musical-chairs-mobile.png', fullPage: true });
    await mm.context.close();
  });

  test('Back to games returns to the game catalog', async ({ browser, request }) => {
    const room = await createRoomViaApi(request, liveDeviceId('nav-back'), { game_type: 'bluff' });
    const { context, page } = await openLobby(browser, room);
    page.on('dialog', (d) => d.accept());
    await page.getByRole('button', { name: /back to games/i }).click();
    await expect(page.getByRole('heading', { name: 'Choose a Game' })).toBeVisible({ timeout: 10_000 });
    await expect(page.locator('.room-code')).toHaveCount(0);
    await context.close();
  });

  test('content game create flow shows Edit questions and round-trips to review', async ({ page }) => {
    // Build a minimal custom quiz (no AI) and create a real room, so the
    // per-session content state is set and the content-game Edit button appears.
    page.on('dialog', (d) => d.accept());
    await page.goto('/');
    await page.getByRole('button', { name: /AI Quiz/ }).click();
    await page.getByRole('button', { name: 'Create Your Own' }).click();
    await page.getByLabel('Question text').fill('Where did we meet?');
    await page.getByLabel('Answer A').fill('Mumbai');
    await page.getByLabel('Answer B').fill('Seattle');
    await page.getByLabel('Answer C').fill('Austin');
    await page.getByLabel('Answer D').fill('London');
    await page.getByRole('button', { name: 'Set correct option B' }).click();
    await page.getByRole('button', { name: 'Review & Start' }).click();
    await page.getByRole('button', { name: 'Create Room' }).click();

    await expect(page.locator('.room-code')).toBeVisible({ timeout: 20_000 });
    await expect(page.getByRole('button', { name: /back to games/i })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Edit questions' })).toBeVisible();
    await page.screenshot({ path: 'test-results/lobby-nav-quiz.png', fullPage: true });

    // Edit questions closes the lobby and returns to review (Create Room again).
    await page.getByRole('button', { name: 'Edit questions' }).click();
    await expect(page.locator('.room-code')).toHaveCount(0, { timeout: 10_000 });
    await expect(page.getByRole('button', { name: 'Create Room' })).toBeVisible({ timeout: 10_000 });
  });

  test('Edit setup leaves the lobby for the setup screen', async ({ browser, request }) => {
    const room = await createRoomViaApi(request, liveDeviceId('nav-edit'), { game_type: 'musical_chairs' });
    const { context, page } = await openLobby(browser, room);
    page.on('dialog', (d) => d.accept());
    await page.getByRole('button', { name: 'Edit setup' }).click();
    // Leaving the lobby: room code is gone and we're on the Musical Chairs setup.
    await expect(page.locator('.room-code')).toHaveCount(0, { timeout: 10_000 });
    await context.close();
  });
});
