import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, fireEvent, act } from '@testing-library/react';
import SparkPurchaseModal from '../SparkPurchaseModal';

// Platform + native IAP are mutable so we can exercise web and native-unconfigured builds.
let mockPlatform: 'web' | 'ios' | 'android' = 'web';
let mockIapConfigured = false;
vi.mock('../../utils/platform', () => ({
    getPlatform: () => mockPlatform,
    isNativePlatform: () => mockPlatform !== 'web',
}));
vi.mock('../../utils/iap', () => ({
    isIAPConfigured: () => mockIapConfigured,
    getNativePrices: async () => ({}),
    buySparksNative: async () => ({ status: 'error' as const }),
}));

function checkoutFetch(createResponse: Partial<Response> & { json?: () => Promise<unknown> }) {
    return vi.fn(async (url: string) => {
        const u = String(url);
        if (u.endsWith('/checkout/create')) return createResponse as Response;
        if (u.endsWith('/checkout/token')) {
            return { ok: true, status: 200, json: async () => ({ tokens_added: 200 }) } as Response;
        }
        if (u.endsWith('/tokens/balance')) {
            return { ok: true, status: 200, json: async () => ({ balance: 0 }) } as Response;
        }
        return { ok: false, status: 404, json: async () => ({}) } as Response;
    });
}

describe('SparkPurchaseModal', () => {
    let fetchMock: ReturnType<typeof vi.fn>;

    beforeEach(() => {
        mockPlatform = 'web';
        mockIapConfigured = false;
        vi.useFakeTimers();
        vi.stubGlobal('open', vi.fn());
        fetchMock = checkoutFetch({ ok: true, status: 200, json: async () => ({ checkout_url: 'https://pay', session_id: 'cs_1' }) });
        vi.stubGlobal('fetch', fetchMock);
    });

    afterEach(() => {
        vi.runOnlyPendingTimers();
        vi.useRealTimers();
        vi.unstubAllGlobals();
        vi.restoreAllMocks();
    });

    describe('information a buyer needs before paying', () => {
        beforeEach(() => render(<SparkPurchaseModal onSuccess={() => {}} onClose={() => {}} />));

        it('explains what sparks are and what they cost to use', () => {
            expect(screen.getByText('Get Sparks')).toBeInTheDocument();
            expect(screen.getByText(/Sparks are used to generate quizzes and host games/)).toBeInTheDocument();
            // "What does a spark buy?" — pack sizes are meaningless without this.
            const cost = screen.getByTestId('spark-cost-context');
            expect(cost).toHaveTextContent('Host a game: 10');
            expect(cost).toHaveTextContent('Each AI quiz: 1');
        });

        it('shows all three tiers with amounts, prices and value badges', () => {
            expect(screen.getByText('50')).toBeInTheDocument();
            expect(screen.getByText('200')).toBeInTheDocument();
            expect(screen.getByText('500')).toBeInTheDocument();
            expect(screen.getByText('$1.99')).toBeInTheDocument();
            expect(screen.getByText('$4.99')).toBeInTheDocument();
            expect(screen.getByText('$9.99')).toBeInTheDocument();
            expect(screen.getByText('Popular')).toBeInTheDocument();
            expect(screen.getByText('Best value')).toBeInTheDocument();
        });

        it('discloses purchase terms (one-time, no subscription, no expiry)', () => {
            const terms = screen.getByTestId('spark-purchase-terms');
            expect(terms).toHaveTextContent(/one-time purchase/i);
            expect(terms).toHaveTextContent(/no subscription/i);
            expect(terms).toHaveTextContent(/never expire/i);
        });

        it('offers a no-cost way out', () => {
            expect(screen.getByText('Maybe Later')).toBeInTheDocument();
        });
    });

    describe('web Stripe checkout', () => {
        it('starts checkout with the selected sku, opens Stripe, and credits on poll', async () => {
            const onSuccess = vi.fn();
            render(<SparkPurchaseModal onSuccess={onSuccess} onClose={() => {}} />);

            fireEvent.click(screen.getByText('$4.99').closest('button')!);
            await act(async () => { await vi.advanceTimersByTimeAsync(0); });

            const createCall = fetchMock.mock.calls.find((c) => String(c[0]).endsWith('/checkout/create'));
            expect(JSON.parse((createCall![1] as RequestInit).body as string).sku).toBe('spark_pack_200');
            expect(globalThis.open as unknown as ReturnType<typeof vi.fn>).toHaveBeenCalledWith('https://pay', '_blank');
            expect(screen.getByText(/Waiting for payment/)).toBeInTheDocument();

            await act(async () => { await vi.advanceTimersByTimeAsync(2000); });
            expect(onSuccess).toHaveBeenCalledWith(200);
        });

        it('shows a graceful, reassuring message when payments are unavailable (500)', async () => {
            vi.stubGlobal('fetch', checkoutFetch({ ok: false, status: 500, json: async () => ({}) }));
            render(<SparkPurchaseModal onSuccess={() => {}} onClose={() => {}} />);
            fireEvent.click(screen.getByText('$1.99').closest('button')!);
            await act(async () => { await vi.advanceTimersByTimeAsync(0); });
            expect(screen.getByText(/Payments are not available right now/)).toBeInTheDocument();
        });

        it('redirects the user to in-app purchase when the platform is blocked (403)', async () => {
            vi.stubGlobal('fetch', checkoutFetch({ ok: false, status: 403, json: async () => ({}) }));
            render(<SparkPurchaseModal onSuccess={() => {}} onClose={() => {}} />);
            fireEvent.click(screen.getByText('$9.99').closest('button')!);
            await act(async () => { await vi.advanceTimersByTimeAsync(0); });
            expect(screen.getByText(/use the in-app purchase option/i)).toBeInTheDocument();
        });
    });

    describe('native build with IAP not configured', () => {
        it('hides purchasing and says so rather than showing dead buttons', () => {
            mockPlatform = 'ios';
            mockIapConfigured = false;
            render(<SparkPurchaseModal onSuccess={() => {}} onClose={() => {}} />);
            expect(screen.getByText(/Purchases aren.t available in this build/)).toBeInTheDocument();
            expect(screen.queryByText('$1.99')).not.toBeInTheDocument();
            // still dismissable
            expect(screen.getByText('Maybe Later')).toBeInTheDocument();
        });
    });

    it('calls onClose from Maybe Later', () => {
        const onClose = vi.fn();
        render(<SparkPurchaseModal onSuccess={() => {}} onClose={onClose} />);
        fireEvent.click(screen.getByText('Maybe Later'));
        expect(onClose).toHaveBeenCalled();
    });
});
