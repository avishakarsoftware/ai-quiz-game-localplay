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
  launchable?: boolean;
  can_create_content?: boolean;
  can_quick_start?: boolean;
  config_schema?: { time_limit?: { default?: number } };
};

const REQUIRED_REVELRY_GAME_TYPES = [
  'acronym',
  'bluff',
  'chit_pull',
  'drawing',
  'find_someone',
  'housie',
  'mafia',
  'musical_chairs',
  'never_have_i_ever',
  'party_quests',
  'photo_clue',
  'poker',
  'quiz',
  'word_association',
  'would_you_rather',
  'wmlt',
];

function gameType(game: RevelryCatalogGame) {
  return game.game_type || game.id;
}

function sortedTitles(games: RevelryCatalogGame[]) {
  return games.map((game) => game.title).sort((a, b) => a.localeCompare(b, undefined, { sensitivity: 'base' }));
}

function contentPayloadFor(game: RevelryCatalogGame, title: string) {
  const type = gameType(game);
  if (type === 'quiz') {
    return {
      quiz: {
        quiz_title: title,
        questions: [
          {
            id: 1,
            text: 'Which game launched this Revelry pre-prod test?',
            options: ['LocalPlay', 'Calendar', 'Photos', 'Email'],
            answer_index: 0,
            image_prompt: '',
          },
        ],
      },
    };
  }
  if (type === 'wmlt') {
    return {
      game: {
        game_title: title,
        statements: [
          { id: 1, text: 'Who is most likely to remember the room code?' },
          { id: 2, text: 'Who is most likely to cheer first?' },
          { id: 3, text: 'Who is most likely to explain the rules?' },
        ],
      },
    };
  }
  if (type === 'drawing') {
    return {
      game: {
        game_title: title,
        prompts: [
          { id: 1, text: 'birthday cake', aliases: [], difficulty: 'easy' },
          { id: 2, text: 'party hat', aliases: [], difficulty: 'easy' },
          { id: 3, text: 'dance floor', aliases: [], difficulty: 'medium' },
        ],
      },
      time_limit: 30,
    };
  }
  if (type === 'housie') {
    return {
      game: {
        game_title: title,
        pattern_ids: ['quick_5', 'four_corners', 'top_row', 'middle_row', 'bottom_row', 'full_house'],
        play_mode: 'beginner',
        caller_mode: 'manual',
        auto_interval_seconds: 8,
        auto_pause_on_claim: true,
      },
    };
  }
  if (type === 'chit_pull') {
    return {
      game: {
        game_title: title,
        rounds: 5,
        safe_level: 'family',
        chits: [
          { id: 'c1', text: 'Make your best celebration face.', category: 'funny_face', safe_level: 'family' },
          { id: 'c2', text: 'Tell the room your favorite snack.', category: 'question', safe_level: 'family' },
          { id: 'c3', text: 'Invent a tiny award for someone nearby.', category: 'group', safe_level: 'family' },
          { id: 'c4', text: 'Do a five second victory dance.', category: 'action', safe_level: 'family' },
          { id: 'c5', text: 'Give the party a headline.', category: 'mini_challenge', safe_level: 'family' },
        ],
      },
    };
  }
  if (type === 'party_quests') {
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
          { id: 'q1', display: 'Meet someone who has hosted a party game before.', category: 'mingling', points: 1 },
          { id: 'q2', display: 'Find someone who can recommend a great snack.', category: 'food', points: 1 },
          { id: 'q3', display: 'Meet someone who knows a good road trip song.', category: 'music', points: 1 },
          { id: 'q4', display: 'Find someone who has tried a new hobby this year.', category: 'stories', points: 1 },
          { id: 'q5', display: 'Meet someone who can teach you a two-word phrase in another language.', category: 'stories', points: 1 },
        ],
      },
    };
  }
  throw new Error(`No Revelry content fixture for ${type}. Add one before exposing the game in the Revelry catalog.`);
}

async function saveContentForGame(
  request: APIRequestContext,
  token: string,
  game: RevelryCatalogGame,
  title: string,
) {
  const type = gameType(game);
  if (!game.can_create_content) return '';
  const save = await request.post('/integrations/revelry/party-games/content', {
    data: {
      party_games_token: token,
      game_type: type,
      title,
      content_payload: contentPayloadFor(game, title),
      status: 'ready',
    },
  });
  await expect(save, `save content for ${type}`).toBeOK();
  const saved = await save.json();
  expect(saved.localplay_content_id, `content id for ${type}`).toBeTruthy();
  return saved.localplay_content_id as string;
}

async function startGameFromRevelry(
  request: APIRequestContext,
  token: string,
  game: RevelryCatalogGame,
  contentId: string,
  title: string,
) {
  const workspace = await resolveWorkspace(request, token);
  const activeSessionId = workspace.workspace.active_session?.session_id || '';
  const start = await request.post('/integrations/revelry/party-games/start', {
    data: {
      party_games_token: token,
      content_id: contentId || undefined,
      game_type: gameType(game),
      title,
      time_limit: game.config_schema?.time_limit?.default || 30,
      replacement_confirmed: Boolean(activeSessionId),
      replace_session_id: activeSessionId || null,
    },
  });
  await expect(start, `start ${gameType(game)}`).toBeOK();
  const body = await start.json();
  expect(body.session?.session_id, `session id for ${gameType(game)}`).toBeTruthy();
  expect(body.launch_url, `organizer launch url for ${gameType(game)}`).toContain('launch_token=');
  return body;
}

async function expectLaunchRoutesForActiveSession(
  request: APIRequestContext,
  token: string,
  sessionId: string,
) {
  for (const [scope, route] of [
    ['organizer', 'organizer'],
    ['player', 'join'],
    ['spectator', 'spectate'],
  ] as const) {
    const launch = await request.post('/integrations/revelry/party-games/launch-token', {
      data: {
        party_games_token: token,
        session_id: sessionId,
        scope,
        route,
        embed: true,
      },
    });
    await expect(launch, `mint ${scope} launch`).toBeOK();
    const launchBody = await launch.json();
    expect(launchBody.launch_url).toContain('launch_token=');
    expect(launchBody.launch_url).toContain('embed=1');
  }
}

async function assertOrganizerPageLoads(page: Page, launchUrl: string, title: string) {
  await page.goto(launchUrl);
  await expectOrganizerLaunch(page);
  await expect(page.getByText('Organizer launch token required')).not.toBeVisible();
  await expect(
    page.getByRole('heading', { name: title })
      .or(page.getByRole('button', { name: 'Start Game' }))
      .or(page.getByText('Back to Revelry Games')),
  ).toBeVisible({ timeout: 15000 });
  await expectNoHorizontalOverflow(page);
}

async function exerciseLobbyReconnect(page: Page, roomCode: string, organizerToken: string) {
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
        if (message.type === 'ERROR') {
          for (const waiter of waiters.splice(0)) {
            window.clearTimeout(waiter.timer);
            waiter.reject(new Error(`Unexpected ERROR while waiting for ${waiter.type}: ${JSON.stringify(message)}`));
          }
          return;
        }
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
    const nickname = `Lull${String(stamp).slice(-6)}`;
    const organizer = connect(`/ws/${code}/revelry-lull-org-${stamp}?organizer=true`, (ws) => {
      ws.send(JSON.stringify({ type: 'AUTH', token }));
    });
    await organizer.opened;

    let player = connect(`/ws/${code}/revelry-lull-p-${stamp}`);
    await player.opened;

    try {
      await organizer.waitFor('ROOM_CREATED');
      player.send({ type: 'JOIN', nickname, avatar: '🎮' });
      const joined = await player.waitFor('JOINED_ROOM');
      await organizer.waitFor('PLAYER_JOINED');

      player.close();
      await organizer.waitFor('PLAYER_DISCONNECTED');
      await new Promise((resolve) => window.setTimeout(resolve, 300));

      player = connect(`/ws/${code}/revelry-lull-p-${stamp}-reconnect`);
      await player.opened;
      player.send({
        type: 'JOIN',
        nickname,
        avatar: '🎮',
        session_token: joined.session_token,
      });
      const reconnected = await player.waitFor('RECONNECTED');
      const roster = await organizer.waitFor('PLAYER_RECONNECTED');

      organizer.send({ type: 'START_GAME' });
      const starting = await organizer.waitFor('GAME_STARTING');
      await player.waitFor('GAME_STARTING');
      return { joined, reconnected, roster, starting };
    } finally {
      organizer.close();
      player.close();
    }
  }, { roomCode, organizerToken });
}

test.describe('Revelry pre-prod live game matrix', () => {
  test.describe.configure({ mode: 'serial' });

  test('shows a sorted searchable party hub catalog', async ({ page, request }, testInfo) => {
    test.skip(process.env.PREPROD_REVELRY !== '1', 'Set PREPROD_REVELRY=1 to run the stateful Revelry pre-prod matrix.');
    test.skip(testInfo.project.name !== 'chromium-desktop', 'Revelry pre-prod matrix uses one disposable party and runs desktop-only.');

    const hubUrl = getGammaPartyGamesUrl();
    const token = hubUrl.searchParams.get('party_games_token') || '';
    const resolved = await resolveWorkspace(request, token);
    const launchableGames: RevelryCatalogGame[] = (resolved.workspace.catalog || [])
      .filter((game: RevelryCatalogGame) => game.launchable !== false);
    const exposedTypes = launchableGames.map(gameType).sort();

    expect(exposedTypes).toEqual(expect.arrayContaining(REQUIRED_REVELRY_GAME_TYPES));

    await page.goto(hubUrl.toString());
    await expect(page.getByPlaceholder('Search games')).toBeVisible();
    await expect(page.getByRole('button', { name: 'All' })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Most Popular' })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Quiz/Trivia' })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Creative' })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Bingo/Housie' })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Cards', exact: true })).toBeVisible();
    await expectNoHorizontalOverflow(page);

    await page.getByRole('button', { name: 'Most Popular' }).click();
    await expect(page.getByRole('heading', { name: 'AI Quiz' }).first()).toBeVisible();
    await page.getByRole('button', { name: 'All' }).click();

    for (const title of sortedTitles(launchableGames)) {
      await expect(page.getByRole('heading', { name: title }).first()).toBeVisible();
    }

    const firstTitle = sortedTitles(launchableGames)[0];
    await page.getByPlaceholder('Search games').fill(firstTitle);
    await expect(page.getByRole('heading', { name: firstTitle }).first()).toBeVisible();
  });

  test('starts every Revelry-enabled game and resolves host/player/watch launches', async ({ page, request }, testInfo) => {
    test.setTimeout(120000);
    test.skip(process.env.PREPROD_REVELRY !== '1', 'Set PREPROD_REVELRY=1 to run the stateful Revelry pre-prod matrix.');
    test.skip(testInfo.project.name !== 'chromium-desktop', 'Revelry pre-prod matrix uses one disposable party and runs desktop-only.');

    const hubUrl = getGammaPartyGamesUrl();
    const token = hubUrl.searchParams.get('party_games_token') || '';
    const resolved = await resolveWorkspace(request, token);
    const launchableGames: RevelryCatalogGame[] = (resolved.workspace.catalog || [])
      .filter((game: RevelryCatalogGame) => game.launchable !== false)
      .sort((a: RevelryCatalogGame, b: RevelryCatalogGame) => gameType(a).localeCompare(gameType(b)));
    const testedTypes: string[] = [];

    for (const game of launchableGames) {
      if (!game.can_create_content && !game.can_quick_start) {
        throw new Error(`${gameType(game)} is launchable in Revelry but has no tested create or quick-start path.`);
      }
      if (game.can_create_content && !['chit_pull', 'drawing', 'housie', 'party_quests', 'quiz', 'wmlt'].includes(gameType(game))) {
        throw new Error(`${gameType(game)} is exposed in Revelry but the pre-prod harness has no content fixture.`);
      }

      const title = `Revelry Matrix ${game.title} ${Date.now()}`;
      const contentId = await saveContentForGame(request, token, game, title);
      const started = await startGameFromRevelry(request, token, game, contentId, title);
      await expectLaunchRoutesForActiveSession(request, token, started.session.session_id);
      await assertOrganizerPageLoads(page, started.launch_url, title);
      testedTypes.push(gameType(game));
    }

    expect(testedTypes.sort()).toEqual(expect.arrayContaining(REQUIRED_REVELRY_GAME_TYPES));
  });

  test('keeps a Revelry-launched lobby usable after a player drops and reconnects', async ({ page, request }, testInfo) => {
    test.setTimeout(60000);
    test.skip(process.env.PREPROD_REVELRY !== '1', 'Set PREPROD_REVELRY=1 to run the stateful Revelry pre-prod matrix.');
    test.skip(testInfo.project.name !== 'chromium-desktop', 'Revelry pre-prod matrix uses one disposable party and runs desktop-only.');

    const hubUrl = getGammaPartyGamesUrl();
    const token = hubUrl.searchParams.get('party_games_token') || '';
    const resolved = await resolveWorkspace(request, token);
    const findSomeone: RevelryCatalogGame | undefined = (resolved.workspace.catalog || [])
      .find((game: RevelryCatalogGame) => gameType(game) === 'find_someone' && game.launchable !== false);
    expect(findSomeone, 'find_someone must be launchable for the Revelry lobby-lull regression').toBeTruthy();
    expect(findSomeone?.can_quick_start, 'find_someone should quick-start from Revelry').toBe(true);

    const started = await startGameFromRevelry(
      request,
      token,
      findSomeone as RevelryCatalogGame,
      '',
      `Revelry Lobby Lull ${Date.now()}`,
    );
    const launchToken = new URL(started.launch_url).searchParams.get('launch_token') || '';
    expect(launchToken).toBeTruthy();

    const resolveLaunch = await request.get(`/integrations/revelry/launch-token/resolve?scope=organizer&launch_token=${encodeURIComponent(launchToken)}`);
    await expect(resolveLaunch).toBeOK();
    const organizerLaunch = await resolveLaunch.json();
    expect(organizerLaunch.room_code).toBeTruthy();
    expect(organizerLaunch.organizer_token).toBeTruthy();

    const result = await exerciseLobbyReconnect(page, organizerLaunch.room_code, organizerLaunch.organizer_token);
    expect(result.reconnected.state).toBe('LOBBY');
    expect(result.reconnected.game_type).toBe('find_someone');
    expect(result.roster.player_count).toBe(1);
    expect(result.starting.game_type).toBe('find_someone');
  });
});
