import { expect, test, type APIRequestContext, type Page } from '@playwright/test';
import { expectNoHorizontalOverflow } from './helpers';
import {
  expectOrganizerLaunch,
  getGammaPartyGamesUrl,
  resolveWorkspace,
} from './revelryHarness';

type RevelryCatalogGame = {
  id: string;
  game_type?: string;
  title: string;
  can_create_content?: boolean;
  can_edit_content?: boolean;
  supports_ai_generation?: boolean;
  embedded_authoring_supported?: boolean;
  requires_prepared_content_for_checkin?: boolean;
};

function partyQuestsPayload(title: string) {
  return {
    game: {
      game_title: title,
      theme: 'work_safe',
      duration_minutes: 45,
      quests_per_player: 5,
      confirmation_mode: 'honor',
      allow_late_join: true,
      default_for_checkin: true,
      auto_start_on_first_checkin: true,
      checkin_join_policy: 'resume_or_join',
      quests: [
        'Meet someone who has hosted a party game before.',
        'Find someone who can recommend a great snack.',
        'Meet someone who knows a good road trip song.',
        'Find someone who has tried a new hobby this year.',
        'Meet someone who can teach you a two-word phrase in another language.',
      ],
    },
  };
}

async function cancelActiveIfAny(request: APIRequestContext, token: string) {
  const resolved = await resolveWorkspace(request, token);
  const activeSessionId = resolved.workspace?.active_session?.session_id;
  if (!activeSessionId) return;
  const cancel = await request.post('/integrations/revelry/party-games/cancel', {
    data: {
      party_games_token: token,
      session_id: activeSessionId,
      reason: 'host_cancelled',
    },
  });
  await expect(cancel, `cancel active session ${activeSessionId}`).toBeOK();
}

async function savePartyQuests(request: APIRequestContext, token: string, title: string) {
  const save = await request.post('/integrations/revelry/party-games/content', {
    data: {
      party_games_token: token,
      game_type: 'party_quests',
      title,
      content_payload: partyQuestsPayload(title),
      status: 'ready',
    },
  });
  await expect(save, 'save prepared Party Quests content').toBeOK();
  const body = await save.json();
  expect(body.content?.game_type).toBe('party_quests');
  expect(body.content?.question_count).toBe(5);
  expect(body.content?.localplay_content_id).toBeTruthy();
  return body.content.localplay_content_id as string;
}

async function assertSavedPreview(page: Page, hubUrl: URL, title: string) {
  await page.goto(hubUrl.toString());
  await expect(page.getByPlaceholder('Search games')).toBeVisible();
  const card = page.locator('.party-hub__card').filter({ has: page.getByRole('heading', { name: title }) });
  await expect(card).toBeVisible();
  await card.getByRole('button', { name: 'Preview' }).click();
  await expect(page.getByRole('heading', { name: title })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Player' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Host' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'TV' })).toBeVisible();
  await expect(page.getByText('Preview uses sample guests')).toBeVisible();
  await page.getByRole('button', { name: 'Host' }).click();
  await expect(page.getByRole('heading', { name: 'Host controls' })).toBeVisible();
  await page.getByRole('button', { name: 'TV' }).click();
  await expect(page.getByText('Private quests stay on phones')).toBeVisible();
  await expectNoHorizontalOverflow(page);
}

async function assertAutoStartLateJoinAndCancel(page: Page, roomCode: string, token: string, sessionId: string) {
  await page.goto('/');
  const result = await page.evaluate(async ({ roomCode: code, partyGamesToken, activeSessionId }) => {
    type Message = Record<string, any>;

    function connect(path: string) {
      const messages: Message[] = [];
      const waiters: Array<{
        predicate: (message: Message) => boolean;
        description: string;
        resolve: (message: Message) => void;
        reject: (error: Error) => void;
        timer: number;
      }> = [];
      const ws = new WebSocket(`${window.location.origin.replace(/^http/, 'ws')}${path}`);
      ws.addEventListener('message', (event) => {
        const message = JSON.parse(String(event.data));
        messages.push(message);
        const index = waiters.findIndex((waiter) => waiter.predicate(message));
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
          resolve();
        }, { once: true });
        ws.addEventListener('error', () => {
          window.clearTimeout(timer);
          reject(new Error(`WebSocket error opening ${path}`));
        }, { once: true });
      });
      function waitFor(predicate: (message: Message) => boolean, description: string, timeoutMs = 15000): Promise<Message> {
        const existingIndex = messages.findIndex(predicate);
        if (existingIndex >= 0) {
          const [message] = messages.splice(existingIndex, 1);
          return Promise.resolve(message);
        }
        return new Promise((resolve, reject) => {
          const timer = window.setTimeout(() => {
            reject(new Error(`Timed out waiting for ${description}; seen ${messages.map((message) => message.type).join(', ')}`));
          }, timeoutMs);
          waiters.push({ predicate, description, resolve, reject, timer });
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
    const first = connect(`/ws/${code}/pq-first-${stamp}`);
    await first.opened;
    first.send({ type: 'JOIN', nickname: `Avi ${stamp}`, avatar: '🗺️' });
    await first.waitFor((message) => message.type === 'JOINED_ROOM', 'first player joined');
    await first.waitFor((message) => message.type === 'GAME_STARTING' && message.game_type === 'party_quests', 'Party Quests auto-start');
    const firstSync = await first.waitFor(
      (message) => message.type === 'QUESTS_SYNC' && message.party_quests?.phase === 'QUESTS_ACTIVE',
      'first active quest board',
    );
    if ((firstSync.party_quests?.my_board || []).length !== 5) {
      throw new Error(`Expected 5 quests for first player, got ${(firstSync.party_quests?.my_board || []).length}`);
    }

    const late = connect(`/ws/${code}/pq-late-${stamp}`);
    await late.opened;
    late.send({ type: 'JOIN', nickname: `Ruchi ${stamp}`, avatar: '🎒' });
    const lateJoin = await late.waitFor((message) => message.type === 'JOINED_ROOM', 'late player joined');
    if (lateJoin.party_quests?.phase !== 'QUESTS_ACTIVE') {
      throw new Error(`Expected late join to enter active Party Quests, got ${lateJoin.party_quests?.phase}`);
    }
    if ((lateJoin.party_quests?.my_board || []).length !== 5) {
      throw new Error(`Expected 5 quests for late player, got ${(lateJoin.party_quests?.my_board || []).length}`);
    }

    const cancel = await fetch('/integrations/revelry/party-games/cancel', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        party_games_token: partyGamesToken,
        session_id: activeSessionId,
        reason: 'host_cancelled',
      }),
    });
    if (!cancel.ok) {
      throw new Error(`Cancel failed ${cancel.status}: ${await cancel.text()}`);
    }
    const cancelBody = await cancel.json();
    const closedFirst = await first.waitFor((message) => message.type === 'ROOM_CLOSED', 'first player room closed');
    const closedLate = await late.waitFor((message) => message.type === 'ROOM_CLOSED', 'late player room closed');
    first.close();
    late.close();
    return {
      cancelStatus: cancelBody.session?.status,
      alreadyTerminal: cancelBody.already_terminal,
      closedFirst: closedFirst.message || closedFirst.reason || '',
      closedLate: closedLate.message || closedLate.reason || '',
    };
  }, { roomCode, partyGamesToken: token, activeSessionId: sessionId });

  expect(result.cancelStatus).toBe('cancelled');
  expect(result.alreadyTerminal).toBe(false);
  expect(`${result.closedFirst} ${result.closedLate}`).toContain('ended');
}

test.describe('Revelry Party Quests staged check-in flow', () => {
  test('requires setup, previews saved quests, auto-starts on first guest, late-joins, and cancels cleanly', async ({ page, request }, testInfo) => {
    test.setTimeout(90000);
    test.skip(process.env.PREPROD_REVELRY !== '1', 'Set PREPROD_REVELRY=1 to run the stateful Revelry Party Quests staging check.');
    test.skip(testInfo.project.name !== 'chromium-desktop', 'Revelry staging acceptance runs desktop-only against the disposable gamma party.');

    const hubUrl = getGammaPartyGamesUrl();
    const token = hubUrl.searchParams.get('party_games_token') || '';
    await cancelActiveIfAny(request, token);

    const resolved = await resolveWorkspace(request, token);
    const partyQuests: RevelryCatalogGame | undefined = (resolved.workspace.catalog || [])
      .find((game: RevelryCatalogGame) => (game.game_type || game.id) === 'party_quests');
    expect(partyQuests).toBeTruthy();
    expect(partyQuests?.can_create_content).toBe(true);
    expect(partyQuests?.can_edit_content).toBe(true);
    expect(partyQuests?.supports_ai_generation).toBe(true);
    expect(partyQuests?.embedded_authoring_supported).toBe(true);
    expect(partyQuests?.requires_prepared_content_for_checkin).toBe(true);

    const missingSetup = await request.post('/integrations/revelry/party-games/start', {
      data: {
        party_games_token: token,
        game_type: 'party_quests',
        open_or_create: true,
        settings: {
          party_quests_config: {
            default_for_checkin: true,
            auto_start_on_first_checkin: true,
            duration_minutes: 45,
            quests_per_player: 5,
          },
        },
      },
    });
    expect(missingSetup.status()).toBe(409);
    const missingBody = await missingSetup.json();
    expect(missingBody.detail).toMatchObject({
      code: 'party_quests_setup_required',
      action_required: 'host_configure_party_quests',
    });

    const title = `Revelry Staged Party Quests ${Date.now()}`;
    const contentId = await savePartyQuests(request, token, title);
    await assertSavedPreview(page, hubUrl, title);

    const start = await request.post('/integrations/revelry/party-games/start', {
      data: {
        party_games_token: token,
        game_type: 'party_quests',
        content_id: contentId,
        open_or_create: true,
        replacement_confirmed: true,
        settings: {
          content_id: contentId,
          party_quests_config: {
            default_for_checkin: true,
            auto_start_on_first_checkin: true,
          },
        },
      },
    });
    await expect(start, 'start prepared Party Quests session').toBeOK();
    const started = await start.json();
    expect(started.opened_existing).toBe(false);
    expect(started.session?.game_type).toBe('party_quests');
    expect(started.session?.content_id).toBe(contentId);
    expect(started.session?.joinable).toBe(true);
    expect(started.launch_url).toContain('launch_token=');

    await page.goto(started.launch_url);
    await expectOrganizerLaunch(page);
    await expect(page.getByRole('heading', { name: 'Party Quests Lobby' })).toBeVisible({ timeout: 15000 });
    await expectNoHorizontalOverflow(page);

    await assertAutoStartLateJoinAndCancel(page, started.session.room_code, token, started.session.session_id);

    const afterCancel = await resolveWorkspace(request, token);
    expect(afterCancel.workspace.active_session).toBeFalsy();
  });
});
