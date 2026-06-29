import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, fireEvent, act } from '@testing-library/react';
import SparkPurchaseModal from '../SparkPurchaseModal';

// Web platform (no Capacitor in jsdom). Mock the native iap module so nothing native is touched.
vi.mock('../../utils/iap', () => ({
    isIAPConfigured: () => false,
    getNativePrices: async () => ({}),
    buySparksNative: async () => ({ status: 'error' as const }),
}));

describe('SparkPurchaseModal (web)', () => {
    let fetchMock: ReturnType<typeof vi.fn>;

    beforeEach(() => {
        vi.useFakeTimers();
        vi.stubGlobal('open', vi.fn());
        fetchMock = vi.fn(async (url: string) => {
            const u = String(url);
            if (u.endsWith('/checkout/create')) {
                return { ok: true, status: 200, json: async () => ({ checkout_url: 'https://pay', session_id: 'cs_1' }) } as Response;
            }
            if (u.endsWith('/checkout/token')) {
                return { ok: true, status: 200, json: async () => ({ tokens_added: 200 }) } as Response;
            }
            return { ok: false, status: 404, json: async () => ({}) } as Response;
        });
        vi.stubGlobal('fetch', fetchMock);
    });

    afterEach(() => {
        vi.runOnlyPendingTimers();
        vi.useRealTimers();
        vi.unstubAllGlobals();
        vi.restoreAllMocks();
    });

    it('renders the three tiers with web price labels', () => {
        render(<SparkPurchaseModal onSuccess={() => {}} onClose={() => {}} />);
        expect(screen.getByText('50')).toBeInTheDocument();
        expect(screen.getByText('200')).toBeInTheDocument();
        expect(screen.getByText('500')).toBeInTheDocument();
        expect(screen.getByText('$1.99')).toBeInTheDocument();
        expect(screen.getByText('$4.99')).toBeInTheDocument();
        expect(screen.getByText('$9.99')).toBeInTheDocument();
    });

    it('starts Stripe checkout with the selected sku and credits on poll', async () => {
        const onSuccess = vi.fn();
        render(<SparkPurchaseModal onSuccess={onSuccess} onClose={() => {}} />);

        // Click the 200-spark tier (find its button via the price label's enclosing button).
        fireEvent.click(screen.getByText('$4.99').closest('button')!);

        // Flush the create fetch (microtasks) + window.open + interval setup.
        await act(async () => { await vi.advanceTimersByTimeAsync(0); });
        const createCall = fetchMock.mock.calls.find((c) => String(c[0]).endsWith('/checkout/create'));
        expect(createCall).toBeTruthy();
        expect(JSON.parse((createCall![1] as RequestInit).body as string).sku).toBe('spark_pack_200');
        expect((globalThis.open as unknown as ReturnType<typeof vi.fn>)).toHaveBeenCalledWith('https://pay', '_blank');

        // First poll tick → /checkout/token returns tokens_added → onSuccess.
        await act(async () => { await vi.advanceTimersByTimeAsync(2000); });
        expect(onSuccess).toHaveBeenCalledWith(200);
    });

    it('calls onClose from Maybe Later', () => {
        const onClose = vi.fn();
        render(<SparkPurchaseModal onSuccess={() => {}} onClose={onClose} />);
        fireEvent.click(screen.getByText('Maybe Later'));
        expect(onClose).toHaveBeenCalled();
    });
});
