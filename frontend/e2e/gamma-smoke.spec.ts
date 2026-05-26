import { expect, test } from '@playwright/test';
import { expectNoHorizontalOverflow } from './helpers';

test.describe('Gamma deployment smoke', () => {
  test('loads the standalone catalog from the deployed backend', async ({ page, request }) => {
    const consoleErrors: string[] = [];
    const pageErrors: string[] = [];

    page.on('console', (message) => {
      if (message.type() === 'error') {
        consoleErrors.push(message.text());
      }
    });
    page.on('pageerror', (error) => {
      pageErrors.push(error.message);
    });

    const mediaStatus = await request.get('/media/status');
    expect(mediaStatus.ok()).toBe(true);
    await expect(mediaStatus).toBeOK();

    await page.goto('/');

    await expect(page.getByRole('heading', { name: 'Choose a Game' })).toBeVisible();
    await expect(page.getByRole('button', { name: /AI Quiz/ })).toBeVisible();
    await expect(page.getByRole('button', { name: /Most Likely To/ })).toBeVisible();
    await expect(page.getByRole('button', { name: /Drawing Game/ })).toBeVisible();
    await expectNoHorizontalOverflow(page);

    expect(pageErrors).toEqual([]);
    expect(consoleErrors).toEqual([]);
  });
});
