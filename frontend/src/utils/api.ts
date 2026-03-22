/**
 * Shared fetch wrapper that attaches device/platform headers to every API call.
 */
import { API_URL } from '../config';
import { getDeviceId, getPremiumToken, getSessionToken } from './storage';

function getPlatform(): string {
    // Only report ios/android for native Capacitor apps.
    // Mobile Safari/Chrome users are "web" — they should use Stripe, not IAP.
    if ((window as Record<string, unknown>).Capacitor) {
        const cap = (window as Record<string, unknown>).Capacitor as Record<string, unknown>;
        if (typeof cap.isNativePlatform === 'function' && (cap.isNativePlatform as () => boolean)()) {
            const platform = cap.getPlatform ? (cap.getPlatform as () => string)() : '';
            if (platform === 'ios') return 'ios';
            if (platform === 'android') return 'android';
        }
    }
    return 'web';
}

const APP_VERSION = import.meta.env.VITE_APP_VERSION || '1.0.0';
const APP_BUILD = import.meta.env.VITE_APP_BUILD || '1';

export function apiHeaders(extra?: Record<string, string>): Record<string, string> {
    const headers: Record<string, string> = {
        'Content-Type': 'application/json',
        'X-Device-Id': getDeviceId(),
        'X-Platform': getPlatform(),
        'X-App-Version': APP_VERSION,
        'X-Build': APP_BUILD,
    };
    const token = getPremiumToken();
    if (token) {
        headers['Authorization'] = `Bearer ${token}`;
    }
    const sessionToken = getSessionToken();
    if (sessionToken) {
        headers['X-Session-Token'] = sessionToken;
    }
    if (extra) {
        Object.assign(headers, extra);
    }
    return headers;
}

export function apiUrl(path: string): string {
    return `${API_URL}${path}`;
}

export async function apiFetch(path: string, options: RequestInit = {}): Promise<Response> {
    const headers = apiHeaders(options.headers as Record<string, string> | undefined);
    return fetch(apiUrl(path), {
        ...options,
        headers,
    });
}

export function generateIdempotencyKey(): string {
    return crypto.randomUUID();
}
