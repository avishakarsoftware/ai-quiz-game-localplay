import { fireEvent, render, screen } from '@testing-library/react';
import TwoTruthsGame from '../TwoTruthsGame';
import { type TwoTruthsState } from '../../types';

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
