import { render, screen } from '@testing-library/react';
import TimerRing from '../TimerRing';

describe('TimerRing', () => {
    it('renders the remaining time as text', () => {
        render(<TimerRing remaining={15} total={30} />);
        expect(screen.getByText('15')).toBeInTheDocument();
    });

    it('uses primary color when remaining > 10', () => {
        const { container } = render(<TimerRing remaining={20} total={30} />);
        const progressCircle = container.querySelectorAll('circle')[1];
        expect(progressCircle).toHaveAttribute('stroke', 'var(--accent-primary)');
    });

    it('uses warning color when remaining <= 10', () => {
        const { container } = render(<TimerRing remaining={8} total={30} />);
        const progressCircle = container.querySelectorAll('circle')[1];
        expect(progressCircle).toHaveAttribute('stroke', 'var(--accent-warning)');
    });

    it('uses danger color when remaining <= 5', () => {
        const { container } = render(<TimerRing remaining={3} total={30} />);
        const progressCircle = container.querySelectorAll('circle')[1];
        expect(progressCircle).toHaveAttribute('stroke', 'var(--accent-danger)');
    });

    it('adds timer-critical class when remaining <= 5 and > 0', () => {
        const { container } = render(<TimerRing remaining={4} total={30} />);
        expect(container.firstElementChild).toHaveClass('timer-critical');
    });

    it('does not add timer-critical class when remaining is 0', () => {
        const { container } = render(<TimerRing remaining={0} total={30} />);
        expect(container.firstElementChild).not.toHaveClass('timer-critical');
    });

    it('does not add timer-critical class when remaining > 5', () => {
        const { container } = render(<TimerRing remaining={15} total={30} />);
        expect(container.firstElementChild).not.toHaveClass('timer-critical');
    });

    it('calculates correct stroke-dashoffset at full time', () => {
        const { container } = render(<TimerRing remaining={30} total={30} />);
        const progressCircle = container.querySelectorAll('circle')[1];
        // At full time, progress=1, dashOffset = circumference * (1-1) = 0
        expect(progressCircle).toHaveAttribute('stroke-dashoffset', '0');
    });

    it('calculates correct stroke-dashoffset at half time', () => {
        const size = 80;
        const strokeWidth = 4;
        const radius = (size - strokeWidth) / 2;
        const circumference = 2 * Math.PI * radius;

        const { container } = render(<TimerRing remaining={15} total={30} />);
        const progressCircle = container.querySelectorAll('circle')[1];
        const expectedOffset = circumference * 0.5;
        expect(progressCircle).toHaveAttribute('stroke-dashoffset', String(expectedOffset));
    });

    it('uses custom size', () => {
        const { container } = render(<TimerRing remaining={10} total={20} size={120} />);
        const svg = container.querySelector('svg');
        expect(svg).toHaveAttribute('width', '120');
        expect(svg).toHaveAttribute('height', '120');
    });
});
