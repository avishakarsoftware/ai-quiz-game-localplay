import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import SettingsDrawer from '../SettingsDrawer';

vi.mock('../../utils/sound', () => ({
    soundManager: {
        muted: false,
        vibrationEnabled: true,
        toggleMute: vi.fn(() => true),
        toggleVibration: vi.fn(() => false),
        play: vi.fn(),
        vibrate: vi.fn(),
    },
}));

vi.mock('../../context/AuthContext', () => ({
    useAuth: () => ({
        user: null,
        loading: false,
        signIn: vi.fn(),
        signOut: vi.fn(),
    }),
}));

vi.mock('../../utils/analytics', () => ({
    track: vi.fn(),
}));

vi.mock('@capgo/capacitor-social-login', () => ({
    SocialLogin: {
        login: vi.fn(),
    },
}));

describe('SettingsDrawer', () => {
    it('renders the settings trigger button', () => {
        render(<SettingsDrawer />);
        expect(screen.getByTitle('Settings')).toBeInTheDocument();
    });

    it('opens drawer on trigger click', async () => {
        const user = userEvent.setup();
        const { container } = render(<SettingsDrawer />);

        await user.click(screen.getByTitle('Settings'));

        const drawer = container.querySelector('.settings-drawer');
        expect(drawer).toHaveClass('settings-drawer-open');
    });

    it('shows Settings heading when open', async () => {
        const user = userEvent.setup();
        render(<SettingsDrawer />);

        await user.click(screen.getByTitle('Settings'));

        expect(screen.getByText('Settings')).toBeInTheDocument();
    });

    it('shows Sound and Vibration labels', async () => {
        const user = userEvent.setup();
        render(<SettingsDrawer />);

        await user.click(screen.getByTitle('Settings'));

        expect(screen.getByText('Sound')).toBeInTheDocument();
        expect(screen.getByText('Vibration')).toBeInTheDocument();
    });

    it('closes drawer on Escape key', async () => {
        const user = userEvent.setup();
        const { container } = render(<SettingsDrawer />);

        await user.click(screen.getByTitle('Settings'));
        expect(container.querySelector('.settings-drawer')).toHaveClass('settings-drawer-open');

        await user.keyboard('{Escape}');
        expect(container.querySelector('.settings-drawer')).not.toHaveClass('settings-drawer-open');
    });

    it('closes drawer on backdrop click', async () => {
        const user = userEvent.setup();
        const { container } = render(<SettingsDrawer />);

        await user.click(screen.getByTitle('Settings'));
        expect(container.querySelector('.settings-drawer')).toHaveClass('settings-drawer-open');

        const backdrop = container.querySelector('.settings-backdrop');
        expect(backdrop).not.toBeNull();
        await user.click(backdrop!);

        expect(container.querySelector('.settings-drawer')).not.toHaveClass('settings-drawer-open');
    });

    it('shows version text', async () => {
        const user = userEvent.setup();
        render(<SettingsDrawer />);

        await user.click(screen.getByTitle('Settings'));

        expect(screen.getByText('Revelry Quiz v1.0')).toBeInTheDocument();
    });

    it('shows sign-in prompt when not signed in', async () => {
        const user = userEvent.setup();
        render(<SettingsDrawer />);

        await user.click(screen.getByTitle('Settings'));

        expect(screen.getByText(/sign in to keep your party pass/i)).toBeInTheDocument();
    });

    it('shows sign-in coming soon when no client IDs configured', async () => {
        const user = userEvent.setup();
        render(<SettingsDrawer />);

        await user.click(screen.getByTitle('Settings'));

        // No GOOGLE_CLIENT_ID or APPLE_CLIENT_ID in test env → fallback message
        expect(screen.getByText(/sign-in coming soon/i)).toBeInTheDocument();
    });

    it('shows privacy policy link', async () => {
        const user = userEvent.setup();
        render(<SettingsDrawer />);

        await user.click(screen.getByTitle('Settings'));

        const link = screen.getByText('Privacy Policy');
        expect(link).toBeInTheDocument();
        expect(link).toHaveAttribute('href', 'privacy.html');
    });
});

describe('SettingsDrawer (signed in)', () => {
    beforeEach(() => {
        vi.resetModules();
    });

    it('shows signed-in state with sign out button', async () => {
        vi.mocked(await import('../../context/AuthContext')).useAuth = vi.fn(() => ({
            user: { id: '1', provider: 'google', email: 'test@test.com' },
            loading: false,
            signIn: vi.fn(),
            signOut: vi.fn(),
        })) as ReturnType<typeof vi.fn>;

        const user = userEvent.setup();
        render(<SettingsDrawer />);

        await user.click(screen.getByTitle('Settings'));

        expect(screen.getByText('Signed in')).toBeInTheDocument();
        expect(screen.getByText('test@test.com')).toBeInTheDocument();
        expect(screen.getByText('Sign Out')).toBeInTheDocument();
    });
});
