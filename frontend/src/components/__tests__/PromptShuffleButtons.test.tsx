import { fireEvent, render, screen } from '@testing-library/react';
import BingoPromptScreen from '../organizer/BingoPromptScreen';
import DrawingPromptScreen from '../organizer/DrawingPromptScreen';
import MLTPromptScreen from '../organizer/MLTPromptScreen';
import PromptScreen from '../organizer/PromptScreen';
import QuizVariantPromptScreen from '../organizer/QuizVariantPromptScreen';
import { getGameModeConfig } from '../../gameModes';

const providers = [{ id: 'gemini', name: 'Gemini 2.5 Flash Lite', description: '', available: true }];

describe('AI prompt shuffle affordances', () => {
    it('fills the AI Quiz prompt from the visible dice button', () => {
        const setPrompt = vi.fn();
        render(
            <PromptScreen
                prompt=""
                setPrompt={setPrompt}
                difficulty="medium"
                setDifficulty={() => {}}
                numQuestions={10}
                setNumQuestions={() => {}}
                provider="gemini"
                setProvider={() => {}}
                providers={providers}
                onGenerate={() => {}}
                onBack={() => {}}
            />,
        );

        fireEvent.click(screen.getByRole('button', { name: 'Suggest a random topic' }));

        expect(setPrompt).toHaveBeenCalledWith(expect.any(String));
    });

    it('fills quiz variant prompts from the visible dice button', () => {
        const setPrompt = vi.fn();
        render(
            <QuizVariantPromptScreen
                config={getGameModeConfig('fact_fiction')}
                prompt=""
                setPrompt={setPrompt}
                difficulty="medium"
                setDifficulty={() => {}}
                numQuestions={10}
                setNumQuestions={() => {}}
                provider="gemini"
                setProvider={() => {}}
                providers={providers}
                onGenerate={() => {}}
                onBack={() => {}}
            />,
        );

        fireEvent.click(screen.getByRole('button', { name: 'Suggest a random topic' }));

        expect(setPrompt).toHaveBeenCalledWith(expect.any(String));
    });

    it('fills Most Likely To prompts from the visible dice button', () => {
        const setPrompt = vi.fn();
        render(
            <MLTPromptScreen
                prompt=""
                setPrompt={setPrompt}
                difficulty="party"
                setDifficulty={() => {}}
                numRounds={10}
                setNumRounds={() => {}}
                provider="gemini"
                setProvider={() => {}}
                providers={providers}
                onGenerate={() => {}}
                onBack={() => {}}
            />,
        );

        fireEvent.click(screen.getByRole('button', { name: 'Suggest a random theme' }));

        expect(setPrompt).toHaveBeenCalledWith(expect.any(String));
    });

    it('fills shared drawing-style prompts from the visible dice button', () => {
        const setPrompt = vi.fn();
        render(
            <DrawingPromptScreen
                prompt=""
                setPrompt={setPrompt}
                difficulty="medium"
                setDifficulty={() => {}}
                numPrompts={10}
                setNumPrompts={() => {}}
                provider="gemini"
                setProvider={() => {}}
                providers={providers}
                onGenerate={() => {}}
                onBack={() => {}}
                title="Who Am I?"
                generateLabel="Generate Clues"
            />,
        );

        fireEvent.click(screen.getByRole('button', { name: 'Suggest a random topic' }));

        expect(setPrompt).toHaveBeenCalledWith(expect.any(String));
    });

    it('fills Bingo prompts from the visible dice button', () => {
        const setPrompt = vi.fn();
        render(
            <BingoPromptScreen
                prompt=""
                setPrompt={setPrompt}
                difficulty="medium"
                setDifficulty={() => {}}
                numItems={24}
                setNumItems={() => {}}
                provider="gemini"
                setProvider={() => {}}
                providers={providers}
                onGenerate={() => {}}
                onCreateCustom={() => {}}
                onBack={() => {}}
            />,
        );

        fireEvent.click(screen.getByRole('button', { name: 'Suggest a random topic' }));

        expect(setPrompt).toHaveBeenCalledWith(expect.any(String));
    });
});
