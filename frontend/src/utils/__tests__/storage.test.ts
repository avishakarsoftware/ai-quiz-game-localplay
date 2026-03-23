import { describe, it, expect, beforeEach } from 'vitest';

// Mock localStorage for this test since Node's built-in localStorage may interfere
const store: Record<string, string> = {};
const mockLocalStorage = {
    getItem: (key: string) => store[key] ?? null,
    setItem: (key: string, value: string) => { store[key] = value; },
    removeItem: (key: string) => { delete store[key]; },
    clear: () => { Object.keys(store).forEach(k => delete store[k]); },
    get length() { return Object.keys(store).length; },
    key: (i: number) => Object.keys(store)[i] ?? null,
};

Object.defineProperty(globalThis, 'localStorage', {
    value: mockLocalStorage,
    writable: true,
    configurable: true,
});

// Import AFTER localStorage mock is set up
const {
    setCheckoutPending, getCheckoutPending,
    setSessionToken, getSessionToken,
    setUserProfile, getUserProfile,
    signOut,
// eslint-disable-next-line @typescript-eslint/no-require-imports
} = await import('../storage');

describe('storage utilities', () => {
    beforeEach(() => {
        mockLocalStorage.clear();
    });

    describe('signOut', () => {
        it('clears session token, user profile, and checkout pending', () => {
            setSessionToken('session-123');
            setUserProfile({ id: '1', provider: 'google', email: 'a@b.com' });
            setCheckoutPending('cs_123');

            expect(getSessionToken()).toBe('session-123');
            expect(getUserProfile()).not.toBeNull();
            expect(getCheckoutPending().pending).toBe(true);

            signOut();

            expect(getSessionToken()).toBeNull();
            expect(getUserProfile()).toBeNull();
            expect(getCheckoutPending().pending).toBe(false);
        });
    });

    describe('user profile', () => {
        it('returns null for corrupted JSON', () => {
            mockLocalStorage.setItem('revelry_user_profile', 'not-json');
            expect(getUserProfile()).toBeNull();
        });

        it('stores and retrieves profile', () => {
            setUserProfile({ id: '1', provider: 'apple', email: 'test@test.com' });
            const profile = getUserProfile();
            expect(profile).not.toBeNull();
            expect(profile!.provider).toBe('apple');
        });
    });
});
