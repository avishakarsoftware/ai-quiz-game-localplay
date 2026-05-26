import { readFileSync } from 'node:fs';
import { expect, test, type APIRequestContext, type Page } from '@playwright/test';
import { expectNoHorizontalOverflow } from './helpers';

const GAMMA_ORIGIN = 'https://gamesapi-gamma.revelryapp.me';

function getGammaPartyGamesUrl(): URL {
  const rawUrl = process.env.REVELRY_GAMMA_PARTY_GAMES_URL
    || (process.env.REVELRY_GAMMA_PARTY_GAMES_URL_FILE
      ? readFileSync(process.env.REVELRY_GAMMA_PARTY_GAMES_URL_FILE, 'utf8').trim()
      : '');
  test.skip(!rawUrl, 'Set REVELRY_GAMMA_PARTY_GAMES_URL to a short-lived gamma party games URL.');

  const url = new URL(rawUrl);
  expect(url.origin).toBe(GAMMA_ORIGIN);
  expect(url.pathname).toBe('/integrations/revelry/games');
  expect(url.searchParams.get('party_games_token') || '').not.toBe('');
  return url;
}

async function resolveWorkspace(request: APIRequestContext, token: string) {
  const resolve = await request.get(`/integrations/revelry/party-games/resolve?party_games_token=${encodeURIComponent(token)}`);
  await expect(resolve).toBeOK();
  return resolve.json();
}

async function expectOrganizerLaunch(page: Page) {
  await page.waitForFunction(() => {
    const params = new URLSearchParams(window.location.search);
    return window.location.pathname === '/organizer' && params.has('launch_token') && params.get('embed') === '1';
  }, undefined, { timeout: 15000 });
}

test.describe('Revelry gamma embedded flow', () => {
  test('saves Drawing content, starts it, and re-enters the active room', async ({ page, request }, testInfo) => {
    test.skip(testInfo.project.name !== 'chromium-desktop', 'Stateful gamma party flow uses one disposable party and runs desktop-only.');

    const hubUrl = getGammaPartyGamesUrl();
    const token = hubUrl.searchParams.get('party_games_token') || '';
    const drawingTitle = `Gamma E2E Drawing ${Date.now()}`;
    const consoleErrors: string[] = [];
    const pageErrors: string[] = [];

    page.on('console', (message) => {
      if (message.type() !== 'error') return;
      const text = message.text();
      if (text.includes('409 (Conflict)')) return;
      consoleErrors.push(text);
    });
    page.on('pageerror', (error) => {
      pageErrors.push(error.message);
    });

    await page.goto(hubUrl.toString());

    await expect(page.getByRole('heading', { name: /Create a game/i })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Set up drawing' })).toBeVisible();
    await expect(page.getByRole('heading', { name: /Saved games/i })).toBeVisible();
    await expectNoHorizontalOverflow(page);

    await page.getByRole('button', { name: 'Set up drawing' }).click();
    await expect(page.getByRole('heading', { name: 'Set up drawing' })).toBeVisible();
    await page.getByLabel('Title').fill(drawingTitle);
    await page.getByLabel('Drawing prompts').fill([
      'gamma test birthday cake',
      'gamma test disco ball',
      'gamma test party hat',
    ].join('\n'));
    await page.getByLabel('Round timer').fill('30');
    await page.getByRole('button', { name: 'Save', exact: true }).click();

    const savedCard = page.locator('article').filter({ hasText: drawingTitle }).first();
    await expect(savedCard).toBeVisible();
    await expect(savedCard.getByRole('button', { name: 'Start' })).toBeVisible();

    const resolvedAfterSave = await resolveWorkspace(request, token);
    const savedContent = resolvedAfterSave.workspace.prepared_content.find(
      (item: { title?: string }) => item.title === drawingTitle,
    );
    expect(savedContent).toBeTruthy();
    expect(savedContent.game_type).toBe('drawing');

    await savedCard.getByRole('button', { name: 'Start' }).click();
    const replaceButton = page.getByRole('button', { name: 'Replace and start' });
    await replaceButton.waitFor({ state: 'visible', timeout: 5000 })
      .then(() => replaceButton.click())
      .catch(() => undefined);

    await expectOrganizerLaunch(page);
    await expect(page.getByText('Organizer launch token required')).not.toBeVisible();
    await expect(page.getByText('Back to Revelry Games').or(page.getByRole('button', { name: 'Start Game' }))).toBeVisible({ timeout: 15000 });

    const resolvedWithActive = await resolveWorkspace(request, token);
    const activeSession = resolvedWithActive.workspace.active_session;
    expect(activeSession?.session_id).toBeTruthy();
    expect(activeSession?.joinable).toBe(true);

    for (const [scope, route] of [
      ['organizer', 'organizer'],
      ['player', 'join'],
      ['spectator', 'spectate'],
    ] as const) {
      const launch = await request.post('/integrations/revelry/party-games/launch-token', {
        data: {
          party_games_token: token,
          session_id: activeSession.session_id,
          scope,
          route,
          embed: true,
        },
      });
      await expect(launch).toBeOK();
      const launchBody = await launch.json();
      expect(launchBody.launch_url).toContain('launch_token=');
      expect(launchBody.launch_url).toContain('embed=1');
    }

    await page.goto(hubUrl.toString());
    await expect(page.getByRole('heading', { name: 'Game in progress' })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Host game' })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Join to play' })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Join to watch' })).toBeVisible();

    await page.getByRole('button', { name: 'Host game' }).click();
    await expectOrganizerLaunch(page);
    await expect(page.getByText('Organizer launch token required')).not.toBeVisible();

    expect(pageErrors).toEqual([]);
    expect(consoleErrors).toEqual([]);
  });
});
