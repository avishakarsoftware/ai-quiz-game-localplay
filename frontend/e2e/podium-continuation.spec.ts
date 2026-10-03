import { expect, test } from '@playwright/test';
import {
    closePlayers, createRoomViaApi, joinPlayers, liveDeviceId,
    openOrganizerFromRoom, postJson, startLobbyGame, type LivePlayer,
} from './liveGameHarness';

// Exercise the real React event boundary: choosing a default game immediately after
// clearing content must not reuse the previous render's quiz content id.
for (const nextGame of ['odd_question', 'would_you_rather']) {
    test(`podium suggestion continues into ${nextGame} with the same guests and QR`, async ({ page, browser, request }) => {
        const deviceId = liveDeviceId('podium-continuation');
        const imported = await postJson<{ quiz_id: string }>(request, '/quiz/import', {
            quiz: {
                quiz_title: 'QA Continuation',
                questions: [{ id: 1, text: 'Which comes first?', options: ['A', 'B'], answer_index: 0 }],
            },
        }, deviceId);
        const room = await createRoomViaApi(request, deviceId, { quiz_id: imported.quiz_id, time_limit: 30 });
        const resets: Record<string, unknown>[] = [];
        page.on('websocket', (socket) => socket.on('framesent', ({ payload }) => {
            const data = JSON.parse(String(payload)) as Record<string, unknown>;
            if (data.type === 'RESET_ROOM') resets.push(data);
        }));
        await page.addInitScript((id) => {
            localStorage.setItem('revelry_device_id', id);
            const NativeSocket = window.WebSocket;
            window.WebSocket = class extends NativeSocket {
                constructor(url: string | URL, protocols?: string | string[]) {
                    super(url, protocols);
                    if (String(url).includes('organizer=true')) {
                        (window as unknown as { qaOrganizer: WebSocket }).qaOrganizer = this;
                    }
                }
            };
        }, deviceId);
        // Restrict candidates without changing their actual metadata or runtime.
        await page.route('**/catalog', async (route) => {
            const response = await route.fetch();
            const data = await response.json() as { games: Array<{ id: string }> };
            data.games = data.games.filter((game) => ['quiz', nextGame].includes(game.id));
            await route.fulfill({ response, json: data });
        });
        const players: LivePlayer[] = [];
        try {
            await openOrganizerFromRoom(page, room);
            for (const name of ['QA-Ada', 'QA-Grace', 'QA-Hopper']) {
                players.push(...await joinPlayers(browser, room.roomCode, [name]));
            }
            await startLobbyGame(page, players.length);
            await expect(page.getByRole('button', { name: 'End Game' })).toBeVisible();
            await page.getByRole('button', { name: 'End Game' }).click();
            await expect(page.getByTestId(`next-game-${nextGame}`)).toBeVisible();
            await page.getByTestId(`next-game-${nextGame}`).click();
            await expect(page.locator('.room-code')).toHaveText(room.roomCode);
            expect(resets).toHaveLength(1);
            expect(resets[0]).toMatchObject({ game_type: nextGame, content_id: '' });
            for (const player of players) {
                await expect(player.page.getByRole('heading', { name: "You're in!" })).toBeVisible();
            }
            await startLobbyGame(page, players.length);
            await expect(page.locator('.room-code')).not.toBeVisible();
            await expect(page.getByRole('button', { name: 'End Game' })).toBeVisible();
        } finally {
            await page.evaluate(() => {
                const socket = (window as unknown as { qaOrganizer?: WebSocket }).qaOrganizer;
                if (socket?.readyState === WebSocket.OPEN) socket.send(JSON.stringify({ type: 'CANCEL_GAME' }));
            }).catch(() => {});
            await closePlayers(players);
        }
    });
}

test('default game Play Again keeps the room and guest sockets, then restarts with cleared votes', async ({ page, browser, request }) => {
    const deviceId = liveDeviceId('default-replay');
    const room = await createRoomViaApi(request, deviceId, { game_type: 'would_you_rather', time_limit: 45 });
    const resets: Record<string, unknown>[] = [];
    const states: Record<string, unknown>[] = [];
    let hostSockets = 0;
    let replacementPlayerSockets = 0;
    let roomClosed = false;
    page.on('websocket', (socket) => {
        if (!socket.url().includes('organizer=true')) return;
        hostSockets += 1;
        socket.on('framesent', ({ payload }) => {
            const data = JSON.parse(String(payload)) as Record<string, unknown>;
            if (data.type === 'RESET_ROOM') resets.push(data);
        });
        socket.on('framereceived', ({ payload }) => {
            const data = JSON.parse(String(payload)) as Record<string, unknown>;
            if (data.type === 'SIMPLE_SOCIAL_SYNC' && data.would_you_rather) states.push(data.would_you_rather as Record<string, unknown>);
            if (data.type === 'ROOM_CLOSED') roomClosed = true;
        });
    });
    await page.addInitScript((id) => {
        localStorage.setItem('revelry_device_id', id);
        const NativeSocket = window.WebSocket;
        window.WebSocket = class extends NativeSocket {
            constructor(url: string | URL, protocols?: string | string[]) {
                super(url, protocols);
                if (String(url).includes('organizer=true')) {
                    (window as unknown as { qaOrganizer: WebSocket }).qaOrganizer = this;
                }
            }
        };
    }, deviceId);
    const players: LivePlayer[] = [];
    try {
        await openOrganizerFromRoom(page, room);
        for (const name of ['QA-Replay-Ada', 'QA-Replay-Grace']) {
            players.push(...await joinPlayers(browser, room.roomCode, [name]));
        }
        for (const player of players) player.page.on('websocket', () => { replacementPlayerSockets += 1; });
        await startLobbyGame(page, players.length);
        await expect(page.getByRole('heading', { name: 'Would You Rather', exact: true })).toBeVisible();
        await expect.poll(() => states.length).toBeGreaterThan(0);
        const originalState = states[0];
        // Development StrictMode can replace the initial socket before auth.
        // Replay must retain the socket that is serving the running game.
        const originalHostSocketCount = hostSockets;
        for (const player of players) {
            await player.page.getByRole('button', { name: 'Unlimited snacks', exact: true }).click();
            await expect(player.page.getByText('Submitted. You can still change it before reveal.')).toBeVisible();
        }
        await page.getByRole('button', { name: 'Reveal', exact: true }).click();
        await expect(page.getByRole('button', { name: 'Next Round', exact: true })).toBeVisible();
        await page.getByRole('button', { name: 'End Game', exact: true }).click();
        for (const player of players) await expect(player.page.getByRole('heading', { name: 'Final Results' })).toBeVisible();
        await page.getByRole('button', { name: 'Play Again', exact: true }).click();
        await expect(page.locator('.room-code')).toHaveText(room.roomCode);
        expect(resets).toHaveLength(1);
        expect(resets[0]).toMatchObject({ game_type: 'would_you_rather', content_id: '', time_limit: 45 });
        for (const player of players) await expect(player.page.getByRole('heading', { name: "You're in!" })).toBeVisible();
        const beforeRestart = states.length;
        await startLobbyGame(page, players.length);
        await expect.poll(() => states.length).toBeGreaterThan(beforeRestart);
        const restarted = states.at(-1)!;
        expect(restarted).toMatchObject({
            phase: 'WYR_VOTING',
            game_title: originalState.game_title,
            round_count: originalState.round_count,
            prompt: originalState.prompt,
            current_round_index: 0,
            submitted_votes: 0,
            scores: { 'QA-Replay-Ada': 0, 'QA-Replay-Grace': 0 },
        });
        for (const player of players) {
            await expect(player.page.getByRole('button', { name: 'Unlimited snacks', exact: true })).toBeEnabled();
            await expect(player.page.getByText('Submitted. You can still change it before reveal.')).toBeHidden();
        }
        expect(hostSockets).toBe(originalHostSocketCount);
        expect(replacementPlayerSockets).toBe(0);
    } finally {
        try {
            await page.evaluate(() => {
                const socket = (window as unknown as { qaOrganizer?: WebSocket }).qaOrganizer;
                if (socket?.readyState === WebSocket.OPEN) socket.send(JSON.stringify({ type: 'CANCEL_GAME' }));
            });
            await expect.poll(() => roomClosed).toBe(true);
        } finally {
            await closePlayers(players);
        }
    }
});
