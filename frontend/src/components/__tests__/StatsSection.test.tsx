import { render, screen, waitFor } from '@testing-library/react';
import StatsSection from '../StatsSection';

/**
 * Hosting stats (SPEC-GAME-STATS). The behaviours worth locking down are the three ways this
 * section must stay INVISIBLE — no games yet, backend says unavailable, request failed — plus
 * that it never leaks a raw game_type id into the copy.
 */

const FULL = {
    available: true,
    games_hosted: 12,
    players_entertained: 47,
    distinct_games_played: 4,
    favorite_game_type: 'would_you_rather',
    favorite_game_title: 'Would You Rather',
    last_played_at: 1_700_000_000,
    by_game_type: [
        { game_type: 'would_you_rather', game_title: 'Would You Rather', count: 6 },
        { game_type: 'quiz', game_title: 'AI Quiz', count: 4 },
        { game_type: 'poker', game_title: 'Party Poker', count: 2 },
    ],
};

function mockStats(body: unknown, ok = true) {
    globalThis.fetch = vi.fn((url: string) => {
        if (String(url).includes('/stats')) {
            return Promise.resolve({ ok, status: ok ? 200 : 500, json: () => Promise.resolve(body) } as Response);
        }
        return Promise.reject(new Error(`unexpected fetch: ${url}`));
    }) as unknown as typeof fetch;
}

describe('StatsSection', () => {
    afterEach(() => vi.restoreAllMocks());

    it('renders the tiles and the favourite game once the host has parties', async () => {
        mockStats(FULL);
        render(<StatsSection />);
        await screen.findByText('Your parties');
        expect(screen.getByText('12')).toBeInTheDocument();
        expect(screen.getByText('games hosted')).toBeInTheDocument();
        expect(screen.getByText('47')).toBeInTheDocument();
        // Appears twice by design: once as the favourite, once as the top breakdown row.
        expect(screen.getAllByText('Would You Rather')).toHaveLength(2);
    });

    it('says "hosted", never "played" — guests have no wallet, so played would be a lie', async () => {
        mockStats(FULL);
        const { container } = render(<StatsSection />);
        await screen.findByText('Your parties');
        expect(container.textContent).toMatch(/hosted/i);
        expect(container.textContent).not.toMatch(/games played/i);
    });

    it('never shows a raw game_type id', async () => {
        mockStats(FULL);
        const { container } = render(<StatsSection />);
        await screen.findByText('Your parties');
        expect(container.textContent).not.toMatch(/would_you_rather/);
    });

    it('stays hidden for a host with zero games rather than showing a wall of zeros', async () => {
        mockStats({ ...FULL, games_hosted: 0, players_entertained: 0, by_game_type: [] });
        const { container } = render(<StatsSection />);
        await waitFor(() => expect(globalThis.fetch).toHaveBeenCalled());
        expect(container.textContent).toBe('');
    });

    it('stays hidden when the backend reports stats unavailable (table not applied yet)', async () => {
        mockStats({ ...FULL, available: false });
        const { container } = render(<StatsSection />);
        await waitFor(() => expect(globalThis.fetch).toHaveBeenCalled());
        expect(container.textContent).toBe('');
    });

    it('stays hidden when the request fails', async () => {
        mockStats({}, false);
        const { container } = render(<StatsSection />);
        await waitFor(() => expect(globalThis.fetch).toHaveBeenCalled());
        expect(container.textContent).toBe('');
    });

    it('singularises the label for a single hosted game', async () => {
        mockStats({ ...FULL, games_hosted: 1 });
        render(<StatsSection />);
        await screen.findByText('game hosted');
    });
});
