import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
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

    it('offers a clear path back to the game list when provided', async () => {
        const user = userEvent.setup();
        const onBackToGames = vi.fn();
        render(<LobbyScreen {...baseProps} playerCount={2} minPlayers={2} onBackToGames={onBackToGames} />);

        await user.click(screen.getByRole('button', { name: /back to games/i }));

        expect(onBackToGames).toHaveBeenCalledTimes(1);
    });

    it('offers an optional edit setup action before the host starts', async () => {
        const user = userEvent.setup();
        const onEditSetup = vi.fn();
        render(
            <LobbyScreen
                {...baseProps}
                playerCount={2}
                minPlayers={2}
                onBackToGames={() => {}}
                onEditSetup={onEditSetup}
                editSetupLabel="Edit questions"
            />,
        );

        await user.click(screen.getByRole('button', { name: /edit questions/i }));

        expect(onEditSetup).toHaveBeenCalledTimes(1);
    });
});
