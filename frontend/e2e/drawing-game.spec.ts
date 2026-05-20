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

test.describe('DrawingGame organizer UX', () => {
  test.beforeEach(async ({ page }) => {
    await stubBackend(page);
  });

  test('keeps prompt controls readable and aligned on desktop and mobile', async ({ page }, testInfo) => {
    await page.goto('/');
    await page.getByRole('button', { name: /Drawing Game/ }).click();

    await expect(page.getByRole('heading', { name: 'Drawing Game' })).toBeVisible();
    await expect(page.getByPlaceholder('Theme, vibe, or topic')).toBeVisible();
    await expect(page.getByRole('button', { name: 'Generate Prompts' })).toBeDisabled();

    await page.getByPlaceholder('Theme, vibe, or topic').fill('party animals');
    await expect(page.getByRole('button', { name: 'Generate Prompts' })).toBeEnabled();

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

      const promptCounts = await Promise.all(
        ['5', '8', '10', '15', '20'].map((name) => box(page.getByRole('button', { name, exact: true }))),
      );
      expect(Math.max(...promptCounts.map((item) => item.y)) - Math.min(...promptCounts.map((item) => item.y))).toBeLessThan(4);
    }

    const overflowing = await page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth + 1);
    expect(overflowing).toBe(false);

    await expect(page).toHaveScreenshot(`drawing-game-prompt-${testInfo.project.name}.png`, {
      fullPage: true,
      animations: 'disabled',
      maxDiffPixelRatio: 0.02,
    });
  });
});
