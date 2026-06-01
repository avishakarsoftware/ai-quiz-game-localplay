import { expect, test, type Browser, type Page } from '@playwright/test';

async function joinPlayer(browser: Browser, roomCode: string, nickname: string) {
  const context = await browser.newContext({ baseURL: process.env.PLAYWRIGHT_BASE_URL || 'http://localhost:5173' });
  const page = await context.newPage();

  await page.goto(`/join/${roomCode}`);
  await page.getByPlaceholder('Your nickname').fill(nickname);
  await page.getByRole('button', { name: 'Join' }).click();
  await expect(page.getByRole('heading', { name: "You're in!" })).toBeVisible({ timeout: 15_000 });

  return { context, page, nickname };
}

async function findActiveStoryPlayer(players: Array<{ page: Page; nickname: string }>) {
  await expect.poll(async () => {
    let active = 0;
    for (const player of players) {
      if (await player.page.getByRole('button', { name: 'Add Sentence' }).isVisible().catch(() => false)) active += 1;
    }
    return active;
  }, { timeout: 20_000 }).toBe(1);

  for (const player of players) {
    if (await player.page.getByRole('button', { name: 'Add Sentence' }).isVisible().catch(() => false)) {
      return player;
    }
  }
  throw new Error('No active Story Chain player found');
}

test.describe('Standalone live turn handoff on gamma', () => {
  test('Story Chain hands the turn to the next player after a valid sentence', async ({ page, browser }, testInfo) => {
    test.skip(!String(process.env.PLAYWRIGHT_BASE_URL || '').includes('gamma'), 'live gamma test only');
    test.skip(testInfo.project.name !== 'chromium-desktop', 'multi-context live flow runs desktop-only');

    await page.goto('/');
    await page.getByRole('button', { name: /Story Chain/ }).click();

    const roomCode = (await page.locator('.room-code').textContent({ timeout: 20_000 }))?.trim();
    expect(roomCode).toMatch(/^[A-Z0-9]{6}$/);

    const players = await Promise.all([
      joinPlayer(browser, roomCode!, 'Avi'),
      joinPlayer(browser, roomCode!, 'Ruchi'),
      joinPlayer(browser, roomCode!, 'Maya'),
    ]);

    try {
      await expect(page.getByText('3 players')).toBeVisible({ timeout: 20_000 });
      await page.getByRole('button', { name: 'Start Game' }).click();
      await expect(page.getByRole('heading', { name: 'Story Chain' })).toBeVisible({ timeout: 20_000 });

      const firstActive = await findActiveStoryPlayer(players);
      await firstActive.page.getByPlaceholder('Add one sentence...').fill('The first song made everyone laugh loudly.');
      await firstActive.page.getByRole('button', { name: 'Add Sentence' }).click();

      await expect.poll(async () => {
        const activeNames: string[] = [];
        for (const player of players) {
          const active = await player.page.getByRole('button', { name: 'Add Sentence' }).isVisible().catch(() => false);
          if (active) activeNames.push(player.nickname);
        }
        return activeNames;
      }, { timeout: 20_000 }).not.toEqual([firstActive.nickname]);
    } finally {
      await Promise.all(players.map(({ context }) => context.close()));
    }
  });
});
