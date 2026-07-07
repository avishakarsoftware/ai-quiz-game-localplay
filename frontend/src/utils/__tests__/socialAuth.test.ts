import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

async function loadSocialAuth(platform: 'web' | 'ios' | 'android') {
    const initialize = vi.fn().mockResolvedValue(undefined);

    vi.doMock('../platform', () => ({
        getPlatform: () => platform,
    }));

    vi.doMock('@capgo/capacitor-social-login', () => ({
        SocialLogin: { initialize },
    }));

    vi.stubEnv('VITE_GOOGLE_CLIENT_ID', 'google-web-client');
    vi.stubEnv('VITE_GOOGLE_IOS_CLIENT_ID', 'google-ios-client');
    vi.stubEnv('VITE_APPLE_CLIENT_ID', 'apple-service-id');
    vi.stubEnv('VITE_WEB_URL', 'https://gamesapi-gamma.revelryapp.me');

    const mod = await import('../socialAuth');
    return { initialize, ensureSocialLoginInitialized: mod.ensureSocialLoginInitialized };
}

describe('ensureSocialLoginInitialized', () => {
    beforeEach(() => {
        vi.resetModules();
        vi.clearAllMocks();
    });

    afterEach(() => {
        vi.doUnmock('../platform');
        vi.doUnmock('@capgo/capacitor-social-login');
        vi.unstubAllEnvs();
    });

    it('does nothing on web', async () => {
        const { initialize, ensureSocialLoginInitialized } = await loadSocialAuth('web');

        await ensureSocialLoginInitialized();

        expect(initialize).not.toHaveBeenCalled();
    });

    it('initializes iOS Apple without a redirect URL so the native ID token is returned', async () => {
        const { initialize, ensureSocialLoginInitialized } = await loadSocialAuth('ios');

        await ensureSocialLoginInitialized();

        expect(initialize).toHaveBeenCalledWith({
            google: {
                webClientId: 'google-web-client',
                iOSClientId: 'google-ios-client',
                mode: 'online',
            },
            apple: {},
        });
    });

    it('initializes Android Apple with Service ID and redirect URL', async () => {
        const { initialize, ensureSocialLoginInitialized } = await loadSocialAuth('android');

        await ensureSocialLoginInitialized();

        expect(initialize).toHaveBeenCalledWith({
            google: {
                webClientId: 'google-web-client',
                iOSClientId: 'google-ios-client',
                mode: 'online',
            },
            apple: {
                clientId: 'apple-service-id',
                redirectUrl: 'https://gamesapi-gamma.revelryapp.me',
            },
        });
    });
});
