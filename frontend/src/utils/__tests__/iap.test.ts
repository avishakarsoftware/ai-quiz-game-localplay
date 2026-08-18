import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

/**
 * `utils/iap.ts` — the native purchase wrapper — was at **13.4% coverage**, the worst-covered
 * module of any size in the frontend (ANALYSIS-2026-08-09-coverage.md §4). It is also the module
 * that decides whether a paying customer's tap reaches the store at all, and its logic is entirely
 * about *classifying store responses*: cancelled vs failed, matched vs unavailable. Those branches
 * are pure and cheap to test, which makes this the best value-per-line target in the frontend.
 *
 * The RevenueCat plugin is behind a dynamic `import()`, so it is mocked here — the point is our
 * classification and package-matching logic, not the vendor SDK.
 */

// Mutable platform + env so the same suite covers web, native-unconfigured and native-ready.
let mockPlatform: 'web' | 'ios' | 'android' = 'ios';
vi.mock('../platform', () => ({
    getPlatform: () => mockPlatform,
    isNativePlatform: () => mockPlatform !== 'web',
}));
vi.mock('../storage', () => ({
    getDeviceId: () => 'device-abc',
    getUserProfile: () => null,
}));

// Explicit signatures matter here: `vi.fn(async () => ({ availablePackages: [] }))` would infer
// `never[]` and a narrow object type, so every later mockResolvedValue with a real offerings shape
// fails `tsc -b` (vitest itself does not typecheck, so this only shows up in the build).
type AnyFn = (...args: never[]) => Promise<unknown>;
const purchases = {
    configure: vi.fn<AnyFn>(async () => undefined),
    logIn: vi.fn<AnyFn>(async () => ({})),
    logOut: vi.fn<AnyFn>(async () => ({})),
    getOfferings: vi.fn<AnyFn>(async () => ({ offerings: { current: { availablePackages: [] } } })),
    purchasePackage: vi.fn<AnyFn>(async () => ({})),
    restorePurchases: vi.fn<AnyFn>(async () => ({})),
};
vi.mock('@revenuecat/purchases-capacitor', () => ({ Purchases: purchases }));

function pkg(identifier: string, priceString = '$0.99') {
    return { identifier, product: { identifier, priceString } };
}

async function freshIap() {
    // The module memoises the plugin and its configured flag, so each test needs a clean copy.
    vi.resetModules();
    return import('../iap');
}

describe('utils/iap', () => {
    beforeEach(() => {
        mockPlatform = 'ios';
        vi.stubEnv('VITE_REVENUECAT_IOS_KEY', 'appl_testkey');
        vi.stubEnv('VITE_REVENUECAT_ANDROID_KEY', 'goog_testkey');
        Object.values(purchases).forEach((fn) => fn.mockClear());
        purchases.getOfferings.mockResolvedValue({ offerings: { current: { availablePackages: [] } } });
    });

    afterEach(() => {
        vi.unstubAllEnvs();
        vi.restoreAllMocks();
    });

    describe('isIAPConfigured — the gate the UI hides the buy button on', () => {
        it('is false on web even with keys present', async () => {
            mockPlatform = 'web';
            const iap = await freshIap();
            expect(iap.isIAPConfigured()).toBe(false);
        });

        it('is false on native when the key is missing', async () => {
            vi.stubEnv('VITE_REVENUECAT_IOS_KEY', '');
            const iap = await freshIap();
            expect(iap.isIAPConfigured()).toBe(false);
        });

        it('is true on native with a key', async () => {
            const iap = await freshIap();
            expect(iap.isIAPConfigured()).toBe(true);
        });

        it('reads the ANDROID key on android', async () => {
            mockPlatform = 'android';
            vi.stubEnv('VITE_REVENUECAT_IOS_KEY', '');
            const iap = await freshIap();
            expect(iap.isIAPConfigured()).toBe(true);
        });
    });

    describe('buySparksNative — classifying what the store returns', () => {
        it('refuses on web rather than pretending to buy', async () => {
            mockPlatform = 'web';
            const iap = await freshIap();
            const result = await iap.buySparksNative('spark_pack_50');
            expect(result.status).toBe('error');
            expect(purchases.purchasePackage).not.toHaveBeenCalled();
        });

        it('rejects an unknown sku', async () => {
            const iap = await freshIap();
            const result = await iap.buySparksNative('spark_pack_9999' as never);
            expect(result.status).toBe('error');
            expect(result.message).toMatch(/unknown pack/i);
        });

        it('completes when the store resolves', async () => {
            purchases.getOfferings.mockResolvedValue({
                offerings: { current: { availablePackages: [pkg('me.revelryapp.quiz.sparks_50')] } },
            });
            const iap = await freshIap();
            const result = await iap.buySparksNative('spark_pack_50');
            expect(result.status).toBe('completed');
            expect(purchases.purchasePackage).toHaveBeenCalledOnce();
        });

        it('reports "not available" when no package matches, instead of a crash', async () => {
            purchases.getOfferings.mockResolvedValue({
                offerings: { current: { availablePackages: [pkg('some.other.product')] } },
            });
            const iap = await freshIap();
            const result = await iap.buySparksNative('spark_pack_50');
            expect(result.status).toBe('error');
            expect(result.message).toMatch(/not available/i);
            expect(purchases.purchasePackage).not.toHaveBeenCalled();
        });

        // A user backing out is NOT a failure. Misclassifying it shows an error toast for a
        // deliberate action — and RevenueCat signals cancellation four different ways.
        it.each([
            ['userCancelled flag', { userCancelled: true }],
            ['numeric code 1', { code: 1 }],
            ['string code', { code: 'PURCHASE_CANCELLED' }],
            ['message text', { message: 'The user cancelled the purchase' }],
        ])('treats %s as cancelled, not an error', async (_label, rejection) => {
            purchases.getOfferings.mockResolvedValue({
                offerings: { current: { availablePackages: [pkg('me.revelryapp.quiz.sparks_50')] } },
            });
            purchases.purchasePackage.mockRejectedValueOnce(rejection);
            const iap = await freshIap();
            expect((await iap.buySparksNative('spark_pack_50')).status).toBe('cancelled');
        });

        it('surfaces a genuine store failure as an error with its message', async () => {
            purchases.getOfferings.mockResolvedValue({
                offerings: { current: { availablePackages: [pkg('me.revelryapp.quiz.sparks_50')] } },
            });
            purchases.purchasePackage.mockRejectedValueOnce({ code: 42, message: 'Payment declined' });
            const iap = await freshIap();
            const result = await iap.buySparksNative('spark_pack_50');
            expect(result.status).toBe('error');
            expect(result.message).toBe('Payment declined');
        });

        it('does not throw when getOfferings itself fails', async () => {
            purchases.getOfferings.mockRejectedValueOnce(new Error('network down'));
            const iap = await freshIap();
            const result = await iap.buySparksNative('spark_pack_50');
            expect(result.status).toBe('error');
        });
    });

    describe('getNativePrices — localized store prices', () => {
        it('returns {} on web so the UI falls back to catalog labels', async () => {
            mockPlatform = 'web';
            const iap = await freshIap();
            expect(await iap.getNativePrices()).toEqual({});
        });

        it('maps each pack to its store price string', async () => {
            purchases.getOfferings.mockResolvedValue({
                offerings: {
                    current: {
                        availablePackages: [
                            pkg('me.revelryapp.quiz.sparks_50', '£0.89'),
                            pkg('me.revelryapp.quiz.sparks_200', '£3.99'),
                        ],
                    },
                },
            });
            const iap = await freshIap();
            const prices = await iap.getNativePrices();
            expect(prices.spark_pack_50).toBe('£0.89');
            expect(prices.spark_pack_200).toBe('£3.99');
        });

        it('collects packages from offerings.all, not just current', async () => {
            purchases.getOfferings.mockResolvedValue({
                offerings: {
                    current: { availablePackages: [] },
                    all: { legacy: { availablePackages: [pkg('me.revelryapp.quiz.sparks_50', '$1.29')] } },
                },
            });
            const iap = await freshIap();
            expect((await iap.getNativePrices()).spark_pack_50).toBe('$1.29');
        });

        it('tolerates an unwrapped offerings payload (no .offerings key)', async () => {
            purchases.getOfferings.mockResolvedValue({
                current: { availablePackages: [pkg('me.revelryapp.quiz.sparks_50', '$2.00')] },
            });
            const iap = await freshIap();
            expect((await iap.getNativePrices()).spark_pack_50).toBe('$2.00');
        });

        it('returns {} rather than throwing when the store errors', async () => {
            purchases.getOfferings.mockRejectedValueOnce(new Error('offline'));
            const iap = await freshIap();
            expect(await iap.getNativePrices()).toEqual({});
        });

        it('matches by suffix as a last resort, and says so', async () => {
            const warn = vi.spyOn(console, 'warn').mockImplementation(() => {});
            purchases.getOfferings.mockResolvedValue({
                offerings: { current: { availablePackages: [pkg('com.legacy.bundle.sparks_50', '$0.99')] } },
            });
            const iap = await freshIap();
            expect((await iap.getNativePrices()).spark_pack_50).toBe('$0.99');
            expect(warn).toHaveBeenCalledWith(expect.stringContaining('suffix fallback'));
        });
    });

    describe('restoreNative', () => {
        it('is a no-op returning false on web', async () => {
            mockPlatform = 'web';
            const iap = await freshIap();
            expect(await iap.restoreNative()).toBe(false);
            expect(purchases.restorePurchases).not.toHaveBeenCalled();
        });

        it('returns true when the store restore resolves', async () => {
            const iap = await freshIap();
            expect(await iap.restoreNative()).toBe(true);
        });

        it('returns false when the store restore fails', async () => {
            purchases.restorePurchases.mockRejectedValueOnce(new Error('nope'));
            const iap = await freshIap();
            expect(await iap.restoreNative()).toBe(false);
        });
    });

    describe('identity — appUserID must match the backend wallet id', () => {
        it('configures with the device id when signed out', async () => {
            const iap = await freshIap();
            await iap.initIAP();
            expect(purchases.configure).toHaveBeenCalledWith(
                expect.objectContaining({ appUserID: 'device-abc' }),
            );
        });

        it('logs in and out without throwing on web', async () => {
            mockPlatform = 'web';
            const iap = await freshIap();
            await expect(iap.iapLogIn('user-1')).resolves.toBeUndefined();
            await expect(iap.iapLogOut()).resolves.toBeUndefined();
            expect(purchases.logIn).not.toHaveBeenCalled();
        });

        it('logs in with the user id on native', async () => {
            const iap = await freshIap();
            await iap.initIAP();
            await iap.iapLogIn('user-42');
            expect(purchases.logIn).toHaveBeenCalledWith({ appUserID: 'user-42' });
        });
    });
});
