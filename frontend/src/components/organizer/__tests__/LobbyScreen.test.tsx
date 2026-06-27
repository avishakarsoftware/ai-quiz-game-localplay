import { render, screen } from '@testing-library/react';
import LobbyScreen from '../LobbyScreen';

// CastButton pulls in browser/cast APIs that aren't needed for this test.
vi.mock('../../CastButton', () => ({ default: () => null }));

const baseProps = {
    roomCode: 'ABCDEF',
    joinUrl: 'https://games.example.com/quiz/?room=ABCDEF',
    players: [],
    locked: false,
    onStartGame: () => {},
    onToggleLock: () => {},
};

describe('LobbyScreen min-player gating', () => {
    it('disables Start and explains how many more players are needed', () => {
        render(<LobbyScreen {...baseProps} playerCount={1} minPlayers={3} />);
        expect(screen.getByRole('button', { name: 'Start Game' })).toBeDisabled();
        expect(screen.getByText('Need 2 more players to start (1/3)')).toBeInTheDocument();
    });

    it('enables Start once the minimum is met', () => {
        render(<LobbyScreen {...baseProps} playerCount={3} minPlayers={3} />);
        expect(screen.getByRole('button', { name: 'Start Game' })).toBeEnabled();
    });

    it('shows a waiting hint with zero players', () => {
        render(<LobbyScreen {...baseProps} playerCount={0} minPlayers={2} />);
        expect(screen.getByRole('button', { name: 'Start Game' })).toBeDisabled();
        expect(screen.getByText('Needs at least 2 players to start')).toBeInTheDocument();
    });
});
