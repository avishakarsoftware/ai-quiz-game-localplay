import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, vi } from 'vitest';
import { isHostAppSurfaceLocation } from '../utils/hostAppMode';
import { filterGameModesForCatalog } from '../gameModes';
import LobbyScreen from '../components/organizer/LobbyScreen';
import PartyHubPage from '../pages/PartyHubPage';

describe('host-app mode filtering', () => {
    afterEach(() => {
        vi.unstubAllGlobals();
    });

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

    it('renders party hub creation options from the host-app catalog', async () => {
        window.history.pushState({}, '', '/revelry/games?party_games_token=party-token');
        const fetchMock = vi.fn().mockResolvedValue({
            ok: true,
            json: async () => ({
                launch_context: {
                    capabilities: ['author_content', 'operate_game'],
                    external_container_title: 'Ava Birthday',
                },
                workspace: {
                    active_session: null,
                    prepared_content: [
                        {
                            localplay_content_id: 'quiz-pack-1',
                            game_type: 'quiz',
                            title: 'Saved Quiz',
                            status: 'ready',
                            question_count: 4,
                        },
                    ],
                    catalog: [
                        {
                            id: 'quiz',
                            game_type: 'quiz',
                            title: 'AI Quiz',
                            description: 'Trivia',
                            launchable: true,
                            can_create_content: true,
                            can_quick_start: true,
                            creation_modes: ['manual', 'ai'],
                            embedded_authoring_supported: true,
                        },
                        {
                            id: 'wmlt',
                            game_type: 'wmlt',
                            title: 'Most Likely To',
                            description: 'Vote',
                            launchable: true,
                            can_create_content: true,
                            can_edit_content: true,
                            supports_ai_generation: true,
                            creation_modes: ['template', 'manual', 'ai'],
                        },
                        {
                            id: 'drawing',
                            game_type: 'drawing',
                            title: 'Drawing Game',
                            description: 'Draw',
                            launchable: true,
                            can_create_content: true,
                            can_edit_content: true,
                            supports_ai_generation: true,
                            creation_modes: ['template', 'manual', 'ai'],
                        },
                        {
                            id: 'rebus',
                            game_type: 'rebus',
                            title: 'Rebus Rush',
                            launchable: false,
                        },
                    ],
                },
            }),
        });
        vi.stubGlobal('fetch', fetchMock);

        render(<PartyHubPage />);

        expect(await screen.findByRole('heading', { name: /create a game/i })).toBeInTheDocument();
        expect(screen.getByRole('heading', { name: /saved games/i })).toBeInTheDocument();
        expect(screen.getByText('AI Quiz')).toBeInTheDocument();
        expect(screen.getByText('Most Likely To')).toBeInTheDocument();
        expect(screen.getByText('Drawing Game')).toBeInTheDocument();
        expect(screen.queryByText('Rebus Rush')).not.toBeInTheDocument();
        expect(screen.getByText('Saved Quiz')).toBeInTheDocument();
        expect(screen.getByRole('button', { name: /create quiz/i })).toBeInTheDocument();
        expect(screen.getByRole('button', { name: /set up round/i })).toBeInTheDocument();
        expect(screen.getByRole('button', { name: /set up drawing/i })).toBeInTheDocument();
        expect(screen.getByText(/write your own or use ai/i)).toBeInTheDocument();
        expect(screen.getAllByText(/ready-made or ai prompts/i)).toHaveLength(2);
        expect(screen.queryByText(/manual \/ ai/i)).not.toBeInTheDocument();
        expect(screen.queryByText(/^template$/i)).not.toBeInTheDocument();
    });

    it('opens new quiz authoring from catalog without using a saved game id', async () => {
        window.history.pushState({}, '', '/revelry/games?party_games_token=party-token');
        const fetchMock = vi.fn()
            .mockResolvedValueOnce({
                ok: true,
                json: async () => ({
                    launch_context: {
                        capabilities: ['author_content', 'operate_game'],
                        external_container_title: 'Ava Birthday',
                    },
                    workspace: {
                        active_session: null,
                        prepared_content: [{ localplay_content_id: 'saved-1', game_type: 'quiz', title: 'Saved Quiz', status: 'ready' }],
                        catalog: [{
                            id: 'quiz',
                            game_type: 'quiz',
                            title: 'AI Quiz',
                            launchable: true,
                            can_create_content: true,
                            creation_modes: ['manual'],
                            embedded_authoring_supported: true,
                        }],
                    },
                }),
            })
            .mockResolvedValueOnce({
                ok: true,
                json: async () => ({ authoring_url: '/revelry/author?authoring_token=abc' }),
            });
        vi.stubGlobal('fetch', fetchMock);

        render(<PartyHubPage />);

        fireEvent.click(await screen.findByRole('button', { name: /create quiz/i }));

        await waitFor(() => {
            expect(fetchMock).toHaveBeenCalledTimes(2);
        });
        expect(JSON.parse(fetchMock.mock.calls[1][1].body)).toEqual({
            party_games_token: 'party-token',
            game_type: 'quiz',
            mode: 'create',
        });
    });

    it('sets up and saves catalog games before starting them', async () => {
        window.history.pushState({}, '', '/revelry/games?party_games_token=party-token');
        const fetchMock = vi.fn()
            .mockResolvedValueOnce({
                ok: true,
                json: async () => ({
                    launch_context: {
                        capabilities: ['author_content', 'operate_game'],
                        external_container_title: 'Ava Birthday',
                    },
                    workspace: {
                        active_session: null,
                        prepared_content: [],
                        catalog: [{
                            id: 'drawing',
                            game_type: 'drawing',
                            title: 'Drawing Game',
                            launchable: true,
                            can_create_content: true,
                            can_edit_content: true,
                            supports_ai_generation: true,
                            creation_modes: ['template', 'manual', 'ai'],
                            config_schema: { time_limit: { default: 30 } },
                        }],
                    },
                }),
            })
            .mockResolvedValueOnce({
                ok: true,
                json: async () => ({
                    localplay_content_id: 'drawing-content-1',
                    content: { localplay_content_id: 'drawing-content-1', game_type: 'drawing', title: 'Drawing Game', time_limit: 30 },
                    workspace: { active_session: null, prepared_content: [], catalog: [] },
                }),
            })
            .mockResolvedValueOnce({
                ok: true,
                json: async () => ({ launch_url: '/organizer?session_id=lp_1&launch_token=abc' }),
            });
        vi.stubGlobal('fetch', fetchMock);

        render(<PartyHubPage />);

        fireEvent.click(await screen.findByRole('button', { name: /set up drawing/i }));
        expect(await screen.findByRole('heading', { name: /set up drawing game/i })).toBeInTheDocument();
        fireEvent.click(screen.getByRole('button', { name: /save and start/i }));

        await waitFor(() => {
            expect(fetchMock).toHaveBeenCalledTimes(3);
        });
        expect(JSON.parse(fetchMock.mock.calls[1][1].body)).toMatchObject({
            party_games_token: 'party-token',
            game_type: 'drawing',
            title: 'Drawing Game',
            content_payload: {
                time_limit: 30,
            },
        });
        expect(JSON.parse(fetchMock.mock.calls[2][1].body)).toMatchObject({
            party_games_token: 'party-token',
            content_id: 'drawing-content-1',
            game_type: 'drawing',
        });
    });

    it('generates AI prompts for party hub Drawing setup before saving', async () => {
        window.history.pushState({}, '', '/revelry/games?party_games_token=party-token');
        const fetchMock = vi.fn()
            .mockResolvedValueOnce({
                ok: true,
                json: async () => ({
                    launch_context: {
                        capabilities: ['author_content', 'operate_game'],
                        external_container_title: 'Christmas Bash',
                    },
                    workspace: {
                        active_session: null,
                        prepared_content: [],
                        catalog: [{
                            id: 'drawing',
                            game_type: 'drawing',
                            title: 'Drawing Game',
                            launchable: true,
                            can_create_content: true,
                            can_edit_content: true,
                            supports_ai_generation: true,
                            creation_modes: ['template', 'manual', 'ai'],
                            config_schema: { time_limit: { default: 30 } },
                        }],
                    },
                }),
            })
            .mockResolvedValueOnce({
                ok: true,
                json: async () => ({
                    game_type: 'drawing',
                    content_payload: {
                        game: {
                            game_title: 'Christmas Drawing Game',
                            prompts: [
                                { id: 1, text: 'Santa hat', aliases: [] },
                                { id: 2, text: 'Snow globe', aliases: [] },
                            ],
                        },
                    },
                }),
            });
        vi.stubGlobal('fetch', fetchMock);

        render(<PartyHubPage />);

        fireEvent.click(await screen.findByRole('button', { name: /set up drawing/i }));
        expect(await screen.findByRole('heading', { name: /set up drawing game/i })).toBeInTheDocument();
        expect(screen.getByText(/generate prompts with ai/i)).toBeInTheDocument();
        fireEvent.click(screen.getByRole('button', { name: /generate prompts/i }));

        await waitFor(() => {
            expect(fetchMock).toHaveBeenCalledTimes(2);
        });
        expect(JSON.parse(fetchMock.mock.calls[1][1].body)).toMatchObject({
            party_games_token: 'party-token',
            game_type: 'drawing',
            prompt: 'Christmas Bash Drawing Game',
            difficulty: 'medium',
            num_prompts: 10,
        });
        const promptsBox = screen.getByLabelText(/drawing prompts/i) as HTMLTextAreaElement;
        await waitFor(() => {
            expect(promptsBox.value).toContain('Santa hat');
            expect(promptsBox.value).toContain('Snow globe');
        });
    });
});
