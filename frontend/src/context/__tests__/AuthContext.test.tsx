import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { AuthProvider, useAuth } from '../AuthContext';

const mocks = vi.hoisted(() => ({
    getUserProfile: vi.fn(),
    getSessionToken: vi.fn(),
    storageSignOut: vi.fn(),
    signInWithBackend: vi.fn(),
    fetchUserProfile: vi.fn(),
    iapLogIn: vi.fn(),
    iapLogOut: vi.fn(),
    track: vi.fn(),
}));

vi.mock('../../utils/storage', () => ({
    getUserProfile: mocks.getUserProfile,
    getSessionToken: mocks.getSessionToken,
}));

vi.mock('../../utils/auth', () => ({
    signInWithBackend: mocks.signInWithBackend,
    fetchUserProfile: mocks.fetchUserProfile,
    signOut: mocks.storageSignOut,
}));

vi.mock('../../utils/iap', () => ({
    iapLogIn: mocks.iapLogIn,
    iapLogOut: mocks.iapLogOut,
}));

vi.mock('../../utils/analytics', () => ({
    track: mocks.track,
}));

function Harness() {
    const { user, signIn, signOut } = useAuth();
    return (
        <>
            <span>{user?.email || 'anonymous'}</span>
            <button type="button" onClick={() => signIn('google', 'id-token')}>Sign in</button>
            <button type="button" onClick={signOut}>Sign out</button>
        </>
    );
}

describe('AuthProvider', () => {
    beforeEach(() => {
        vi.clearAllMocks();
        mocks.getUserProfile.mockReturnValue(null);
        mocks.getSessionToken.mockReturnValue(null);
        mocks.signInWithBackend.mockResolvedValue({
            user: { id: 'user-1', provider: 'google', email: 'avi@example.com' },
            session_token: 'session-1',
        });
    });

    it('refreshes sparks after sign-in and sign-out', async () => {
        const user = userEvent.setup();
        const refresh = vi.fn();
        window.addEventListener('refresh-sparks', refresh);

        render(<AuthProvider><Harness /></AuthProvider>);

        await user.click(screen.getByRole('button', { name: /sign in/i }));
        await waitFor(() => expect(screen.getByText('avi@example.com')).toBeInTheDocument());

        expect(mocks.iapLogIn).toHaveBeenCalledWith('user-1');
        expect(refresh).toHaveBeenCalledTimes(1);

        await user.click(screen.getByRole('button', { name: /sign out/i }));

        expect(mocks.storageSignOut).toHaveBeenCalledTimes(1);
        expect(mocks.iapLogOut).toHaveBeenCalledTimes(1);
        expect(refresh).toHaveBeenCalledTimes(2);

        window.removeEventListener('refresh-sparks', refresh);
    });
});
