/**
 * Authentication utilities — Google/Apple sign-in flows.
 */
import { apiUrl, apiHeaders } from './api';
import { getDeviceId, setSessionToken, setUserProfile, signOut, type UserProfile } from './storage';

export interface SignInResult {
    user: UserProfile;
    session_token: string;
}

export type UserProfileResult = { user: UserProfile; tokens: Record<string, unknown> };
export type FetchUserProfileResult =
    | UserProfileResult
    | { unauthorized: true }
    | { unavailable: true };

export async function signInWithBackend(provider: 'google' | 'apple', idToken: string): Promise<SignInResult> {
    const res = await fetch(apiUrl('/auth/signin'), {
        method: 'POST',
        headers: apiHeaders(),
        body: JSON.stringify({
            provider,
            id_token: idToken,
            device_id: getDeviceId(),
        }),
    });
    if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: 'Sign-in failed' }));
        throw new Error(err.detail || 'Sign-in failed');
    }
    let data: SignInResult;
    try {
        data = await res.json();
    } catch {
        throw new Error('Invalid server response');
    }
    if (!data.session_token || !data.user) {
        throw new Error('Incomplete sign-in response');
    }
    setSessionToken(data.session_token);
    setUserProfile(data.user);
    return data;
}

export async function fetchUserProfile(): Promise<FetchUserProfileResult> {
    let timeoutId: ReturnType<typeof setTimeout> | undefined;
    try {
        const controller = new AbortController();
        timeoutId = setTimeout(() => controller.abort(), 15000);
        const res = await fetch(apiUrl('/auth/me'), {
            headers: apiHeaders(),
            signal: controller.signal,
        });
        if (res.status === 401 || res.status === 403) return { unauthorized: true };
        if (!res.ok) return { unavailable: true };
        return await res.json();
    } catch {
        return { unavailable: true };
    } finally {
        if (timeoutId) clearTimeout(timeoutId);
    }
}

export { signOut };
