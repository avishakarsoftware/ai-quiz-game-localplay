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
    it('uses the selected game name in the lobby heading', () => {
        render(<LobbyScreen {...baseProps} gameTitle="Party Quests" playerCount={0} minPlayers={1} />);
        expect(screen.getByRole('heading', { name: 'Party Quests Lobby' })).toBeInTheDocument();
    });

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

    it('shows preserved offline seats separately from connected player count', () => {
        render(
            <LobbyScreen
                {...baseProps}
                playerCount={1}
                minPlayers={2}
                players={[
                    { nickname: 'Avi', avatar: 'A', status: 'connected' },
                    { nickname: 'Ruchi', avatar: 'R', status: 'offline' },
                ]}
            />,
        );

        expect(screen.getByText('1')).toBeInTheDocument();
        expect(screen.getByText('connected player')).toBeInTheDocument();
        expect(screen.getByText('1 player reconnecting')).toBeInTheDocument();
        expect(screen.getByText('offline')).toBeInTheDocument();
        expect(screen.getByRole('button', { name: 'Start Game' })).toBeDisabled();
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

    it('offers an optional read-only review action before the host starts', async () => {
        const user = userEvent.setup();
        const onReviewContent = vi.fn();
        render(
            <LobbyScreen
                {...baseProps}
                playerCount={2}
                minPlayers={2}
                onBackToGames={() => {}}
                onReviewContent={onReviewContent}
            />,
        );

        await user.click(screen.getByRole('button', { name: /review questions/i }));

        expect(onReviewContent).toHaveBeenCalledTimes(1);
    });

    it('offers host-app organizers an explicit cancel action', async () => {
        const user = userEvent.setup();
        const onCancelGame = vi.fn();
        render(
            <LobbyScreen
                {...baseProps}
                playerCount={1}
                minPlayers={1}
                onCancelGame={onCancelGame}
            />,
        );

        await user.click(screen.getByRole('button', { name: 'Cancel game' }));

        expect(onCancelGame).toHaveBeenCalledTimes(1);
    });
});

/**
 * Host cleanup for offline lobby seats. Seats are held for the reconnect grace so a slept phone
 * keeps its place; without a host control the lobby just accumulates stale entries nobody can clear.
 */
describe('LobbyScreen offline seat cleanup', () => {
    const offlinePlayers = [
        { nickname: 'Maya', avatar: '🦄', status: 'connected' as const },
        { nickname: 'Leo', avatar: '🐙', status: 'offline' as const },
        { nickname: 'Ada', avatar: '🌮', status: 'reconnecting' as const },
    ];

    const baseProps = {
        roomCode: 'ABC123',
        joinUrl: 'https://games.revelryapp.me/join/ABC123',
        playerCount: 1,
        locked: false,
        onStartGame: () => {},
        onToggleLock: () => {},
    };

    it('offers the host a way to clear offline seats', async () => {
        const onRemoveOfflinePlayers = vi.fn();
        render(<LobbyScreen {...baseProps} players={offlinePlayers} onRemoveOfflinePlayers={onRemoveOfflinePlayers} />);
        expect(screen.getByText(/2 players reconnecting/)).toBeInTheDocument();
        await userEvent.click(screen.getByTestId('lobby-clear-offline'));
        expect(onRemoveOfflinePlayers).toHaveBeenCalledOnce();
    });

    it('hides the control when no seat is offline', () => {
        render(
            <LobbyScreen
                {...baseProps}
                players={[{ nickname: 'Maya', avatar: '🦄', status: 'connected' as const }]}
                onRemoveOfflinePlayers={() => {}}
            />,
        );
        expect(screen.queryByTestId('lobby-clear-offline')).not.toBeInTheDocument();
    });

    it('omits the control entirely when the host cannot act (no handler supplied)', () => {
        render(<LobbyScreen {...baseProps} players={offlinePlayers} />);
        expect(screen.getByText(/2 players reconnecting/)).toBeInTheDocument();
        expect(screen.queryByTestId('lobby-clear-offline')).not.toBeInTheDocument();
    });
});
