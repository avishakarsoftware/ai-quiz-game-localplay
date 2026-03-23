import { renderHook, waitFor } from '@testing-library/react';
import { useTokenBalance } from '../useTokenBalance';

// Mock apiFetch
const mockApiFetch = vi.fn();
vi.mock('../../utils/api', () => ({
    apiFetch: (...args: unknown[]) => mockApiFetch(...args),
}));

describe('useTokenBalance', () => {
    beforeEach(() => {
        mockApiFetch.mockReset();
    });

    it('returns default state while loading', () => {
        mockApiFetch.mockReturnValue(new Promise(() => {})); // never resolves
        const { result } = renderHook(() => useTokenBalance());
        expect(result.current.loading).toBe(true);
        expect(result.current.tokenStatus.balance).toBe(0);
    });

    it('fetches token balance on mount', async () => {
        mockApiFetch.mockResolvedValue({
            ok: true,
            json: () => Promise.resolve({
                balance: 42,
                has_purchased: true,
                daily_bonus_available: false,
                daily_bonus_granted: false,
                bonus_amount: 0,
                cost_generate: 1,
                cost_room: 10,
                ads_remaining_today: 5,
            }),
        });

        const { result } = renderHook(() => useTokenBalance());
        await waitFor(() => expect(result.current.loading).toBe(false));
        expect(result.current.tokenStatus.balance).toBe(42);
        expect(result.current.tokenStatus.has_purchased).toBe(true);
    });

    it('returns default on non-ok response', async () => {
        mockApiFetch.mockResolvedValue({ ok: false });

        const { result } = renderHook(() => useTokenBalance());
        await waitFor(() => expect(result.current.loading).toBe(false));
        expect(result.current.tokenStatus.balance).toBe(0);
    });

    it('returns default on network error', async () => {
        mockApiFetch.mockRejectedValue(new Error('Network error'));

        const { result } = renderHook(() => useTokenBalance());
        await waitFor(() => expect(result.current.loading).toBe(false));
        expect(result.current.tokenStatus.balance).toBe(0);
    });

    it('returns default on malformed JSON', async () => {
        mockApiFetch.mockResolvedValue({
            ok: true,
            json: () => Promise.reject(new Error('Bad JSON')),
        });

        const { result } = renderHook(() => useTokenBalance());
        await waitFor(() => expect(result.current.loading).toBe(false));
        expect(result.current.tokenStatus.balance).toBe(0);
    });

    it('refresh() updates token balance', async () => {
        // Initial fetch: low balance
        mockApiFetch.mockResolvedValueOnce({
            ok: true,
            json: () => Promise.resolve({
                balance: 5,
                has_purchased: false,
                daily_bonus_available: true,
                cost_generate: 1,
                cost_room: 10,
                ads_remaining_today: 5,
            }),
        });

        const { result } = renderHook(() => useTokenBalance());
        await waitFor(() => expect(result.current.loading).toBe(false));
        expect(result.current.tokenStatus.balance).toBe(5);

        // Refresh: balance increased after purchase
        mockApiFetch.mockResolvedValueOnce({
            ok: true,
            json: () => Promise.resolve({
                balance: 115,
                has_purchased: true,
                daily_bonus_available: false,
                cost_generate: 1,
                cost_room: 10,
                ads_remaining_today: 5,
            }),
        });

        result.current.refresh();
        await waitFor(() => expect(result.current.tokenStatus.balance).toBe(115));
        expect(result.current.tokenStatus.has_purchased).toBe(true);
    });
});
