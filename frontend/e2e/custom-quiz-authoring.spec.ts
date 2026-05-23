import { expect, test, type Locator, type Page } from '@playwright/test';

async function stubBackend(page: Page) {
  await page.route('**/config.json', async (route) => {
    await route.fulfill({
      json: {
        version: 'e2e',
        cache_ttl_seconds: 60,
        operations: {},
        pricing: {},
        feature_flags: {},
        announcements: [],
      },
    });
  });

  await page.route('**/providers', async (route) => {
    await route.fulfill({
      json: {
        providers: [
          { id: 'gemini', name: 'Gemini 2.5 Flash Lite', available: true },
        ],
      },
    });
  });

  await page.route('**/sd/status', async (route) => {
    await route.fulfill({ json: { available: false } });
  });
}

async function box(locator: Locator) {
  const value = await locator.boundingBox();
  expect(value).not.toBeNull();
  return value!;
}

test.describe('Custom quiz authoring UX', () => {
  test.beforeEach(async ({ page }) => {
    await stubBackend(page);
  });

  test('keeps editor actions aligned and gives clear completion guidance', async ({ page }) => {
    await page.goto('/');
    await page.getByRole('button', { name: /AI Quiz/ }).click();
    await page.getByRole('button', { name: 'Create Your Own' }).click();

    await expect(page.getByRole('heading', { name: 'Create Your Own' })).toBeVisible();
    await expect(page.getByText('0 ready, 1 to finish')).toBeVisible();
    await expect(page.getByText('Needs question text and all answer choices')).toBeVisible();
    await expect(page.getByRole('button', { name: 'Review & Start' })).toBeDisabled();

    const actionBoxes = await Promise.all([
      box(page.getByRole('button', { name: 'Move question earlier' })),
      box(page.getByRole('button', { name: 'Move question later' })),
      box(page.getByRole('button', { name: 'Duplicate question' })),
    ]);
    expect(Math.max(...actionBoxes.map((item) => item.y)) - Math.min(...actionBoxes.map((item) => item.y))).toBeLessThan(4);
    expect(actionBoxes[1].x).toBeGreaterThan(actionBoxes[0].x);
    expect(actionBoxes[2].x).toBeGreaterThan(actionBoxes[1].x);

    await page.getByLabel('Question text').fill('Where did we first meet?');
    await page.getByLabel('Answer A').fill('Mumbai');
    await page.getByLabel('Answer B').fill('Seattle');
    await page.getByLabel('Answer C').fill('Austin');
    await page.getByLabel('Answer D').fill('London');
    await page.getByRole('button', { name: 'Set correct option B' }).click();

    await expect(page.getByText('1 question is ready')).toBeVisible();
    await expect(page.getByText('Ready to play')).toBeVisible();
    await expect(page.getByRole('button', { name: 'Review & Start' })).toBeEnabled();

    await page.getByRole('button', { name: 'Add Question' }).click();
    await expect(page.getByText('1 ready, 1 to finish')).toBeVisible();

    const overflowing = await page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth + 1);
    expect(overflowing).toBe(false);
  });
});
