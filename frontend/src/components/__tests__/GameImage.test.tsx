import { render, screen, fireEvent } from '@testing-library/react';
import GameImage from '../media/GameImage';

describe('GameImage', () => {
    it('renders an accessible image and clears the loading skeleton on load', () => {
        const { container } = render(<GameImage src="/media/img_test" alt="A party cake" />);

        expect(screen.getByAltText('A party cake')).toBeInTheDocument();
        expect(container.querySelector('.game-image-skeleton')).not.toBeNull();

        fireEvent.load(screen.getByAltText('A party cake'));

        expect(container.querySelector('.game-image-skeleton')).toBeNull();
    });

    it('shows a stable error state when the image cannot load', () => {
        render(<GameImage src="/media/missing" alt="Missing game image" />);

        fireEvent.error(screen.getByAltText('Missing game image'));

        expect(screen.getByRole('img', { name: 'Missing game image' })).toHaveTextContent('Image unavailable');
    });

    it('loads the next round image after a previous image failed', () => {
        const { rerender, container } = render(<GameImage src="/media/missing" alt="Round one" />);
        fireEvent.error(screen.getByAltText('Round one'));
        rerender(<GameImage src="/media/next" alt="Round two" />);
        const image = screen.getByAltText('Round two');
        expect(image).toHaveAttribute('src', '/media/next');
        expect(screen.queryByText('Image unavailable')).toBeNull();
        expect(container.querySelector('.game-image-skeleton')).not.toBeNull();
        fireEvent.load(image);
        expect(container.querySelector('.game-image-skeleton')).toBeNull();
    });
});
