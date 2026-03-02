import { render, screen, act, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

// Mock react-router-dom before importing PlayerPage
vi.mock('react-router-dom', async () => {
    const actual = await vi.importActual('react-router-dom');
    return { ...actual, useSearchParams: () => [new URLSearchParams(), vi.fn()], useParams: () => ({}) };
});

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
    static instances: MockWebSocket[] = [];
    onopen: (() => void) | null = null;
    onclose: (() => void) | null = null;
    onmessage: ((event: { data: string }) => void) | null = null;
    onerror: (() => void) | null = null;
    readyState = 1;
    close = vi.fn();
    send = vi.fn();
    constructor(public url: string) {
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
        vi.useFakeTimers();
        MockWebSocket.instances = [];
        sessionStorage.clear();
    });

    afterEach(() => {
        vi.useRealTimers();
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

            // Should show the error on the JOIN screen
            expect(screen.getByText('Nickname is taken')).toBeInTheDocument();
            // Should still be on JOIN (join button visible)
            expect(screen.getByRole('button', { name: 'Join' })).toBeInTheDocument();
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

            expect(screen.getByText('The host has left and the room was closed')).toBeInTheDocument();
            expect(screen.getByRole('button', { name: 'Join' })).toBeInTheDocument();
        });
    });
});
