import { act, render, screen, waitFor } from '@testing-library/react';
import { AuthProvider, useAuth } from '../AuthContext';
import { initIAP } from '../../utils/iap';

const native = vi.hoisted(() => ({
    profile: { id: 'cached-user', email: 'cached@example.com' } as { id: string; email: string } | null,
    fetchUserProfile: vi.fn(),
    configure: vi.fn(async (_options: { appUserID?: string; apiKey: string }) => {}),
    logIn: vi.fn(async (_options: { appUserID: string }) => ({})),
}));

vi.mock('../../utils/storage', () => ({
    getUserProfile: () => native.profile,
    getSessionToken: () => 'cached-session',
    getDeviceId: () => 'device-wallet',
}));
vi.mock('../../utils/auth', () => ({
    fetchUserProfile: native.fetchUserProfile,
    signInWithBackend: vi.fn(),
    signOut: () => { native.profile = null; },
}));
vi.mock('../../utils/analytics', () => ({ track: vi.fn(), identify: vi.fn(), resetIdentity: vi.fn() }));
vi.mock('../../utils/platform', () => ({ getPlatform: () => 'ios' }));
vi.mock('@revenuecat/purchases-capacitor', () => ({
    Purchases: { configure: native.configure, logIn: native.logIn },
}));

it('switches an initialized cached native wallet to the device when account verification rejects it', async () => {
    vi.stubEnv('VITE_REVENUECAT_IOS_KEY', 'test-native-key');
    let rejectSession!: (value: { unauthorized: true }) => void;
    native.fetchUserProfile.mockReturnValue(new Promise((resolve) => { rejectSession = resolve; }));
    const refresh = vi.fn();
    window.addEventListener('refresh-sparks', refresh);
    function Profile() {
        const { user } = useAuth();
        return <span>{user?.email || 'anonymous'}</span>;
    }
    try {
        render(<AuthProvider><Profile /></AuthProvider>);
        // AppShell initializes the native SDK while account verification is still pending.
        await initIAP();
        expect(native.configure).toHaveBeenCalledWith({ apiKey: 'test-native-key', appUserID: 'cached-user' });
        expect(screen.getByText('cached@example.com')).toBeInTheDocument();
        await act(async () => rejectSession({ unauthorized: true }));
        await waitFor(() => expect(native.logIn).toHaveBeenCalledWith({ appUserID: 'device-wallet' }));
        expect(screen.getByText('anonymous')).toBeInTheDocument();
        expect(refresh).toHaveBeenCalledTimes(1);
    } finally {
        window.removeEventListener('refresh-sparks', refresh);
        vi.unstubAllEnvs();
    }
});
