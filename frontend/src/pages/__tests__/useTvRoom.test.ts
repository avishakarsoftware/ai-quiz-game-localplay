import { act, renderHook, waitFor } from '@testing-library/react';
import { useTvRoom } from '../useTvRoom';

/**
 * The TV hosting its own room (SPEC-TV-APP §7a).
 *
 * These lock down the two things that were previously broken on the TV surface:
 *   1. The join QR must carry a REAL room code — a bare `/join` is a dead end.
 *   2. `connectedPhones` must track live socket traffic, because it drives whether locked game
 *      tiles un-grey as guests arrive. It was previously `useState(0)` and never updated, so every
 *      phone-requiring game was permanently unavailable.
 */

class FakeSocket {
    static last: FakeSocket | null = null;
    sent: string[] = [];
    onopen: (() => void) | null = null;
    onmessage: ((e: { data: string }) => void) | null = null;
    onclose: (() => void) | null = null;
    closed = false;
    url: string;
    constructor(url: string) { this.url = url; FakeSocket.last = this; }
    send(payload: string) { this.sent.push(payload); }
    close() { this.closed = true; }
    emit(msg: unknown) { this.onmessage?.({ data: JSON.stringify(msg) }); }
}

function mockCreateRoom(body: unknown, ok = true, status = 200) {
    globalThis.fetch = vi.fn((url: string) => {
        if (String(url).includes('/room/create')) {
            return Promise.resolve({ ok, status, json: () => Promise.resolve(body) } as Response);
        }
        return Promise.reject(new Error(`unexpected fetch: ${url}`));
    }) as unknown as typeof fetch;
}

beforeEach(() => {
    FakeSocket.last = null;
    (globalThis as unknown as { WebSocket: unknown }).WebSocket = FakeSocket;
});

afterEach(() => vi.restoreAllMocks());

describe('useTvRoom', () => {
    it('creates a room and exposes a join URL containing the real code', async () => {
        mockCreateRoom({ room_code: 'HY2XKQ', organizer_token: 'tok' });
        const { result } = renderHook(() => useTvRoom());

        await act(async () => { await result.current.host('housie'); });

        expect(result.current.roomCode).toBe('HY2XKQ');
        // The bug this prevents: a bare `/join` sends the guest to a code prompt with no code.
        expect(result.current.joinUrl).toContain('/join/HY2XKQ');
        expect(result.current.status).toBe('lobby');
    });

    it('authenticates on the organizer socket with the token it was given', async () => {
        mockCreateRoom({ room_code: 'ABC123', organizer_token: 'secret-tok' });
        const { result } = renderHook(() => useTvRoom());
        await act(async () => { await result.current.host('bingo'); });

        const sock = FakeSocket.last!;
        expect(sock.url).toContain('/ws/ABC123/');
        expect(sock.url).toContain('organizer=true');
        act(() => { sock.onopen?.(); });
        expect(JSON.parse(sock.sent[0])).toEqual({ type: 'AUTH', token: 'secret-tok' });
    });

    it('tracks connected phones from socket traffic so tiles can un-grey live', async () => {
        mockCreateRoom({ room_code: 'ABC123', organizer_token: 'tok' });
        const { result } = renderHook(() => useTvRoom());
        await act(async () => { await result.current.host('impostor'); });

        expect(result.current.connectedPhones).toBe(0);
        act(() => {
            FakeSocket.last!.emit({ type: 'PLAYER_JOINED', player_count: 2, players: [{ nickname: 'Maya' }, { nickname: 'Leo' }] });
        });
        await waitFor(() => expect(result.current.connectedPhones).toBe(2));
        expect(result.current.players.map((p) => p.nickname)).toEqual(['Maya', 'Leo']);
    });

    it('reads the count off any roster-bearing message, not a list of known types', async () => {
        // Player counts arrive as PLAYER_JOINED / PLAYER_LEFT / PLAYER_DISCONNECTED / SYNC. Keying
        // off the payload rather than the type means a new message type can't freeze the unlock.
        mockCreateRoom({ room_code: 'ABC123', organizer_token: 'tok' });
        const { result } = renderHook(() => useTvRoom());
        await act(async () => { await result.current.host('quiz'); });

        act(() => { FakeSocket.last!.emit({ type: 'SOME_FUTURE_TYPE', players: [{ nickname: 'Ada' }] }); });
        await waitFor(() => expect(result.current.connectedPhones).toBe(1));
    });

    it('falls back to roster length when no player_count is present', async () => {
        mockCreateRoom({ room_code: 'ABC123', organizer_token: 'tok' });
        const { result } = renderHook(() => useTvRoom());
        await act(async () => { await result.current.host('quiz'); });

        act(() => { FakeSocket.last!.emit({ type: 'PLAYER_LEFT', players: [{ nickname: 'Ada' }, { nickname: 'Bo' }] }); });
        await waitFor(() => expect(result.current.connectedPhones).toBe(2));
    });

    it('surfaces the backend message when a room cannot be created', async () => {
        // Insufficient sparks is the likeliest failure and the host must be told specifically.
        mockCreateRoom({ detail: 'Not enough sparks to start a room.' }, false, 402);
        const { result } = renderHook(() => useTvRoom());
        await act(async () => { await result.current.host('housie'); });

        expect(result.current.status).toBe('error');
        expect(result.current.error).toMatch(/sparks/i);
        expect(result.current.roomCode).toBe('');
    });

    it('survives a malformed socket frame', async () => {
        mockCreateRoom({ room_code: 'ABC123', organizer_token: 'tok' });
        const { result } = renderHook(() => useTvRoom());
        await act(async () => { await result.current.host('quiz'); });

        act(() => { FakeSocket.last!.onmessage?.({ data: 'not json{' }); });
        expect(result.current.status).toBe('lobby');   // a bad frame must not kill the party
    });

    it('keeps the room code visible if the socket drops mid-party', async () => {
        mockCreateRoom({ room_code: 'KEEPME', organizer_token: 'tok' });
        const { result } = renderHook(() => useTvRoom());
        await act(async () => { await result.current.host('housie'); });

        act(() => { FakeSocket.last!.onclose?.(); });
        // Blanking the QR because a socket blipped is worse than a stale-but-correct code —
        // guests may still be mid-join.
        expect(result.current.roomCode).toBe('KEEPME');
        expect(result.current.error).toMatch(/reconnect/i);
    });

    it('leave clears the room and closes the socket', async () => {
        mockCreateRoom({ room_code: 'ABC123', organizer_token: 'tok' });
        const { result } = renderHook(() => useTvRoom());
        await act(async () => { await result.current.host('quiz'); });
        const sock = FakeSocket.last!;

        act(() => { result.current.leave(); });
        expect(sock.closed).toBe(true);
        expect(result.current.roomCode).toBe('');
        expect(result.current.status).toBe('idle');
    });
});
