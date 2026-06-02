import { fireEvent, render, screen } from '@testing-library/react';
import CommonGroundGame from '../CommonGroundGame';
import { type CommonGroundState } from '../../types';

function baseState(overrides: Partial<CommonGroundState> = {}): CommonGroundState {
    return {
        phase: 'COMMON_DISCUSSION',
        config: {
            game_title: 'Common Ground',
            rounds: 1,
            vote_category: 'most_surprising',
            voting_enabled: true,
        },
        players: [
            { nickname: 'Alice', avatar: '🐵' },
            { nickname: 'Bob', avatar: '🐯' },
            { nickname: 'Cara', avatar: '🐸' },
            { nickname: 'Dee', avatar: '🦊' },
        ],
        teams: [
            { id: 'team_1', name: 'Team A', player_ids: ['Alice', 'Bob'] },
            { id: 'team_2', name: 'Team B', player_ids: ['Cara', 'Dee'] },
        ],
        round_number: 1,
        total_rounds: 1,
        prompt: { id: 'prompt_1', text: 'Find one food everyone likes.', category: 'food' },
        deadline: null,
        submissions: [
            { id: '', team_id: 'team_1', team_name: 'Team A', submitted_by: '', has_submission: false, vote_count: 0 },
            { id: '', team_id: 'team_2', team_name: 'Team B', submitted_by: '', has_submission: false, vote_count: 0 },
        ],
        votes_count: 0,
        scores: { team_1: 0, team_2: 0 },
        round_results: [],
        my_team_id: 'team_1',
        my_vote: '',
        my_submission: null,
        ...overrides,
    };
}

describe('CommonGroundGame', () => {
    it('lets a player submit a valid shared fact', () => {
        const onSubmitFact = vi.fn();
        render(
            <CommonGroundGame
                state={baseState()}
                viewerName="Alice"
                controls="player"
                onSubmitFact={onSubmitFact}
            />,
        );

        fireEvent.change(screen.getByPlaceholderText('We all...'), { target: { value: 'We all like mangoes.' } });
        fireEvent.click(screen.getByRole('button', { name: 'Submit Answer' }));

        expect(onSubmitFact).toHaveBeenCalledWith('We all like mangoes.');
    });

    it('shows reveal and vote controls for the host at the right phases', () => {
        const onStartVoting = vi.fn();
        render(
            <CommonGroundGame
                state={baseState({
                    phase: 'COMMON_REVEAL',
                    submissions: [
                        { id: 'sub_1', team_id: 'team_1', team_name: 'Team A', submitted_by: 'Alice', has_submission: true, vote_count: 0, text: 'We all like mangoes.' },
                        { id: 'sub_2', team_id: 'team_2', team_name: 'Team B', submitted_by: 'Cara', has_submission: true, vote_count: 0, text: 'We all enjoy spicy snacks.' },
                    ],
                })}
                controls="host"
                onStartVoting={onStartVoting}
            />,
        );

        expect(screen.getByText('We all like mangoes.')).toBeInTheDocument();
        fireEvent.click(screen.getByRole('button', { name: 'Start Voting' }));

        expect(onStartVoting).toHaveBeenCalled();
    });

    it('prevents players from voting for their own team and records another-team vote', () => {
        const onVote = vi.fn();
        render(
            <CommonGroundGame
                state={baseState({
                    phase: 'COMMON_VOTING',
                    submissions: [
                        { id: 'sub_1', team_id: 'team_1', team_name: 'Team A', submitted_by: 'Alice', has_submission: true, vote_count: 0, text: 'We all like mangoes.' },
                        { id: 'sub_2', team_id: 'team_2', team_name: 'Team B', submitted_by: 'Cara', has_submission: true, vote_count: 0, text: 'We all enjoy spicy snacks.' },
                    ],
                })}
                viewerName="Alice"
                controls="player"
                onVote={onVote}
            />,
        );

        expect(screen.getByRole('button', { name: /Team A/ })).toBeDisabled();
        fireEvent.click(screen.getByRole('button', { name: /Team B/ }));

        expect(onVote).toHaveBeenCalledWith('sub_2');
    });
});
