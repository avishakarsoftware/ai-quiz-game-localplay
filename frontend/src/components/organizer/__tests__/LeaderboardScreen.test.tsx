import { act, fireEvent, render, screen } from '@testing-library/react';
import LeaderboardScreen from '../LeaderboardScreen';
import { type LeaderboardEntry } from '../../../types';

// Recharts ResponsiveContainer needs a real size; render children directly.
vi.mock('recharts', async () => {
    const actual = await vi.importActual<typeof import('recharts')>('recharts');
    return {
        ...actual,
        ResponsiveContainer: ({ children }: { children: React.ReactNode }) => (
            <div style={{ width: 800, height: 600 }}>{children}</div>
        ),
    };
});

const leaderboard: LeaderboardEntry[] = [
    { nickname: 'Avi', score: 30, avatar: '🦊' },
    { nickname: 'Ruchi', score: 20, avatar: '🐯' },
];

describe('LeaderboardScreen', () => {
    afterEach(() => {
        vi.useRealTimers();
    });

    it('gives the host Next + End Game controls instead of forcing a silent wait', () => {
        const onNextQuestion = vi.fn();
        const onEndQuiz = vi.fn();
        render(
            <LeaderboardScreen
                leaderboard={leaderboard}
                questionNumber={1}
                totalQuestions={5}
                onNextQuestion={onNextQuestion}
                onEndQuiz={onEndQuiz}
            />,
        );

        const next = screen.getByRole('button', { name: /Next Question/ });
        fireEvent.click(next);
        expect(onNextQuestion).toHaveBeenCalledTimes(1);

        fireEvent.click(screen.getByRole('button', { name: 'End Game' }));
        expect(onEndQuiz).toHaveBeenCalledTimes(1);
    });

    it('labels the final round "Show Results", not "Next Question"', () => {
        render(
            <LeaderboardScreen
                leaderboard={leaderboard}
                questionNumber={5}
                totalQuestions={5}
                onNextQuestion={() => {}}
                onEndQuiz={() => {}}
            />,
        );
        expect(screen.getByRole('button', { name: /Show Results/ })).toBeInTheDocument();
        expect(screen.queryByRole('button', { name: /Next Question/ })).not.toBeInTheDocument();
    });

    it('resets countdown when a new leaderboard round reuses the same component instance', () => {
        vi.useFakeTimers();
        const onNextQuestion = vi.fn();
        const { rerender } = render(
            <LeaderboardScreen
                leaderboard={leaderboard}
                questionNumber={1}
                totalQuestions={5}
                onNextQuestion={onNextQuestion}
                onEndQuiz={() => {}}
            />,
        );

        act(() => {
            vi.advanceTimersByTime(3000);
        });
        expect(screen.getByRole('button', { name: /Next Question \(2\)/ })).toBeInTheDocument();

        rerender(
            <LeaderboardScreen
                leaderboard={leaderboard}
                questionNumber={2}
                totalQuestions={5}
                onNextQuestion={onNextQuestion}
                onEndQuiz={() => {}}
            />,
        );

        expect(screen.getByRole('button', { name: /Next Question \(5\)/ })).toBeInTheDocument();
        act(() => {
            vi.advanceTimersByTime(4999);
        });
        expect(onNextQuestion).not.toHaveBeenCalled();
        act(() => {
            vi.advanceTimersByTime(1);
        });
        expect(onNextQuestion).toHaveBeenCalledTimes(1);
    });
});
