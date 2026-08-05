import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, render, screen } from '@testing-library/react';
import PartyGraceBanner from '../PartyGraceBanner';

function balanceFetch(partyGrace: unknown) {
    return vi.fn(async (url: string) => {
        if (String(url).endsWith('/tokens/balance')) {
            return {
                ok: true, status: 200,
                json: async () => ({ balance: 20, cost_room: 10, cost_generate: 1, party_grace: partyGrace }),
            } as Response;
        }
        return { ok: false, status: 404, json: async () => ({}) } as Response;
    });
}

async function renderWith(partyGrace: unknown) {
    vi.stubGlobal('fetch', balanceFetch(partyGrace));
    render(<PartyGraceBanner />);
    await act(async () => { await Promise.resolve(); });
}

describe('PartyGraceBanner (REVIEW-2026-08 P1)', () => {
    beforeEach(() => vi.stubGlobal('fetch', vi.fn()));
    afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks(); });

    it('invites a brand-new host before their first room', async () => {
        await renderWith({ state: 'available', until: 0, rooms_used: 0 });
        expect(screen.getByTestId('party-grace-banner')).toHaveTextContent('first party’s on us');
    });

    it('shows the live deadline while the window is open', async () => {
        const until = Math.floor(Date.now() / 1000) + 3 * 3600;
        await renderWith({ state: 'active', until, rooms_used: 2 });
        expect(screen.getByTestId('party-grace-banner')).toHaveTextContent('Free game rooms until');
    });

    it.each(['expired', 'ineligible'])('renders nothing for %s hosts — no clutter, no dead promise', async (state) => {
        await renderWith({ state, until: 0, rooms_used: 0 });
        expect(screen.queryByTestId('party-grace-banner')).toBeNull();
    });

    it('renders nothing against an old backend without the field', async () => {
        await renderWith(undefined);
        expect(screen.queryByTestId('party-grace-banner')).toBeNull();
    });
});
