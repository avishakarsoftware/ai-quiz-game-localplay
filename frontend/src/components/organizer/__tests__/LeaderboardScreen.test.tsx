import { fireEvent, render, screen } from '@testing-library/react';
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
});
