import { render, screen } from '@testing-library/react';
import AnimatedNumber from '../AnimatedNumber';

describe('AnimatedNumber', () => {
    it('renders the initial value', () => {
        render(<AnimatedNumber value={100} />);
        expect(screen.getByText('100')).toBeInTheDocument();
    });

    it('renders zero', () => {
        render(<AnimatedNumber value={0} />);
        expect(screen.getByText('0')).toBeInTheDocument();
    });

    it('formats large numbers with locale string', () => {
        render(<AnimatedNumber value={1500} />);
        // toLocaleString() formats 1500 as "1,500" in en-US
        expect(screen.getByText('1,500')).toBeInTheDocument();
    });

    it('applies custom className', () => {
        render(<AnimatedNumber value={42} className="score-text" />);
        const span = screen.getByText('42');
        expect(span).toHaveClass('score-text');
    });

    it('renders as a span element', () => {
        render(<AnimatedNumber value={10} />);
        const el = screen.getByText('10');
        expect(el.tagName).toBe('SPAN');
    });
});
