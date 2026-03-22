import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import SignInNudge from '../SignInNudge';

// Default: no user signed in
const mockUseAuth = vi.fn(() => ({
    user: null,
    loading: false,
    signIn: vi.fn(),
    signOut: vi.fn(),
}));

vi.mock('../../context/AuthContext', () => ({
    useAuth: () => mockUseAuth(),
}));

describe('SignInNudge', () => {
    beforeEach(() => {
        sessionStorage.clear();
        mockUseAuth.mockReturnValue({
            user: null,
            loading: false,
            signIn: vi.fn(),
            signOut: vi.fn(),
        });
    });

    it('shows nudge for premium users who are not signed in', () => {
        render(<SignInNudge isPremium={true} />);
        expect(screen.getByText(/sign in to keep your party pass/i)).toBeInTheDocument();
    });

    it('shows different message for non-premium users', () => {
        render(<SignInNudge isPremium={false} />);
        expect(screen.getByText(/sign in to save your progress/i)).toBeInTheDocument();
    });

    it('dispatches open-settings event on click', async () => {
        const user = userEvent.setup();
        const handler = vi.fn();
        window.addEventListener('open-settings', handler);
        render(<SignInNudge isPremium={false} />);
        await user.click(screen.getByText(/sign in to save your progress/i));
        expect(handler).toHaveBeenCalledTimes(1);
        window.removeEventListener('open-settings', handler);
    });

    it('does not show for signed-in users', () => {
        mockUseAuth.mockReturnValue({
            user: { id: '1', provider: 'google', email: 'test@test.com' },
            loading: false,
            signIn: vi.fn(),
            signOut: vi.fn(),
        });
        const { container } = render(<SignInNudge isPremium={true} />);
        expect(container.innerHTML).toBe('');
    });

    it('can be dismissed', async () => {
        const user = userEvent.setup();
        const { container } = render(<SignInNudge isPremium={true} />);

        expect(screen.getByText(/sign in to keep your party pass/i)).toBeInTheDocument();

        await user.click(screen.getByTitle('Dismiss'));

        expect(container.innerHTML).toBe('');
    });

    it('stays dismissed across re-renders', () => {
        sessionStorage.setItem('signin_nudge_dismissed', '1');
        const { container } = render(<SignInNudge isPremium={true} />);
        expect(container.innerHTML).toBe('');
    });
});
