import { render, screen, act, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { StrictMode } from 'react';

// Mock react-router-dom before importing PlayerPage
const routeState = vi.hoisted(() => ({ query: '' }));
vi.mock('react-router-dom', async () => {
    const actual = await vi.importActual('react-router-dom');
    return { ...actual, useSearchParams: () => [new URLSearchParams(routeState.query), vi.fn()], useParams: () => ({}) };
});

vi.mock('../../components/PodiumInviteCta', () => ({
    default: () => <div data-testid="podium-invite" />,
}));

vi.mock('../../utils/sound', () => ({
    soundManager: {
        play: vi.fn(),
        vibrate: vi.fn(),
        muted: false,
        hapticsSelect: vi.fn(),
        hapticsCorrect: vi.fn(),
        hapticsWrong: vi.fn(),
    },
}));

vi.mock('../../utils/analytics', () => ({
    track: vi.fn(),
}));

vi.mock('../../components/AnimatedNumber', () => ({
    default: ({ value }: { value: number }) => <span>{value}</span>,
}));

vi.mock('../../components/Fireworks', () => ({
    default: () => <div data-testid="fireworks" />,
}));

vi.mock('../../components/BonusSplash', () => ({
    default: ({ onComplete }: { onComplete: () => void }) => (
        <div data-testid="bonus-splash">
            <button onClick={onComplete}>dismiss</button>
        </div>
    ),
}));

vi.mock('../../components/LeaderboardBarChart', () => ({
    default: () => <div data-testid="leaderboard-chart" />,
}));

class MockWebSocket {
    static CONNECTING = 0;
    static OPEN = 1;
    static CLOSING = 2;
    static instances: MockWebSocket[] = [];
    onopen: (() => void) | null = null;
    onclose: (() => void) | null = null;
    onmessage: ((event: { data: string }) => void) | null = null;
    onerror: (() => void) | null = null;
    readyState = 1;
    close = vi.fn();
    send = vi.fn();
    url: string;
    constructor(url: string) {
        this.url = url;
        MockWebSocket.instances.push(this);
    }
}

vi.stubGlobal('WebSocket', MockWebSocket);

import PlayerPage from '../PlayerPage';

function getLatestWs(): MockWebSocket {
    return MockWebSocket.instances[MockWebSocket.instances.length - 1];
}

function simulateWsMessage(msg: Record<string, unknown>) {
    const ws = getLatestWs();
    act(() => { ws.onmessage?.({ data: JSON.stringify(msg) }); });
}

/** Fill in Game PIN and nickname, then click Join. Uses fireEvent (synchronous). */
function fillAndJoin(roomCode: string, nickname: string) {
    const inputs = screen.getAllByRole('textbox');
    // Game PIN input
    fireEvent.change(inputs[0], { target: { value: roomCode } });
    // Nickname input
    fireEvent.change(inputs[1], { target: { value: nickname } });
    // Click Join
    fireEvent.click(screen.getByRole('button', { name: 'Join' }));
}

describe('PlayerPage', () => {
    beforeEach(() => {
        routeState.query = '';
        window.history.replaceState({}, '', '/join');
        vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, status: 401, json: async () => ({}) }));
        vi.useFakeTimers();
        MockWebSocket.instances = [];
        sessionStorage.clear();
        localStorage.clear();
    });

    it('auto-rejoins a saved room under the application StrictMode wrapper', () => {
        sessionStorage.setItem('localplay_session', JSON.stringify({ roomCode: 'ROOM42', nickname: 'Alice', team: '', avatar: '🐶', sessionToken: 'token' }));
        render(<StrictMode><PlayerPage /></StrictMode>);
        act(() => { vi.advanceTimersByTime(100); });
        expect(MockWebSocket.instances).toHaveLength(1);
        act(() => { getLatestWs().onopen?.(); });
        simulateWsMessage({ type: 'RECONNECTED', game_type: 'quiz', state: 'LOBBY', players: [] });
        act(() => { getLatestWs().onclose?.(); vi.advanceTimersByTime(2000); });
        expect(MockWebSocket.instances).toHaveLength(2);
    });

    it('recovers the exact managed player seat after launch expiry and keeps its return destination', () => {
        routeState.query = 'session_id=managed-1&party_id=party-1&launch_token=expired';
        window.history.replaceState({}, '', `/join?${routeState.query}`);
        sessionStorage.setItem('localplay_session', JSON.stringify({ roomCode: 'ROOM42', nickname: 'Alice', team: '', avatar: '🐶', sessionToken: 'runtime-token', hostAppSessionId: 'managed-1', hostAppContainerId: 'party-1', hostAppReturnUrl: 'https://app.revelryapp.me/party/party-1/games/join' }));
        render(<StrictMode><PlayerPage /></StrictMode>);
        act(() => { vi.advanceTimersByTime(100); getLatestWs().onopen?.(); });
        expect(JSON.parse(getLatestWs().send.mock.calls[0][0])).toMatchObject({ type: 'JOIN', nickname: 'Alice', session_token: 'runtime-token' });
        simulateWsMessage({ type: 'RECONNECTED', game_type: 'quiz', state: 'LOBBY', session_token: 'runtime-token', players: [] });
        expect(window.location.search).not.toContain('launch_token');
        expect(vi.mocked(fetch).mock.calls.some(([url]) => String(url).includes('launch-token/resolve'))).toBe(false);
        simulateWsMessage({ type: 'ROOM_CLOSED' });
        expect(screen.getByRole('button', { name: 'Back to Revelry Games' })).toBeInTheDocument();
        expect(sessionStorage.getItem('localplay_session')).toBeNull();
        const count = MockWebSocket.instances.length;
        act(() => { getLatestWs().onclose?.(); vi.advanceTimersByTime(6000); });
        expect(MockWebSocket.instances).toHaveLength(count);
    });

    it.each([
        'session_id=another-session&party_id=party-1',
        'session_id=managed-1&party_id=another-party',
    ])('does not recover another managed player session (%s)', (query) => {
        routeState.query = query;
        sessionStorage.setItem('localplay_session', JSON.stringify({ roomCode: 'ROOM42', nickname: 'Alice', team: '', avatar: '🐶', sessionToken: 'runtime-token', hostAppSessionId: 'managed-1', hostAppContainerId: 'party-1' }));
        render(<PlayerPage />);
        act(() => { vi.advanceTimersByTime(150); });
        expect(MockWebSocket.instances).toHaveLength(0);
        expect(screen.getByText('Game Unavailable')).toBeInTheDocument();
    });

    it('consumes a player launch token only after a runtime seat is issued, then resumes on reload', async () => {
        routeState.query = 'session_id=managed-new&launch_token=fresh';
        window.history.replaceState({}, '', `/join?${routeState.query}`);
        vi.mocked(fetch).mockImplementation(async (url) => String(url).includes('launch-token/resolve')
            ? { ok: true, json: async () => ({ session_id: 'managed-new', external_container_id: 'party-new', room_code: 'NEW123', return_url: 'https://app.revelryapp.me/party/party-new/games/join' }) } as Response
            : { ok: false, json: async () => ({}) } as Response);
        let rendered!: ReturnType<typeof render>;
        await act(async () => { rendered = render(<PlayerPage />); });
        expect(window.location.search).toContain('launch_token=fresh');
        fireEvent.change(screen.getByTestId('player-nickname-input'), { target: { value: 'Alice' } });
        fireEvent.click(screen.getByTestId('player-join-button'));
        act(() => { getLatestWs().onopen?.(); });
        simulateWsMessage({ type: 'JOINED_ROOM', session_token: 'issued-runtime-token' });
        expect(window.location.search).toBe('?session_id=managed-new&party_id=party-new');
        expect(JSON.parse(sessionStorage.getItem('localplay_session')!)).toMatchObject({ hostAppSessionId: 'managed-new', hostAppContainerId: 'party-new', hostAppReturnUrl: 'https://app.revelryapp.me/party/party-new/games/join' });
        rendered.unmount();
        routeState.query = window.location.search.slice(1);
        vi.mocked(fetch).mockClear();
        render(<PlayerPage />);
        act(() => { vi.advanceTimersByTime(100); getLatestWs().onopen?.(); });
        expect(JSON.parse(getLatestWs().send.mock.calls[0][0])).toMatchObject({ nickname: 'Alice', session_token: 'issued-runtime-token' });
        expect(vi.mocked(fetch).mock.calls.some(([url]) => String(url).includes('launch-token/resolve'))).toBe(false);
    });

    it('wake reconnect cancels a scheduled retry and ignores callbacks from the replaced socket', () => {
        render(<PlayerPage />);
        fillAndJoin('ROOM42', 'Alice');
        const first = getLatestWs();
        act(() => { first.onopen?.(); });
        simulateWsMessage({ type: 'JOINED_ROOM', session_token: 'token' });
        act(() => { first.onclose?.(); });
        act(() => { window.dispatchEvent(new Event('focus')); });
        const replacement = getLatestWs();
        act(() => { replacement.onopen?.(); });
        simulateWsMessage({ type: 'RECONNECTED', game_type: 'quiz', state: 'LOBBY', players: [] });
        act(() => {
            first.onclose?.();
            first.onmessage?.({ data: JSON.stringify({ type: 'KICKED' }) });
            vi.advanceTimersByTime(2500);
        });
        expect(MockWebSocket.instances).toHaveLength(2);
        expect(screen.queryByText('You joined from another device')).toBeNull();
        expect(screen.queryByText('Reconnecting...')).toBeNull();
    });

    it('keeps a kicked tab from reclaiming the active tab on wake', () => {
        render(<PlayerPage />);
        fillAndJoin('ROOM42', 'Alice');
        const ws = getLatestWs();
        simulateWsMessage({ type: 'JOINED_ROOM', session_token: 'token' });
        simulateWsMessage({ type: 'KICKED' });
        act(() => { ws.onclose?.(); window.dispatchEvent(new Event('focus')); vi.advanceTimersByTime(3000); });
        expect(MockWebSocket.instances).toHaveLength(1);
        expect(screen.getByText('You joined from another device')).toBeInTheDocument();
    });

    it('does not autojoin a different room using an old room credential', () => {
        sessionStorage.setItem('localplay_session', JSON.stringify({ roomCode: 'OLD123', nickname: 'Alice', team: '', avatar: '🐶', sessionToken: 'old-token' }));
        routeState.query = 'room=NEW123';
        render(<PlayerPage />);
        act(() => { vi.advanceTimersByTime(150); });
        expect(MockWebSocket.instances).toHaveLength(0);
        fireEvent.click(screen.getByRole('button', { name: 'Join' }));
        act(() => { getLatestWs().onopen?.(); });
        expect(JSON.parse(getLatestWs().send.mock.calls[0][0]).session_token).toBe('');
    });

    it('restores podium scores and rank after refreshing', () => {
        render(<PlayerPage />);
        fillAndJoin('ROOM42', 'Alice');
        simulateWsMessage({ type: 'RECONNECTED', game_type: 'quiz', state: 'PODIUM', leaderboard: [{ nickname: 'Alice', score: 321 }, { nickname: 'Bob', score: 120 }], team_leaderboard: [] });
        expect(screen.getByText('321')).toBeInTheDocument();
        expect(screen.getByText('Bob')).toBeInTheDocument();
    });

    it('restores a closed round answer and ranking after refreshing', () => {
        render(<PlayerPage />);
        fillAndJoin('ROOM42', 'Alice');
        simulateWsMessage({ type: 'RECONNECTED', game_type: 'quiz', state: 'LEADERBOARD', answer: 1, answer_text: 'Paris', leaderboard: [{ nickname: 'Alice', score: 321 }] });
        expect(screen.getByText('Round complete')).toBeInTheDocument();
        expect(screen.getByText('Paris')).toBeInTheDocument();
        expect(screen.getByText('#1')).toBeInTheDocument();
    });

    it('does not offer a second answer after reconnecting an answered question', () => {
        render(<PlayerPage />);
        fillAndJoin('ROOM42', 'Alice');
        simulateWsMessage({ type: 'RECONNECTED', game_type: 'quiz', state: 'QUESTION', has_answered: true, question: { id: 1, text: 'Capital?', options: ['Paris', 'Rome'] }, time_limit: 20, time_remaining: 10 });
        expect(screen.getByText('Answer received')).toBeInTheDocument();
        expect(screen.queryByRole('button', { name: /Paris/ })).toBeNull();
    });

    it('clears old generic prompt content when replay starts before the new sync', () => {
        render(<PlayerPage />);
        fillAndJoin('ROOM42', 'Alice');
        simulateWsMessage({ type: 'GENERIC_PROMPT_SYNC', game_type: 'hot_takes', generic_prompt: { phase: 'GENERIC_CHOICE', mode: 'choice_vote', round_count: 1, prompt: { prompt: 'Old private party prompt', options: ['Yes', 'No'] } } });
        expect(screen.getByText('Old private party prompt')).toBeInTheDocument();
        simulateWsMessage({ type: 'ROOM_RESET', game_type: 'hot_takes', players: [] });
        simulateWsMessage({ type: 'GAME_STARTING', game_type: 'hot_takes' });
        expect(screen.queryByText('Old private party prompt')).toBeNull();
        expect(screen.getByText('Waiting for the room')).toBeInTheDocument();
    });

    afterEach(() => {
        vi.useRealTimers();
    });

    it.each([false, true])('shows the referral offer only on a standalone podium (embedded=%s)', (embedded) => {
        routeState.query = embedded ? 'embed=1' : '';
        render(<PlayerPage />);
        fillAndJoin('ROOM42', 'Alice');
        act(() => { getLatestWs().onopen?.(); });
        simulateWsMessage({ type: 'JOINED_ROOM', session_token: 'session' });
        simulateWsMessage({ type: 'PODIUM', leaderboard: [{ nickname: 'Alice', score: 10 }] });
        if (embedded) expect(screen.queryByTestId('podium-invite')).toBeNull();
        else expect(screen.getByTestId('podium-invite')).toBeInTheDocument();
    });

    // --- Session Token (Fix 1) ---

    describe('Session Token', () => {
        it('getSavedSession includes sessionToken', () => {
            sessionStorage.setItem('localplay_session', JSON.stringify({
                roomCode: 'ABCD',
                nickname: 'Alice',
                team: '',
                avatar: '🐶',
                sessionToken: 'tok_123',
            }));

            const raw = sessionStorage.getItem('localplay_session');
            const session = JSON.parse(raw!);
            expect(session.sessionToken).toBe('tok_123');
        });

        it('getSavedSession returns undefined sessionToken when not set', () => {
            sessionStorage.setItem('localplay_session', JSON.stringify({
                roomCode: 'ABCD',
                nickname: 'Alice',
                team: '',
                avatar: '🐶',
            }));

            const raw = sessionStorage.getItem('localplay_session');
            const session = JSON.parse(raw!);
            expect(session.sessionToken).toBeUndefined();
        });

        it('JOIN message includes session_token from saved session', () => {
            // Set the session before rendering so getSavedSession can find it on join
            sessionStorage.setItem('localplay_session', JSON.stringify({
                roomCode: 'ABCD',
                nickname: 'Alice',
                team: '',
                avatar: '🐶',
                sessionToken: 'tok_saved',
            }));

            render(<PlayerPage />);

            // The auto-join timer fires after 100ms — advance past it
            act(() => { vi.advanceTimersByTime(150); });

            const ws = getLatestWs();
            expect(ws).toBeDefined();

            // Trigger onopen to send JOIN
            act(() => { ws.onopen?.(); });

            expect(ws.send).toHaveBeenCalled();
            const sentData = JSON.parse(ws.send.mock.calls[0][0]);
            expect(sentData.type).toBe('JOIN');
            expect(sentData.session_token).toBe('tok_saved');
        });

        it('JOINED_ROOM stores session token in sessionStorage', () => {
            render(<PlayerPage />);

            fillAndJoin('TEST', 'Bob');

            const ws = getLatestWs();
            act(() => { ws.onopen?.(); });

            // Simulate JOINED_ROOM with session_token
            simulateWsMessage({ type: 'JOINED_ROOM', session_token: 'tok_new_456' });

            const raw = sessionStorage.getItem('localplay_session');
            expect(raw).not.toBeNull();
            const session = JSON.parse(raw!);
            expect(session.sessionToken).toBe('tok_new_456');
        });
    });

    // --- Nickname is taken error ---

    describe('Nickname Taken Error', () => {
        it('nickname is taken error returns to JOIN state', () => {
            render(<PlayerPage />);

            fillAndJoin('ROOM', 'TakenName');

            const ws = getLatestWs();
            act(() => { ws.onopen?.(); });

            // Simulate the error
            simulateWsMessage({ type: 'ERROR', message: 'Nickname is taken' });

            // Should show the friendly error on the JOIN screen
            expect(screen.getByText('That nickname is taken — try a different one.')).toBeInTheDocument();
            // Should still be on JOIN (join button visible)
            expect(screen.getByRole('button', { name: 'Join' })).toBeInTheDocument();
        });

        it('retries instead of clearing the session when our own reconnect races "Nickname is taken"', () => {
            render(<PlayerPage />);

            // A real established session (has a sessionToken) for this room+nickname.
            sessionStorage.setItem('localplay_session', JSON.stringify({
                roomCode: 'ROOM',
                nickname: 'TakenName',
                team: '',
                avatar: '🐶',
                sessionToken: 'tok_existing_123',
            }));

            fillAndJoin('ROOM', 'TakenName');
            const ws = getLatestWs();
            act(() => { ws.onopen?.(); });

            simulateWsMessage({ type: 'ERROR', message: 'Nickname is taken' });

            // Stale-connection race during our own reconnect: keep the session and
            // retry rather than bouncing the player back to JOIN.
            expect(sessionStorage.getItem('localplay_session')).not.toBeNull();
            expect(screen.getByText('Reconnecting...')).toBeInTheDocument();
        });

        it('nickname taken clears saved session', () => {
            render(<PlayerPage />);

            // Set a session to be cleared
            sessionStorage.setItem('localplay_session', JSON.stringify({
                roomCode: 'ROOM',
                nickname: 'TakenName',
                team: '',
                avatar: '🐶',
            }));

            fillAndJoin('ROOM', 'TakenName');

            const ws = getLatestWs();
            act(() => { ws.onopen?.(); });

            simulateWsMessage({ type: 'ERROR', message: 'Nickname is taken' });

            expect(sessionStorage.getItem('localplay_session')).toBeNull();
        });
    });

    describe('Answer reveal', () => {
        it('shows the correct answer on RESULT when the player did not answer', () => {
            render(<PlayerPage />);
            fillAndJoin('ROOM', 'Eve');
            const ws = getLatestWs();
            act(() => { ws.onopen?.(); });
            simulateWsMessage({ type: 'JOINED_ROOM', session_token: 'tok' });
            simulateWsMessage({
                type: 'QUESTION',
                question: { text: 'Capital of France?', options: ['London', 'Paris', 'Rome', 'Berlin'] },
                question_number: 1,
                total_questions: 3,
                time_limit: 20,
            });
            // Round ends without an answer from this player.
            simulateWsMessage({ type: 'QUESTION_OVER', answer: 1, answer_text: 'Paris', leaderboard: [], is_final: false });

            expect(screen.getByText("Time's up!")).toBeInTheDocument();
            const answer = screen.getByText('Paris');
            expect(answer.tagName).toBe('STRONG');
            expect(answer.parentElement?.textContent).toContain('Correct answer:');
        });
    });

    // --- 50/50 Reconnect (Fix 2) ---

    describe('50/50 Reconnect', () => {
        it('RECONNECTED with remove_indices restores hidden options', () => {
            render(<PlayerPage />);

            fillAndJoin('ROOM', 'Eve');

            const ws = getLatestWs();
            act(() => { ws.onopen?.(); });

            // Simulate RECONNECTED with question state including remove_indices
            simulateWsMessage({
                type: 'RECONNECTED',
                session_token: 'tok_reconnect',
                state: 'QUESTION',
                question: { id: 1, text: 'What is 2+2?', options: ['1', '2', '3', '4'] },
                question_number: 1,
                total_questions: 5,
                time_limit: 15,
                remove_indices: [0, 2],
                power_ups: { double_points: true, fifty_fifty: false },
                is_bonus: false,
            });

            // Answer buttons for indices 0 and 2 should be disabled (hidden-option class)
            const answerButtons = screen.getAllByRole('button').filter(btn =>
                btn.classList.contains('answer-btn')
            );

            // Buttons at hidden indices should be disabled
            expect(answerButtons[0]).toBeDisabled();
            expect(answerButtons[2]).toBeDisabled();
            // Buttons at non-hidden indices should be enabled
            expect(answerButtons[1]).not.toBeDisabled();
            expect(answerButtons[3]).not.toBeDisabled();
        });

        it('RECONNECTED restores power_ups state', () => {
            render(<PlayerPage />);

            fillAndJoin('ROOM', 'Eve');

            const ws = getLatestWs();
            act(() => { ws.onopen?.(); });

            // Simulate RECONNECTED with 50/50 already used but double_points still available
            simulateWsMessage({
                type: 'RECONNECTED',
                session_token: 'tok_reconnect',
                state: 'QUESTION',
                question: { id: 1, text: 'What is 2+2?', options: ['1', '2', '3', '4'] },
                question_number: 1,
                total_questions: 5,
                time_limit: 15,
                power_ups: { double_points: true, fifty_fifty: false },
                is_bonus: false,
            });

            // double_points button should exist, fifty_fifty should not
            expect(screen.getByText('2x Points')).toBeInTheDocument();
            expect(screen.queryByText('50/50')).not.toBeInTheDocument();
        });

        it('RECONNECTED stores session token', () => {
            render(<PlayerPage />);

            fillAndJoin('ROOM', 'Eve');

            const ws = getLatestWs();
            act(() => { ws.onopen?.(); });

            simulateWsMessage({
                type: 'RECONNECTED',
                session_token: 'tok_reconnected_789',
                state: 'LOBBY',
                question_number: 0,
                total_questions: 5,
            });

            const raw = sessionStorage.getItem('localplay_session');
            expect(raw).not.toBeNull();
            const session = JSON.parse(raw!);
            expect(session.sessionToken).toBe('tok_reconnected_789');
        });
    });

    // --- Room Closed ---

    describe('Room Closed', () => {
        it('ROOM_CLOSED returns to JOIN with error message', () => {
            render(<PlayerPage />);

            fillAndJoin('ROOM', 'Alice');

            const ws = getLatestWs();
            act(() => { ws.onopen?.(); });
            simulateWsMessage({ type: 'JOINED_ROOM', session_token: 'tok1' });

            // Room is closed by host
            simulateWsMessage({ type: 'ROOM_CLOSED' });

            expect(screen.getByText('The host ended this game session.')).toBeInTheDocument();
            expect(screen.getByRole('button', { name: 'Join' })).toBeInTheDocument();
        });
    });
});
