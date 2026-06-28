import { expect, test, type Browser } from '@playwright/test';
import { expectNoHorizontalOverflow } from './helpers';

async function joinBluffPlayer(browser: Browser, roomCode: string, nickname: string) {
  const context = await browser.newContext({ baseURL: process.env.PLAYWRIGHT_BASE_URL || 'http://localhost:5173' });
  const page = await context.newPage();

  await page.goto(`/join/${roomCode}`);
  await page.getByPlaceholder('Your nickname').fill(nickname);
  await page.getByRole('button', { name: 'Join' }).click();
  await expect(page.getByRole('heading', { name: "You're in!" })).toBeVisible({ timeout: 15_000 });

  return { context, page };
}

test.describe('Bluff gamma live flow', () => {
  test('creates a Bluff room, joins players, and renders card tables on gamma', async ({ page, browser }, testInfo) => {
    test.skip(!String(process.env.PLAYWRIGHT_BASE_URL || '').includes('gamma'), 'live gamma test only');
    test.skip(testInfo.project.name !== 'chromium-desktop', 'multi-context live flow runs desktop-only');

    await page.goto('/');
    await page.getByRole('button', { name: /Bluff/ }).click();

    const roomCode = (await page.locator('.room-code').textContent({ timeout: 20_000 }))?.trim();
    expect(roomCode).toMatch(/^[A-Z0-9]{6}$/);

    const players = await Promise.all([
      joinBluffPlayer(browser, roomCode!, 'Avi'),
      joinBluffPlayer(browser, roomCode!, 'Ruchi'),
      joinBluffPlayer(browser, roomCode!, 'Maya'),
    ]);

    try {
      await expect(page.getByText(/3\s+connected players?/i)).toBeVisible({ timeout: 20_000 });
      await page.getByRole('button', { name: 'Start Game' }).click();

      await expect(page.getByRole('heading', { name: 'Bluff' })).toBeVisible({ timeout: 20_000 });
      await expect(page.getByText('Card table')).toBeVisible();
      await expect(page.getByText('Required rank')).toBeVisible();
      await expect(page.getByText('Players')).toBeVisible();
      await expectNoHorizontalOverflow(page);

      for (const { page: playerPage } of players) {
        await expect(playerPage.getByRole('heading', { name: 'Bluff' })).toBeVisible({ timeout: 20_000 });
        await expect(playerPage.getByText('Your hand')).toBeVisible();
        await expect(playerPage.locator('.bluff-card').first()).toBeVisible();
        await expectNoHorizontalOverflow(playerPage);
      }

      const activePlayer = await (async () => {
        await expect.poll(async () => {
          for (const [index, player] of players.entries()) {
            if (await player.page.getByRole('button', { name: 'Pass' }).isEnabled().catch(() => false)) return index;
          }
          return -1;
        }, { timeout: 20_000 }).not.toBe(-1);
        for (const player of players) {
          if (await player.page.getByRole('button', { name: 'Pass' }).isEnabled().catch(() => false)) return player;
        }
        throw new Error('No active Bluff player found');
      })();
      await activePlayer.page.locator('.bluff-hand .bluff-card').first().click();
      await activePlayer.page.getByRole('button', { name: /Play 1/ }).click();

      await expect(page.getByText(/claims 1/)).toBeVisible({ timeout: 20_000 });
      await expect(page.getByText('Challenge window')).toBeVisible();
      await expect(page.getByText(/Call bluff or continue to pass control/)).toBeVisible();
      await expect(page.getByRole('button', { name: 'Continue', exact: true })).toBeVisible();
      await page.getByRole('button', { name: 'Continue', exact: true }).click();
      await expect(page.getByText(/'s turn · claim/)).toBeVisible({ timeout: 20_000 });
    } finally {
      await Promise.all(players.map(({ context }) => context.close()));
    }
  });
});
