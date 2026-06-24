import { fireEvent, render, screen } from '@testing-library/react';
import MafiaGame from '../MafiaGame';
import { type MafiaState } from '../../types';

function baseState(overrides: Partial<MafiaState> = {}): MafiaState {
    return {
        phase: 'MAFIA_NIGHT',
        config: { game_title: 'Mafia' },
        round: 1,
        players: [
            { nickname: 'Avi', avatar: '🐯', alive: true, role: null },
            { nickname: 'Ruchi', avatar: '🎱', alive: true, role: null },
            { nickname: 'Ashu', avatar: '🐸', alive: true, role: null },
        ],
        alive_count: 3,
        eliminated_count: 0,
        deadline: null,
        vote_progress: { submitted: 0, eligible: 0 },
        last_night: null,
        last_vote: null,
        winner: null,
        my_role: 'mafia',
        my_action: {
            kind: 'mafia_kill',
            eligible_targets: ['Ruchi', 'Ashu'],
            submitted_target: '',
            mafia_teammates: [],
            night_read: {
                prompt_id: 'suspect_mafia',
                label: 'Most suspected',
                question: 'Who do you most suspect is Mafia right now?',
                eligible_targets: ['Ruchi', 'Ashu'],
                submitted_target: '',
            },
        },
        my_vote: '',
        my_investigations: [],
        ghost: false,
        ...overrides,
    };
}

describe('MafiaGame', () => {
    it('shows both private night tasks before they are submitted', () => {
        render(<MafiaGame state={baseState()} viewerName="Avi" controls="player" />);

        expect(screen.getByText('Choose your target')).toBeInTheDocument();
        expect(screen.getByText('Answer the Night Read')).toBeInTheDocument();
        expect(screen.getByText('Everyone gets one, so roles stay hidden.')).toBeInTheDocument();
    });

    it('shows submitted night action and night read status', () => {
        render(
            <MafiaGame
                state={baseState({
                    my_action: {
                        kind: 'mafia_kill',
                        eligible_targets: ['Ruchi', 'Ashu'],
                        submitted_target: 'Ruchi',
                        mafia_teammates: [],
                        night_read: {
                            prompt_id: 'suspect_mafia',
                            label: 'Most suspected',
                            question: 'Who do you most suspect is Mafia right now?',
                            eligible_targets: ['Ruchi', 'Ashu'],
                            submitted_target: 'Ashu',
                        },
                    },
                })}
                viewerName="Avi"
                controls="player"
            />,
        );

        expect(screen.getByText('Action submitted')).toBeInTheDocument();
        expect(screen.getByText('Night Read submitted')).toBeInTheDocument();
        expect(screen.getByText('Selected: Ruchi. You can change it until night resolves.')).toBeInTheDocument();
        expect(screen.getByText('Selected: Ashu. You can change it until night resolves.')).toBeInTheDocument();
    });

    it('submits night action and night read selections', () => {
        const onNightAction = vi.fn();
        const onNightRead = vi.fn();
        render(<MafiaGame state={baseState()} viewerName="Avi" controls="player" onNightAction={onNightAction} onNightRead={onNightRead} />);

        fireEvent.click(screen.getAllByRole('button', { name: 'Ruchi' })[0]);
        fireEvent.click(screen.getAllByRole('button', { name: 'Ashu' })[1]);

        expect(onNightAction).toHaveBeenCalledWith('Ruchi');
        expect(onNightRead).toHaveBeenCalledWith('Ashu');
    });
});
