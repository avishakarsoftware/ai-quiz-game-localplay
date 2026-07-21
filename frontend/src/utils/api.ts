/**
 * Shared fetch wrapper that attaches device/platform headers to every API call.
 */
import { API_URL } from '../config';
import { getDeviceId, getSessionToken } from './storage';
import { getPlatform } from './platform';
import { randomId } from './ids';

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
    return randomId();
}
