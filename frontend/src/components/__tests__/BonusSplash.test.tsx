import { render, screen, act } from '@testing-library/react';
import BonusSplash from '../BonusSplash';

vi.mock('../../utils/sound', () => ({
    soundManager: {
        play: vi.fn(),
        vibrate: vi.fn(),
    },
}));

describe('BonusSplash', () => {
    beforeEach(() => {
        vi.useFakeTimers();
    });

    afterEach(() => {
        vi.useRealTimers();
    });

    it('renders 2X multiplier text', () => {
        render(<BonusSplash onComplete={vi.fn()} />);
        expect(screen.getByText('2X')).toBeInTheDocument();
    });

    it('renders DOUBLE POINTS title', () => {
        render(<BonusSplash onComplete={vi.fn()} />);
        expect(screen.getByText('DOUBLE POINTS')).toBeInTheDocument();
    });

    it('renders subtitle text', () => {
        render(<BonusSplash onComplete={vi.fn()} />);
        expect(screen.getByText('This round is worth double!')).toBeInTheDocument();
    });

    it('renders 16 burst particles', () => {
        const { container } = render(<BonusSplash onComplete={vi.fn()} />);
        const particles = container.querySelectorAll('.burst-particle');
        expect(particles).toHaveLength(16);
    });

    it('calls onComplete after duration', () => {
        const onComplete = vi.fn();
        render(<BonusSplash onComplete={onComplete} duration={1800} />);

        expect(onComplete).not.toHaveBeenCalled();

        act(() => {
            vi.advanceTimersByTime(1800);
        });

        expect(onComplete).toHaveBeenCalledTimes(1);
    });

    it('adds exiting class 400ms before completion', () => {
        const { container } = render(<BonusSplash onComplete={vi.fn()} duration={1800} />);
        const overlay = container.querySelector('.bonus-splash-overlay');

        expect(overlay).not.toHaveClass('exiting');

        act(() => {
            vi.advanceTimersByTime(1400); // duration - 400 = 1400
        });

        expect(overlay).toHaveClass('exiting');
    });

    it('plays bonusRound sound on mount', async () => {
        const { soundManager } = await import('../../utils/sound');
        render(<BonusSplash onComplete={vi.fn()} />);
        expect(soundManager.play).toHaveBeenCalledWith('bonusRound');
    });

    it('triggers vibration on mount', async () => {
        const { soundManager } = await import('../../utils/sound');
        render(<BonusSplash onComplete={vi.fn()} />);
        expect(soundManager.vibrate).toHaveBeenCalledWith([100, 50, 100, 50, 200]);
    });
});
