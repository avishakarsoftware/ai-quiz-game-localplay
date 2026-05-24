import { expect, test } from '@playwright/test';
import { expectNoHorizontalOverflow, stubCoreBackend } from './helpers';

test.describe('Player and TV entry surfaces', () => {
  test.beforeEach(async ({ page }) => {
    await stubCoreBackend(page);
  });

  test('player join route normalizes room code and requires nickname', async ({ page }) => {
    await page.goto('/join/tvjvna');

    await expect(page.getByRole('heading', { name: 'Join Game' })).toBeVisible();
    await expect(page.getByPlaceholder('Game PIN')).toHaveValue('TVJVNA');
    await expect(page.getByRole('button', { name: 'Join' })).toBeDisabled();

    await page.getByPlaceholder('Your nickname').fill('Avi');
    await expect(page.getByRole('button', { name: 'Join' })).toBeEnabled();
    await expectNoHorizontalOverflow(page);
  });

  test('player launch token resolves room and hides standalone chrome', async ({ page }) => {
    await page.route('**/integrations/revelry/launch-token/resolve?**', async (route) => {
      expect(route.request().url()).toContain('scope=player');
      await route.fulfill({
        json: {
          room_code: 'TVJVNA',
          launch_context: {
            host_app: 'revelry',
            return_url: 'https://api-gamma.revelryapp.me/party/party-e2e?tab=games',
          },
        },
      });
    });

    await page.goto('/join?launch_token=player-token&embed=1');

    await expect(page.getByRole('heading', { name: 'Join Game' })).toBeVisible();
    await expect(page.getByPlaceholder('Game PIN')).toHaveValue('TVJVNA');
    await expect(page.locator('.settings-trigger')).not.toBeVisible();
    await expect(page.getByText(/sparks/i)).not.toBeVisible();
  });

  test('TV mode accepts direct room code entry', async ({ page }) => {
    await page.goto('/tv');

    await expect(page.getByRole('heading', { name: 'TV Mode' })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Watch Game' })).toBeDisabled();
    await page.getByPlaceholder('ROOM CODE').fill('tvjvna');
    await expect(page.getByPlaceholder('ROOM CODE')).toHaveValue('TVJVNA');
    await expect(page.getByRole('button', { name: 'Watch Game' })).toBeEnabled();
    await expectNoHorizontalOverflow(page);
  });

  test('spectator launch token resolves room and hides standalone chrome', async ({ page }) => {
    await page.route('**/integrations/revelry/launch-token/resolve?**', async (route) => {
      expect(route.request().url()).toContain('scope=spectator');
      await route.fulfill({ json: { room_code: 'TVJVNA' } });
    });
    await page.goto('/spectate?launch_token=spectator-token&embed=1');

    await expect(page.getByText(/Connecting|Reconnecting|Connection Error/)).toBeVisible();
    await expect(page.getByText(/Room: TVJVNA|Unable to connect/)).toBeVisible();
    await expect(page.locator('.settings-trigger')).not.toBeVisible();
  });
});
