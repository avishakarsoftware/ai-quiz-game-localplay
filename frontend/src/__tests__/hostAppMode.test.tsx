import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { vi } from 'vitest';
import { isHostAppSurfaceLocation } from '../utils/hostAppMode';
import { filterGameModesForCatalog } from '../gameModes';
import LobbyScreen from '../components/organizer/LobbyScreen';

describe('host-app mode filtering', () => {
    it('hides standalone chrome for Revelry-launched surfaces', () => {
        expect(isHostAppSurfaceLocation('/revelry/games', '')).toBe(true);
        expect(isHostAppSurfaceLocation('/organizer', '?embed=1&launch_token=abc')).toBe(true);
        expect(isHostAppSurfaceLocation('/join', '?launch_token=abc')).toBe(true);
        expect(isHostAppSurfaceLocation('/spectator', '?embed=1')).toBe(true);
        expect(isHostAppSurfaceLocation('/organizer', '')).toBe(false);
    });

    it('only exposes launchable catalog games in host-app menus', () => {
        const modes = filterGameModesForCatalog([
            { id: 'quiz', launchable: true },
            { id: 'wmlt', launchable: true },
            { id: 'drawing', launchable: true },
            { id: 'rebus', launchable: false },
        ]);

        expect(modes.map((mode) => mode.id)).toEqual(['quiz', 'wmlt', 'drawing']);
    });

    it('hides raw standalone share UX in host-app lobby mode', () => {
        render(
            <LobbyScreen
                roomCode="ABCD12"
                joinUrl="https://gamesapi-gamma.revelryapp.me/join/ABCD12"
                playerCount={0}
                players={[]}
                locked={false}
                onStartGame={() => {}}
                onToggleLock={() => {}}
                hostAppMode
            />,
        );

        expect(screen.queryByRole('button', { name: /share link/i })).not.toBeInTheDocument();
        expect(screen.queryByText(/gamesapi-gamma\.revelryapp\.me/)).not.toBeInTheDocument();
        expect(screen.getByText(/players can join from revelry/i)).toBeInTheDocument();
    });

    it('renders and copies a Revelry-owned join affordance in host-app lobby mode when provided', async () => {
        const writeText = vi.fn().mockResolvedValue(undefined);
        Object.defineProperty(navigator, 'clipboard', {
            configurable: true,
            value: { writeText },
        });

        render(
            <LobbyScreen
                roomCode="ABCD12"
                joinUrl="https://gamesapi-gamma.revelryapp.me/join/ABCD12"
                hostAppJoinUrl="https://app.revelryapp.me/party/party-1/games/join"
                hostAppJoinLabel="Scan to join Ava's Birthday"
                playerCount={0}
                players={[]}
                locked={false}
                onStartGame={() => {}}
                onToggleLock={() => {}}
                hostAppMode
            />,
        );

        expect(screen.getByText(/scan to join ava's birthday/i)).toBeInTheDocument();
        expect(screen.queryByRole('button', { name: /share link/i })).not.toBeInTheDocument();
        expect(screen.queryByText(/gamesapi-gamma\.revelryapp\.me/)).not.toBeInTheDocument();
        fireEvent.click(screen.getByRole('button', { name: /copy join link/i }));
        await waitFor(() => {
            expect(writeText).toHaveBeenCalledWith('https://app.revelryapp.me/party/party-1/games/join');
        });
    });
});
