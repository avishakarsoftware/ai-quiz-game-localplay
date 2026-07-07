/**
 * Native social sign-in init for @capgo/capacitor-social-login.
 *
 * The plugin REQUIRES SocialLogin.initialize(...) before login() — without it, native Google/Apple
 * sign-in throws (the provider has no client config). Web sign-in does NOT use this; it uses Google
 * Identity Services / Apple JS directly (see SettingsDrawer), so this is a no-op on web.
 *
 * Client IDs are public (OAuth client ids / Apple Service ID) and come from the build env; cap-build.mjs
 * bakes defaults for native builds.
 */
import { getPlatform } from './platform';

let _ready: Promise<void> | null = null;

/** Configure the native social-login providers once. Resolves immediately on web. */
export function ensureSocialLoginInitialized(): Promise<void> {
    if (getPlatform() === 'web') return Promise.resolve();
    if (_ready) return _ready;
    _ready = (async () => {
        const { SocialLogin } = await import('@capgo/capacitor-social-login');
        const platform = getPlatform();
        const googleWebId = import.meta.env.VITE_GOOGLE_CLIENT_ID || '';
        const googleIosId = import.meta.env.VITE_GOOGLE_IOS_CLIENT_ID || '';
        const appleServiceId = import.meta.env.VITE_APPLE_CLIENT_ID || '';
        const webUrl = import.meta.env.VITE_WEB_URL || '';

        const options: Parameters<typeof SocialLogin.initialize>[0] = {
            google: {
                // webClientId doubles as the serverClientId so the returned ID token's audience
                // matches what the backend verifies (auth.py).
                webClientId: googleWebId,
                ...(googleIosId ? { iOSClientId: googleIosId } : {}),
                mode: 'online',
            },
        };
        if (platform === 'ios') {
            // iOS Apple sign-in uses ASAuthorizationAppleIDProvider and returns the ID token directly.
            // Passing redirectUrl makes the plugin call that URL before resolving, which prevents
            // LocalPlay from receiving the native Apple ID token.
            options.apple = {};
        } else if (appleServiceId) {
            // Android Apple sign-in is web-based and needs the Service ID + redirect URL.
            options.apple = { clientId: appleServiceId, ...(webUrl ? { redirectUrl: webUrl } : {}) };
        }
        await SocialLogin.initialize(options);
    })().catch((e) => {
        _ready = null; // allow a retry on the next attempt
        throw e;
    });
    return _ready;
}
