import { expect, test } from '@playwright/test';
import { expectNoHorizontalOverflow } from './helpers';
import {
  closePlayers,
  createRoomViaApi,
  deterministicBingoDeck,
  deterministicChitPull,
  deterministicDrawing,
  deterministicMlt,
  deterministicQuiz,
  deterministicWhoAmI,
  findPlayerWithEnabledButton,
  findPlayerWithVisibleButton,
  joinPlayers,
  liveDeviceId,
  openOrganizerFromRoom,
  postJson,
  startLobbyGame,
  type LivePlayer,
} from './liveGameHarness';

test.describe('Pre-production live game regression', () => {
  test.describe.configure({ timeout: 90_000 });

  test.beforeEach(async ({}, testInfo) => {
    test.skip(process.env.PREPROD_LIVE !== '1', 'Set PREPROD_LIVE=1 to run the heavy live regression suite.');
    test.skip(testInfo.project.name !== 'chromium-desktop', 'The live regression suite uses multiple browser contexts and runs desktop-only.');
  });

  test('Quiz runtime creates a room, accepts an answer, and advances host state', async ({ page, browser, request }) => {
    const deviceId = liveDeviceId('quiz');
    const { quiz_id: quizId } = await postJson<{ quiz_id: string }>(request, '/quiz/import', { quiz: deterministicQuiz }, deviceId);
    const room = await createRoomViaApi(request, deviceId, { game_type: 'quiz', quiz_id: quizId, time_limit: 60 });
    await openOrganizerFromRoom(page, room);

    const players = await joinPlayers(browser, room.roomCode, ['Alice', 'Bob']);
    try {
      await startLobbyGame(page, players.length);
      await expect(page.getByText('Which color is usually made by mixing blue and yellow?')).toBeVisible({ timeout: 20_000 });
      await expect(players[0].page.getByRole('button', { name: 'Green' })).toBeVisible({ timeout: 20_000 });
      await players[0].page.getByRole('button', { name: 'Green' }).click();
      await expect(page.getByText(/1 answered|1 of 2/i)).toBeVisible({ timeout: 20_000 });
      await expectNoHorizontalOverflow(page);
    } finally {
      await closePlayers(players);
    }
  });

  test('Most Likely To starts a voting round with live players', async ({ page, browser, request }) => {
    const deviceId = liveDeviceId('mlt');
    const { scenario_id: mltId } = await postJson<{ scenario_id: string }>(request, '/mlt/import', { game: deterministicMlt }, deviceId);
    const room = await createRoomViaApi(request, deviceId, { game_type: 'wmlt', mlt_id: mltId, time_limit: 60 });
    await openOrganizerFromRoom(page, room);

    const players = await joinPlayers(browser, room.roomCode, ['Alice', 'Bob', 'Cara']);
    try {
      await startLobbyGame(page, players.length);
      await expect(page.getByText('Who is most likely to organize the snacks?')).toBeVisible();
      await expect(players[0].page.getByText('Who is most likely to organize the snacks?')).toBeVisible({ timeout: 20_000 });
      await players[0].page.getByRole('button', { name: /Bob|Cara/ }).first().click();
      await expect(page.getByText(/1 voted|1 of 3/i)).toBeVisible({ timeout: 20_000 });
      await expectNoHorizontalOverflow(page);
    } finally {
      await closePlayers(players);
    }
  });

  test('Housie starts and calls one number', async ({ page, browser, request }) => {
    const deviceId = liveDeviceId('housie');
    const { housie_id: housieId } = await postJson<{ housie_id: string }>(request, '/housie/create', {
      game_title: 'Preprod Housie',
      pattern_ids: ['top_line', 'middle_line', 'bottom_line', 'full_house'],
      play_mode: 'beginner',
      caller_mode: 'manual',
    }, deviceId);
    const room = await createRoomViaApi(request, deviceId, { game_type: 'housie', housie_id: housieId, time_limit: 15 });
    await openOrganizerFromRoom(page, room);

    const players = await joinPlayers(browser, room.roomCode, ['Alice', 'Bob']);
    try {
      await startLobbyGame(page, players.length);
      await expect(page.getByText('Housie caller')).toBeVisible({ timeout: 20_000 });
      await page.getByRole('button', { name: 'Call Next' }).click();
      await expect(page.getByText(/1 of 90 numbers called/)).toBeVisible({ timeout: 20_000 });
      await expect(players[0].page.getByText(/Claim/)).toBeVisible({ timeout: 20_000 });
      await expectNoHorizontalOverflow(page);
    } finally {
      await closePlayers(players);
    }
  });

  test('Bingo and Baby Bingo start and call one item', async ({ page, browser, request }) => {
    for (const title of ['Preprod Bingo', 'Preprod Baby Bingo']) {
      const deviceId = liveDeviceId(title.toLowerCase().replace(/\s+/g, '-'));
      const { bingo_id: bingoId } = await postJson<{ bingo_id: string }>(request, '/bingo/create', {
        game_title: title,
        deck: deterministicBingoDeck(title.includes('Baby') ? 'Baby' : 'Bingo'),
        pattern_ids: ['line', 'corners', 'full_house'],
        free_center: true,
        free_center_label: 'FREE',
        caller_mode: 'manual',
      }, deviceId);
      const room = await createRoomViaApi(request, deviceId, { game_type: 'bingo', bingo_id: bingoId, time_limit: 15 });
      await openOrganizerFromRoom(page, room);
      const players = await joinPlayers(browser, room.roomCode, ['Alice', 'Bob']);
      try {
        await startLobbyGame(page, players.length);
        await expect(page.getByText('Bingo caller')).toBeVisible({ timeout: 20_000 });
        await page.getByRole('button', { name: 'Call Next' }).click();
        await expect(page.getByText(/1 items called/)).toBeVisible({ timeout: 20_000 });
        await expectNoHorizontalOverflow(page);
      } finally {
        await closePlayers(players);
      }
    }
  });

  test('Musical Chairs starts and stops a physical round', async ({ page, browser, request }) => {
    const deviceId = liveDeviceId('musical-chairs');
    const room = await createRoomViaApi(request, deviceId, {
      game_type: 'musical_chairs',
      time_limit: 5,
      musical_chairs_config: {
        game_title: 'Preprod Musical Chairs',
        gameplay_mode: 'physical',
        music_mode: 'builtin',
        music_style: 'upbeat',
        min_music_seconds: 60,
        max_music_seconds: 300,
        auto_stop: false,
      },
    });
    await openOrganizerFromRoom(page, room);

    const players = await joinPlayers(browser, room.roomCode, ['Alice', 'Bob', 'Cara']);
    try {
      await startLobbyGame(page, players.length);
      await expect(page.getByRole('heading', { name: 'Preprod Musical Chairs' })).toBeVisible({ timeout: 20_000 });
      await page.getByRole('button', { name: 'Start Round' }).click();
      await expect(page.getByRole('button', { name: 'Stop Music' })).toBeVisible({ timeout: 20_000 });
      await page.getByRole('button', { name: 'Stop Music' }).click();
      await expect(page.getByText('Pick who did not get a chair')).toBeVisible({ timeout: 20_000 });
      await expectNoHorizontalOverflow(page);
    } finally {
      await closePlayers(players);
    }
  });

  test('Bluff lets the active player make a claim', async ({ page, browser, request }) => {
    const deviceId = liveDeviceId('bluff');
    const room = await createRoomViaApi(request, deviceId, { game_type: 'bluff', time_limit: 30, bluff_config: { game_title: 'Preprod Bluff' } });
    await openOrganizerFromRoom(page, room);

    const players = await joinPlayers(browser, room.roomCode, ['Alice', 'Bob', 'Cara']);
    try {
      await startLobbyGame(page, players.length);
      await expect(page.getByRole('heading', { name: 'Bluff' })).toBeVisible({ timeout: 20_000 });
      const activePlayer = await findPlayerWithEnabledButton(players, 'Pass');
      await activePlayer.page.locator('.bluff-hand .bluff-card').first().click();
      await activePlayer.page.getByRole('button', { name: /Play 1/ }).click();
      await expect(page.getByText(/claims 1/)).toBeVisible({ timeout: 20_000 });
      await expect(page.getByText('Challenge window')).toBeVisible();
      await expectNoHorizontalOverflow(page);
    } finally {
      await closePlayers(players);
    }
  });

  test('Two Truths and a Lie submits, votes, and reveals', async ({ page, browser, request }) => {
    const deviceId = liveDeviceId('two-truths');
    const room = await createRoomViaApi(request, deviceId, { game_type: 'two_truths', time_limit: 30, two_truths_config: { game_title: 'Preprod Two Truths' } });
    await openOrganizerFromRoom(page, room);

    const players = await joinPlayers(browser, room.roomCode, ['Alice', 'Bob', 'Cara']);
    try {
      await startLobbyGame(page, players.length);
      await expect(page.getByText('0 of 3 players ready')).toBeVisible({ timeout: 20_000 });
      await Promise.all(players.map((player, playerIndex) => submitTwoTruths(player, playerIndex)));
      await expect(page.getByText('3 of 3 players ready')).toBeVisible({ timeout: 20_000 });
      await page.getByRole('button', { name: 'Start Reveals' }).click();
      await expect(page.getByText('Guess the lie')).toBeVisible({ timeout: 20_000 });
      const voter = await firstVisibleVotingPlayer(players);
      await voter.page.locator('.two-truths-options button').first().click();
      await page.getByRole('button', { name: 'Reveal Lie' }).click();
      await expect(page.getByText(/lie revealed/)).toBeVisible({ timeout: 20_000 });
      await expectNoHorizontalOverflow(page);
    } finally {
      await closePlayers(players);
    }
  });

  test('Story Chain hands control to another player', async ({ page, browser, request }) => {
    const deviceId = liveDeviceId('story-chain');
    const room = await createRoomViaApi(request, deviceId, {
      game_type: 'story_chain',
      time_limit: 30,
      story_chain_config: {
        game_title: 'Preprod Story Chain',
        starter_prompt: 'The party lights flickered twice.',
        turn_time_seconds: 30,
      },
    });
    await openOrganizerFromRoom(page, room);

    const players = await joinPlayers(browser, room.roomCode, ['Alice', 'Bob', 'Cara']);
    try {
      await startLobbyGame(page, players.length);
      const active = await findPlayerWithVisibleButton(players, 'Add Sentence');
      await active.page.getByPlaceholder('Add one sentence...').fill('Everyone looked at the ceiling and started laughing.');
      await active.page.getByRole('button', { name: 'Add Sentence' }).click();
      await expect(active.page.getByText(/is writing/)).toBeVisible({ timeout: 20_000 });
      await expectNoHorizontalOverflow(page);
    } finally {
      await closePlayers(players);
    }
  });

  test('Common Ground assigns teams and reveals submitted answers', async ({ page, browser, request }) => {
    const deviceId = liveDeviceId('common-ground');
    const room = await createRoomViaApi(request, deviceId, {
      game_type: 'common_ground',
      time_limit: 30,
      common_ground_config: {
        game_title: 'Preprod Common Ground',
        team_size: 2,
        rounds: 1,
        discussion_time_seconds: 30,
        vote_time_seconds: 10,
        voting_enabled: true,
        prompts: [{ id: 'prompt_1', text: 'Find one snack everyone on your team likes.', category: 'food' }],
      },
    });
    await openOrganizerFromRoom(page, room);

    const players = await joinPlayers(browser, room.roomCode, ['Alice', 'Bob', 'Cara', 'Dev']);
    try {
      await startLobbyGame(page, players.length);
      await expect(page.getByText('Team progress')).toBeVisible({ timeout: 20_000 });
      await submitCommonGroundFacts(players);
      await expect(page.getByRole('button', { name: 'Start Voting' })).toBeVisible({ timeout: 20_000 });
      await expect(page.getByText('Pizza party')).toBeVisible();
      await expectNoHorizontalOverflow(page);
    } finally {
      await closePlayers(players);
    }
  });

  test('Who Am I imports clues and accepts a correct guess', async ({ page, browser, request }) => {
    const deviceId = liveDeviceId('who-am-i');
    const { who_am_i_id: whoAmIId } = await postJson<{ who_am_i_id: string }>(request, '/who-am-i/import', deterministicWhoAmI, deviceId);
    const room = await createRoomViaApi(request, deviceId, { game_type: 'who_am_i', who_am_i_id: whoAmIId, time_limit: 30 });
    await openOrganizerFromRoom(page, room);

    const players = await joinPlayers(browser, room.roomCode, ['Alice', 'Bob']);
    try {
      await startLobbyGame(page, players.length);
      await expect(page.getByRole('heading', { name: 'Preprod Who Am I' })).toBeVisible({ timeout: 20_000 });
      await players[0].page.getByPlaceholder('Type your guess').fill('Sherlock Holmes');
      await players[0].page.getByRole('button', { name: 'Submit Guess' }).click();
      await expect(players[0].page.getByText('You got it')).toBeVisible({ timeout: 20_000 });
      await page.getByRole('button', { name: 'Reveal Answer' }).click();
      await expect(page.getByText('Sherlock Holmes').first()).toBeVisible({ timeout: 20_000 });
      await expectNoHorizontalOverflow(page);
    } finally {
      await closePlayers(players);
    }
  });

  test('Chit Pull imports a deck, pulls one chit, and completes it', async ({ page, browser, request }) => {
    const deviceId = liveDeviceId('chit-pull');
    const { chit_pull_id: chitPullId } = await postJson<{ chit_pull_id: string }>(request, '/chit-pull/import', deterministicChitPull, deviceId);
    const room = await createRoomViaApi(request, deviceId, { game_type: 'chit_pull', chit_pull_id: chitPullId, time_limit: 20 });
    await openOrganizerFromRoom(page, room);

    const players = await joinPlayers(browser, room.roomCode, ['Alice', 'Bob', 'Cara']);
    try {
      await startLobbyGame(page, players.length);
      await expect(page.getByRole('heading', { name: 'Preprod Chit Pull' })).toBeVisible({ timeout: 20_000 });
      await page.getByRole('button', { name: 'Pull Chit' }).click();
      await expect(page.getByRole('button', { name: 'Completed' })).toBeVisible({ timeout: 20_000 });
      await page.getByRole('button', { name: 'Completed' }).click();
      await expect(page.getByText(/completed/).first()).toBeVisible({ timeout: 20_000 });
      await expectNoHorizontalOverflow(page);
    } finally {
      await closePlayers(players);
    }
  });

  test('Drawing imports prompts, assigns a drawer, and accepts a correct guess', async ({ page, browser, request }) => {
    const deviceId = liveDeviceId('drawing');
    const { drawing_id: drawingId } = await postJson<{ drawing_id: string }>(request, '/drawing/import', deterministicDrawing, deviceId);
    const room = await createRoomViaApi(request, deviceId, {
      game_type: 'drawing',
      drawing_id: drawingId,
      time_limit: 30,
      drawing_auto_advance: false,
    });
    await openOrganizerFromRoom(page, room);

    const players = await joinPlayers(browser, room.roomCode, ['Alice', 'Bob', 'Cara']);
    try {
      await startLobbyGame(page, players.length);
      await expect(page.getByText(/Drawer:/)).toBeVisible({ timeout: 20_000 });
      await expect(page.getByText(/Clue:/)).toBeVisible({ timeout: 20_000 });

      const drawerIndexes: number[] = [];
      for (const [index, player] of players.entries()) {
        if (await player.page.getByText('You are drawing').isVisible({ timeout: 5_000 }).catch(() => false)) {
          drawerIndexes.push(index);
        }
      }
      expect(drawerIndexes).toHaveLength(1);
      const guesser = players.find((_, index) => index !== drawerIndexes[0])!;
      await expect(guesser.page.getByLabel('Drawing clue')).toContainText('_', { timeout: 20_000 });
      await expect(guesser.page.getByText('robot chef')).toHaveCount(0);
      await guesser.page.getByPlaceholder('Type your guess').fill('robot cook');
      await guesser.page.getByRole('button', { name: 'Guess' }).click();
      await expect(guesser.page.getByText('Correct!')).toBeVisible({ timeout: 20_000 });
      await expect(page.getByText(/1 of 2 guessed|1 guessed/i)).toBeVisible({ timeout: 20_000 });
      await expectNoHorizontalOverflow(page);
    } finally {
      await closePlayers(players);
    }
  });
});

async function submitTwoTruths(player: LivePlayer, playerIndex: number) {
  const rows = player.page.locator('.two-truths-statement-input');
  await expect(rows).toHaveCount(3, { timeout: 20_000 });
  await rows.nth(0).locator('textarea').fill(`${player.nickname} has visited Jaipur ${playerIndex + 1} times.`);
  await rows.nth(1).locator('textarea').fill(`${player.nickname} likes mango ice cream.`);
  await rows.nth(2).locator('textarea').fill(`${player.nickname} can breathe underwater.`);
  await rows.nth(2).getByRole('button', { name: 'Lie' }).click();
  await player.page.getByRole('button', { name: /Submit Statements|Update Statements/ }).click();
}

async function firstVisibleVotingPlayer(players: LivePlayer[]): Promise<LivePlayer> {
  await expect.poll(async () => {
    for (const [index, player] of players.entries()) {
      if (await player.page.locator('.two-truths-options button').first().isVisible().catch(() => false)) return index;
    }
    return -1;
  }, { timeout: 20_000 }).not.toBe(-1);
  for (const player of players) {
    if (await player.page.locator('.two-truths-options button').first().isVisible().catch(() => false)) {
      return player;
    }
  }
  return players[0];
}

async function submitCommonGroundFacts(players: LivePlayer[]) {
  const submissions = new Set<string>();
  for (const player of players) {
    if (submissions.size >= 2) break;
    const submitButton = player.page.getByRole('button', { name: /Submit Answer|Update Answer/ });
    if (!(await submitButton.isVisible().catch(() => false))) continue;
    const teamName = (await player.page.locator('.common-ground-panel h2').textContent().catch(() => player.nickname)) || player.nickname;
    if (submissions.has(teamName)) continue;
    await player.page.getByPlaceholder('We all...').fill(submissions.size === 0 ? 'Pizza party' : 'Chocolate cake');
    await submitButton.click();
    submissions.add(teamName);
  }

  if (submissions.size < 2) {
    await expect.poll(async () => {
      let visible = 0;
      for (const player of players) {
        if (await player.page.getByRole('button', { name: /Submit Answer|Update Answer/ }).isVisible().catch(() => false)) visible += 1;
      }
      return visible;
    }, { timeout: 20_000 }).toBeGreaterThanOrEqual(2);
  }
}
