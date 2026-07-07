import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

async function loadIap(platform: 'web' | 'ios' | 'android') {
    const Purchases = {
        configure: vi.fn().mockResolvedValue(undefined),
        logIn: vi.fn().mockResolvedValue(undefined),
        logOut: vi.fn().mockResolvedValue(undefined),
        getOfferings: vi.fn().mockResolvedValue({}),
        purchasePackage: vi.fn().mockResolvedValue({}),
        restorePurchases: vi.fn().mockResolvedValue({}),
    };

    vi.doMock('../platform', () => ({
        getPlatform: () => platform,
    }));
    vi.doMock('../storage', () => ({
        getDeviceId: () => 'device-wallet-1',
        getUserProfile: () => null,
    }));
    vi.doMock('@revenuecat/purchases-capacitor', () => ({ Purchases }));

    vi.stubEnv('VITE_REVENUECAT_IOS_KEY', 'ios-key');
    vi.stubEnv('VITE_REVENUECAT_ANDROID_KEY', 'android-key');

    const mod = await import('../iap');
    return { Purchases, ...mod };
}

describe('iap identity', () => {
    beforeEach(() => {
        vi.resetModules();
        vi.clearAllMocks();
    });

    afterEach(() => {
        vi.doUnmock('../platform');
        vi.doUnmock('../storage');
        vi.doUnmock('@revenuecat/purchases-capacitor');
        vi.unstubAllEnvs();
    });

    it('switches back to the LocalPlay device wallet on sign-out', async () => {
        const { Purchases, iapLogOut } = await loadIap('ios');

        await iapLogOut();

        expect(Purchases.logIn).toHaveBeenCalledWith({ appUserID: 'device-wallet-1' });
        expect(Purchases.logOut).not.toHaveBeenCalled();
    });
});
