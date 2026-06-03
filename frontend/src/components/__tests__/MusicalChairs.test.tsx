import { fireEvent, render, screen } from '@testing-library/react';
import MusicalChairsSetupScreen, { defaultMusicalChairsConfig } from '../organizer/MusicalChairsSetupScreen';
import MusicalChairsGameScreen from '../organizer/MusicalChairsGameScreen';
import MusicalChairsPlayer from '../player/MusicalChairsPlayer';
import { type MusicalChairsState } from '../../types';

const state: MusicalChairsState = {
    game_title: 'Birthday Musical Chairs',
    phase: 'MC_GRAB',
    round_number: 2,
    total_rounds: 4,
    active_players: [
        { nickname: 'Avi', avatar: '🐯' },
        { nickname: 'Ruchi', avatar: '🎱' },
        { nickname: 'Nia', avatar: '🐸' },
    ],
    eliminated_players: [],
    grabbed: 1,
    chairs: 2,
    gameplay_mode: 'digital',
    music_mode: 'builtin',
    music_style: 'upbeat',
    music_track_id: 'upbeat-confetti',
    grab_window_seconds: 5,
    intensity: 0.55,
};

describe('Musical Chairs', () => {
    it('renders setup controls and creates a room', () => {
        const onCreateRoom = vi.fn();
        render(
            <MusicalChairsSetupScreen
                config={defaultMusicalChairsConfig}
                setConfig={() => {}}
                onCreateRoom={onCreateRoom}
                onBack={() => {}}
            />,
        );

        expect(screen.getByRole('heading', { name: 'Musical Chairs' })).toBeInTheDocument();
        expect(screen.getByRole('button', { name: 'Built-in' })).toBeInTheDocument();
        expect(screen.getByRole('button', { name: 'External' })).toBeInTheDocument();
        expect(screen.getByRole('button', { name: /Confetti Pop/ })).toBeInTheDocument();
        expect(screen.getByRole('button', { name: 'Physical chairs' })).toBeInTheDocument();
        expect(screen.getByRole('button', { name: 'Phone tap' })).toBeInTheDocument();

        fireEvent.click(screen.getByRole('button', { name: 'Create Room' }));
        expect(onCreateRoom).toHaveBeenCalled();
    });

    it('shows host stop controls while music is playing', () => {
        const onStopMusic = vi.fn();
        render(
            <MusicalChairsGameScreen
                state={{ ...state, phase: 'MC_MUSIC' }}
                onStartRound={() => {}}
                onStopMusic={onStopMusic}
                onEliminatePlayer={() => {}}
                onEndGame={() => {}}
            />,
        );

        expect(screen.getByText('Music is playing')).toBeInTheDocument();
        fireEvent.click(screen.getByRole('button', { name: 'Stop Music' }));
        expect(onStopMusic).toHaveBeenCalled();
    });

    it('lets players grab only during the grab phase', () => {
        const onGrab = vi.fn();
        render(
            <MusicalChairsPlayer
                state={state}
                grabbed={false}
                eliminated={false}
                reactionMs={null}
                onGrab={onGrab}
            />,
        );

        fireEvent.click(screen.getByRole('button', { name: 'GRAB A CHAIR!' }));
        expect(onGrab).toHaveBeenCalled();
    });

    it('lets the host choose an eliminated player in physical mode', () => {
        const onEliminatePlayer = vi.fn();
        render(
            <MusicalChairsGameScreen
                state={{ ...state, gameplay_mode: 'physical', phase: 'MC_PHYSICAL_ELIMINATION' }}
                onStartRound={() => {}}
                onStopMusic={() => {}}
                onEliminatePlayer={onEliminatePlayer}
                onEndGame={() => {}}
            />,
        );

        fireEvent.click(screen.getByRole('button', { name: /Avi/ }));
        expect(onEliminatePlayer).toHaveBeenCalledWith('Avi');
    });

    it('shows eliminated players an out state', () => {
        render(
            <MusicalChairsPlayer
                state={state}
                grabbed={false}
                eliminated
                reactionMs={null}
                onGrab={() => {}}
            />,
        );

        expect(screen.getByRole('heading', { name: "You're out" })).toBeInTheDocument();
        expect(screen.queryByRole('button', { name: 'GRAB A CHAIR!' })).not.toBeInTheDocument();
    });
});
