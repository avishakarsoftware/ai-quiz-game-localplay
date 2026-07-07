/* eslint-disable react-refresh/only-export-components */
import { createContext, useContext, useState, useEffect, useCallback, type ReactNode } from 'react';
import { getUserProfile, getSessionToken, type UserProfile } from '../utils/storage';
import { signInWithBackend, fetchUserProfile, signOut as storageSignOut } from '../utils/auth';
import { track } from '../utils/analytics';
import { iapLogIn, iapLogOut } from '../utils/iap';

interface AuthState {
    user: UserProfile | null;
    loading: boolean;
    signIn: (provider: 'google' | 'apple', idToken: string) => Promise<void>;
    signOut: () => void;
}

const AuthContext = createContext<AuthState>({
    user: null,
    loading: true,
    signIn: async () => {},
    signOut: () => {},
});

export function AuthProvider({ children }: { children: ReactNode }) {
    const [user, setUser] = useState<UserProfile | null>(getUserProfile());
    const [loading, setLoading] = useState(!!getSessionToken());

    // On mount, verify session is still valid if we have a token
    useEffect(() => {
        if (!getSessionToken()) return;
        let cancelled = false;
        fetchUserProfile()
            .then(data => {
                if (cancelled) return;
                if ('user' in data && data.user) {
                    setUser(data.user);
                } else if ('unauthorized' in data) {
                    storageSignOut();
                    setUser(null);
                }
                // Network/timeout failures keep the cached session. A slow phone network
                // should not silently sign out an otherwise valid user.
            })
            .finally(() => { if (!cancelled) setLoading(false); });
        return () => { cancelled = true; };
    }, []);

    const signIn = useCallback(async (provider: 'google' | 'apple', idToken: string) => {
        try {
            const result = await signInWithBackend(provider, idToken);
            setUser(result.user);
            // Tie RevenueCat purchases to the user wallet (best-effort, native only).
            if (result.user?.id) void iapLogIn(result.user.id);
            track('signed_in', { provider });
        } catch (err) {
            // Clean up any partial state from failed sign-in
            storageSignOut();
            setUser(null);
            throw err;
        }
    }, []);

    const signOut = useCallback(() => {
        storageSignOut();
        setUser(null);
        void iapLogOut();  // revert RevenueCat to the device-scoped wallet (best-effort, native only)
        track('signed_out');
    }, []);

    return (
        <AuthContext.Provider value={{ user, loading, signIn, signOut }}>
            {children}
        </AuthContext.Provider>
    );
}

export function useAuth() {
    return useContext(AuthContext);
}
