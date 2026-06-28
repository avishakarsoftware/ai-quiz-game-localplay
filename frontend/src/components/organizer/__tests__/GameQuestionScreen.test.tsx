import { fireEvent, render, screen } from '@testing-library/react';
import GameQuestionScreen from '../GameQuestionScreen';
import { type Question } from '../../../types';

const question: Question = {
    id: 1,
    text: 'Capital of France?',
    options: ['London', 'Paris', 'Rome', 'Berlin'],
    answer_index: 1,
    image_prompt: '',
};

describe('GameQuestionScreen answer reveal', () => {
    it('highlights the correct option and offers Show Scores in reveal mode', () => {
        const onContinue = vi.fn();
        render(
            <GameQuestionScreen
                question={question}
                questionNumber={1}
                totalQuestions={5}
                timeRemaining={0}
                timeLimit={20}
                revealAnswerIndex={1}
                onContinue={onContinue}
                onEndQuiz={() => {}}
            />,
        );

        // Correct option is marked with a check; the Show Scores control advances.
        expect(screen.getByText(/Paris ✓/)).toBeInTheDocument();
        expect(screen.getByText('✓ Answer')).toBeInTheDocument();
        fireEvent.click(screen.getByRole('button', { name: /Show Scores/ }));
        expect(onContinue).toHaveBeenCalledTimes(1);

        // The live "Next Question" control is not shown during the reveal.
        expect(screen.queryByRole('button', { name: /Next Question/ })).not.toBeInTheDocument();
    });

    it('shows the live timer (not the reveal) when no reveal index is set', () => {
        render(
            <GameQuestionScreen
                question={question}
                questionNumber={1}
                totalQuestions={5}
                timeRemaining={12}
                timeLimit={20}
                onNextQuestion={() => {}}
            />,
        );
        expect(screen.getByText('12s')).toBeInTheDocument();
        expect(screen.queryByText('✓ Answer')).not.toBeInTheDocument();
        expect(screen.queryByText(/Paris ✓/)).not.toBeInTheDocument();
    });
});
