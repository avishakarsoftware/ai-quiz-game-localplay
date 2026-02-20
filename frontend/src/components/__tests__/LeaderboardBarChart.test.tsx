import { render } from '@testing-library/react';
import LeaderboardBarChart from '../LeaderboardBarChart';
import { BAR_COLORS, AVATAR_COLORS } from '../LeaderboardBarChart.constants';
import type { LeaderboardEntry } from '../../types';

// Recharts ResponsiveContainer needs a real width/height to render children.
// Mock it to just render children directly.
vi.mock('recharts', async () => {
    const actual = await vi.importActual<typeof import('recharts')>('recharts');
    return {
        ...actual,
        ResponsiveContainer: ({ children }: { children: React.ReactNode }) => (
            <div style={{ width: 800, height: 600 }}>{children}</div>
        ),
    };
});

const mockLeaderboard: LeaderboardEntry[] = [
    { nickname: 'Alice', score: 1000, avatar: '🦊', rank_change: 0 },
    { nickname: 'Bob', score: 800, avatar: '🐼', rank_change: 2 },
    { nickname: 'Charlie', score: 600, avatar: '🐶', rank_change: -1 },
    { nickname: 'Diana', score: 400, rank_change: -1 },
    { nickname: 'Eve', score: 200, rank_change: 0 },
];

describe('LeaderboardBarChart', () => {
    it('renders without crashing', () => {
        const { container } = render(
            <LeaderboardBarChart leaderboard={mockLeaderboard} />
        );
        expect(container.querySelector('.recharts-wrapper')).toBeInTheDocument();
    });

    it('handles empty leaderboard without crashing', () => {
        const { container } = render(
            <LeaderboardBarChart leaderboard={[]} />
        );
        expect(container).toBeTruthy();
    });

    it('handles single player leaderboard', () => {
        const single: LeaderboardEntry[] = [
            { nickname: 'Solo', score: 500, rank_change: 0 },
        ];
        const { container } = render(
            <LeaderboardBarChart leaderboard={single} />
        );
        expect(container.querySelector('.recharts-wrapper')).toBeInTheDocument();
    });

    it('renders with large size config', () => {
        const { container } = render(
            <LeaderboardBarChart leaderboard={mockLeaderboard} size="large" />
        );
        expect(container.querySelector('.recharts-wrapper')).toBeInTheDocument();
    });

    it('renders with animation disabled', () => {
        const { container } = render(
            <LeaderboardBarChart leaderboard={mockLeaderboard} animate={false} />
        );
        expect(container.querySelector('.recharts-wrapper')).toBeInTheDocument();
    });

    it('renders with highlight nickname', () => {
        const { container } = render(
            <LeaderboardBarChart leaderboard={mockLeaderboard} highlightNickname="Bob" />
        );
        expect(container.querySelector('.recharts-wrapper')).toBeInTheDocument();
    });
});

describe('LeaderboardBarChart.constants', () => {
    it('BAR_COLORS has gold, silver, bronze entries', () => {
        expect(BAR_COLORS.gold).toBeDefined();
        expect(BAR_COLORS.silver).toBeDefined();
        expect(BAR_COLORS.bronze).toBeDefined();
    });

    it('each BAR_COLORS entry has two gradient stops', () => {
        expect(BAR_COLORS.gold).toHaveLength(2);
        expect(BAR_COLORS.silver).toHaveLength(2);
        expect(BAR_COLORS.bronze).toHaveLength(2);
    });

    it('AVATAR_COLORS has at least 4 entries', () => {
        expect(AVATAR_COLORS.length).toBeGreaterThanOrEqual(4);
    });

    it('AVATAR_COLORS are valid CSS color strings', () => {
        AVATAR_COLORS.forEach((color) => {
            expect(typeof color).toBe('string');
            expect(color.length).toBeGreaterThan(0);
        });
    });
});
