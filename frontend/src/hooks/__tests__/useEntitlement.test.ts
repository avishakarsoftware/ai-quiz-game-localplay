import { renderHook, waitFor } from '@testing-library/react';
import { useEntitlement } from '../useEntitlement';

// Mock apiFetch
const mockApiFetch = vi.fn();
vi.mock('../../utils/api', () => ({
    apiFetch: (...args: unknown[]) => mockApiFetch(...args),
}));

describe('useEntitlement', () => {
    beforeEach(() => {
        mockApiFetch.mockReset();
    });

    it('returns default state while loading', () => {
        mockApiFetch.mockReturnValue(new Promise(() => {})); // never resolves
        const { result } = renderHook(() => useEntitlement());
        expect(result.current.loading).toBe(true);
        expect(result.current.entitlement.premium).toBe(false);
    });

    it('fetches entitlement on mount', async () => {
        mockApiFetch.mockResolvedValue({
            ok: true,
            json: () => Promise.resolve({
                premium: true,
                status: 'active',
                games_remaining: 42,
                expires_at: null,
                free_games_used: 1,
                free_games_limit: 3,
                pending_purchase: false,
            }),
        });

        const { result } = renderHook(() => useEntitlement());
        await waitFor(() => expect(result.current.loading).toBe(false));
        expect(result.current.entitlement.premium).toBe(true);
        expect(result.current.entitlement.games_remaining).toBe(42);
    });

    it('returns default on non-ok response', async () => {
        mockApiFetch.mockResolvedValue({ ok: false });

        const { result } = renderHook(() => useEntitlement());
        await waitFor(() => expect(result.current.loading).toBe(false));
        expect(result.current.entitlement.premium).toBe(false);
        expect(result.current.entitlement.free_games_limit).toBe(3);
    });

    it('returns default on network error', async () => {
        mockApiFetch.mockRejectedValue(new Error('Network error'));

        const { result } = renderHook(() => useEntitlement());
        await waitFor(() => expect(result.current.loading).toBe(false));
        expect(result.current.entitlement.premium).toBe(false);
    });

    it('returns default on malformed JSON', async () => {
        mockApiFetch.mockResolvedValue({
            ok: true,
            json: () => Promise.reject(new Error('Bad JSON')),
        });

        const { result } = renderHook(() => useEntitlement());
        await waitFor(() => expect(result.current.loading).toBe(false));
        expect(result.current.entitlement.premium).toBe(false);
    });

    it('refresh() updates entitlement', async () => {
        // Initial fetch: free tier
        mockApiFetch.mockResolvedValueOnce({
            ok: true,
            json: () => Promise.resolve({
                premium: false, status: null, games_remaining: 0,
                expires_at: null, free_games_used: 1, free_games_limit: 3, pending_purchase: false,
            }),
        });

        const { result } = renderHook(() => useEntitlement());
        await waitFor(() => expect(result.current.loading).toBe(false));
        expect(result.current.entitlement.free_games_used).toBe(1);

        // Refresh: now premium
        mockApiFetch.mockResolvedValueOnce({
            ok: true,
            json: () => Promise.resolve({
                premium: true, status: 'active', games_remaining: 50,
                expires_at: null, free_games_used: 1, free_games_limit: 3, pending_purchase: false,
            }),
        });

        result.current.refresh();
        await waitFor(() => expect(result.current.entitlement.premium).toBe(true));
        expect(result.current.entitlement.games_remaining).toBe(50);
    });
});
