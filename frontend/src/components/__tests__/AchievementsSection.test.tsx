import { render, screen, waitFor } from '@testing-library/react';
import AchievementsSection from '../AchievementsSection';

/**
 * Achievements / badges (SPEC-ACHIEVEMENTS). The backend owns the catalog; the component renders
 * whatever badges it's handed, lighting earned ones and dimming locked ones, and stays hidden if
 * the fetch fails or returns nothing.
 */

const CATALOG = [
    { id: 'welcome', emoji: '👋', name: 'Welcome to Revelry', description: 'Joined the party.', earned: true, awarded_at: 1 },
    { id: 'first_referral', emoji: '🔗', name: 'Connector', description: 'Completed a referral.', earned: false, awarded_at: null },
    { id: 'first_gift', emoji: '🎁', name: 'Generous', description: 'Sent your first spark gift.', earned: false, awarded_at: null },
];

function mockAchievements(body: unknown, ok = true) {
    global.fetch = vi.fn((url: string) => {
        if (String(url).includes('/achievements')) {
            return Promise.resolve({ ok, status: ok ? 200 : 500, json: () => Promise.resolve(body) } as Response);
        }
        return Promise.reject(new Error(`unexpected fetch: ${url}`));
    }) as unknown as typeof fetch;
}

describe('AchievementsSection', () => {
    afterEach(() => vi.restoreAllMocks());

    it('renders the catalog with an earned count and lights only earned badges', async () => {
        mockAchievements({ badges: CATALOG, earned_count: 1 });
        render(<AchievementsSection />);
        await screen.findByText('Welcome to Revelry');
        // count reflects earned/total
        expect(screen.getByText('(1/3)')).toBeInTheDocument();
        // earned badge is not grayscaled; locked one is
        const welcome = screen.getByLabelText('Welcome to Revelry: earned');
        const connector = screen.getByLabelText('Connector: locked');
        expect(welcome).toHaveAttribute('data-earned', 'true');
        expect(connector).toHaveAttribute('data-earned', 'false');
    });

    it('stays hidden when there are no badges', async () => {
        mockAchievements({ badges: [], earned_count: 0 });
        const { container } = render(<AchievementsSection />);
        await waitFor(() => expect(container).toBeEmptyDOMElement());
    });

    it('stays hidden when the fetch fails', async () => {
        mockAchievements({}, false);
        const { container } = render(<AchievementsSection />);
        await waitFor(() => expect(container).toBeEmptyDOMElement());
    });
});
