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
      if (game.can_create_content && !['chit_pull', 'drawing', 'housie', 'quiz', 'wmlt'].includes(gameType(game))) {
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
});
