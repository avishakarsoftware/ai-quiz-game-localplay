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
});
