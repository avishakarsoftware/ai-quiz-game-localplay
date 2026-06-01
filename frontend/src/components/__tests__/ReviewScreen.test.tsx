import { fireEvent, render, screen } from '@testing-library/react';
import { type ComponentProps } from 'react';
import ReviewScreen from '../organizer/ReviewScreen';
import { type Quiz } from '../../types';

const quiz: Quiz = {
    quiz_title: 'Preview Quiz',
    questions: [
        {
            id: 1,
            text: 'First question?',
            options: ['Alpha', 'Beta', 'Gamma', 'Delta'],
            answer_index: 0,
            image_prompt: '',
            image_url: '/media/first',
            image_alt: 'First image',
        },
        {
            id: 2,
            text: 'Second question?',
            options: ['One', 'Two', 'Three', 'Four'],
            answer_index: 1,
            image_prompt: '',
        },
        {
            id: 3,
            text: 'Third question?',
            options: ['Red', 'Blue'],
            answer_index: 0,
            image_prompt: '',
        },
    ],
};

function renderReview(overrides: Partial<ComponentProps<typeof ReviewScreen>> = {}) {
    return render(
        <ReviewScreen
            quiz={quiz}
            timeLimit={20}
            setTimeLimit={() => {}}
            sdAvailable={false}
            questionImages={{}}
            onGenerateImages={() => {}}
            onCreateRoom={() => {}}
            onUpdateQuiz={() => {}}
            onBack={() => {}}
            {...overrides}
        />,
    );
}

describe('ReviewScreen', () => {
    it('uses a numbered navigator and selected player-style preview', () => {
        renderReview();

        expect(screen.getByText('First question?')).toBeInTheDocument();
        expect(screen.queryByText('Second question?')).not.toBeInTheDocument();

        fireEvent.click(screen.getByRole('button', { name: 'Question 2' }));
        expect(screen.getByText('Second question?')).toBeInTheDocument();
        expect(screen.queryByText('First question?')).not.toBeInTheDocument();

        fireEvent.click(screen.getByRole('button', { name: 'Next' }));
        expect(screen.getByText('Third question?')).toBeInTheDocument();

        fireEvent.click(screen.getByRole('button', { name: 'Previous' }));
        expect(screen.getByText('Second question?')).toBeInTheDocument();
    });

    it('supports swipe navigation between questions', () => {
        const { container } = renderReview();
        const card = container.querySelector('.review-selected-card');
        expect(card).not.toBeNull();

        fireEvent.touchStart(card!, { touches: [{ clientX: 220 }], changedTouches: [{ clientX: 220 }] });
        fireEvent.touchEnd(card!, { touches: [], changedTouches: [{ clientX: 80 }] });

        expect(screen.getByText('Second question?')).toBeInTheDocument();
    });

    it('shows a generate images action when image generation is available', () => {
        const onGenerateImages = vi.fn();
        renderReview({ sdAvailable: true, onGenerateImages });

        fireEvent.click(screen.getByRole('button', { name: 'Generate Images' }));

        expect(onGenerateImages).toHaveBeenCalled();
    });

    it('makes the correct answer visible when answers are shown', () => {
        renderReview();

        expect(screen.queryByText('Correct')).toBeNull();
        fireEvent.click(screen.getByRole('button', { name: /Show Answers/i }));

        expect(screen.getByText('Correct')).toBeInTheDocument();
        expect(screen.getByText('Answer key visible')).toBeInTheDocument();
        expect(screen.getByRole('button', { name: /Hide Answers/i })).toHaveAttribute('aria-pressed', 'true');
        expect(screen.getByText('Correct').closest('.answer-option')).toHaveClass('review-option-correct');
    });

    it('separates generated variant topics from the game title', () => {
        renderReview({ quiz: { ...quiz, quiz_title: 'Animal Kingdom Odd One Out' } });

        expect(screen.getByRole('heading', { name: 'Odd One Out' })).toBeInTheDocument();
        expect(screen.getByText('Animal Kingdom')).toBeInTheDocument();
    });
});
