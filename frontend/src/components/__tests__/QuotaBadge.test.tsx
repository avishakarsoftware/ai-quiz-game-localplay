import { render, screen } from '@testing-library/react';
import TokenBadge from '../TokenBadge';
import type { TokenStatus } from '../../hooks/useTokenBalance';

const BASE: TokenStatus = {
    balance: 0,
    has_purchased: false,
    daily_bonus_available: false,
    cost_generate: 1,
    cost_room: 10,
};

describe('TokenBadge', () => {
    it('renders nothing when loading', () => {
        const { container } = render(<TokenBadge tokenStatus={BASE} loading={true} />);
        expect(container.innerHTML).toBe('');
    });

    it('shows spark count', () => {
        render(<TokenBadge tokenStatus={{ ...BASE, balance: 42 }} loading={false} />);
        expect(screen.getByText('42 sparks')).toBeInTheDocument();
    });

    it('shows singular "spark" for balance of 1', () => {
        render(<TokenBadge tokenStatus={{ ...BASE, balance: 1 }} loading={false} />);
        expect(screen.getByText('1 spark')).toBeInTheDocument();
    });

    it('shows exhausted state when balance is 0', () => {
        const { container } = render(<TokenBadge tokenStatus={BASE} loading={false} />);
        expect(container.querySelector('.quota-badge-exhausted')).not.toBeNull();
    });

    it('shows warning state when balance is low (< 10)', () => {
        const { container } = render(
            <TokenBadge tokenStatus={{ ...BASE, balance: 5 }} loading={false} />
        );
        expect(container.querySelector('.quota-badge-warning')).not.toBeNull();
    });

    it('shows premium class for normal balance', () => {
        const { container } = render(
            <TokenBadge tokenStatus={{ ...BASE, balance: 42 }} loading={false} />
        );
        expect(container.querySelector('.quota-badge-premium')).not.toBeNull();
    });
});
