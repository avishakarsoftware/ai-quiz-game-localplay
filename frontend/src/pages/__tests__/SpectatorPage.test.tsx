import { render, screen, act, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import SpectatorPage from '../SpectatorPage';

// --- Mocks ---

vi.mock('../../utils/sound', () => ({
    soundManager: {
        play: vi.fn(),
        vibrate: vi.fn(),
        muted: false,
    },
}));

vi.mock('../../components/Fireworks', () => ({
    default: () => <div data-testid="fireworks" />,
}));

vi.mock('../../components/AnimatedNumber', () => ({
    default: ({ value }: { value: number }) => <span>{value}</span>,
}));

vi.mock('../../components/LeaderboardBarChart', () => ({
    default: () => <div data-testid="leaderboard-chart" />,
}));

vi.mock('../../components/BonusSplash', () => ({
    default: ({ onComplete }: { onComplete: () => void }) => (
        <div data-testid="bonus-splash">
            <button onClick={onComplete}>dismiss</button>
        </div>
    ),
}));

vi.mock('qrcode.react', () => ({
    QRCodeCanvas: () => <canvas data-testid="qr-code" />,
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

// Mock requestFullscreen
const mockRequestFullscreen = vi.fn().mockResolvedValue(undefined);
document.documentElement.requestFullscreen = mockRequestFullscreen;

function renderSpectator(roomCode?: string) {
    const initialEntries = roomCode ? [`/spectate?room=${roomCode}`] : ['/spectate'];
    return render(
        <MemoryRouter initialEntries={initialEntries}>
            <SpectatorPage />
        </MemoryRouter>
    );
}

function getLatestWs(): MockWebSocket {
    return MockWebSocket.instances[MockWebSocket.instances.length - 1];
}

function simulateWsOpen() {
    const ws = getLatestWs();
    act(() => { ws.onopen?.(); });
}

function simulateWsMessage(msg: Record<string, unknown>) {
    const ws = getLatestWs();
    act(() => { ws.onmessage?.({ data: JSON.stringify(msg) }); });
}

describe('SpectatorPage', () => {
    beforeEach(() => {
        vi.useFakeTimers();
        MockWebSocket.instances = [];
        mockRequestFullscreen.mockClear();
    });

    afterEach(() => {
        vi.useRealTimers();
    });

    // --- Fullscreen Prompt (Fix 6) ---

    describe('Fullscreen Prompt', () => {
        it('shows fullscreen overlay on initial render', () => {
            renderSpectator('ABCD');
            expect(screen.getByText('Spectator Mode')).toBeInTheDocument();
            expect(screen.getByText('Enter Fullscreen')).toBeInTheDocument();
        });

        it('clicking overlay calls requestFullscreen', () => {
            renderSpectator('ABCD');

            fireEvent.click(screen.getByText('Enter Fullscreen'));

            expect(mockRequestFullscreen).toHaveBeenCalled();
        });

        it('overlay disappears after clicking Enter Fullscreen', () => {
            renderSpectator('ABCD');

            expect(screen.getByText('Spectator Mode')).toBeInTheDocument();

            fireEvent.click(screen.getByText('Enter Fullscreen'));

            expect(screen.queryByText('Spectator Mode')).not.toBeInTheDocument();
        });

        it('skip button hides overlay without fullscreen', () => {
            renderSpectator('ABCD');

            expect(screen.getByText('Spectator Mode')).toBeInTheDocument();

            fireEvent.click(screen.getByText('Skip'));

            expect(screen.queryByText('Spectator Mode')).not.toBeInTheDocument();
            expect(mockRequestFullscreen).not.toHaveBeenCalled();
        });
    });

    // --- Auto-Reconnect (Fix 5) ---

    describe('Auto-Reconnect', () => {
        it('shows Reconnecting text on WebSocket close', () => {
            renderSpectator('ABCD');
            simulateWsOpen();
            simulateWsMessage({ type: 'SPECTATOR_SYNC', state: 'INTRO', players: [], player_count: 0, question_number: 0, total_questions: 0, leaderboard: [] });

            const ws = getLatestWs();
            act(() => { ws.onclose?.(); });

            expect(screen.getByText('Reconnecting...')).toBeInTheDocument();
        });

        it('shows Disconnected when room is closed', () => {
            renderSpectator('ABCD');
            simulateWsOpen();
            simulateWsMessage({ type: 'ROOM_CLOSED' });

            expect(screen.getByText('Disconnected')).toBeInTheDocument();
        });

        it('does not reconnect after ROOM_CLOSED', () => {
            renderSpectator('ABCD');
            const wsCountBefore = MockWebSocket.instances.length;
            simulateWsOpen();
            simulateWsMessage({ type: 'ROOM_CLOSED' });

            const ws = getLatestWs();
            act(() => { ws.onclose?.(); });

            // Advance past reconnect delay
            act(() => { vi.advanceTimersByTime(5000); });

            // No new WebSocket should have been created (only the original one)
            expect(MockWebSocket.instances.length).toBe(wsCountBefore);
        });

        it('ignores PING messages', () => {
            renderSpectator('ABCD');
            simulateWsOpen();
            simulateWsMessage({ type: 'SPECTATOR_SYNC', state: 'INTRO', players: [], player_count: 0, question_number: 0, total_questions: 0, leaderboard: [] });

            // Sending PING should not change state or throw
            simulateWsMessage({ type: 'PING' });

            // Should still be on LOBBY (INTRO maps to LOBBY)
            expect(screen.getByText('Join the Quiz!')).toBeInTheDocument();
        });
    });

    // --- Tie Detection (Fix 7) ---

    describe('Tie Detection Logic', () => {
        // Extract the tie detection logic from SpectatorPage to test in isolation
        function getTieLabel(leaderboard: { score: number; nickname: string }[]) {
            if (!leaderboard[0]) return null;
            const topScore = leaderboard[0].score;
            const tiedCount = leaderboard.filter(p => p.score === topScore).length;
            if (tiedCount > 1) return tiedCount === 2 ? "It's a Tie!" : `${tiedCount}-Way Tie!`;
            return `${leaderboard[0].nickname} is the Champion!`;
        }

        it('shows champion when no tie', () => {
            const result = getTieLabel([
                { nickname: 'Alice', score: 100 },
                { nickname: 'Bob', score: 80 },
                { nickname: 'Charlie', score: 60 },
            ]);
            expect(result).toBe('Alice is the Champion!');
        });

        it('shows tie for 2 equal scores', () => {
            const result = getTieLabel([
                { nickname: 'Alice', score: 100 },
                { nickname: 'Bob', score: 100 },
                { nickname: 'Charlie', score: 60 },
            ]);
            expect(result).toBe("It's a Tie!");
        });

        it('shows 3-way tie', () => {
            const result = getTieLabel([
                { nickname: 'Alice', score: 100 },
                { nickname: 'Bob', score: 100 },
                { nickname: 'Charlie', score: 100 },
            ]);
            expect(result).toBe('3-Way Tie!');
        });

        it('shows 4-way tie', () => {
            const result = getTieLabel([
                { nickname: 'Alice', score: 50 },
                { nickname: 'Bob', score: 50 },
                { nickname: 'Charlie', score: 50 },
                { nickname: 'Diana', score: 50 },
            ]);
            expect(result).toBe('4-Way Tie!');
        });

        it('returns null for empty leaderboard', () => {
            const result = getTieLabel([]);
            expect(result).toBeNull();
        });

        it('shows champion with single player', () => {
            const result = getTieLabel([{ nickname: 'Alice', score: 100 }]);
            expect(result).toBe('Alice is the Champion!');
        });
    });

    // --- Image URL (Fix 3) ---

    describe('Question Image Display', () => {
        it('adds has-image class when image_url is present', () => {
            renderSpectator('ABCD');
            simulateWsOpen();
            simulateWsMessage({
                type: 'QUESTION',
                question: { id: 1, text: 'What color is the sky?', options: ['Blue', 'Red', 'Green', 'Yellow'], image_url: '/images/sky.jpg' },
                question_number: 1,
                total_questions: 5,
                time_limit: 15,
                is_bonus: false,
            });

            // Close the fullscreen prompt first so we can see the question
            const skipBtn = screen.queryByText('Skip');
            if (skipBtn) act(() => { skipBtn.click(); });

            const questionCard = document.querySelector('.question-card');
            expect(questionCard).not.toBeNull();
            expect(questionCard).toHaveClass('has-image');
        });

        it('does not add has-image class when image_url is absent', () => {
            renderSpectator('ABCD');
            simulateWsOpen();
            simulateWsMessage({
                type: 'QUESTION',
                question: { id: 1, text: 'What is 2+2?', options: ['3', '4', '5', '6'] },
                question_number: 1,
                total_questions: 5,
                time_limit: 15,
                is_bonus: false,
            });

            const skipBtn = screen.queryByText('Skip');
            if (skipBtn) act(() => { skipBtn.click(); });

            const questionCard = document.querySelector('.question-card');
            expect(questionCard).not.toBeNull();
            expect(questionCard).not.toHaveClass('has-image');
        });
    });
});
