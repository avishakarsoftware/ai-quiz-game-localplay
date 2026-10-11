import { StrictMode } from 'react';
import { act, fireEvent, render, screen } from '@testing-library/react';
import { getSavedOrganizerSession, saveOrganizerSession } from '../../utils/storage';
import OrganizerPage from '../OrganizerPage';

vi.mock('../../utils/sound', () => ({ soundManager: { play: vi.fn(), hapticsSelect: vi.fn(), stopAllMusic: vi.fn(), muted: false } }));
vi.mock('../../utils/analytics', () => ({ track: vi.fn() }));
vi.mock('../../components/organizer/GameSelectScreen', () => ({ default: () => <div>Game catalog</div> }));
vi.mock('../../components/organizer/LobbyScreen', () => ({ default: ({ roomCode, playerCount, connectionReady, onStartGame, onToggleLock }: { roomCode: string; playerCount: number; connectionReady: boolean; onStartGame: () => void; onToggleLock: () => void }) => <>
    <div>Lobby {roomCode}: {playerCount} connected</div>
    <button onClick={onStartGame} disabled={!connectionReady}>Start mocked game</button>
    <button onClick={onToggleLock}>Toggle mocked lock</button>
</> }));
vi.mock('../../components/Fireworks', () => ({ default: () => null }));
const hostAppReturn = vi.hoisted(() => vi.fn());
vi.mock('../../utils/hostAppReturn', () => ({ returnToHostApp: hostAppReturn }));

class MockWebSocket {
    static CONNECTING = 0;
    static OPEN = 1;
    static initialReadyState = MockWebSocket.OPEN;
    static instances: MockWebSocket[] = [];
    onopen: (() => void) | null = null;
    onclose: (() => void) | null = null;
    onmessage: ((event: { data: string }) => void) | null = null;
    readyState = MockWebSocket.initialReadyState;
    url: string;
    close = vi.fn();
    send = vi.fn((_body: string) => {
        if (this.readyState !== MockWebSocket.OPEN) throw new Error('WebSocket is not open');
    });
    constructor(url: string) { this.url = url; MockWebSocket.instances.push(this); }
    emit(msg: Record<string, unknown>) { this.onmessage?.({ data: JSON.stringify(msg) }); }
}

beforeEach(() => {
    vi.useFakeTimers();
    vi.stubGlobal('WebSocket', MockWebSocket);
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, json: async () => ({}) }));
    vi.spyOn(window, 'scrollTo').mockImplementation(() => {});
    window.history.replaceState({}, '', '/');
    MockWebSocket.instances = [];
    MockWebSocket.initialReadyState = MockWebSocket.OPEN;
    localStorage.clear();
    hostAppReturn.mockReset();
    saveOrganizerSession({ roomCode: 'ROOM42', organizerToken: 'host-token', gameType: 'quiz' });
});

afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
});

it('restores and reconnects a host room under the application StrictMode wrapper', () => {
    render(<StrictMode><OrganizerPage /></StrictMode>);
    const ws = MockWebSocket.instances.at(-1)!;
    act(() => { ws.onopen?.(); });
    expect(ws.send).toHaveBeenCalledWith(JSON.stringify({ type: 'AUTH', token: 'host-token' }));
    act(() => { ws.emit({ type: 'ORGANIZER_RECONNECTED', room_code: 'ROOM42', state: 'LOBBY', game_type: 'quiz', player_count: 2, players: [], time_limit: 20 }); });
    expect(screen.getByText('Lobby ROOM42: 2 connected')).toBeInTheDocument();
    const before = MockWebSocket.instances.length;
    act(() => { ws.onclose?.(); vi.advanceTimersByTime(2000); });
    expect(MockWebSocket.instances).toHaveLength(before + 1);
});

it('preserves the latest pass-and-play roster while connecting and authenticates before sending it', () => {
    MockWebSocket.initialReadyState = MockWebSocket.CONNECTING;
    saveOrganizerSession({ roomCode: 'ROOM42', organizerToken: 'host-token', gameType: 'impostor' });
    render(<OrganizerPage />);
    const first = MockWebSocket.instances.at(-1)!;
    for (const [index, name] of ['Alice', 'Bob', 'Cara'].entries()) {
        fireEvent.change(screen.getByTestId(`seat-input-${index}`), { target: { value: name } });
    }
    expect(first.send).not.toHaveBeenCalled();
    expect(screen.getByTestId('seat-start')).toBeDisabled();

    act(() => { first.readyState = MockWebSocket.OPEN; first.onopen?.(); });
    expect(first.send.mock.calls.map(([body]) => JSON.parse(body))).toEqual([
        { type: 'AUTH', token: 'host-token' },
        { type: 'IMPOSTOR_SET_SEATS', seat_names: ['Alice', 'Bob', 'Cara'], seat_emojis: ['🥭', '🐙', '🦊'] },
    ]);
    fireEvent.click(screen.getByTestId('seat-start'));
    expect(first.send.mock.calls.slice(-2).map(([body]) => JSON.parse(body).type)).toEqual(['IMPOSTOR_SET_SEATS', 'START_GAME']);
    expect(first.send.mock.calls.map(([body]) => JSON.parse(body).type)).not.toContain('NEXT_QUESTION');

    act(() => { first.onclose?.(); vi.advanceTimersByTime(2000); });
    const second = MockWebSocket.instances.at(-1)!;
    expect(screen.getByTestId('seat-start')).toBeDisabled();
    fireEvent.change(screen.getByTestId('seat-input-0'), { target: { value: 'Alicia' } });
    fireEvent.change(screen.getByTestId('seat-input-1'), { target: { value: 'Rob' } });
    expect(second.send).not.toHaveBeenCalled();
    act(() => { second.readyState = MockWebSocket.OPEN; second.onopen?.(); });
    expect(second.send.mock.calls.map(([body]) => JSON.parse(body))).toEqual([
        { type: 'AUTH', token: 'host-token' },
        { type: 'IMPOSTOR_SET_SEATS', seat_names: ['Alicia', 'Rob', 'Cara'], seat_emojis: ['🥭', '🐙', '🦊'] },
    ]);
    expect(screen.getByTestId('seat-start')).toBeEnabled();
});

it('blocks organizer game actions until the current socket opens', () => {
    MockWebSocket.initialReadyState = MockWebSocket.CONNECTING;
    render(<OrganizerPage />);
    const ws = MockWebSocket.instances.at(-1)!;
    expect(screen.getByRole('button', { name: 'Start mocked game' })).toBeDisabled();
    fireEvent.click(screen.getByRole('button', { name: 'Toggle mocked lock' }));
    expect(ws.send).not.toHaveBeenCalled();

    act(() => { ws.readyState = MockWebSocket.OPEN; ws.onopen?.(); });
    fireEvent.click(screen.getByRole('button', { name: 'Start mocked game' }));
    expect(ws.send.mock.calls.map(([body]) => JSON.parse(body).type)).toEqual(['AUTH', 'START_GAME', 'NEXT_QUESTION']);
});

it('ignores an old socket closure and terminal frame after replacing a host socket', () => {
    render(<OrganizerPage />);
    const first = MockWebSocket.instances.at(-1)!;
    act(() => { first.emit({ type: 'ORGANIZER_RECONNECTED', room_code: 'ROOM42', state: 'LOBBY', game_type: 'quiz', player_count: 2, players: [] }); });
    act(() => { first.onclose?.(); vi.advanceTimersByTime(2000); });
    const second = MockWebSocket.instances.at(-1)!;
    act(() => {
        first.emit({ type: 'ROOM_CLOSED' });
        first.onclose?.();
        second.emit({ type: 'ORGANIZER_RECONNECTED', room_code: 'ROOM42', state: 'LOBBY', game_type: 'quiz', player_count: 3, players: [] });
        vi.advanceTimersByTime(2500);
    });
    expect(screen.getByText('Lobby ROOM42: 3 connected')).toBeInTheDocument();
    expect(MockWebSocket.instances).toHaveLength(2);
});

it('a terminal host error closes the socket and cancels recovery', () => {
    render(<OrganizerPage />);
    const ws = MockWebSocket.instances.at(-1)!;
    act(() => { ws.emit({ type: 'ERROR', message: 'Invalid organizer token' }); });
    expect(ws.close).toHaveBeenCalled();
    expect(screen.getByText('Game catalog')).toBeInTheDocument();
    act(() => { ws.onclose?.(); vi.advanceTimersByTime(6000); });
    expect(MockWebSocket.instances).toHaveLength(1);
    expect(localStorage.getItem('localplay_organizer_session')).toBeNull();
});

it('managed podium starts another game through Revelry instead of resetting the completed room', () => {
    window.history.replaceState({}, '', '/organizer?embed=1&session_id=managed-1&party_id=party-1');
    saveOrganizerSession({ roomCode: 'ROOM42', organizerToken: 'host-token', gameType: 'quiz', contentId: 'pack-id', hostAppSessionId: 'managed-1', hostAppContainerId: 'party-1', hostAppReturnUrl: 'https://app.revelryapp.me/party/1/games' });
    render(<OrganizerPage />);
    const ws = MockWebSocket.instances.at(-1)!;
    act(() => {
        ws.emit({ type: 'ORGANIZER_RECONNECTED', room_code: 'ROOM42', state: 'PODIUM', game_type: 'quiz', leaderboard: [{ nickname: 'Alice', score: 321 }], players: [], player_count: 1 });
    });
    act(() => { vi.advanceTimersByTime(2600); });
    expect(screen.queryByRole('button', { name: 'Play Again' })).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: 'Start another Revelry game' }));
    expect(hostAppReturn).toHaveBeenCalledWith('https://app.revelryapp.me/party/1/games');
    expect(ws.send.mock.calls.map(([body]) => JSON.parse(body).type)).not.toContain('RESET_ROOM');
});

it('recovers an exact managed session after its launch token expires and retains return context', () => {
    window.history.replaceState({}, '', '/organizer?session_id=managed-1&party_id=party-1&launch_token=expired');
    saveOrganizerSession({ roomCode: 'ROOM42', organizerToken: 'runtime-token', gameType: 'quiz', hostAppSessionId: 'managed-1', hostAppContainerId: 'party-1', hostAppReturnUrl: 'https://app.revelryapp.me/party/party-1?tab=games' });
    render(<StrictMode><OrganizerPage /></StrictMode>);
    const ws = MockWebSocket.instances.at(-1)!;
    act(() => {
        ws.onopen?.();
        ws.emit({ type: 'ORGANIZER_RECONNECTED', room_code: 'ROOM42', state: 'LOBBY', game_type: 'quiz', player_count: 2, players: [] });
    });
    expect(ws.send).toHaveBeenCalledWith(JSON.stringify({ type: 'AUTH', token: 'runtime-token' }));
    expect(vi.mocked(fetch).mock.calls.some(([url]) => String(url).includes('launch-token/resolve'))).toBe(false);
    expect(window.location.search).not.toContain('launch_token');
    expect(window.location.search).toContain('session_id=managed-1');
    const count = MockWebSocket.instances.length;
    act(() => { ws.emit({ type: 'ROOM_CLOSED', message: 'Game cancelled' }); });
    expect(getSavedOrganizerSession()).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: 'OK' }));
    expect(hostAppReturn).toHaveBeenCalledWith('https://app.revelryapp.me/party/party-1?tab=games');
    act(() => { ws.onclose?.(); vi.advanceTimersByTime(6000); });
    expect(MockWebSocket.instances).toHaveLength(count);
});

it.each([
    { sessionId: 'another-session', partyId: 'party-1' },
    { sessionId: 'managed-1', partyId: 'another-party' },
])('does not restore a different managed session or party ($sessionId, $partyId)', ({ sessionId, partyId }) => {
    window.history.replaceState({}, '', `/organizer?session_id=${sessionId}&party_id=${partyId}`);
    saveOrganizerSession({ roomCode: 'ROOM42', organizerToken: 'runtime-token', hostAppSessionId: 'managed-1', hostAppContainerId: 'party-1' });
    render(<OrganizerPage />);
    expect(MockWebSocket.instances).toHaveLength(0);
    expect(screen.getByText('Open From Revelry')).toBeInTheDocument();
});

it('exchanges a new organizer launch once and persists the authenticated session binding', async () => {
    window.history.replaceState({}, '', '/organizer?session_id=managed-new&launch_token=fresh');
    vi.mocked(fetch).mockImplementation(async (url) => String(url).includes('launch-token/resolve')
        ? { ok: true, json: async () => ({ session_id: 'managed-new', external_container_id: 'party-new', room_code: 'NEW123', organizer_token: 'new-runtime-token', return_url: 'https://app.revelryapp.me/party/party-new?tab=games' }) } as Response
        : { ok: false, json: async () => ({}) } as Response);
    await act(async () => { render(<OrganizerPage />); });
    expect(getSavedOrganizerSession()).toMatchObject({ hostAppSessionId: 'managed-new', hostAppContainerId: 'party-new', organizerToken: 'new-runtime-token' });
    expect(window.location.search).toBe('?session_id=managed-new&party_id=party-new');
    expect(MockWebSocket.instances.at(-1)?.url).toContain('/ws/NEW123/');
});

it.each([
    { gameType: 'quiz', contentId: 'pack-id', config: undefined },
    { gameType: 'would_you_rather', contentId: '', config: undefined },
    { gameType: 'odd_question', contentId: '', config: undefined },
    { gameType: 'musical_chairs', contentId: '', config: { gameplay_mode: 'physical', music_mode: 'external' } },
    { gameType: 'party_quests', contentId: '', config: { duration_minutes: 15, confirmation_mode: 'honor' } },
])('standalone $gameType podium reuses the finished room for Play Again', ({ gameType, contentId, config }) => {
    saveOrganizerSession({ roomCode: 'ROOM42', organizerToken: 'host-token', gameType, contentId });
    render(<OrganizerPage />);
    const ws = MockWebSocket.instances.at(-1)!;
    act(() => {
        ws.emit({ type: 'ORGANIZER_RECONNECTED', room_code: 'ROOM42', state: 'PODIUM', game_type: gameType, quiz: config, leaderboard: [{ nickname: 'Alice', score: 321 }], players: [], player_count: 1 });
    });
    act(() => { vi.advanceTimersByTime(2600); });
    fireEvent.click(screen.getByRole('button', { name: 'Play Again' }));
    const reset = ws.send.mock.calls.map(([body]) => JSON.parse(body)).find((body) => body.type === 'RESET_ROOM');
    expect(reset).toMatchObject({ type: 'RESET_ROOM', content_id: contentId, game_type: gameType });
    if (config) expect(reset.runtime_config).toMatchObject(config);
    expect(hostAppReturn).not.toHaveBeenCalled();
});

it.each([
    { gameType: 'would_you_rather', config: undefined },
    { gameType: 'musical_chairs', config: { gameplay_mode: 'physical', music_mode: 'external' } },
    { gameType: 'party_quests', config: { duration_minutes: 15, confirmation_mode: 'honor' } },
])('restores empty-lobby $gameType settings before replaying', ({ gameType, config }) => {
    saveOrganizerSession({ roomCode: 'ROOM42', organizerToken: 'host-token', gameType });
    render(<OrganizerPage />);
    const ws = MockWebSocket.instances.at(-1)!;
    act(() => {
        ws.emit({ type: 'ROOM_CREATED', room_code: 'ROOM42', game_type: gameType, time_limit: 45, quiz: config, players: [], player_count: 0 });
    });
    act(() => {
        ws.emit({ type: 'PODIUM', leaderboard: [{ nickname: 'Alice', score: 321 }] });
    });
    act(() => { vi.advanceTimersByTime(2600); });
    fireEvent.click(screen.getByRole('button', { name: 'Play Again' }));
    const reset = ws.send.mock.calls.map(([body]) => JSON.parse(body)).find((body) => body.type === 'RESET_ROOM');
    expect(reset).toMatchObject({ type: 'RESET_ROOM', game_type: gameType, content_id: '', time_limit: 45 });
    if (config) expect(reset.runtime_config).toMatchObject(config);
});
