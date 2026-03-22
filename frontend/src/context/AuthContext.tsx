import { createContext, useContext, useState, useEffect, useCallback, type ReactNode } from 'react';
import { getUserProfile, getSessionToken, type UserProfile } from '../utils/storage';
import { signInWithBackend, fetchUserProfile, signOut as storageSignOut } from '../utils/auth';
import { track } from '../utils/analytics';

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
        const token = getSessionToken();
        if (!token) {
            setLoading(false);
            return;
        }
        fetchUserProfile()
            .then(data => {
                if (data?.user) {
                    setUser(data.user);
                } else {
                    // Session expired or invalid
                    storageSignOut();
                    setUser(null);
                }
            })
            .finally(() => setLoading(false));
    }, []);

    const signIn = useCallback(async (provider: 'google' | 'apple', idToken: string) => {
        try {
            const result = await signInWithBackend(provider, idToken);
            setUser(result.user);
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
