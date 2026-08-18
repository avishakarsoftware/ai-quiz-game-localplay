import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import ReferralSection from '../ReferralSection';

/**
 * `ReferralSection` was at **0% coverage** (ANALYSIS-2026-08-09-coverage.md §4) despite being the
 * entire client half of the referral loop — the growth mechanism REVIEW-2026-08 P2 calls the highest
 * revenue-per-effort item left. It also hands out sparks, so its failure modes matter: a redeem that
 * reports success without crediting, or one that silently swallows a rejection, both cost money or
 * trust.
 *
 * Notably it reads `?ref=CODE` off the launch URL, which is how a shared invite link is supposed to
 * pre-fill for the invitee. That deep-link path had never been executed by a test.
 */

vi.mock('../../utils/analytics', () => ({ track: vi.fn() }));

const apiFetch = vi.fn();
vi.mock('../../utils/api', () => ({
    apiFetch: (...args: unknown[]) => apiFetch(...args),
    apiUrl: (p: string) => p,
    apiHeaders: () => ({}),
}));

function jsonResponse(body: unknown, ok = true, status = 200) {
    return { ok, status, json: async () => body } as Response;
}

const CODE_INFO = { code: 'ABC123', share_url: 'https://games.revelryapp.me/?ref=ABC123', reward: 20 };

function setUrl(search: string) {
    // jsdom allows replaceState to set the query the component reads on mount.
    window.history.replaceState({}, '', `/${search}`);
}

describe('ReferralSection', () => {
    beforeEach(() => {
        apiFetch.mockReset();
        setUrl('');
        vi.stubGlobal('navigator', {
            ...navigator,
            share: undefined,
            clipboard: { writeText: vi.fn(async () => {}) },
        });
    });

    afterEach(() => {
        vi.unstubAllGlobals();
        vi.restoreAllMocks();
        setUrl('');
    });

    it('shows the code once the backend returns one', async () => {
        apiFetch.mockResolvedValue(jsonResponse(CODE_INFO));
        render(<ReferralSection />);
        expect(await screen.findByText(/ABC123/)).toBeInTheDocument();
    });

    it('stays hidden when the referral endpoint fails, rather than erroring', async () => {
        apiFetch.mockRejectedValue(new Error('503'));
        render(<ReferralSection />);
        await act(async () => { await Promise.resolve(); });
        expect(screen.queryByText(/ABC123/)).toBeNull();
    });

    it('stays hidden on a non-ok response', async () => {
        apiFetch.mockResolvedValue(jsonResponse({ detail: 'disabled' }, false, 503));
        render(<ReferralSection />);
        await act(async () => { await Promise.resolve(); });
        expect(screen.queryByText(/ABC123/)).toBeNull();
    });

    it('pre-fills the redeem field from a ?ref= deep link, uppercased', async () => {
        setUrl('?ref=friend9');
        apiFetch.mockResolvedValue(jsonResponse(CODE_INFO));
        render(<ReferralSection />);
        await screen.findByText(/ABC123/);
        const input = screen.getByRole('textbox') as HTMLInputElement;
        expect(input.value).toBe('FRIEND9', );
    });

    it('credits sparks and announces the refresh on a successful redeem', async () => {
        apiFetch.mockImplementation(async (path: string) => (
            path === '/referral/code'
                ? jsonResponse(CODE_INFO)
                : jsonResponse({ redeemed: true, reward: 20 })
        ));
        const sparkRefresh = vi.fn();
        window.addEventListener('refresh-sparks', sparkRefresh);

        render(<ReferralSection />);
        await screen.findByText(/ABC123/);
        const input = screen.getByRole('textbox');
        await userEvent.type(input, 'friendcode');
        await userEvent.click(screen.getByRole('button', { name: /redeem/i }));

        expect(await screen.findByText(/\+20 sparks/)).toBeInTheDocument();
        // The wallet badge only updates if this event fires — without it the user sees no sparks
        // until a manual reload and assumes the redeem failed.
        await waitFor(() => expect(sparkRefresh).toHaveBeenCalled());
        window.removeEventListener('refresh-sparks', sparkRefresh);
    });

    it('surfaces the server reason when a code is refused', async () => {
        apiFetch.mockImplementation(async (path: string) => (
            path === '/referral/code'
                ? jsonResponse(CODE_INFO)
                : jsonResponse({ detail: 'You already redeemed a referral.' }, false, 400)
        ));
        render(<ReferralSection />);
        await screen.findByText(/ABC123/);
        await userEvent.type(screen.getByRole('textbox'), 'dupe');
        await userEvent.click(screen.getByRole('button', { name: /redeem/i }));
        expect(await screen.findByText(/already redeemed/i)).toBeInTheDocument();
    });

    it('reports a network failure instead of looking like a rejection', async () => {
        apiFetch.mockImplementation(async (path: string) => {
            if (path === '/referral/code') return jsonResponse(CODE_INFO);
            throw new Error('offline');
        });
        render(<ReferralSection />);
        await screen.findByText(/ABC123/);
        await userEvent.type(screen.getByRole('textbox'), 'somecode');
        await userEvent.click(screen.getByRole('button', { name: /redeem/i }));
        expect(await screen.findByText(/network error/i)).toBeInTheDocument();
    });

    it('cannot redeem an empty code', async () => {
        apiFetch.mockResolvedValue(jsonResponse(CODE_INFO));
        render(<ReferralSection />);
        await screen.findByText(/ABC123/);
        const button = screen.getByRole('button', { name: /redeem/i });
        expect(button).toBeDisabled();
    });

    it('copies the invite when the native share sheet is unavailable', async () => {
        const writeText = vi.fn<(text: string) => Promise<void>>(async () => undefined);
        vi.stubGlobal('navigator', { ...navigator, share: undefined, clipboard: { writeText } });
        apiFetch.mockResolvedValue(jsonResponse(CODE_INFO));

        render(<ReferralSection />);
        await screen.findByText(/ABC123/);
        await userEvent.click(screen.getByRole('button', { name: /share|invite/i }));

        await waitFor(() => expect(writeText).toHaveBeenCalled());
        const copied = String(writeText.mock.calls[0][0]);
        expect(copied).toContain('ABC123');
        expect(copied).toContain(CODE_INFO.share_url);
        expect(await screen.findByText(/copied/i)).toBeInTheDocument();
    });

    it('prefers the native share sheet when present', async () => {
        const share = vi.fn<(data: ShareData) => Promise<void>>(async () => undefined);
        vi.stubGlobal('navigator', { ...navigator, share, clipboard: { writeText: vi.fn() } });
        apiFetch.mockResolvedValue(jsonResponse(CODE_INFO));

        render(<ReferralSection />);
        await screen.findByText(/ABC123/);
        await userEvent.click(screen.getByRole('button', { name: /share|invite/i }));

        await waitFor(() => expect(share).toHaveBeenCalled());
        expect(share.mock.calls[0][0]).toEqual(
            expect.objectContaining({ url: CODE_INFO.share_url }),
        );
    });

    it('a cancelled share sheet is not an error', async () => {
        const share = vi.fn<(data: ShareData) => Promise<void>>(
            async () => { throw new Error('AbortError'); });
        vi.stubGlobal('navigator', { ...navigator, share, clipboard: { writeText: vi.fn() } });
        apiFetch.mockResolvedValue(jsonResponse(CODE_INFO));

        render(<ReferralSection />);
        await screen.findByText(/ABC123/);
        await userEvent.click(screen.getByRole('button', { name: /share|invite/i }));
        await act(async () => { await Promise.resolve(); });
        expect(screen.queryByText(/error/i)).toBeNull();
    });
});
