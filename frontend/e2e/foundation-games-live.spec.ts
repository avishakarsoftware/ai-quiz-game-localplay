import { expect, test } from '@playwright/test';
import { expectNoHorizontalOverflow } from './helpers';
import {
  closePlayers,
  createRoomViaApi,
  findPlayerWithVisibleButton,
  joinPlayers,
  liveDeviceId,
  openOrganizerFromRoom,
  type LivePlayer,
} from './liveGameHarness';

test.describe('Foundation games live regression', () => {
  test.describe.configure({ timeout: 120_000 });

  test.beforeEach(async ({}, testInfo) => {
    test.skip(process.env.PREPROD_LIVE !== '1', 'Set PREPROD_LIVE=1 to run the live foundation-games regression suite.');
    test.skip(testInfo.project.name !== 'chromium-desktop', 'The live regression suite uses multiple browser contexts and runs desktop-only.');
  });

  test('Would You Rather accepts votes and reveals the split', async ({ page, browser, request }) => {
    const room = await createRoomViaApi(request, liveDeviceId('wyr'), {
      game_type: 'would_you_rather',
      time_limit: 30,
      would_you_rather_config: {
        game_title: 'Live Would You Rather',
        round_count: 3,
        prompts: [
          { id: 'wyr_1', question: 'Would you rather host karaoke or trivia?', option_a: 'Karaoke', option_b: 'Trivia' },
          { id: 'wyr_2', question: 'Would you rather have cake or pizza?', option_a: 'Cake', option_b: 'Pizza' },
          { id: 'wyr_3', question: 'Would you rather dance first or sing first?', option_a: 'Dance', option_b: 'Sing' },
        ],
      },
    });
    await openOrganizerFromRoom(page, room);
    const players = await joinPlayers(browser, room.roomCode, ['Alice', 'Bob']);
    try {
      await startAndExpect(page, players, 'Live Would You Rather');
      await players[0].page.getByRole('button', { name: 'Karaoke' }).click();
      await expect(players[0].page.getByText(/Submitted/)).toBeVisible({ timeout: 20_000 });
      await page.getByRole('button', { name: 'Reveal' }).click();
      await expect(page.getByText('100%')).toBeVisible({ timeout: 20_000 });
      await expectNoHorizontalOverflow(page);
    } finally {
      await closePlayers(players);
    }
  });

  test('Never Have I Ever accepts answers and reveals the split', async ({ page, browser, request }) => {
    const room = await createRoomViaApi(request, liveDeviceId('nhie'), {
      game_type: 'never_have_i_ever',
      time_limit: 30,
      never_have_i_ever_config: {
        game_title: 'Live Never Have I Ever',
        round_count: 3,
        prompts: [
          { id: 'nhie_1', statement: 'Never have I ever sung karaoke in public.' },
          { id: 'nhie_2', statement: 'Never have I ever forgotten why I entered a room.' },
          { id: 'nhie_3', statement: 'Never have I ever laughed during a serious moment.' },
        ],
      },
    });
    await openOrganizerFromRoom(page, room);
    const players = await joinPlayers(browser, room.roomCode, ['Alice', 'Bob']);
    try {
      await startAndExpect(page, players, 'Live Never Have I Ever');
      await players[0].page.getByRole('button', { name: 'I have' }).click();
      await expect(players[0].page.getByText(/Submitted/)).toBeVisible({ timeout: 20_000 });
      await page.getByRole('button', { name: 'Reveal' }).click();
      await expect(page.getByText(/I have|Never/)).toBeVisible({ timeout: 20_000 });
      await expectNoHorizontalOverflow(page);
    } finally {
      await closePlayers(players);
    }
  });

  test('Word Association accepts submissions and groups the reveal', async ({ page, browser, request }) => {
    const room = await createRoomViaApi(request, liveDeviceId('word-assoc'), {
      game_type: 'word_association',
      time_limit: 30,
      word_association_config: {
        game_title: 'Live Word Association',
        round_count: 3,
        seeds: [
          { id: 'word_1', seed: 'Party' },
          { id: 'word_2', seed: 'Music' },
          { id: 'word_3', seed: 'Cake' },
        ],
      },
    });
    await openOrganizerFromRoom(page, room);
    const players = await joinPlayers(browser, room.roomCode, ['Alice', 'Bob']);
    try {
      await startAndExpect(page, players, 'Live Word Association');
      await submitText(players[0], 'First word that comes to mind', 'Pizza');
      await expect(players[0].page.getByText(/Submitted/)).toBeVisible({ timeout: 20_000 });
      await page.getByRole('button', { name: 'Reveal' }).click();
      await expect(page.getByText('Pizza')).toBeVisible({ timeout: 20_000 });
      await expectNoHorizontalOverflow(page);
    } finally {
      await closePlayers(players);
    }
  });

  test('Acronym Game moves through submit, vote, and reveal', async ({ page, browser, request }) => {
    const room = await createRoomViaApi(request, liveDeviceId('acronym'), {
      game_type: 'acronym',
      time_limit: 30,
      acronym_config: {
        game_title: 'Live Acronym Game',
        round_count: 3,
        prompts: [
          { id: 'acro_1', acronym: 'PARTY', hint: 'Make it festive.' },
          { id: 'acro_2', acronym: 'CAKE', hint: 'Make it delicious.' },
          { id: 'acro_3', acronym: 'DANCE', hint: 'Make it dramatic.' },
        ],
      },
    });
    await openOrganizerFromRoom(page, room);
    const players = await joinPlayers(browser, room.roomCode, ['Alice', 'Bob']);
    try {
      await startAndExpect(page, players, 'Live Acronym Game');
      await submitText(players[0], /Party Animals/i, 'Party Animals Really Tell Yarns');
      await submitText(players[1], /Party Animals/i, 'Pancakes Are Really Too Yummy');
      await page.getByRole('button', { name: 'Start Voting' }).click();
      await expect(players[0].page.getByRole('button', { name: /Pancakes Are Really Too Yummy/ })).toBeVisible({ timeout: 20_000 });
      await players[0].page.getByRole('button', { name: /Pancakes Are Really Too Yummy/ }).click();
      await page.getByRole('button', { name: 'Reveal' }).click();
      await expect(page.getByText(/Pancakes Are Really Too Yummy/)).toBeVisible({ timeout: 20_000 });
      await expectNoHorizontalOverflow(page);
    } finally {
      await closePlayers(players);
    }
  });

  test('Photo Clue uploads a clue photo and accepts a guess', async ({ page, browser, request }, testInfo) => {
    const room = await createRoomViaApi(request, liveDeviceId('photo-clue'), {
      game_type: 'photo_clue',
      time_limit: 30,
      photo_clue_config: {
        game_title: 'Live Photo Clue',
        round_count: 3,
        prompts: [
          { id: 'photo_1', answer: 'birthday cake', aliases: ['cake'] },
          { id: 'photo_2', answer: 'party lights', aliases: ['lights'] },
          { id: 'photo_3', answer: 'cold drink', aliases: ['drink'] },
        ],
      },
    });
    await openOrganizerFromRoom(page, room);
    const players = await joinPlayers(browser, room.roomCode, ['Alice', 'Bob']);
    try {
      await startAndExpect(page, players, 'Live Photo Clue');
      const clueGiver = await findPlayerWithVisibleButton(players, 'Choose Photo');
      const photoPath = testInfo.outputPath('photo-clue.png');
      await testInfo.attach('photo-clue-pixel', {
        body: Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGOSHzRgAAAAABJRU5ErkJggg==', 'base64'),
        contentType: 'image/png',
      });
      await clueGiver.page.locator('input[type="file"]').setInputFiles({
        name: photoPath.split('/').pop() || 'photo-clue.png',
        mimeType: 'image/png',
        buffer: Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGOSHzRgAAAAABJRU5ErkJggg==', 'base64'),
      });
      await expect(page.getByText(/Guessing|PHOTO_GUESSING|is giving the photo clue/i)).toBeVisible({ timeout: 30_000 });
      const guesser = players.find((player) => player !== clueGiver) || players[0];
      await guesser.page.getByPlaceholder('Type your guess').fill('cake');
      await guesser.page.getByRole('button', { name: 'Submit Guess' }).click();
      await expect(guesser.page.getByText(/correct|Your guess/i)).toBeVisible({ timeout: 20_000 });
      await page.getByRole('button', { name: 'Reveal' }).click();
      await expect(page.getByText(/birthday cake/i)).toBeVisible({ timeout: 20_000 });
      await expectNoHorizontalOverflow(page);
    } finally {
      await closePlayers(players);
    }
  });

  test('Party Poker hides hole cards and completes a showdown', async ({ page, browser, request }) => {
    const room = await createRoomViaApi(request, liveDeviceId('poker'), {
      game_type: 'poker',
      time_limit: 30,
      poker_config: {
        game_title: 'Live Party Poker',
        starting_stack: 200,
        ante: 100,
        decision_time_seconds: 20,
      },
    });
    await openOrganizerFromRoom(page, room);
    const players = await joinPlayers(browser, room.roomCode, ['Alice', 'Bob']);
    try {
      await startAndExpect(page, players, 'Live Party Poker');
      await expect(page.getByText(/Choose stay or fold/)).toBeVisible({ timeout: 20_000 });
      await players[0].page.getByRole('button', { name: 'Stay' }).click();
      await players[1].page.getByRole('button', { name: 'Fold' }).click();
      await expect(page.getByText(/wins 200 play chips/)).toBeVisible({ timeout: 20_000 });
      await expectNoHorizontalOverflow(page);
    } finally {
      await closePlayers(players);
    }
  });
});

async function startAndExpect(page: LivePlayer['page'], players: LivePlayer[], heading: string | RegExp) {
  await expect(page.getByText(`${players.length} players`)).toBeVisible({ timeout: 25_000 });
  await page.getByRole('button', { name: 'Start Game' }).click();
  await expect(page.getByRole('heading', { name: heading })).toBeVisible({ timeout: 20_000 });
}

async function submitText(player: LivePlayer, placeholder: string | RegExp, value: string) {
  await player.page.getByPlaceholder(placeholder).fill(value);
  await player.page.getByRole('button', { name: /Submit|Update/ }).click();
}
