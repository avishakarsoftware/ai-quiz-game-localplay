/**
 * Storage abstraction — web uses localStorage, native uses Capacitor Preferences.
 * All token/ID reads go through this wrapper so native apps can switch to
 * Keychain (iOS) / Keystore (Android) in the future.
 */
const DEVICE_ID_KEY = 'revelry_device_id';
const PREMIUM_TOKEN_KEY = 'revelry_premium_token';
const CHECKOUT_PENDING_KEY = 'checkout_pending';
const CHECKOUT_SESSION_KEY = 'checkout_session_id';

// For now, always use localStorage. When Capacitor secure-storage plugin
// is added, this wrapper makes the switch transparent.
function get(key: string): string | null {
    try {
        return localStorage.getItem(key);
    } catch {
        return null;
    }
}

function set(key: string, value: string): void {
    try {
        localStorage.setItem(key, value);
    } catch {
        // Storage full or unavailable
    }
}

function remove(key: string): void {
    try {
        localStorage.removeItem(key);
    } catch {
        // Ignore
    }
}

// --- Device ID ---

export function getDeviceId(): string {
    let id = get(DEVICE_ID_KEY);
    if (!id) {
        id = crypto.randomUUID();
        set(DEVICE_ID_KEY, id);
    }
    return id;
}

// --- Premium Token ---

export function getPremiumToken(): string | null {
    return get(PREMIUM_TOKEN_KEY);
}

export function setPremiumToken(token: string): void {
    set(PREMIUM_TOKEN_KEY, token);
}

export function clearPremiumToken(): void {
    remove(PREMIUM_TOKEN_KEY);
}

// --- Checkout Pending ---

export function setCheckoutPending(sessionId: string): void {
    set(CHECKOUT_PENDING_KEY, 'true');
    set(CHECKOUT_SESSION_KEY, sessionId);
}

export function getCheckoutPending(): { pending: boolean; sessionId: string | null } {
    return {
        pending: get(CHECKOUT_PENDING_KEY) === 'true',
        sessionId: get(CHECKOUT_SESSION_KEY),
    };
}

export function clearCheckoutPending(): void {
    remove(CHECKOUT_PENDING_KEY);
    remove(CHECKOUT_SESSION_KEY);
}

// --- Session Token (Auth Phase 2) ---

const SESSION_TOKEN_KEY = 'revelry_session_token';
const USER_PROFILE_KEY = 'revelry_user_profile';

export function getSessionToken(): string | null {
    return get(SESSION_TOKEN_KEY);
}

export function setSessionToken(token: string): void {
    set(SESSION_TOKEN_KEY, token);
}

export function clearSessionToken(): void {
    remove(SESSION_TOKEN_KEY);
}

export interface UserProfile {
    id: string;
    provider: 'google' | 'apple';
    email?: string | null;
}

export function getUserProfile(): UserProfile | null {
    const raw = get(USER_PROFILE_KEY);
    if (!raw) return null;
    try {
        return JSON.parse(raw);
    } catch {
        return null;
    }
}

export function setUserProfile(profile: UserProfile): void {
    set(USER_PROFILE_KEY, JSON.stringify(profile));
}

export function clearUserProfile(): void {
    remove(USER_PROFILE_KEY);
}

export function signOut(): void {
    clearSessionToken();
    clearUserProfile();
}
