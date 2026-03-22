/**
 * Authentication utilities — Google/Apple sign-in flows.
 */
import { apiUrl, apiHeaders } from './api';
import { getDeviceId, setSessionToken, setUserProfile, signOut, type UserProfile } from './storage';

export interface SignInResult {
    user: UserProfile;
    session_token: string;
}

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

export async function fetchUserProfile(): Promise<{ user: UserProfile; entitlement: Record<string, unknown> } | null> {
    try {
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), 5000);
        const res = await fetch(apiUrl('/auth/me'), {
            headers: apiHeaders(),
            signal: controller.signal,
        });
        clearTimeout(timeoutId);
        if (!res.ok) return null;
        return await res.json();
    } catch {
        return null;
    }
}

export { signOut };
