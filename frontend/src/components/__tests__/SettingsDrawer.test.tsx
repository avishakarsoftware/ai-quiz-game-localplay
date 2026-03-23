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

vi.mock('../../hooks/useTokenBalance', () => ({
    useTokenBalance: () => ({
        tokenStatus: { balance: 42, has_purchased: false, daily_bonus_available: false, cost_generate: 1, cost_room: 10 },
        loading: false,
        refresh: vi.fn(),
    }),
}));

vi.mock('@capgo/capacitor-social-login', () => ({
    SocialLogin: {
        login: vi.fn(),
    },
}));

describe('SettingsDrawer', () => {
    it('renders the menu trigger button', () => {
        render(<SettingsDrawer />);
        expect(screen.getByTitle('Menu')).toBeInTheDocument();
    });

    it('opens drawer on trigger click', async () => {
        const user = userEvent.setup();
        const { container } = render(<SettingsDrawer />);

        await user.click(screen.getByTitle('Menu'));

        const drawer = container.querySelector('.settings-drawer');
        expect(drawer).toHaveClass('settings-drawer-open');
    });

    it('shows Menu heading when open', async () => {
        const user = userEvent.setup();
        render(<SettingsDrawer />);

        await user.click(screen.getByTitle('Menu'));

        expect(screen.getByText('Menu')).toBeInTheDocument();
    });

    it('shows Home button in drawer', async () => {
        const user = userEvent.setup();
        render(<SettingsDrawer />);

        await user.click(screen.getByTitle('Menu'));

        expect(screen.getByText('Home')).toBeInTheDocument();
    });

    it('shows Sound and Vibration labels', async () => {
        const user = userEvent.setup();
        render(<SettingsDrawer />);

        await user.click(screen.getByTitle('Menu'));

        expect(screen.getByText('Sound')).toBeInTheDocument();
        expect(screen.getByText('Vibration')).toBeInTheDocument();
    });

    it('closes drawer on Escape key', async () => {
        const user = userEvent.setup();
        const { container } = render(<SettingsDrawer />);

        await user.click(screen.getByTitle('Menu'));
        expect(container.querySelector('.settings-drawer')).toHaveClass('settings-drawer-open');

        await user.keyboard('{Escape}');
        expect(container.querySelector('.settings-drawer')).not.toHaveClass('settings-drawer-open');
    });

    it('closes drawer on backdrop click', async () => {
        const user = userEvent.setup();
        const { container } = render(<SettingsDrawer />);

        await user.click(screen.getByTitle('Menu'));
        expect(container.querySelector('.settings-drawer')).toHaveClass('settings-drawer-open');

        const backdrop = container.querySelector('.settings-backdrop');
        expect(backdrop).not.toBeNull();
        await user.click(backdrop!);

        expect(container.querySelector('.settings-drawer')).not.toHaveClass('settings-drawer-open');
    });

    it('shows version text', async () => {
        const user = userEvent.setup();
        render(<SettingsDrawer />);

        await user.click(screen.getByTitle('Menu'));

        expect(screen.getByText('Revelry Quiz v1.0')).toBeInTheDocument();
    });

    it('shows sign-in prompt when not signed in', async () => {
        const user = userEvent.setup();
        render(<SettingsDrawer />);

        await user.click(screen.getByTitle('Menu'));

        expect(screen.getByText(/sign in to sync your sparks/i)).toBeInTheDocument();
    });

    it('shows sign-in prompt when no client IDs configured', async () => {
        const user = userEvent.setup();
        render(<SettingsDrawer />);

        await user.click(screen.getByTitle('Menu'));

        expect(screen.getByText(/sign in to sync your sparks/i)).toBeInTheDocument();
    });

    it('shows privacy policy link', async () => {
        const user = userEvent.setup();
        render(<SettingsDrawer />);

        await user.click(screen.getByTitle('Menu'));

        const link = screen.getByText('Privacy Policy');
        expect(link).toBeInTheDocument();
        expect(link).toHaveAttribute('href', 'privacy.html');
    });

    it('dispatches navigate-home event when Home is clicked', async () => {
        const user = userEvent.setup();
        const handler = vi.fn();
        window.addEventListener('navigate-home', handler);

        render(<SettingsDrawer />);
        await user.click(screen.getByTitle('Menu'));
        await user.click(screen.getByText('Home'));

        expect(handler).toHaveBeenCalledTimes(1);
        window.removeEventListener('navigate-home', handler);
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

        await user.click(screen.getByTitle('Menu'));

        expect(screen.getByText('Signed in')).toBeInTheDocument();
        expect(screen.getByText('test@test.com')).toBeInTheDocument();
        expect(screen.getByText('Sign Out')).toBeInTheDocument();
    });
});
