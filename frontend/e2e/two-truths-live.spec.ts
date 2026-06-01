import { expect, test, type Browser, type Page } from '@playwright/test';
import { expectNoHorizontalOverflow } from './helpers';

const submissions: Record<string, Array<{ text: string; lie: boolean }>> = {
  Alice: [
    { text: 'I once baked a wedding cake.', lie: false },
    { text: 'I have lived in three cities.', lie: false },
    { text: 'I can juggle flaming torches.', lie: true },
  ],
  Bob: [
    { text: 'I have run a half marathon.', lie: false },
    { text: 'I collect vintage postcards.', lie: true },
    { text: 'I speak a little Spanish.', lie: false },
  ],
  Cara: [
    { text: 'I broke my arm roller skating.', lie: false },
    { text: 'I have never eaten mango.', lie: true },
    { text: 'I can play the piano.', lie: false },
  ],
};

async function joinPlayer(browser: Browser, roomCode: string, nickname: string) {
  const context = await browser.newContext({ baseURL: process.env.PLAYWRIGHT_BASE_URL || 'http://127.0.0.1:5173' });
  const page = await context.newPage();
  await page.goto(`/join/${roomCode}`);
  await page.getByPlaceholder('Your nickname').fill(nickname);
  await page.getByRole('button', { name: 'Join' }).click();
  await expect(page.getByRole('heading', { name: "You're in!" })).toBeVisible({ timeout: 15_000 });
  return { context, page, nickname };
}

async function submitStatements(page: Page, nickname: string) {
  await expect(page.getByRole('heading', { name: 'Two Truths and a Lie' })).toBeVisible({ timeout: 15_000 });
  const rows = page.locator('.two-truths-statement-input');
  await expect(rows).toHaveCount(3);
  const playerSubmission = submissions[nickname];
  for (let index = 0; index < playerSubmission.length; index += 1) {
    await rows.nth(index).locator('textarea').fill(playerSubmission[index].text);
    if (playerSubmission[index].lie) {
      await rows.nth(index).getByRole('button', { name: 'Lie' }).click();
    }
  }
  await page.getByRole('button', { name: /Submit Statements|Update Statements/ }).click();
}

test.describe('Two Truths live flow', () => {
  test('creates a room, submits statements, votes, and reveals the lie', async ({ page, browser }, testInfo) => {
    test.skip(!process.env.TWO_TRUTHS_LIVE, 'live local/gamma flow only');
    test.skip(testInfo.project.name !== 'chromium-desktop', 'multi-context live flow runs desktop-only');

    await page.goto('/');
    await page.getByRole('button', { name: /Two Truths and a Lie/ }).click();

    const roomCode = (await page.locator('.room-code').textContent({ timeout: 20_000 }))?.trim();
    expect(roomCode).toMatch(/^[A-Z0-9]{6}$/);

    const players = await Promise.all([
      joinPlayer(browser, roomCode!, 'Alice'),
      joinPlayer(browser, roomCode!, 'Bob'),
      joinPlayer(browser, roomCode!, 'Cara'),
    ]);

    try {
      await expect(page.getByText('3 players')).toBeVisible({ timeout: 20_000 });
      await page.getByRole('button', { name: 'Start Game' }).click();
      await expect(page.getByText('0 of 3 players ready')).toBeVisible({ timeout: 20_000 });

      await Promise.all(players.map(({ page: playerPage, nickname }) => submitStatements(playerPage, nickname)));
      await expect(page.getByText('3 of 3 players ready')).toBeVisible({ timeout: 20_000 });
      await expectNoHorizontalOverflow(page);

      await page.getByRole('button', { name: 'Start Reveals' }).click();
      await expect(page.getByText('Guess the lie')).toBeVisible({ timeout: 20_000 });

      const author = (await page.locator('.two-truths-author strong').textContent())?.trim() || '';
      const lieText = submissions[author].find((item) => item.lie)!.text;
      const voter = players.find((player) => player.nickname !== author)!;
      await expect(voter.page.getByText('Guess the lie')).toBeVisible({ timeout: 20_000 });
      await voter.page.getByRole('button', { name: new RegExp(lieText) }).click();

      await page.getByRole('button', { name: 'Reveal Lie' }).click();
      await expect(page.getByText(`${author}'s lie revealed`)).toBeVisible({ timeout: 20_000 });
      await expect(page.getByRole('button', { name: new RegExp(lieText) })).toBeVisible();
      await expectNoHorizontalOverflow(page);
    } finally {
      await Promise.all(players.map(({ context }) => context.close()));
    }
  });
});
