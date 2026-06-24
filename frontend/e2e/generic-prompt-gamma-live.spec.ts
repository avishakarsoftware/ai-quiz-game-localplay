import { expect, test, type Page } from '@playwright/test';
import { expectNoHorizontalOverflow } from './helpers';
import {
  closePlayers,
  createRoomViaApi,
  joinPlayers,
  liveDeviceId,
  openOrganizerFromRoom,
  startLobbyGame,
  type LivePlayer,
} from './liveGameHarness';

type GenericMode = 'choice_vote' | 'text_vote' | 'text_group';

interface GenericCase {
  gameType: string;
  title: string;
  mode: GenericMode;
  choices?: [string, string];
}

const genericGames: GenericCase[] = [
  { gameType: 'hot_takes', title: 'Hot Takes', mode: 'choice_vote', choices: ['Agree', 'Agree'] },
  { gameType: 'this_or_that', title: 'This or That', mode: 'choice_vote', choices: ['DJ', 'DJ'] },
  { gameType: 'caption_contest', title: 'Caption Contest', mode: 'text_vote' },
  { gameType: 'pitch_battle', title: 'Pitch Battle', mode: 'text_vote' },
  { gameType: 'roast_toast', title: 'Roast & Toast', mode: 'text_vote' },
  { gameType: 'desert_island', title: 'Desert Island', mode: 'text_vote' },
  { gameType: 'memory_lane', title: 'Memory Lane', mode: 'text_vote' },
  { gameType: 'rapid_fire', title: 'Rapid Fire', mode: 'text_group' },
  { gameType: 'one_word_vibes', title: 'One Word Vibes', mode: 'text_group' },
  { gameType: 'emoji_story', title: 'Emoji Story', mode: 'text_vote' },
];

test.describe('Generic Prompt Party games on gamma', () => {
  test.describe.configure({ timeout: 90_000 });

  test.beforeEach(async ({}, testInfo) => {
    test.skip(!String(process.env.PLAYWRIGHT_BASE_URL || '').includes('gamma'), 'live gamma test only');
    test.skip(testInfo.project.name !== 'chromium-desktop', 'multi-context live flow runs desktop-only');
  });

  for (const game of genericGames) {
    test(`${game.title} plays one full live round`, async ({ page, browser, request }) => {
      const deviceId = liveDeviceId(game.gameType);
      const room = await createRoomViaApi(request, deviceId, {
        game_type: game.gameType,
        time_limit: 30,
        generic_prompt_config: {
          game_title: game.title,
          round_count: 3,
        },
      });
      await openOrganizerFromRoom(page, room);

      const players = await joinPlayers(browser, room.roomCode, ['Alice', 'Bob']);
      try {
        await startLobbyGame(page, players.length);
        await expect(page.getByRole('heading', { name: game.title, exact: true })).toBeVisible({ timeout: 20_000 });
        await expect(page.getByText(/Round 1 of 3/)).toBeVisible({ timeout: 20_000 });
        await expectNoHorizontalOverflow(page);

        if (game.mode === 'choice_vote') {
          await playChoiceRound(page, players, game.choices || ['Agree', 'Agree']);
        } else if (game.mode === 'text_vote') {
          await playTextVoteRound(page, players, game.title);
        } else {
          await playTextGroupRound(page, players);
        }

        await expect(page.getByRole('button', { name: 'Next Round' })).toBeVisible({ timeout: 20_000 });
        await expect(page.getByRole('heading', { name: 'Scores' })).toBeVisible();
        await expectNoHorizontalOverflow(page);
      } finally {
        await closePlayers(players);
      }
    });
  }
});

async function playChoiceRound(page: Page, players: LivePlayer[], choices: [string, string]) {
  await players[0].page.getByRole('button', { name: choices[0], exact: true }).click();
  await players[1].page.getByRole('button', { name: choices[1], exact: true }).click();
  await expect(page.getByText(/2 submitted/)).toBeVisible({ timeout: 20_000 });
  await page.getByRole('button', { name: 'Reveal' }).click();
  await expect(page.getByText(/2 votes?/)).toBeVisible({ timeout: 20_000 });
  await expect(players[0].page.getByText('1 point').first()).toBeVisible({ timeout: 20_000 });
}

async function playTextVoteRound(page: Page, players: LivePlayer[], title: string) {
  const aliceEntry = `${title} Alice answer`;
  const bobEntry = `${title} Bob answer`;
  await submitText(players[0], aliceEntry);
  await submitText(players[1], bobEntry);
  await expect(page.getByText(/2 submitted/)).toBeVisible({ timeout: 20_000 });

  await page.getByRole('button', { name: 'Start Voting' }).click();
  await expect(players[0].page.getByRole('button', { name: bobEntry })).toBeVisible({ timeout: 20_000 });
  await expect(players[1].page.getByRole('button', { name: aliceEntry })).toBeVisible({ timeout: 20_000 });
  await players[0].page.getByRole('button', { name: bobEntry }).click();
  await players[1].page.getByRole('button', { name: aliceEntry }).click();

  await page.getByRole('button', { name: 'Reveal' }).click();
  await expect(page.getByRole('button', { name: 'Next Round' })).toBeVisible({ timeout: 20_000 });
  await expect(page.getByText(aliceEntry).first()).toBeVisible({ timeout: 20_000 });
  await expect(page.getByText(bobEntry).first()).toBeVisible({ timeout: 20_000 });
  await expect(page.getByText(/1 vote/).first()).toBeVisible({ timeout: 20_000 });
}

async function playTextGroupRound(page: Page, players: LivePlayer[]) {
  await submitText(players[0], 'Pizza');
  await submitText(players[1], 'pizza!');
  await expect(page.getByText(/2 submitted/)).toBeVisible({ timeout: 20_000 });
  await page.getByRole('button', { name: 'Reveal' }).click();
  await expect(page.getByText('Pizza')).toBeVisible({ timeout: 20_000 });
  await expect(page.getByText(/Alice, Bob/)).toBeVisible({ timeout: 20_000 });
}

async function submitText(player: LivePlayer, text: string) {
  await player.page.locator('.input-field').fill(text);
  await player.page.getByRole('button', { name: 'Submit' }).click();
  await expect(player.page.getByText(/Submitted/)).toBeVisible({ timeout: 20_000 });
}
