import { render, screen } from '@testing-library/react';
import { rulesForGame, type GameRules } from '../../gameRules';
import GameRulesModal from '../GameRulesModal';

it('shows Mafia objective, night/day flow, winning rules, and privacy while the catalog is unavailable', () => {
    render(<GameRulesModal rules={rulesForGame('mafia', [])} onClose={() => {}} />);
    for (const name of ['Objective', 'How it works', 'Scoring and winning', 'Keep private']) {
        expect(screen.getByRole('heading', { name })).toBeInTheDocument();
    }
    expect(screen.getByText('Town wins by eliminating all Mafia.')).toBeInTheDocument();
    expect(screen.getByText(/Night prompts are private/)).toBeInTheDocument();
    expect(screen.getByText('The game ends when a side reaches its win condition.')).toBeInTheDocument();
    expect(screen.getByText('Do not show your role screen unless the game reveals it.')).toBeInTheDocument();
});

it('renders every supplied catalog section and item rather than replacing it with the fallback', () => {
    const catalogRules: GameRules = {
        version: 2, title: 'Current Mafia Rules', summary: 'Rules from the deployed catalog.',
        sections: [
            { id: 'objective', title: 'Objective', items: ['Find the Mafia in the current ruleset.'] },
            { id: 'night', title: 'Night actions', items: ['Choose your private target.', 'Answer a Night Read.'] },
            { id: 'win', title: 'Winning', items: ['Town wins after all Mafia are eliminated.'] },
        ],
    };
    render(<GameRulesModal rules={rulesForGame('mafia', [{ id: 'mafia', rules: catalogRules }])} onClose={() => {}} />);
    expect(screen.getByRole('heading', { name: catalogRules.title })).toBeInTheDocument();
    for (const section of catalogRules.sections) {
        expect(screen.getByRole('heading', { name: section.title })).toBeInTheDocument();
        for (const item of section.items) expect(screen.getByText(item)).toBeInTheDocument();
    }
    expect(screen.queryByRole('heading', { name: 'Keep private' })).not.toBeInTheDocument();
});
