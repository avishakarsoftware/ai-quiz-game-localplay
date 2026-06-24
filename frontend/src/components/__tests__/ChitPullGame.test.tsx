import { fireEvent, render, screen } from '@testing-library/react';
import ChitPullGame from '../ChitPullGame';
import { type ChitPullState } from '../../types';

function baseState(overrides: Partial<ChitPullState> = {}): ChitPullState {
    return {
        phase: 'CHIT_ACTIVE',
        config: {
            game_title: 'Birthday Chits',
            rounds: 2,
            turn_time_seconds: 30,
            safe_level: 'family',
            chit_count: 5,
        },
        players: [
            { nickname: 'Alice', avatar: '🐵' },
            { nickname: 'Bob', avatar: '🐯' },
            { nickname: 'Cara', avatar: '🐸' },
        ],
        round_number: 1,
        total_rounds: 2,
        selected_player_id: 'Alice',
        current_chit: {
            id: 'chit_1',
            text: 'Make your best celebration face.',
            category: 'funny_face',
            safe_level: 'family',
        },
        used_chit_ids: [],
        player_turn_counts: { Alice: 0, Bob: 0, Cara: 0 },
        skips_by_player: { Alice: 0, Bob: 0, Cara: 0 },
        scores: { Alice: 0, Bob: 0, Cara: 0 },
        turn_results: [],
        deadline: null,
        ...overrides,
    };
}

describe('ChitPullGame', () => {
    it('uses Random Chit as the default game title', () => {
        render(<ChitPullGame state={baseState({ config: { ...baseState().config, game_title: undefined } })} controls="spectator" />);

        expect(screen.getByText('Random Chit')).toBeInTheDocument();
    });

    it('highlights the selected player and current chit', () => {
        render(<ChitPullGame state={baseState()} viewerName="Alice" controls="player" />);

        expect(screen.getByText('Birthday Chits')).toBeInTheDocument();
        expect(screen.getByText('Alice is up')).toBeInTheDocument();
        expect(screen.getByText('Make your best celebration face.')).toBeInTheDocument();
        expect(screen.getByText("You're up!")).toBeInTheDocument();
    });

    it('shows host controls for resolving and redrawing an active chit', () => {
        const onComplete = vi.fn();
        const onSkip = vi.fn();
        const onRedrawPlayer = vi.fn();
        const onRedrawChit = vi.fn();
        render(
            <ChitPullGame
                state={baseState()}
                controls="host"
                onComplete={onComplete}
                onSkip={onSkip}
                onRedrawPlayer={onRedrawPlayer}
                onRedrawChit={onRedrawChit}
            />,
        );

        fireEvent.click(screen.getByRole('button', { name: 'Completed' }));
        fireEvent.click(screen.getByRole('button', { name: 'Skip' }));
        fireEvent.click(screen.getByRole('button', { name: 'New Player' }));
        fireEvent.click(screen.getByRole('button', { name: 'New Chit' }));

        expect(onComplete).toHaveBeenCalledWith(false);
        expect(onSkip).toHaveBeenCalled();
        expect(onRedrawPlayer).toHaveBeenCalled();
        expect(onRedrawChit).toHaveBeenCalled();
    });

    it('shows pull control between turns', () => {
        const onNext = vi.fn();
        render(
            <ChitPullGame
                state={baseState({
                    phase: 'CHIT_RESULT',
                    selected_player_id: '',
                    current_chit: null,
                    turn_results: [{
                        round_number: 1,
                        player_id: 'Alice',
                        chit_id: 'chit_1',
                        chit_text: 'Make your best celebration face.',
                        category: 'funny_face',
                        outcome: 'completed',
                        bonus: false,
                        points_awarded: 100,
                    }],
                })}
                controls="host"
                onNext={onNext}
            />,
        );

        fireEvent.click(screen.getByRole('button', { name: 'Pull Chit' }));
        expect(onNext).toHaveBeenCalled();
    });
});
