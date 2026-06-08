import { expect, type APIRequestContext, type Browser, type BrowserContext, type Page } from '@playwright/test';
import { randomUUID } from 'node:crypto';

export interface LivePlayer {
  context: BrowserContext;
  page: Page;
  nickname: string;
}

export interface LiveRoom {
  roomCode: string;
  organizerToken: string;
  gameType: string;
  contentId?: string;
}

export const liveBaseURL = process.env.PLAYWRIGHT_BASE_URL || 'http://127.0.0.1:5173';

export function liveDeviceId(prefix: string): string {
  void prefix;
  return randomUUID();
}

export function liveApiHeaders(deviceId: string): Record<string, string> {
  return {
    'Content-Type': 'application/json',
    'X-Device-Id': deviceId,
    'X-Platform': 'web',
    'X-App-Version': 'preprod-live',
    'X-Build': 'e2e',
    'X-Idempotency-Key': randomUUID(),
  };
}

export async function postJson<T>(
  request: APIRequestContext,
  path: string,
  body: unknown,
  deviceId: string,
): Promise<T> {
  const response = await request.post(path, {
    data: body,
    headers: liveApiHeaders(deviceId),
  });
  if (!response.ok()) {
    throw new Error(`${path} ${response.status()} ${await response.text().catch(() => '')}`);
  }
  return response.json() as Promise<T>;
}

export async function createRoomViaApi(
  request: APIRequestContext,
  deviceId: string,
  body: Record<string, unknown>,
): Promise<LiveRoom> {
  const response = await postJson<{ room_code: string; organizer_token: string }>(request, '/room/create', body, deviceId);
  expect(response.room_code).toMatch(/^[A-Z0-9]{6}$/);
  expect(response.organizer_token).toBeTruthy();
  return {
    roomCode: response.room_code,
    organizerToken: response.organizer_token,
    gameType: String(body.game_type || 'quiz'),
    contentId: String(body.quiz_id || body.mlt_id || body.drawing_id || body.housie_id || body.bingo_id || body.who_am_i_id || body.chit_pull_id || ''),
  };
}

export async function openOrganizerFromRoom(page: Page, room: LiveRoom) {
  await page.addInitScript((session) => {
    window.localStorage.setItem('localplay_organizer_session', JSON.stringify(session));
  }, {
    roomCode: room.roomCode,
    organizerToken: room.organizerToken,
    gameType: room.gameType,
    contentId: room.contentId,
    savedAt: Date.now(),
  });
  await page.goto('/');
  await expect(page.locator('.room-code')).toHaveText(room.roomCode, { timeout: 20_000 });
}

export async function joinPlayer(browser: Browser, roomCode: string, nickname: string): Promise<LivePlayer> {
  const context = await browser.newContext({ baseURL: liveBaseURL });
  const page = await context.newPage();
  await page.goto(`/join/${roomCode}`);
  await page.getByPlaceholder('Your nickname').fill(nickname);
  await page.getByRole('button', { name: 'Join' }).click();
  await expect(page.getByRole('heading', { name: "You're in!" })).toBeVisible({ timeout: 20_000 });
  return { context, page, nickname };
}

export async function joinPlayers(browser: Browser, roomCode: string, nicknames: string[]): Promise<LivePlayer[]> {
  return Promise.all(nicknames.map((nickname) => joinPlayer(browser, roomCode, nickname)));
}

export async function closePlayers(players: LivePlayer[]) {
  await Promise.all(players.map(({ context }) => context.close()));
}

export async function startLobbyGame(page: Page, playerCount: number) {
  await expect(page.getByText(`${playerCount} players`)).toBeVisible({ timeout: 25_000 });
  await page.getByRole('button', { name: 'Start Game' }).click();
}

export async function findPlayerWithVisibleButton(players: LivePlayer[], name: string | RegExp): Promise<LivePlayer> {
  await expect.poll(async () => {
    for (const [index, player] of players.entries()) {
      if (await player.page.getByRole('button', { name }).isVisible().catch(() => false)) return index;
    }
    return -1;
  }, { timeout: 25_000 }).not.toBe(-1);

  for (const player of players) {
    if (await player.page.getByRole('button', { name }).isVisible().catch(() => false)) return player;
  }
  throw new Error(`No player has visible button ${String(name)}`);
}

export async function findPlayerWithEnabledButton(players: LivePlayer[], name: string | RegExp): Promise<LivePlayer> {
  await expect.poll(async () => {
    for (const [index, player] of players.entries()) {
      if (await player.page.getByRole('button', { name }).isEnabled().catch(() => false)) return index;
    }
    return -1;
  }, { timeout: 25_000 }).not.toBe(-1);

  for (const player of players) {
    if (await player.page.getByRole('button', { name }).isEnabled().catch(() => false)) return player;
  }
  throw new Error(`No player has enabled button ${String(name)}`);
}

export const deterministicQuiz = {
  quiz_title: 'Preprod Live Quiz',
  questions: [
    {
      id: 1,
      text: 'Which color is usually made by mixing blue and yellow?',
      options: ['Purple', 'Green', 'Orange', 'Black'],
      answer_index: 1,
      image_prompt: '',
    },
    {
      id: 2,
      text: 'True or false: the Earth orbits the Sun.',
      options: ['True', 'False'],
      answer_index: 0,
      image_prompt: '',
    },
  ],
};

export const deterministicMlt = {
  game_title: 'Preprod Most Likely To',
  statements: [
    { id: 1, text: 'Who is most likely to organize the snacks?' },
    { id: 2, text: "Who is most likely to remember everyone's birthday?" },
  ],
};

export function deterministicBingoDeck(prefix = 'Item') {
  return Array.from({ length: 24 }, (_, index) => ({
    id: `${prefix.toLowerCase()}_${index + 1}`,
    kind: 'text',
    value: `${prefix} ${index + 1}`,
    display: `${prefix} ${index + 1}`,
  }));
}

export const deterministicWhoAmI = {
  game_title: 'Preprod Who Am I',
  theme: 'famous characters',
  round_count: 3,
  clues_per_round: 3,
  rounds: [
    {
      id: 'round_1',
      answer: 'Sherlock Holmes',
      aliases: ['Sherlock'],
      category: 'fictional detective',
      difficulty: 'easy',
      clues: ['I solve mysteries.', 'I live at 221B Baker Street.', 'My friend is Dr. Watson.'],
    },
    {
      id: 'round_2',
      answer: 'Mickey Mouse',
      aliases: ['Mickey'],
      category: 'animated character',
      difficulty: 'easy',
      clues: ['I am animated.', 'I have round ears.', 'My friend is Minnie.'],
    },
    {
      id: 'round_3',
      answer: 'Darth Vader',
      aliases: ['Vader'],
      category: 'movie character',
      difficulty: 'easy',
      clues: ['I wear a helmet.', 'I breathe loudly.', 'I say I am your father.'],
    },
  ],
};

export const deterministicChitPull = {
  game_title: 'Preprod Chit Pull',
  rounds: 5,
  turn_time_seconds: 20,
  safe_level: 'family',
  chits: [
    { id: 'chit_1', text: 'Make your best celebration pose.', category: 'funny_face', safe_level: 'family' },
    { id: 'chit_2', text: 'Name a snack everyone should try.', category: 'question', safe_level: 'family' },
    { id: 'chit_3', text: 'Give the room a tiny victory dance.', category: 'action', safe_level: 'family' },
    { id: 'chit_4', text: 'Say one kind thing about the person on your left.', category: 'group', safe_level: 'family' },
    { id: 'chit_5', text: 'Pretend to be a game show host for ten seconds.', category: 'mini_challenge', safe_level: 'family' },
  ],
};
