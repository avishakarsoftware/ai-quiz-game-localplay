/**
 * Shared platform detection for payment/IAP gating.
 *
 * Returns the strict surface used to decide Stripe (web) vs in-app purchase (native):
 * only a native Capacitor app reports 'ios'/'android'; mobile Safari/Chrome stays 'web'.
 *
 * NOTE: `utils/analytics.ts` keeps its OWN getPlatform() on purpose — it returns finer
 * telemetry labels ('pwa', 'native'). Do not collapse the two; they answer different questions.
 */
export type LocalPlayPlatform = 'web' | 'ios' | 'android';

export function getPlatform(): LocalPlayPlatform {
    const win = window as unknown as Record<string, unknown>;
    if (win.Capacitor) {
        const cap = win.Capacitor as Record<string, unknown>;
        if (typeof cap.isNativePlatform === 'function' && (cap.isNativePlatform as () => boolean)()) {
            const platform = cap.getPlatform ? (cap.getPlatform as () => string)() : '';
            if (platform === 'ios') return 'ios';
            if (platform === 'android') return 'android';
        }
    }
    return 'web';
}

export function isNativePlatform(): boolean {
    const p = getPlatform();
    return p === 'ios' || p === 'android';
}
