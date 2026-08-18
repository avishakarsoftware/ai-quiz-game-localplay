import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import PodiumInviteCta from '../PodiumInviteCta';

/**
 * The guest-facing half of the referral loop (REVIEW-2026-08 P2). Two properties matter more than
 * the happy path:
 *
 *  1. It must render NOTHING unless an invite is genuinely available. This sits on a celebration
 *     screen, where a broken or empty CTA is worse than no CTA — so every failure path is silence.
 *  2. The shared text must carry the HOST's code, since that is what makes the loop pay both sides.
 */

vi.mock('../../utils/analytics', () => ({ track: vi.fn() }));
vi.mock('../../utils/api', () => ({ apiUrl: (p: string) => p }));

const INVITE = {
    available: true,
    code: 'HOST42',
    reward: 20,
    share_url: 'https://games.revelryapp.me/?ref=HOST42',
};

function fetchReturning(body: unknown, ok = true) {
    // Typed signature: an untyped vi.fn gives `mock.calls[0]` a zero-length tuple, which
    // `tsc -b` rejects even though vitest runs it happily.
    return vi.fn<(url: string) => Promise<Response>>(
        async () => ({ ok, status: ok ? 200 : 500, json: async () => body } as Response));
}

describe('PodiumInviteCta', () => {
    beforeEach(() => {
        vi.stubGlobal('navigator', {
            ...navigator,
            share: undefined,
            clipboard: { writeText: vi.fn<(t: string) => Promise<void>>(async () => undefined) },
        });
    });

    afterEach(() => {
        vi.unstubAllGlobals();
        vi.restoreAllMocks();
    });

    it("shows the host's code and the mutual reward", async () => {
        vi.stubGlobal('fetch', fetchReturning(INVITE));
        render(<PodiumInviteCta roomCode="ABC123" />);
        expect(await screen.findByTestId('podium-invite-cta')).toBeInTheDocument();
        expect(screen.getByTestId('podium-invite-code')).toHaveTextContent('HOST42');
        expect(screen.getByText(/both get 20 sparks/i)).toBeInTheDocument();
    });

    it('asks the room-scoped endpoint for the code', async () => {
        const fetchMock = fetchReturning(INVITE);
        vi.stubGlobal('fetch', fetchMock);
        render(<PodiumInviteCta roomCode="ABC123" />);
        await screen.findByTestId('podium-invite-cta');
        expect(String(fetchMock.mock.calls[0][0])).toBe('/room/ABC123/invite');
    });

    it.each([
        ['available:false', { available: false }],
        ['available but no code', { available: true }],
        ['an empty body', {}],
    ])('renders nothing for %s', async (_label, body) => {
        vi.stubGlobal('fetch', fetchReturning(body));
        render(<PodiumInviteCta roomCode="ABC123" />);
        await act(async () => { await Promise.resolve(); });
        expect(screen.queryByTestId('podium-invite-cta')).toBeNull();
    });

    it('renders nothing when the request fails', async () => {
        vi.stubGlobal('fetch', vi.fn(async () => { throw new Error('offline'); }));
        render(<PodiumInviteCta roomCode="ABC123" />);
        await act(async () => { await Promise.resolve(); });
        expect(screen.queryByTestId('podium-invite-cta')).toBeNull();
    });

    it('renders nothing on a non-ok response', async () => {
        vi.stubGlobal('fetch', fetchReturning({ available: true, code: 'X' }, false));
        render(<PodiumInviteCta roomCode="ABC123" />);
        await act(async () => { await Promise.resolve(); });
        expect(screen.queryByTestId('podium-invite-cta')).toBeNull();
    });

    it('does not call the endpoint without a room code', async () => {
        const fetchMock = fetchReturning(INVITE);
        vi.stubGlobal('fetch', fetchMock);
        render(<PodiumInviteCta roomCode="" />);
        await act(async () => { await Promise.resolve(); });
        expect(fetchMock).not.toHaveBeenCalled();
    });

    it('copies an invite containing the code and link when there is no share sheet', async () => {
        const writeText = vi.fn<(t: string) => Promise<void>>(async () => undefined);
        vi.stubGlobal('navigator', { ...navigator, share: undefined, clipboard: { writeText } });
        vi.stubGlobal('fetch', fetchReturning(INVITE));

        render(<PodiumInviteCta roomCode="ABC123" />);
        await screen.findByTestId('podium-invite-cta');
        await userEvent.click(screen.getByTestId('podium-invite-share'));

        await waitFor(() => expect(writeText).toHaveBeenCalled());
        const text = String(writeText.mock.calls[0][0]);
        expect(text).toContain('HOST42');
        expect(text).toContain(INVITE.share_url);
        expect(await screen.findByText('Copied!')).toBeInTheDocument();
    });

    it('prefers the native share sheet, passing the invite link', async () => {
        const share = vi.fn<(d: ShareData) => Promise<void>>(async () => undefined);
        vi.stubGlobal('navigator', { ...navigator, share, clipboard: { writeText: vi.fn() } });
        vi.stubGlobal('fetch', fetchReturning(INVITE));

        render(<PodiumInviteCta roomCode="ABC123" />);
        await screen.findByTestId('podium-invite-cta');
        await userEvent.click(screen.getByTestId('podium-invite-share'));

        await waitFor(() => expect(share).toHaveBeenCalled());
        expect(share.mock.calls[0][0]).toEqual(
            expect.objectContaining({ url: INVITE.share_url }),
        );
        expect(String(share.mock.calls[0][0].text)).toContain('HOST42');
    });

    it('a dismissed share sheet leaves the CTA intact and shows no error', async () => {
        const share = vi.fn<(d: ShareData) => Promise<void>>(async () => {
            throw new Error('AbortError');
        });
        vi.stubGlobal('navigator', { ...navigator, share, clipboard: { writeText: vi.fn() } });
        vi.stubGlobal('fetch', fetchReturning(INVITE));

        render(<PodiumInviteCta roomCode="ABC123" />);
        await screen.findByTestId('podium-invite-cta');
        await userEvent.click(screen.getByTestId('podium-invite-share'));
        await act(async () => { await Promise.resolve(); });

        expect(screen.getByTestId('podium-invite-cta')).toBeInTheDocument();
        expect(screen.queryByText('Copied!')).toBeNull();
    });

    it('omits the reward clause when the backend reports no reward', async () => {
        vi.stubGlobal('fetch', fetchReturning({ available: true, code: 'HOST42', reward: 0 }));
        render(<PodiumInviteCta roomCode="ABC123" />);
        await screen.findByTestId('podium-invite-cta');
        expect(screen.queryByText(/both get/i)).toBeNull();
    });
});
