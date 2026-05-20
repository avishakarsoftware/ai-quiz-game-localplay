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

function overlaps(
  a: { x: number; y: number; width: number; height: number },
  b: { x: number; y: number; width: number; height: number },
) {
  return a.x < b.x + b.width
    && a.x + a.width > b.x
    && a.y < b.y + b.height
    && a.y + a.height > b.y;
}

test.describe('Quiz variant organizer UX', () => {
  test.beforeEach(async ({ page }) => {
    await stubBackend(page);
  });

  test('keeps Rebus Rush prompt controls readable and aligned', async ({ page }) => {
    await page.goto('/');
    await page.getByRole('button', { name: /Rebus Rush/ }).click();

    await expect(page.getByRole('heading', { name: 'Rebus Rush' })).toBeVisible();
    await expect(page.getByPlaceholder(/movies, travel, 90s hits/i)).toBeVisible();
    await expect(page.getByRole('button', { name: 'Generate Rebus' })).toBeDisabled();

    await page.getByPlaceholder(/movies, travel, 90s hits/i).fill('90s movies');
    await expect(page.getByRole('button', { name: 'Generate Rebus' })).toBeEnabled();

    const menuTrigger = page.locator('.settings-trigger');
    const backButton = page.getByRole('button', { name: 'Back' });
    expect(overlaps(await box(menuTrigger), await box(backButton))).toBe(false);

    const viewport = page.viewportSize();
    const isDesktop = (viewport?.width ?? 0) >= 900;

    if (isDesktop) {
      const difficulty = await Promise.all(
        ['Easy', 'Medium', 'Hard'].map((name) => box(page.getByRole('button', { name }))),
      );
      expect(Math.max(...difficulty.map((item) => item.y)) - Math.min(...difficulty.map((item) => item.y))).toBeLessThan(4);

      const rounds = await Promise.all(
        ['5', '10', '15', '20', '25'].map((name) => box(page.getByRole('button', { name, exact: true }))),
      );
      expect(Math.max(...rounds.map((item) => item.y)) - Math.min(...rounds.map((item) => item.y))).toBeLessThan(4);
    }

    const overflowing = await page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth + 1);
    expect(overflowing).toBe(false);
  });

  test('sends the selected quiz mode to generation', async ({ page }) => {
    let requestBody: Record<string, unknown> | undefined;
    await page.route('**/quiz/generate', async (route) => {
      requestBody = route.request().postDataJSON();
      await route.fulfill({
        json: {
          quiz_id: 'quiz-variant-test',
          quiz: {
            quiz_title: 'Fact or Fiction',
            questions: [
              { id: 1, text: 'Bananas are berries.', options: ['True', 'False'], image_prompt: '' },
            ],
          },
        },
      });
    });

    await page.goto('/');
    await page.getByRole('button', { name: /Fact or Fiction/ }).click();
    await page.getByPlaceholder(/Science myths/i).fill('food facts');
    await page.getByRole('button', { name: 'Generate Claims' }).click();

    await expect(page.getByRole('heading', { name: 'Fact or Fiction' })).toBeVisible();
    expect(requestBody?.mode).toBe('fact_fiction');
  });
});
