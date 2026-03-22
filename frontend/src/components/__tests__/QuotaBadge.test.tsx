import { render, screen } from '@testing-library/react';
import QuotaBadge from '../QuotaBadge';
import type { EntitlementStatus } from '../../hooks/useEntitlement';

const BASE: EntitlementStatus = {
    premium: false,
    status: null,
    games_remaining: 0,
    expires_at: null,
    free_games_used: 0,
    free_games_limit: 3,
    pending_purchase: false,
};

describe('QuotaBadge', () => {
    it('renders nothing when loading', () => {
        const { container } = render(<QuotaBadge entitlement={BASE} loading={true} />);
        expect(container.innerHTML).toBe('');
    });

    it('shows free games used count', () => {
        render(<QuotaBadge entitlement={{ ...BASE, free_games_used: 1 }} loading={false} />);
        expect(screen.getByText('1 of 3 free games used')).toBeInTheDocument();
    });

    it('shows exhausted state when limit reached', () => {
        const { container } = render(
            <QuotaBadge entitlement={{ ...BASE, free_games_used: 3 }} loading={false} />
        );
        expect(container.querySelector('.quota-badge-exhausted')).not.toBeNull();
    });

    it('shows premium games remaining', () => {
        render(
            <QuotaBadge
                entitlement={{ ...BASE, premium: true, games_remaining: 42 }}
                loading={false}
            />
        );
        expect(screen.getByText('42 games remaining')).toBeInTheDocument();
    });

    it('shows singular "game" for 1 remaining', () => {
        render(
            <QuotaBadge
                entitlement={{ ...BASE, premium: true, games_remaining: 1 }}
                loading={false}
            />
        );
        expect(screen.getByText('1 game remaining')).toBeInTheDocument();
    });

    it('applies premium class for premium users', () => {
        const { container } = render(
            <QuotaBadge
                entitlement={{ ...BASE, premium: true, games_remaining: 10 }}
                loading={false}
            />
        );
        expect(container.querySelector('.quota-badge-premium')).not.toBeNull();
    });
});
