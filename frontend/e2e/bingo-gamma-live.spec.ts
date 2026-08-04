import { expect, test } from '@playwright/test';

const PNG_1X1 = Buffer.from(
  'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII=',
  'base64',
);

test.describe('Bingo gamma live flow', () => {
  test('creates a custom Bingo room with text and an uploaded image on gamma', async ({ page, request }) => {
    test.skip(!String(process.env.PLAYWRIGHT_BASE_URL || '').includes('gamma'), 'live gamma test only');

    const mediaStatus = await request.get('/media/status');
    await expect(mediaStatus).toBeOK();
    expect((await mediaStatus.json()).upload_available).toBe(true);

    await page.goto('/');
    await page.getByTestId('game-card-bingo').locator('.game-select-main').click();
    await page.getByRole('button', { name: 'Custom Deck' }).click();
    await expect(page.getByRole('heading', { name: 'Set Up Bingo' })).toBeVisible();

    const firstDeckRow = page.locator('.bingo-deck-row').nth(0);
    await firstDeckRow.locator('input[type="file"]').setInputFiles({
      name: 'gamma-bingo.png',
      mimeType: 'image/png',
      buffer: PNG_1X1,
    });
    await expect(page.getByText('Image uploaded')).toBeVisible({ timeout: 20_000 });
    await expect(firstDeckRow.getByAltText('Dance floor')).toBeVisible();

    await page.getByPlaceholder('Paste one item per line').fill('Baby bottle\nTiny shoes');
    await page.getByRole('button', { name: 'Add List' }).click();
    await expect(page.getByText('Deck (27/24 ready)')).toBeVisible();

    await page.getByLabel('Game title').fill('Gamma Live Bingo');
    await page.getByRole('button', { name: 'Create Room' }).click();

    await expect(page.locator('.room-code')).toHaveText(/[A-Z0-9]{6}/, { timeout: 20_000 });
    await expect(page.getByRole('button', { name: /Start Game/ })).toBeVisible();
  });
});
