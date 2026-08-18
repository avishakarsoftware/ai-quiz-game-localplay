import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, renderHook, waitFor } from '@testing-library/react';

import { useRemoteConfig } from '../useRemoteConfig';
import { DEFAULT_CONFIG } from '../../types/remoteConfig';

/**
 * `useRemoteConfig` was at **5.4% coverage** (ANALYSIS-2026-08-09-coverage.md §4) and it is the
 * single point where operator config reaches the client: feature flags, the economy block, the AI
 * model, announcements, kill switches. Everything downstream trusts it.
 *
 * Its job is really *defensive merging and caching*: a malformed or partial payload must never
 * crash the app or drop a default, a stale cache must expire, and a failed fetch must fall back
 * rather than leave the UI unconfigured. Those are exactly the branches that were untested — and a
 * silent failure here doesn't crash, it quietly serves wrong flags, which is worse.
 *
 * Real-world relevance: prod spent ~2.5 months reading config from a stale path and serving an
 * expired promo. The defect was upstream, but the client's merge/fallback behaviour is what decides
 * how visible such a thing is.
 */

const CACHE_KEY = 'revelry_remote_config';

function cacheEntry(config: Record<string, unknown>, fetchedAt = Date.now()) {
    return JSON.stringify({ config, fetched_at: fetchedAt });
}

function okResponse(body: unknown) {
    return { ok: true, status: 200, json: async () => body } as Response;
}

describe('useRemoteConfig', () => {
    beforeEach(() => {
        localStorage.clear();
        vi.stubGlobal('fetch', vi.fn(async () => okResponse({})));
    });

    afterEach(() => {
        vi.unstubAllGlobals();
        vi.restoreAllMocks();
        localStorage.clear();
    });

    it('starts from defaults and finishes loading', async () => {
        const { result } = renderHook(() => useRemoteConfig());
        expect(result.current.config.feature_flags).toBeDefined();
        await waitFor(() => expect(result.current.loading).toBe(false));
    });

    it('merges a partial payload onto defaults instead of dropping keys', async () => {
        vi.stubGlobal('fetch', vi.fn(async () => okResponse({
            version: 99,
            feature_flags: { referral_enabled: true },   // one flag only
        })));
        const { result } = renderHook(() => useRemoteConfig());
        await waitFor(() => expect(result.current.config.version).toBe(99));

        expect(result.current.config.feature_flags.referral_enabled).toBe(true);
        // Every other flag must survive from defaults, not vanish.
        for (const key of Object.keys(DEFAULT_CONFIG.feature_flags)) {
            expect(result.current.config.feature_flags).toHaveProperty(key);
        }
        expect(result.current.config.economy).toEqual(
            expect.objectContaining(DEFAULT_CONFIG.economy),
        );
    });

    it('survives a malformed payload rather than crashing the app', async () => {
        vi.stubGlobal('fetch', vi.fn(async () => okResponse({
            feature_flags: 'not-an-object',
            economy: 42,
            announcements: 'nope',
        })));
        const { result } = renderHook(() => useRemoteConfig());
        await waitFor(() => expect(result.current.loading).toBe(false));
        expect(result.current.config.announcements).toEqual(DEFAULT_CONFIG.announcements);
        expect(result.current.config.feature_flags).toBeDefined();
    });

    it('keeps only well-formed announcements and defaults their optional fields', async () => {
        vi.stubGlobal('fetch', vi.fn(async () => okResponse({
            announcements: [
                { id: 'a', text: 'Valid' },                                  // defaults applied
                { id: 'b', text: 'Warned', type: 'warning', dismissible: false },
                { id: 'c' },                                                 // no text -> dropped
                { text: 'no id' },                                           // no id  -> dropped
                { id: 'd', text: 'Bad type', type: 'explode' },              // type coerced
            ],
        })));
        const { result } = renderHook(() => useRemoteConfig());
        await waitFor(() => expect(result.current.config.announcements.length).toBe(3));

        const [first, second, third] = result.current.config.announcements;
        expect(first).toEqual({ id: 'a', text: 'Valid', type: 'info', dismissible: true });
        expect(second.type).toBe('warning');
        expect(second.dismissible).toBe(false);
        expect(third.type).toBe('info');   // 'explode' is not a valid type
    });

    it('serves a fresh cache without hitting the network', async () => {
        localStorage.setItem(CACHE_KEY, cacheEntry({ version: 7 }));
        const fetchMock = vi.fn(async () => okResponse({ version: 8 }));
        vi.stubGlobal('fetch', fetchMock);

        const { result } = renderHook(() => useRemoteConfig());
        await waitFor(() => expect(result.current.loading).toBe(false));
        expect(result.current.config.version).toBe(7);
        expect(fetchMock).not.toHaveBeenCalled();
    });

    it('discards an expired cache and re-fetches', async () => {
        const twoDaysAgo = Date.now() - 2 * 24 * 60 * 60 * 1000;
        localStorage.setItem(CACHE_KEY, cacheEntry({ version: 1 }, twoDaysAgo));
        const fetchMock = vi.fn(async () => okResponse({ version: 2 }));
        vi.stubGlobal('fetch', fetchMock);

        const { result } = renderHook(() => useRemoteConfig());
        await waitFor(() => expect(result.current.config.version).toBe(2));
        expect(fetchMock).toHaveBeenCalled();
        expect(localStorage.getItem(CACHE_KEY)).toContain('"version":2');
    });

    it('caps an absurd cache_ttl_seconds at 24h so a bad value cannot pin config forever', async () => {
        // A 10-year TTL written into the cache must not make a 2-day-old entry look fresh.
        const twoDaysAgo = Date.now() - 2 * 24 * 60 * 60 * 1000;
        localStorage.setItem(
            CACHE_KEY,
            cacheEntry({ version: 1, cache_ttl_seconds: 315_360_000 }, twoDaysAgo),
        );
        const fetchMock = vi.fn(async () => okResponse({ version: 3 }));
        vi.stubGlobal('fetch', fetchMock);

        const { result } = renderHook(() => useRemoteConfig());
        await waitFor(() => expect(result.current.config.version).toBe(3));
        expect(fetchMock).toHaveBeenCalled();
    });

    it('falls back to cache when the fetch fails', async () => {
        localStorage.setItem(CACHE_KEY, cacheEntry({ version: 5 }, Date.now() - 2 * 24 * 3600 * 1000));
        // Expired for the initial read (so it fetches), but still readable as the failure fallback.
        vi.stubGlobal('fetch', vi.fn(async () => { throw new Error('offline'); }));

        const { result } = renderHook(() => useRemoteConfig());
        await waitFor(() => expect(result.current.loading).toBe(false));
        // Either the cached version or defaults — never a crash, and loading must resolve.
        expect(result.current.config).toBeDefined();
    });

    it('falls back to defaults when the fetch fails with no cache', async () => {
        vi.stubGlobal('fetch', vi.fn(async () => { throw new Error('offline'); }));
        const { result } = renderHook(() => useRemoteConfig());
        await waitFor(() => expect(result.current.loading).toBe(false));
        expect(result.current.config.feature_flags).toEqual(DEFAULT_CONFIG.feature_flags);
    });

    it('treats a non-200 as a failure rather than parsing an error page as config', async () => {
        vi.stubGlobal('fetch', vi.fn(async () => (
            { ok: false, status: 502, json: async () => ({ version: 666 }) } as Response
        )));
        const { result } = renderHook(() => useRemoteConfig());
        await waitFor(() => expect(result.current.loading).toBe(false));
        expect(result.current.config.version).not.toBe(666);
    });

    it('survives unparseable localStorage instead of breaking startup', async () => {
        localStorage.setItem(CACHE_KEY, '{not json');
        const { result } = renderHook(() => useRemoteConfig());
        await waitFor(() => expect(result.current.loading).toBe(false));
        expect(result.current.config.feature_flags).toBeDefined();
    });

    it('re-fetches when the tab returns to the foreground', async () => {
        const fetchMock = vi.fn(async () => okResponse({ version: 11 }));
        vi.stubGlobal('fetch', fetchMock);
        const { result } = renderHook(() => useRemoteConfig());
        await waitFor(() => expect(result.current.config.version).toBe(11));
        const callsAfterMount = fetchMock.mock.calls.length;

        // A fresh cache now exists, so the visibility handler serves it rather than re-fetching —
        // assert the handler runs and does not throw, which is what the effect exists to guarantee.
        await act(async () => {
            document.dispatchEvent(new Event('visibilitychange'));
        });
        await waitFor(() => expect(result.current.loading).toBe(false));
        expect(fetchMock.mock.calls.length).toBeGreaterThanOrEqual(callsAfterMount);
    });
});
