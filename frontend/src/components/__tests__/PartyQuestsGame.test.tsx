import { fireEvent, render, screen } from '@testing-library/react';
import PartyQuestsGame from '../PartyQuestsGame';
import { type PartyQuestsState } from '../../types';

function baseState(overrides: Partial<PartyQuestsState> = {}): PartyQuestsState {
    return {
        phase: 'QUESTS_ACTIVE',
        config: {
            game_title: 'Party Quests',
            duration_minutes: 60,
            quests_per_player: 2,
            confirmation_mode: 'tap_confirm',
            allow_late_join: true,
            theme: 'party',
        },
        players: [
            { nickname: 'Avi', avatar: '🐯' },
            { nickname: 'Ruchi', avatar: '🎱' },
        ],
        started_at: 1000,
        ends_at: 4600,
        player_count: 2,
        completed_count: 0,
        pending_count: 0,
        leaderboard: [],
        standings: [],
        awards: [],
        my_board: [
            {
                quest_id: 'quest_1',
                display: 'Find someone who likes cake.',
                category: 'food',
                points: 100,
                status: 'open',
                confirmed_by_player_id: '',
                confirmed_by_name: '',
                completed_at: null,
            },
        ],
        my_score: 0,
        incoming_requests: [],
        outgoing_requests: [],
        ...overrides,
    };
}

describe('PartyQuestsGame', () => {
    it('lets a player request confirmation from another player', () => {
        const onRequestConfirmation = vi.fn();
        render(<PartyQuestsGame state={baseState()} viewerName="Avi" controls="player" onRequestConfirmation={onRequestConfirmation} />);

        fireEvent.change(screen.getByRole('combobox'), { target: { value: 'Ruchi' } });
        fireEvent.click(screen.getByRole('button', { name: 'Ask Confirm' }));

        expect(onRequestConfirmation).toHaveBeenCalledWith('quest_1', 'Ruchi');
    });

    it('shows incoming confirmation requests', () => {
        const onConfirm = vi.fn();
        render(
            <PartyQuestsGame
                state={baseState({
                    incoming_requests: [{
                        id: 'req_1',
                        requester_id: 'Avi',
                        partner_player_id: 'Ruchi',
                        quest_id: 'quest_1',
                        display: 'Find someone who likes cake.',
                        points: 100,
                    }],
                })}
                viewerName="Ruchi"
                controls="player"
                onConfirm={onConfirm}
            />,
        );

        fireEvent.click(screen.getByRole('button', { name: 'Confirm' }));
        expect(onConfirm).toHaveBeenCalledWith('req_1', true);
    });

    it('shows host controls for final call and reveal', () => {
        const onFinalCall = vi.fn();
        const onReveal = vi.fn();
        const onEndGame = vi.fn();
        const onCancelGame = vi.fn();
        render(<PartyQuestsGame state={baseState()} controls="host" onFinalCall={onFinalCall} onReveal={onReveal} onEndGame={onEndGame} onCancelGame={onCancelGame} />);

        fireEvent.click(screen.getByRole('button', { name: 'Final Call' }));
        fireEvent.click(screen.getByRole('button', { name: 'Reveal Scores' }));
        fireEvent.click(screen.getByRole('button', { name: 'End and reveal' }));
        fireEvent.click(screen.getByRole('button', { name: 'Cancel game' }));

        expect(onFinalCall).toHaveBeenCalled();
        expect(onReveal).toHaveBeenCalled();
        expect(onEndGame).toHaveBeenCalled();
        expect(onCancelGame).toHaveBeenCalled();
    });
});
