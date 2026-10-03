import { StrictMode } from 'react';
import { act, fireEvent, render, screen } from '@testing-library/react';
import { saveOrganizerSession } from '../../utils/storage';
import OrganizerPage from '../OrganizerPage';

vi.mock('../../utils/sound', () => ({ soundManager: { play: vi.fn(), hapticsSelect: vi.fn(), stopAllMusic: vi.fn(), muted: false } }));
vi.mock('../../utils/analytics', () => ({ track: vi.fn() }));
vi.mock('../../components/organizer/GameSelectScreen', () => ({ default: () => <div>Game catalog</div> }));
vi.mock('../../components/organizer/LobbyScreen', () => ({ default: ({ roomCode, playerCount }: { roomCode: string; playerCount: number }) => <div>Lobby {roomCode}: {playerCount} connected</div> }));
vi.mock('../../components/Fireworks', () => ({ default: () => null }));
const hostAppReturn = vi.hoisted(() => vi.fn());
vi.mock('../../utils/hostAppReturn', () => ({ returnToHostApp: hostAppReturn }));

class MockWebSocket {
    static OPEN = 1;
    static instances: MockWebSocket[] = [];
    onopen: (() => void) | null = null;
    onclose: (() => void) | null = null;
    onmessage: ((event: { data: string }) => void) | null = null;
    readyState = 1;
    url: string;
    close = vi.fn();
    send = vi.fn();
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
    window.history.replaceState({}, '', '/organizer?embed=1');
    saveOrganizerSession({ roomCode: 'ROOM42', organizerToken: 'host-token', gameType: 'quiz', contentId: 'pack-id', hostAppReturnUrl: 'https://app.revelryapp.me/party/1/games' });
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
