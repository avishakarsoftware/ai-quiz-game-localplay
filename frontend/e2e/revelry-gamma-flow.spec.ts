import { expect, test } from '@playwright/test';
import { expectNoHorizontalOverflow } from './helpers';
import { closePlayers, joinPlayer, startLobbyGame, type LivePlayer } from './liveGameHarness';
import {
  decodeJwtPayload,
  expectOrganizerLaunch,
  getGammaPartyGamesUrl,
  resolveWorkspace,
  revelryGammaJson,
  revelryGammaLogin,
  waitForCondition,
} from './revelryHarness';

type MirroredSession = {
  id: string;
  localplay_session_id: string;
  status: string;
  joinable: boolean;
  game_type?: string;
  completed_at?: string | null;
  result_summary?: {
    game_type?: string;
    winner?: { nickname?: string; display_name?: string };
    players?: Array<{ score?: number }>;
  } | null;
};

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

  test('mirrors quiz results and continues from the podium into a fresh Revelry session', async ({ page, browser, request }, testInfo) => {
    test.setTimeout(150000);
    test.skip(testInfo.project.name !== 'chromium-desktop', 'Stateful gamma party flow uses one disposable party and runs desktop-only.');

    const hubUrl = getGammaPartyGamesUrl();
    const token = hubUrl.searchParams.get('party_games_token') || '';
    const launchClaims = decodeJwtPayload(token);
    const partyId = launchClaims.launch_context.external_container_id;
    const quizTitle = `Gamma E2E Completion Quiz ${Date.now()}`;

    const save = await test.step('Save the completion quiz', () => request.post('/integrations/revelry/party-games/content', {
      timeout: 15000,
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
    }), { timeout: 20000 });
    await expect(save).toBeOK();
    const saved = await save.json();
    const contentId = saved.localplay_content_id;
    expect(contentId).toBeTruthy();

    const currentWorkspace = await test.step('Resolve the current party workspace', () => resolveWorkspace(request, token), { timeout: 20000 });
    const activeSessionId = currentWorkspace.workspace.active_session?.session_id || '';
    const start = await test.step('Register the quiz session', () => request.post('/integrations/revelry/party-games/start', {
      timeout: 20000,
      data: {
        party_games_token: token,
        content_id: contentId,
        game_type: 'quiz',
        time_limit: 30,
        replacement_confirmed: Boolean(activeSessionId),
        replace_session_id: activeSessionId || null,
      },
    }), { timeout: 25000 });
    await expect(start).toBeOK();
    const started = await start.json();
    const localplaySessionId = started.session.session_id;
    const launchToken = new URL(started.launch_url).searchParams.get('launch_token') || '';
    expect(localplaySessionId).toBeTruthy();
    expect(launchToken).toBeTruthy();

    const resolveLaunch = await test.step('Resolve the organizer credential', () => request.get(
      `/integrations/revelry/launch-token/resolve?scope=organizer&launch_token=${encodeURIComponent(launchToken)}`,
      { timeout: 15000 },
    ), { timeout: 20000 });
    await expect(resolveLaunch).toBeOK();
    const organizerLaunch = await resolveLaunch.json();
    const roomCode = organizerLaunch.room_code;
    expect(roomCode).toBeTruthy();
    expect(organizerLaunch.organizer_token).toBeTruthy();

    let resetCount = 0;
    page.on('websocket', (socket) => {
      if (!socket.url().includes('organizer=true')) return;
      socket.on('framesent', ({ payload }) => {
        const message = JSON.parse(String(payload)) as { type?: string };
        if (message.type === 'RESET_ROOM') resetCount += 1;
      });
    });

    // Authenticate before completion: terminal sessions intentionally reject fresh
    // organizer launch-token resolution. Keep the real host UI through its podium.
    const players: LivePlayer[] = [];
    try {
      await test.step('Play the quiz through the real host and player UI', async () => {
        await page.goto(started.launch_url, { timeout: 20000 });
        await expectOrganizerLaunch(page);
        await expect(page.locator('.room-code')).toHaveText(roomCode, { timeout: 15000 });
        players.push(await joinPlayer(browser, roomCode, `E2E ${Date.now()}`));
        await startLobbyGame(page, players.length);
        await players[0].page.getByRole('button', { name: /Correct callback/ }).click();
        await page.getByRole('button', { name: /Show Scores/ }).click();
        await page.getByRole('button', { name: 'Show Results', exact: true }).click();
        await expect(page.getByRole('heading', { name: 'Final Results', exact: true })).toBeVisible();
        await expect(page.getByRole('button', { name: 'Start another Revelry game', exact: true })).toBeVisible();
      }, { timeout: 45000 });
    } finally {
      await test.step('Close the quiz player browser context', () => closePlayers(players), { timeout: 15000 });
    }

    const revelryAuth = await test.step('Authenticate the seeded Revelry host', () => revelryGammaLogin(), { timeout: 15000 });
    const completedSession = await test.step('Wait for the completed quiz callback in Revelry', () => waitForCondition<MirroredSession>(
      'Revelry mirrored completed LocalPlay session',
      async () => {
        const sessionsBody = await revelryGammaJson(`/api/games/parties/${partyId}/sessions`, revelryAuth.token);
        const session = (sessionsBody.sessions || []).find((item: MirroredSession) => item.localplay_session_id === localplaySessionId);
        if (session?.status === 'complete' && session.result_summary?.winner) return session;
        return undefined;
      },
      30000,
    ), { timeout: 45000 });

    expect(completedSession.joinable).toBe(false);
    expect(completedSession.result_summary?.game_type).toBe('quiz');
    expect(completedSession.result_summary?.winner?.nickname || completedSession.result_summary?.winner?.display_name).toBeTruthy();

    const results = await test.step('Read the mirrored quiz results from Revelry', () => revelryGammaJson(
      `/api/games/sessions/${completedSession.id}/results?party_id=${partyId}`,
      revelryAuth.token,
    ), { timeout: 15000 });
    expect(results.status).toBe('complete');
    expect(results.players?.[0]?.score).toBeGreaterThan(0);
    expect(results.feed_card?.title).toMatch(/results/i);

    const workspace = await test.step('Confirm the completed quiz leaves no active Revelry session', () => revelryGammaJson(
      `/api/games/parties/${partyId}/workspace`, revelryAuth.token,
    ), { timeout: 15000 });
    expect(workspace.active_session).toBeFalsy();

    const refreshedSessions = await test.step('Capture the persisted quiz results before continuation', () => revelryGammaJson(
      `/api/games/parties/${partyId}/sessions`, revelryAuth.token,
    ), { timeout: 15000 });
    // Revelry's results endpoint normalizes and saves its result_summary. Capture
    // that persisted form so the subsequent session cannot erase or reuse it.
    const previousSession = (refreshedSessions.sessions || []).find(
      (item: MirroredSession) => item.localplay_session_id === localplaySessionId,
    ) as MirroredSession | undefined;
    expect(previousSession?.status).toBe('complete');
    expect(previousSession?.result_summary?.players?.[0]?.score).toBeGreaterThan(0);

    const returnToken = await test.step('Return from the podium to the authenticated party hub', async () => {
      await page.getByRole('button', { name: 'Start another Revelry game', exact: true }).click();
      await expect(page.getByRole('heading', { name: /Create a game/i })).toBeVisible({ timeout: 15000 });
      const returnUrl = new URL(page.url());
      expect(returnUrl.pathname).toBe('/revelry/games');
      const returnedToken = returnUrl.searchParams.get('party_games_token') || '';
      expect(Boolean(returnedToken)).toBe(true);
      const returnWorkspace = await resolveWorkspace(request, returnedToken);
      expect(returnWorkspace.launch_context.external_container_id).toBe(partyId);
      expect(returnWorkspace.workspace.active_session).toBeFalsy();
      expect(resetCount).toBe(0);
      return returnedToken;
    }, { timeout: 30000 });

    const nextStarted = await test.step('Register a fresh Odd Question session from the hub', async () => {
      await page.getByPlaceholder('Search games').fill('Odd Question');
      const oddQuestionCard = page.locator('article').filter({
        has: page.getByRole('heading', { name: 'Odd Question', exact: true }),
      });
      const oddQuestionStart = oddQuestionCard.getByRole('button', { name: 'Start now', exact: true });
      await expect(oddQuestionStart).toBeEnabled();
      const nextStartResponse = page.waitForResponse((response) => (
        new URL(response.url()).pathname === '/integrations/revelry/party-games/start'
        && response.request().method() === 'POST'
      ), { timeout: 20000 });
      await oddQuestionStart.click();
      const nextStart = await nextStartResponse;
      expect(nextStart.status()).toBe(200);
      return nextStart.json();
    }, { timeout: 25000 });
    const nextSessionId = nextStarted.session?.session_id;
    expect(nextSessionId).toBeTruthy();
    expect(nextSessionId).not.toBe(localplaySessionId);
    expect(nextStarted.session.game_type).toBe('odd_question');
    expect(nextStarted.opened_existing).toBe(false);

    try {
      await test.step('Open the fresh Odd Question lobby', async () => {
        await expectOrganizerLaunch(page);
        await expect(page.locator('.room-code')).toHaveText(nextStarted.session.room_code, { timeout: 15000 });
      }, { timeout: 20000 });
      const nextMirroredSession = await test.step('Wait for the fresh session callback in Revelry', () => waitForCondition<MirroredSession>(
        'Revelry mirrored the fresh podium continuation session',
        async () => {
          const sessions = await revelryGammaJson(`/api/games/parties/${partyId}/sessions`, revelryAuth.token);
          const session = (sessions.sessions || []).find(
            (item: MirroredSession) => item.localplay_session_id === nextSessionId,
          );
          return session?.status === 'lobby' && session.joinable ? session : undefined;
        },
        30000,
      ), { timeout: 45000 });
      expect(nextMirroredSession.id).not.toBe(completedSession.id);
      expect(nextMirroredSession.game_type).toBe('odd_question');
      expect(nextMirroredSession.result_summary || null).toBeNull();
      expect(nextMirroredSession.completed_at || null).toBeNull();

      await test.step('Verify the completed quiz results remain unchanged', async () => {
        const sessionsAfterContinuation = await revelryGammaJson(`/api/games/parties/${partyId}/sessions`, revelryAuth.token);
        const previousAfterContinuation = (sessionsAfterContinuation.sessions || []).find(
          (item: MirroredSession) => item.localplay_session_id === localplaySessionId,
        ) as MirroredSession | undefined;
        expect(previousAfterContinuation?.id).toBe(previousSession?.id);
        expect(previousAfterContinuation?.status).toBe('complete');
        expect(previousAfterContinuation?.joinable).toBe(false);
        expect(previousAfterContinuation?.completed_at).toBe(previousSession?.completed_at);
        expect(previousAfterContinuation?.result_summary).toEqual(previousSession?.result_summary);
        const resultsAfterContinuation = await revelryGammaJson(
          `/api/games/sessions/${completedSession.id}/results?party_id=${partyId}`,
          revelryAuth.token,
        );
        expect(resultsAfterContinuation.status).toBe('complete');
        expect(resultsAfterContinuation.players).toEqual(results.players);
        expect(resultsAfterContinuation.feed_card).toEqual(results.feed_card);
        expect(resetCount).toBe(0);
      }, { timeout: 30000 });
    } finally {
      await test.step('Clean up the fresh Odd Question lobby', async () => {
        const cancel = await request.post('/integrations/revelry/party-games/cancel', {
          timeout: 15000,
          data: { party_games_token: returnToken, session_id: nextSessionId, reason: 'host_cancelled' },
        });
        await expect(cancel).toBeOK();
      }, { timeout: 20000 });
    }
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

    // Two-step authoring: choose the custom path before the editor appears.
    await expect(page.getByRole('heading', { name: 'Create a quiz' })).toBeVisible({ timeout: 15000 });
    await page.getByRole('button', { name: /Custom quiz/ }).click();

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
