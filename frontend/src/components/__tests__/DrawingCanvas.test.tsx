import { render, screen } from '@testing-library/react';
import DrawingCanvas from '../DrawingCanvas';

function mockCanvasContext() {
    return {
        setTransform: vi.fn(),
        clearRect: vi.fn(),
        beginPath: vi.fn(),
        moveTo: vi.fn(),
        lineTo: vi.fn(),
        stroke: vi.fn(),
        lineCap: 'round',
        lineJoin: 'round',
        strokeStyle: '#111111',
        lineWidth: 5,
    };
}

describe('DrawingCanvas', () => {
    beforeEach(() => {
        vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue(mockCanvasContext() as unknown as CanvasRenderingContext2D);
    });

    afterEach(() => {
        vi.restoreAllMocks();
    });

    it('selects black as the initial drawing color', () => {
        render(<DrawingCanvas ops={[]} drawable />);

        expect(screen.getByRole('button', { name: 'Use color #111111' }).getAttribute('style')).toContain('border: 3px solid var(--accent-primary)');
    });
});
