import { fireEvent, render, screen } from '@testing-library/react';
import TwoTruthsGame from '../TwoTruthsGame';
import { type TwoTruthsState, type TwoTruthsSubmission } from '../../types';

function submissionState(): TwoTruthsState {
    return {
        phase: 'TT_SUBMISSION',
        config: { game_title: 'Two Truths and a Lie' },
        players: [
            { nickname: 'Avi', avatar: '🐵' },
            { nickname: 'Ruchi', avatar: '🐯' },
            { nickname: 'Ashu', avatar: '🐸' },
        ],
        submitted_players: [],
        submitted_count: 0,
        total_players: 3,
        current_author_id: '',
        current_round: 0,
        total_rounds: 3,
        statements: [],
        votes_count: 0,
        scores: { Avi: 0, Ruchi: 0, Ashu: 0 },
        round_result: null,
        my_vote: '',
        is_author: false,
    };
}

describe('TwoTruthsGame', () => {
    it('allows short unique party statements and one lie', () => {
        const onSubmitStatements = vi.fn();
        render(
            <TwoTruthsGame
                state={submissionState()}
                viewerName="Avi"
                controls="player"
                onSubmitStatements={onSubmitStatements}
            />,
        );

        const inputs = screen.getAllByRole('textbox');
        fireEvent.change(inputs[0], { target: { value: 'Hehe' } });
        fireEvent.change(inputs[1], { target: { value: 'Motu' } });
        fireEvent.change(inputs[2], { target: { value: 'Pakalu' } });

        expect(screen.getByText('Pick one lie, then submit.')).toBeInTheDocument();
        fireEvent.click(screen.getByRole('button', { name: 'Submit Statements' }));

        expect(onSubmitStatements).toHaveBeenCalledWith([
            { text: 'Hehe', is_lie: false },
            { text: 'Motu', is_lie: false },
            { text: 'Pakalu', is_lie: true },
        ]);
    });

    it('does not clobber in-progress edits when another player triggers a broadcast', () => {
        // After this player has submitted, they can keep editing. A broadcast
        // caused by *another* player (same my_submission content, new object
        // reference) must not reset their in-progress edit.
        const mySubmission = (): TwoTruthsSubmission => ({
            player_id: 'Avi',
            statements: [
                { id: 's0', text: 'Alpha', display_order: 0, is_lie: false },
                { id: 's1', text: 'Beta', display_order: 1, is_lie: false },
                { id: 's2', text: 'Gamma', display_order: 2, is_lie: true },
            ],
        });
        const base: TwoTruthsState = {
            ...submissionState(),
            submitted_players: ['Avi'],
            submitted_count: 1,
            my_submission: mySubmission(),
        };

        const { rerender } = render(
            <TwoTruthsGame state={base} viewerName="Avi" controls="player" onSubmitStatements={() => {}} />,
        );

        // Form is pre-filled from the prior submission.
        const inputs = () => screen.getAllByRole('textbox');
        expect((inputs()[0] as HTMLInputElement).value).toBe('Alpha');

        // Player edits the first statement.
        fireEvent.change(inputs()[0], { target: { value: 'Alpha edited' } });
        expect((inputs()[0] as HTMLInputElement).value).toBe('Alpha edited');

        // Another player submits -> server rebroadcasts. my_submission content is
        // identical but is a brand-new object (fresh JSON parse each frame).
        rerender(
            <TwoTruthsGame
                state={{ ...base, submitted_count: 2, submitted_players: ['Avi', 'Ruchi'], my_submission: mySubmission() }}
                viewerName="Avi"
                controls="player"
                onSubmitStatements={() => {}}
            />,
        );

        // The edit must survive.
        expect((inputs()[0] as HTMLInputElement).value).toBe('Alpha edited');
    });

    it('explains why duplicate statements cannot be submitted', () => {
        render(
            <TwoTruthsGame
                state={submissionState()}
                viewerName="Avi"
                controls="player"
                onSubmitStatements={() => {}}
            />,
        );

        const inputs = screen.getAllByRole('textbox');
        fireEvent.change(inputs[0], { target: { value: 'Same' } });
        fireEvent.change(inputs[1], { target: { value: 'Same' } });
        fireEvent.change(inputs[2], { target: { value: 'Other' } });

        expect(screen.getByText('Make each statement different.')).toBeInTheDocument();
        expect(screen.getByRole('button', { name: 'Submit Statements' })).toBeDisabled();
    });
});
