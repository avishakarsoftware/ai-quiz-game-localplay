import { readFileSync } from 'node:fs';
import { expect, test, type APIRequestContext, type Page } from '@playwright/test';
import { expectNoHorizontalOverflow } from './helpers';

const GAMMA_ORIGIN = 'https://gamesapi-gamma.revelryapp.me';
const REVELRY_GAMMA_ORIGIN = 'https://api-gamma.revelryapp.me';
const REVELRY_GAMMA_HOST_PHONE = '+15550199000';
const REVELRY_GAMMA_HOST_NAME = 'Gamma Test Host';

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

function decodeJwtPayload(token: string): Record<string, any> {
  const payload = token.split('.')[1] || '';
  const padded = `${payload}${'='.repeat((4 - (payload.length % 4)) % 4)}`;
  return JSON.parse(Buffer.from(padded, 'base64url').toString('utf8'));
}

async function resolveWorkspace(request: APIRequestContext, token: string) {
  const resolve = await request.get(`/integrations/revelry/party-games/resolve?party_games_token=${encodeURIComponent(token)}`);
  await expect(resolve).toBeOK();
  return resolve.json();
}

async function waitForCondition<T>(
  description: string,
  probe: () => Promise<T | undefined>,
  timeoutMs = 20000,
  intervalMs = 750,
): Promise<T> {
  const deadline = Date.now() + timeoutMs;
  let lastValue: T | undefined;
  while (Date.now() < deadline) {
    lastValue = await probe();
    if (lastValue) return lastValue;
    await new Promise((resolve) => setTimeout(resolve, intervalMs));
  }
  throw new Error(`Timed out waiting for ${description}; last value: ${JSON.stringify(lastValue)}`);
}

async function expectOrganizerLaunch(page: Page) {
  await page.waitForFunction(() => {
    const params = new URLSearchParams(window.location.search);
    return window.location.pathname === '/organizer' && params.has('launch_token') && params.get('embed') === '1';
  }, undefined, { timeout: 15000 });
}

async function revelryGammaLogin(): Promise<{ token: string; user: { id: string; name: string } }> {
  const response = await fetch(`${REVELRY_GAMMA_ORIGIN}/auth/dev/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ phone: REVELRY_GAMMA_HOST_PHONE, name: REVELRY_GAMMA_HOST_NAME }),
  });
  const body = await response.text();
  expect(response.ok, body).toBeTruthy();
  return JSON.parse(body);
}

async function driveQuizToCompletion(page: Page, roomCode: string, organizerToken: string) {
  await page.goto('/');
  return page.evaluate(async ({ roomCode: code, organizerToken: token }) => {
    type Message = Record<string, any>;

    function connect(path: string, onOpen?: (ws: WebSocket) => void) {
      const messages: Message[] = [];
      const waiters: Array<{
        type: string;
        resolve: (message: Message) => void;
        reject: (error: Error) => void;
        timer: number;
      }> = [];
      const ws = new WebSocket(`${window.location.origin.replace(/^http/, 'ws')}${path}`);
      ws.addEventListener('message', (event) => {
        const message = JSON.parse(String(event.data));
        messages.push(message);
        const index = waiters.findIndex((waiter) => waiter.type === message.type);
        if (index >= 0) {
          const [waiter] = waiters.splice(index, 1);
          window.clearTimeout(waiter.timer);
          waiter.resolve(message);
        }
      });
      const opened = new Promise<void>((resolve, reject) => {
        const timer = window.setTimeout(() => reject(new Error(`Timed out opening ${path}`)), 10000);
        ws.addEventListener('open', () => {
          window.clearTimeout(timer);
          onOpen?.(ws);
          resolve();
        }, { once: true });
        ws.addEventListener('error', () => {
          window.clearTimeout(timer);
          reject(new Error(`WebSocket error opening ${path}`));
        }, { once: true });
      });
      function waitFor(type: string, timeoutMs = 10000): Promise<Message> {
        const existingIndex = messages.findIndex((message) => message.type === type);
        if (existingIndex >= 0) {
          const [message] = messages.splice(existingIndex, 1);
          return Promise.resolve(message);
        }
        return new Promise((resolve, reject) => {
          const timer = window.setTimeout(() => {
            const index = waiters.findIndex((waiter) => waiter.type === type && waiter.reject === reject);
            if (index >= 0) waiters.splice(index, 1);
            reject(new Error(`Timed out waiting for ${type}; seen ${messages.map((message) => message.type).join(', ')}`));
          }, timeoutMs);
          waiters.push({ type, resolve, reject, timer });
        });
      }
      return {
        opened,
        send(payload: Message) {
          ws.send(JSON.stringify(payload));
        },
        waitFor,
        close() {
          ws.close();
          for (const waiter of waiters.splice(0)) {
            window.clearTimeout(waiter.timer);
            waiter.reject(new Error('WebSocket closed'));
          }
        },
      };
    }

    const stamp = Date.now();
    const organizer = connect(`/ws/${code}/e2e-org-${stamp}?organizer=true`, (ws) => {
      ws.send(JSON.stringify({ type: 'AUTH', token }));
    });
    await organizer.opened;
    const player = connect(`/ws/${code}/e2e-player-${stamp}`);
    await player.opened;

    try {
      await organizer.waitFor('ROOM_CREATED');
      player.send({ type: 'JOIN', nickname: `E2E ${stamp}`, avatar: '🎮' });
      await player.waitFor('JOINED_ROOM');
      await organizer.waitFor('PLAYER_JOINED');
      organizer.send({ type: 'START_GAME' });
      await organizer.waitFor('GAME_STARTING');
      organizer.send({ type: 'NEXT_QUESTION' });
      await player.waitFor('QUESTION');
      player.send({ type: 'ANSWER', answer_index: 0 });
      const answer = await player.waitFor('ANSWER_RESULT');
      await organizer.waitFor('QUESTION_OVER');
      organizer.send({ type: 'NEXT_QUESTION' });
      const podium = await organizer.waitFor('PODIUM');
      return { answer, podium };
    } finally {
      organizer.close();
      player.close();
    }
  }, { roomCode, organizerToken });
}

async function revelryGammaJson(path: string, token: string) {
  const response = await fetch(`${REVELRY_GAMMA_ORIGIN}${path}`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  const body = await response.text();
  expect(response.ok, body).toBeTruthy();
  return JSON.parse(body);
}

test.describe('Revelry gamma embedded flow', () => {
  test.describe.configure({ mode: 'serial' });

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

  test('completes a Revelry-started quiz and mirrors results back to Revelry', async ({ page, request }, testInfo) => {
    test.setTimeout(90000);
    test.skip(testInfo.project.name !== 'chromium-desktop', 'Stateful gamma party flow uses one disposable party and runs desktop-only.');

    const hubUrl = getGammaPartyGamesUrl();
    const token = hubUrl.searchParams.get('party_games_token') || '';
    const launchClaims = decodeJwtPayload(token);
    const partyId = launchClaims.launch_context.external_container_id;
    const quizTitle = `Gamma E2E Completion Quiz ${Date.now()}`;

    const save = await request.post('/integrations/revelry/party-games/content', {
      data: {
        party_games_token: token,
        game_type: 'quiz',
        title: quizTitle,
        content_payload: {
          quiz: {
            quiz_title: quizTitle,
            questions: [
              {
                id: 1,
                text: 'Which answer completes the gamma callback test?',
                options: ['Correct callback', 'Manual smoke', 'Skipped result', 'Wrong room'],
                answer_index: 0,
                image_prompt: '',
              },
            ],
          },
        },
        status: 'ready',
      },
    });
    await expect(save).toBeOK();
    const saved = await save.json();
    const contentId = saved.localplay_content_id;
    expect(contentId).toBeTruthy();

    const currentWorkspace = await resolveWorkspace(request, token);
    const activeSessionId = currentWorkspace.workspace.active_session?.session_id || '';
    const start = await request.post('/integrations/revelry/party-games/start', {
      data: {
        party_games_token: token,
        content_id: contentId,
        game_type: 'quiz',
        time_limit: 5,
        replacement_confirmed: Boolean(activeSessionId),
        replace_session_id: activeSessionId || null,
      },
    });
    await expect(start).toBeOK();
    const started = await start.json();
    const localplaySessionId = started.session.session_id;
    const launchToken = new URL(started.launch_url).searchParams.get('launch_token') || '';
    expect(localplaySessionId).toBeTruthy();
    expect(launchToken).toBeTruthy();

    const resolveLaunch = await request.get(`/integrations/revelry/launch-token/resolve?scope=organizer&launch_token=${encodeURIComponent(launchToken)}`);
    await expect(resolveLaunch).toBeOK();
    const organizerLaunch = await resolveLaunch.json();
    const roomCode = organizerLaunch.room_code;
    const organizerToken = organizerLaunch.organizer_token;
    expect(roomCode).toBeTruthy();
    expect(organizerToken).toBeTruthy();

    const { answer, podium } = await driveQuizToCompletion(page, roomCode, organizerToken);
    expect(answer.correct).toBe(true);
    expect(podium.leaderboard?.[0]?.score).toBeGreaterThan(0);

    const revelryAuth = await revelryGammaLogin();
    const completedSession = await waitForCondition<Record<string, any>>(
      'Revelry mirrored completed LocalPlay session',
      async () => {
        const sessionsBody = await revelryGammaJson(`/api/games/parties/${partyId}/sessions`, revelryAuth.token);
        const session = (sessionsBody.sessions || []).find((item: Record<string, any>) => item.localplay_session_id === localplaySessionId);
        if (session?.status === 'complete' && session.result_summary?.winner) return session;
        return undefined;
      },
      30000,
    );

    expect(completedSession.joinable).toBe(false);
    expect(completedSession.result_summary.game_type).toBe('quiz');
    expect(completedSession.result_summary.winner.nickname || completedSession.result_summary.winner.display_name).toBeTruthy();

    const results = await revelryGammaJson(
      `/api/games/sessions/${completedSession.id}/results?party_id=${partyId}`,
      revelryAuth.token,
    );
    expect(results.status).toBe('complete');
    expect(results.players?.[0]?.score).toBeGreaterThan(0);
    expect(results.feed_card?.title).toMatch(/results/i);

    const workspace = await revelryGammaJson(`/api/games/parties/${partyId}/workspace`, revelryAuth.token);
    expect(workspace.active_session).toBeFalsy();

    const refreshedSessions = await revelryGammaJson(`/api/games/parties/${partyId}/sessions`, revelryAuth.token);
    expect((refreshedSessions.sessions || []).some((item: Record<string, any>) => (
      item.localplay_session_id === localplaySessionId
      && item.status === 'complete'
      && item.result_summary?.players?.[0]?.score > 0
    ))).toBeTruthy();
  });

  test('creates a custom Quiz with an uploaded question image', async ({ page, request }, testInfo) => {
    test.skip(testInfo.project.name !== 'chromium-desktop', 'Stateful gamma party flow uses one disposable party and runs desktop-only.');

    const hubUrl = getGammaPartyGamesUrl();
    const token = hubUrl.searchParams.get('party_games_token') || '';
    const quizTitle = `Gamma E2E Photo Quiz ${Date.now()}`;
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
    await expect(page.getByRole('button', { name: 'Create quiz' })).toBeVisible();
    await page.getByRole('button', { name: 'Create quiz' }).click();

    await expect(page.getByRole('heading', { name: 'Create Your Own' })).toBeVisible({ timeout: 15000 });
    await page.getByLabel('Quiz title').fill(quizTitle);
    await page.getByLabel('Question text').fill('Which icon did the gamma upload test attach?');
    await page.getByLabel('Answer A').fill('LocalPlay icon');
    await page.getByLabel('Answer B').fill('Random mountain');
    await page.getByLabel('Answer C').fill('Empty placeholder');
    await page.getByLabel('Answer D').fill('No image');
    await page.locator('input[type="file"]').setInputFiles('public/icons/favicon-32x32.png');

    await expect(page.getByText('Image uploaded')).toBeVisible({ timeout: 30000 });
    await expect(page.getByLabel('Quiz title')).toHaveValue(quizTitle);
    await expect(page.getByLabel('Question text')).toHaveValue('Which icon did the gamma upload test attach?');
    await expect(page.getByLabel('Question image alt text')).toBeVisible();
    await page.getByLabel('Question image alt text').fill('Uploaded LocalPlay icon');
    await page.getByRole('button', { name: 'Save', exact: true }).last().click();
    await expect(page.getByText('Saved')).toBeVisible({ timeout: 15000 });

    const resolved = await resolveWorkspace(request, token);
    const savedContent = resolved.workspace.prepared_content.find(
      (item: { title?: string }) => item.title === quizTitle,
    );
    expect(savedContent).toBeTruthy();
    expect(savedContent.game_type).toBe('quiz');
    expect(savedContent.status).toBe('ready');

    const content = await request.get(
      `/integrations/revelry/party-games/content/${encodeURIComponent(savedContent.localplay_content_id)}?party_games_token=${encodeURIComponent(token)}&include_payload=true`,
    );
    await expect(content).toBeOK();
    const contentBody = await content.json();
    const question = contentBody.quiz?.questions?.[0];
    expect(question?.image_url).toContain('media.revelryapp.me/apps/localplay/gamma/');
    expect(question?.image_alt).toBe('Uploaded LocalPlay icon');

    expect(pageErrors).toEqual([]);
    expect(consoleErrors).toEqual([]);
  });
});
