import { fireEvent, render, screen } from '@testing-library/react';
import SimpleSocialGame from '../SimpleSocialGame';
import { type AcronymState, type WouldYouRatherState } from '../../types';

function acronymVoting(overrides: Partial<AcronymState> = {}): AcronymState {
    return {
        phase: 'ACRONYM_VOTING',
        game_title: 'Acronym',
        current_round_index: 0,
        round_count: 1,
        prompt: { acronym: 'FUN', hint: 'Make it funny' },
        submitted_count: 3,
        vote_count: 0,
        scores: {},
        standings: [],
        your_entry_id: 'entry_mine',
        entries: [
            { entry_id: 'entry_mine', text: 'Funny Unique Notes' },
            { entry_id: 'entry_b', text: 'Free Unlimited Nachos' },
        ],
        ...overrides,
    };
}

describe('SimpleSocialGame — acronym voting', () => {
    it('marks the voter own entry and prevents voting for it', () => {
        const onAcronymVote = vi.fn();
        render(
            <SimpleSocialGame
                gameType="acronym"
                state={acronymVoting()}
                controls="player"
                viewerName="me"
                onAcronymVote={onAcronymVote}
            />,
        );

        const mine = screen.getByRole('button', { name: /your entry/ });
        expect(mine).toBeDisabled();

        const other = screen.getByRole('button', { name: /Free Unlimited Nachos/ });
        fireEvent.click(other);
        expect(onAcronymVote).toHaveBeenCalledWith('entry_b');
    });

    it('locks voting and shows confirmation once a vote is cast', () => {
        render(
            <SimpleSocialGame
                gameType="acronym"
                state={acronymVoting({ your_vote: 'entry_b' })}
                controls="player"
                viewerName="me"
                onAcronymVote={() => {}}
            />,
        );
        expect(screen.getByText('Vote locked.')).toBeInTheDocument();
        // Every entry button is disabled after voting.
        expect(screen.getByRole('button', { name: /Free Unlimited Nachos/ })).toBeDisabled();
    });

    it('explains when there are not enough entries to vote on', () => {
        render(
            <SimpleSocialGame
                gameType="acronym"
                state={acronymVoting({ entries: [{ entry_id: 'entry_mine', text: 'Only mine' }] })}
                controls="player"
                viewerName="me"
                onAcronymVote={() => {}}
            />,
        );
        expect(screen.getByText('Not enough entries to vote on this round.')).toBeInTheDocument();
    });
});

describe('SimpleSocialGame — host reveal guard', () => {
    function wyr(overrides: Partial<WouldYouRatherState> = {}): WouldYouRatherState {
        return {
            phase: 'WYR_VOTING',
            game_title: 'Would You Rather',
            current_round_index: 0,
            round_count: 1,
            prompt: { question: 'Pizza or tacos?', option_a: 'Pizza', option_b: 'Tacos' },
            submitted_votes: 0,
            scores: {},
            standings: [],
            ...overrides,
        };
    }

    it('disables Reveal until at least one player has answered', () => {
        const { rerender } = render(
            <SimpleSocialGame gameType="would_you_rather" state={wyr()} controls="host" onReveal={() => {}} />,
        );
        expect(screen.getByRole('button', { name: 'Reveal' })).toBeDisabled();

        rerender(
            <SimpleSocialGame gameType="would_you_rather" state={wyr({ submitted_votes: 2 })} controls="host" onReveal={() => {}} />,
        );
        expect(screen.getByRole('button', { name: 'Reveal' })).toBeEnabled();
    });
});
