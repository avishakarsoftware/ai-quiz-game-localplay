import { expect, test } from '@playwright/test';
import { expectNoHorizontalOverflow } from './helpers';

const AI_PROMPT_GAMES = [
  { id: 'quiz', heading: 'Create Quiz' },
  { id: 'bingo', heading: 'Create Bingo' },
  { id: 'chit_pull', heading: 'Random Chit' },
  { id: 'drawing', heading: 'Drawing Game' },
  { id: 'emoji_charades', heading: 'Emoji Charades' },
  { id: 'fact_fiction', heading: 'Fact or Fiction' },
  { id: 'wmlt', heading: 'Most Likely To' },
  { id: 'odd_one_out', heading: 'Odd One Out' },
  { id: 'rebus', heading: 'Rebus Rush' },
  { id: 'timeline', heading: 'Timeline Twist' },
  { id: 'who_am_i', heading: 'Who Am I?' },
];

test.describe('prompt UX audit', () => {
  for (const setup of AI_PROMPT_GAMES) {
    test(`${setup.heading} keeps random prompt controls visible and usable`, async ({ page }) => {
      await page.goto('/');
      await page.getByTestId(`game-card-${setup.id}`).click();

      await expect(page.getByRole('heading', { name: setup.heading })).toBeVisible();
      await expect(page.locator('textarea')).toBeVisible();

      const shuffle = page.getByRole('button', { name: /Suggest a random/ });
      await expect(shuffle).toBeVisible();
      const box = await shuffle.boundingBox();
      expect(box?.width).toBeGreaterThanOrEqual(40);
      expect(box?.height).toBeGreaterThanOrEqual(40);

      await shuffle.click();
      await expect(page.locator('textarea')).not.toHaveValue('');
      await expectNoHorizontalOverflow(page);
    });
  }

  test('mobile join screen keeps entry controls in reach for a real room', async ({ page, browser }, testInfo) => {
    test.skip(!String(process.env.PLAYWRIGHT_BASE_URL || '').includes('gamma'), 'real room join audit runs on gamma');

    await page.goto('/');
    await page.getByTestId('game-card-story_chain').click();
    const roomCode = (await page.locator('.room-code').textContent({ timeout: 20_000 }))?.trim();
    expect(roomCode).toMatch(/^[A-Z0-9]{6}$/);

    const mobile = await browser.newPage({
      baseURL: process.env.PLAYWRIGHT_BASE_URL,
      ...testInfo.project.use,
    });
    await mobile.goto(`/join/${roomCode}`);

    await expect(mobile.getByRole('heading', { name: 'Join Game' })).toBeVisible();
    await expect(mobile.getByPlaceholder('Your nickname')).toBeVisible();
    await expect(mobile.getByRole('button', { name: 'Join' })).toBeVisible();
    await expectNoHorizontalOverflow(mobile);
    await mobile.close();
  });
});
