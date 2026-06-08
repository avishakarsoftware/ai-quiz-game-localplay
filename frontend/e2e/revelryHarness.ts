import { readFileSync } from 'node:fs';
import { expect, test, type APIRequestContext, type Page } from '@playwright/test';

export const GAMMA_ORIGIN = 'https://gamesapi-gamma.revelryapp.me';
const REVELRY_GAMMA_ORIGIN = 'https://api-gamma.revelryapp.me';
const REVELRY_GAMMA_HOST_PHONE = '+15550199000';
const REVELRY_GAMMA_HOST_NAME = 'Gamma Test Host';

export function getGammaPartyGamesUrl(): URL {
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

export function decodeJwtPayload(token: string): Record<string, any> {
  const payload = token.split('.')[1] || '';
  const padded = `${payload}${'='.repeat((4 - (payload.length % 4)) % 4)}`;
  return JSON.parse(Buffer.from(padded, 'base64url').toString('utf8'));
}

export async function resolveWorkspace(request: APIRequestContext, token: string) {
  const resolve = await request.get(`/integrations/revelry/party-games/resolve?party_games_token=${encodeURIComponent(token)}`);
  await expect(resolve).toBeOK();
  return resolve.json();
}

export async function waitForCondition<T>(
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

export async function expectOrganizerLaunch(page: Page) {
  await page.waitForFunction(() => {
    const params = new URLSearchParams(window.location.search);
    return window.location.pathname === '/organizer' && params.has('launch_token') && params.get('embed') === '1';
  }, undefined, { timeout: 15000 });
}

export async function revelryGammaLogin(): Promise<{ token: string; user: { id: string; name: string } }> {
  const response = await fetch(`${REVELRY_GAMMA_ORIGIN}/auth/dev/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ phone: REVELRY_GAMMA_HOST_PHONE, name: REVELRY_GAMMA_HOST_NAME }),
  });
  const body = await response.text();
  expect(response.ok, body).toBeTruthy();
  return JSON.parse(body);
}

export async function driveQuizToCompletion(page: Page, roomCode: string, organizerToken: string) {
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

export async function revelryGammaJson(path: string, token: string) {
  const response = await fetch(`${REVELRY_GAMMA_ORIGIN}${path}`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  const body = await response.text();
  expect(response.ok, body).toBeTruthy();
  return JSON.parse(body);
}
