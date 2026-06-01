import { render, screen, fireEvent } from '@testing-library/react';
import GameSelectScreen from '../organizer/GameSelectScreen';
import QuizVariantPromptScreen from '../organizer/QuizVariantPromptScreen';
import { getGameModeConfig } from '../../gameModes';

describe('quiz variant game modes', () => {
    it('renders all five quiz variant game cards', () => {
        render(<GameSelectScreen onSelect={() => {}} />);

        expect(screen.getByRole('button', { name: /Rebus Rush/ })).toBeInTheDocument();
        expect(screen.getByRole('button', { name: /Emoji Charades/ })).toBeInTheDocument();
        expect(screen.getByRole('button', { name: /Fact or Fiction/ })).toBeInTheDocument();
        expect(screen.getByRole('button', { name: /Timeline Twist/ })).toBeInTheDocument();
        expect(screen.getByRole('button', { name: /Odd One Out/ })).toBeInTheDocument();
    });

    it('selects a variant from the game grid', () => {
        const onSelect = vi.fn();
        render(<GameSelectScreen onSelect={onSelect} />);

        fireEvent.click(screen.getByRole('button', { name: /Rebus Rush/ }));

        expect(onSelect).toHaveBeenCalledWith('rebus');
    });

    it('filters games by category and search text', () => {
        render(<GameSelectScreen onSelect={() => {}} />);

        fireEvent.click(screen.getByRole('button', { name: 'Bingo/Housie' }));
        expect(screen.getByRole('button', { name: /^🎱\s*Housie/ })).toBeInTheDocument();
        expect(screen.queryByRole('button', { name: /Most Likely To/ })).not.toBeInTheDocument();

        fireEvent.change(screen.getByRole('searchbox', { name: 'Search games' }), { target: { value: 'bingo' } });
        expect(screen.queryByRole('button', { name: /^🎱\s*Housie/ })).not.toBeInTheDocument();
        expect(screen.getByRole('button', { name: /^▦\s*Bingo/ })).toBeInTheDocument();
    });

    it('renders tailored variant prompt copy and generate action', () => {
        const onGenerate = vi.fn();
        render(
            <QuizVariantPromptScreen
                config={getGameModeConfig('fact_fiction')}
                prompt=""
                setPrompt={() => {}}
                difficulty="medium"
                setDifficulty={() => {}}
                numQuestions={10}
                setNumQuestions={() => {}}
                provider="gemini"
                setProvider={() => {}}
                providers={[{ id: 'gemini', name: 'Gemini 2.5 Flash Lite', description: '', available: true }]}
                onGenerate={onGenerate}
                onBack={() => {}}
            />,
        );

        expect(screen.getByRole('heading', { name: 'Fact or Fiction' })).toBeInTheDocument();
        expect(screen.getByPlaceholderText('Science myths, history, sports records, office lore...')).toBeInTheDocument();
        expect(screen.getByRole('button', { name: 'Generate Questions' })).toBeDisabled();
    });
});
