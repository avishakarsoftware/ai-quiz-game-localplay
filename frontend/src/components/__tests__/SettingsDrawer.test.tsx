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
});
