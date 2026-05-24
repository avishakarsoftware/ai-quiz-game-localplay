import { expect, test, type Request } from '@playwright/test';
import {
  expectNoHorizontalOverflow,
  revelryLaunchContext,
  revelryWorkspace,
  stubCoreBackend,
} from './helpers';

test.describe('Revelry Games party hub', () => {
  test.beforeEach(async ({ page }) => {
    await stubCoreBackend(page);
  });

  test('renders creation options from launchable catalog and keeps saved games separate', async ({ page }) => {
    await page.route('**/integrations/revelry/party-games/resolve?**', async (route) => {
      await route.fulfill({
        json: {
          launch_context: revelryLaunchContext(),
          workspace: revelryWorkspace(),
        },
      });
    });

    await page.goto('/revelry/games?party_games_token=party-token');

    await expect(page.getByRole('heading', { name: 'Christmas 2026 Bash' })).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Create a game' })).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Saved games' })).toBeVisible();
    await expect(page.getByRole('heading', { name: 'AI Quiz' })).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Most Likely To' })).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Drawing Game' })).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Rebus Rush' })).not.toBeVisible();
    await expect(page.getByText('Christmas Quiz')).toBeVisible();
    await expect(page.getByRole('button', { name: 'Create quiz' })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Set up round' })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Set up drawing' })).toBeVisible();
    await expectNoHorizontalOverflow(page);
  });

  test('saves configurable game setup before start', async ({ page }) => {
    let saveRequest: Record<string, unknown> | undefined;
    await page.route('**/integrations/revelry/party-games/resolve?**', async (route) => {
      await route.fulfill({
        json: {
          launch_context: revelryLaunchContext(),
          workspace: revelryWorkspace({ prepared_content: [] }),
        },
      });
    });
    await page.route('**/integrations/revelry/party-games/content', async (route) => {
      saveRequest = route.request().postDataJSON();
      await route.fulfill({
        json: {
          localplay_content_id: 'drawing-party-1',
          content: {
            localplay_content_id: 'drawing-party-1',
            game_type: 'drawing',
            title: 'Christmas Drawing',
            question_count: 2,
            time_limit: 30,
            status: 'ready',
          },
          workspace: revelryWorkspace({
            prepared_content: [
              {
                localplay_content_id: 'drawing-party-1',
                game_type: 'drawing',
                title: 'Christmas Drawing',
                question_count: 2,
                time_limit: 30,
                status: 'ready',
              },
            ],
          }),
        },
      });
    });

    await page.goto('/revelry/games?party_games_token=party-token');
    await page.getByRole('button', { name: 'Set up drawing' }).click();

    await expect(page.getByRole('heading', { name: 'Set up drawing' })).toBeVisible();
    await expect(page.getByLabel('Title')).toHaveValue('Drawing Game');
    await expect(page.getByLabel('Round timer')).toHaveValue('30');
    await page.getByLabel('Title').fill('Christmas Drawing');
    await page.getByLabel('Drawing prompts').fill('snow globe\ngingerbread house');
    await page.getByRole('button', { name: 'Save', exact: true }).click();

    await expect(page.getByText('Christmas Drawing')).toBeVisible();
    expect(saveRequest).toMatchObject({
      party_games_token: 'party-token',
      game_type: 'drawing',
      title: 'Christmas Drawing',
      status: 'ready',
    });
    expect(saveRequest?.content_payload).toMatchObject({
      time_limit: 30,
      game: {
        game_title: 'Christmas Drawing',
        prompts: [
          { id: 1, text: 'snow globe' },
          { id: 2, text: 'gingerbread house' },
        ],
      },
    });
  });

  test('shows replacement confirmation and retries start with confirmation', async ({ page }) => {
    const startRequests: Request[] = [];
    await page.route('**/integrations/revelry/party-games/resolve?**', async (route) => {
      await route.fulfill({
        json: {
          launch_context: revelryLaunchContext(),
          workspace: revelryWorkspace(),
        },
      });
    });
    await page.route('**/integrations/revelry/party-games/start', async (route) => {
      startRequests.push(route.request());
      const body = route.request().postDataJSON();
      if (!body.replacement_confirmed) {
        await route.fulfill({
          status: 409,
          json: {
            detail: {
              code: 'active_session_exists',
              session_id: 'lp-active',
              game_type: 'drawing',
              game_title: 'Drawing Game',
              message: 'A LocalPlay game is already active for this party.',
            },
          },
        });
        return;
      }
      await route.fulfill({
        json: {
          session: { session_id: 'lp-new', status: 'lobby', room_code: 'ABC123' },
          launch_url: '/organizer?session_id=lp-new&launch_token=launch-token&embed=1',
        },
      });
    });

    await page.goto('/revelry/games?party_games_token=party-token');
    await page.getByRole('button', { name: 'Start' }).click();

    await expect(page.getByRole('dialog', { name: 'Replace the current game?' })).toBeVisible();
    await expect(page.getByText('Current game: "Drawing Game".')).toBeVisible();
    await page.getByRole('button', { name: 'Replace and start' }).click();

    await expect(page).toHaveURL(/\/organizer\?session_id=lp-new/);
    expect(startRequests).toHaveLength(2);
    expect(startRequests[0].postDataJSON()).toMatchObject({
      party_games_token: 'party-token',
      content_id: 'quiz-party-1',
      game_type: 'quiz',
      replacement_confirmed: false,
    });
    expect(startRequests[1].postDataJSON()).toMatchObject({
      party_games_token: 'party-token',
      content_id: 'quiz-party-1',
      game_type: 'quiz',
      replacement_confirmed: true,
      replace_session_id: 'lp-active',
    });
  });
});

