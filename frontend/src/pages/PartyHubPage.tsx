import { type CSSProperties, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { API_URL } from '../config';
import { getGameModeConfig } from '../gameModes';

type LaunchContext = {
    external_container_title?: string;
    return_url?: string;
    capabilities?: string[];
    display?: {
        container_label?: string;
        container_image_url?: string;
        accent_color?: string;
        return_label?: string;
    };
};

type PreparedContent = {
    localplay_content_id: string;
    game_type: string;
    title: string;
    status: string;
    thumbnail_url?: string;
    question_count?: number;
    updated_at?: string;
    action_requirements?: Record<string, string[]>;
};

type Workspace = {
    prepared_content: PreparedContent[];
    active_session?: {
        session_id: string;
        status: string;
        room_code: string;
        joinable: boolean;
    } | null;
    catalog?: CatalogGame[];
};

type ReplacementPrompt = {
    game: StartableGame;
    sessionId: string;
    message: string;
};

type CatalogGame = {
    id: string;
    game_type?: string;
    runtime_type?: string;
    title: string;
    description?: string;
    min_players?: number;
    estimated_minutes?: number;
    launchable: boolean;
    can_create_content?: boolean;
    can_edit_content?: boolean;
    can_quick_start?: boolean;
    creation_modes?: string[];
    embedded_authoring_supported?: boolean;
    config_schema?: {
        time_limit?: {
            default?: number;
        };
    };
};

type StartableGame = {
    localplay_content_id?: string;
    game_type: string;
    title: string;
    time_limit?: number;
};

function hasCapability(context: LaunchContext | null, capability: string): boolean {
    return Boolean(context?.capabilities?.includes(capability) || context?.capabilities?.includes('manage_games'));
}

function actionLabelForGame(game: CatalogGame, canCreate: boolean): string {
    const gameType = game.game_type || game.id;
    if (canCreate) {
        if (gameType === 'quiz') return 'Create quiz';
        return `Create ${game.title}`;
    }
    if (gameType === 'wmlt') return 'Start a round';
    if (gameType === 'drawing') return 'Start drawing';
    return 'Start now';
}

function cardMetaForGame(game: CatalogGame): string {
    const gameType = game.game_type || game.id;
    const modes = new Set(game.creation_modes || []);
    const creationCopy = gameType === 'quiz' && (modes.has('manual') || modes.has('ai'))
        ? 'Write your own or use AI'
        : modes.has('template')
            ? 'Ready-made prompts'
            : '';
    const details = [
        creationCopy,
        game.min_players ? `${game.min_players}+ players` : '',
        game.estimated_minutes ? `${game.estimated_minutes} min` : '',
    ].filter(Boolean);
    return details.join(' · ') || 'Party game';
}

function savedContentSummary(content: PreparedContent): string {
    const count = content.question_count || 0;
    const unit = content.game_type === 'quiz'
        ? `${count} question${count === 1 ? '' : 's'}`
        : content.game_type;
    return `${unit} · ${content.status}`;
}

function returnToHostApp(returnUrl: string) {
    const url = new URL(returnUrl, window.location.origin);
    if (window.parent && window.parent !== window) {
        window.parent.postMessage({
            type: 'LOCALPLAY_REQUEST_CLOSE',
            return_url: url.toString(),
        }, url.origin);
        return;
    }
    window.location.href = url.toString();
}

export default function PartyHubPage() {
    const params = new URLSearchParams(window.location.search);
    const partyGamesToken = params.get('party_games_token') || '';
    const startContentId = params.get('start_content_id') || params.get('content_id') || '';
    const startGameType = params.get('game_type') || '';
    const startTimeLimit = params.get('time_limit') || '';
    const [launchContext, setLaunchContext] = useState<LaunchContext | null>(null);
    const [workspace, setWorkspace] = useState<Workspace | null>(null);
    const [loading, setLoading] = useState(true);
    const [startingId, setStartingId] = useState('');
    const [error, setError] = useState('');
    const [replacementPrompt, setReplacementPrompt] = useState<ReplacementPrompt | null>(null);
    const autoStartRef = useRef('');

    useEffect(() => {
        let cancelled = false;
        async function load() {
            if (!partyGamesToken) {
                setError('Open this from Revelry again.');
                setLoading(false);
                return;
            }
            try {
                const res = await fetch(`${API_URL}/integrations/revelry/party-games/resolve?party_games_token=${encodeURIComponent(partyGamesToken)}`);
                if (!res.ok) throw new Error('resolve_failed');
                const data = await res.json();
                if (!cancelled) {
                    setLaunchContext(data.launch_context);
                    setWorkspace(data.workspace);
                }
            } catch {
                if (!cancelled) setError('Open this from Revelry again.');
            } finally {
                if (!cancelled) setLoading(false);
            }
        }
        void load();
        return () => { cancelled = true; };
    }, [partyGamesToken]);

    const display = launchContext?.display || {};
    const title = display.container_label || launchContext?.external_container_title || 'Revelry Games';
    const canStart = hasCapability(launchContext, 'operate_game');
    const canEdit = hasCapability(launchContext, 'author_content');
    const canDelete = hasCapability(launchContext, 'manage_games');

    const preparedContent = useMemo(() => workspace?.prepared_content || [], [workspace]);
    const catalogGames = useMemo(
        () => (workspace?.catalog || []).filter((game) => game.launchable !== false),
        [workspace],
    );

    const startGame = useCallback(async (game: StartableGame, replacement?: { confirmed: boolean; sessionId?: string }) => {
        const actionId = game.localplay_content_id || game.game_type;
        setStartingId(actionId);
        setError('');
        if (replacement?.confirmed) setReplacementPrompt(null);
        try {
            const parsedTimeLimit = game.time_limit ?? Number.parseInt(startTimeLimit, 10);
            const res = await fetch(`${API_URL}/integrations/revelry/party-games/start`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    party_games_token: partyGamesToken,
                    content_id: game.localplay_content_id || '',
                    game_type: startGameType || game.game_type,
                    time_limit: Number.isFinite(parsedTimeLimit) ? parsedTimeLimit : undefined,
                    replacement_confirmed: replacement?.confirmed || false,
                    replace_session_id: replacement?.sessionId,
                }),
            });
            if (res.status === 409) {
                const detail = (await res.json()).detail;
                if (detail?.code === 'active_session_exists') {
                    setReplacementPrompt({
                        game,
                        sessionId: detail.session_id || '',
                        message: detail.message || 'A LocalPlay game is already active for this party.',
                    });
                    return;
                }
            }
            if (!res.ok) throw new Error('start_failed');
            const data = await res.json();
            window.location.href = data.launch_url;
        } catch {
            setError('Could not start that game. Please try again.');
        } finally {
            setStartingId('');
        }
    }, [partyGamesToken, startGameType, startTimeLimit]);

    const confirmReplacement = useCallback(() => {
        if (!replacementPrompt) return;
        void startGame(replacementPrompt.game, { confirmed: true, sessionId: replacementPrompt.sessionId });
    }, [replacementPrompt, startGame]);

    useEffect(() => {
        if (!startContentId || loading || !workspace || !canStart) return;
        if (autoStartRef.current === startContentId) return;
        const content = preparedContent.find((item) => item.localplay_content_id === startContentId);
        if (!content) {
            setError('That saved game was not found for this party.');
            autoStartRef.current = startContentId;
            return;
        }
        autoStartRef.current = startContentId;
        void startGame({
            localplay_content_id: content.localplay_content_id,
            game_type: content.game_type,
            title: content.title,
        });
    }, [canStart, loading, preparedContent, startContentId, startGame, workspace]);

    async function openAuthoring(mode: 'create' | 'edit', gameType: string, content?: PreparedContent) {
        setError('');
        try {
            const res = await fetch(`${API_URL}/integrations/revelry/party-games/authoring-link`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    party_games_token: partyGamesToken,
                    game_type: gameType,
                    mode,
                    content_id: content?.localplay_content_id,
                }),
            });
            if (!res.ok) throw new Error('authoring_failed');
            const data = await res.json();
            window.location.href = data.authoring_url;
        } catch {
            setError('Could not open the editor. Please try again.');
        }
    }

    function createFromCatalog(game: CatalogGame) {
        if (game.can_create_content || game.embedded_authoring_supported) {
            void openAuthoring('create', game.game_type || game.id);
            return;
        }
        if (game.can_quick_start) {
            void startGame({
                game_type: game.game_type || game.id,
                title: game.title,
                time_limit: game.config_schema?.time_limit?.default,
            });
        }
    }

    async function deleteContent(content: PreparedContent) {
        if (!window.confirm(`Delete "${content.title}" from this party?`)) return;
        setStartingId(content.localplay_content_id);
        setError('');
        try {
            const res = await fetch(`${API_URL}/integrations/revelry/party-games/content/${encodeURIComponent(content.localplay_content_id)}`, {
                method: 'DELETE',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ party_games_token: partyGamesToken }),
            });
            if (!res.ok) throw new Error('delete_failed');
            const data = await res.json();
            setWorkspace(data.workspace);
        } catch {
            setError('Could not delete that game. Please try again.');
        } finally {
            setStartingId('');
        }
    }

    function returnToRevelry() {
        if (launchContext?.return_url) {
            returnToHostApp(launchContext.return_url);
        }
    }

    if (loading) {
        return <main className="party-hub party-hub--center">Loading Revelry Games...</main>;
    }

    if (error && !workspace) {
        return <main className="party-hub party-hub--center">{error}</main>;
    }

    return (
        <main className="party-hub" style={{ '--party-accent': display.accent_color || '#ff4f9a' } as CSSProperties}>
            <header className="party-hub__header">
                {display.container_image_url && <img src={display.container_image_url} alt="" className="party-hub__cover" />}
                <div className="party-hub__title-block">
                    <p>Revelry Games</p>
                    <h1>{title}</h1>
                    <span>{workspace?.active_session ? `Active room ${workspace.active_session.room_code}` : 'Party game hub'}</span>
                </div>
                {launchContext?.return_url && (
                    <button className="party-hub__return" onClick={returnToRevelry}>
                        {display.return_label || 'Back to Revelry'}
                    </button>
                )}
            </header>

            {error && <div className="party-hub__error">{error}</div>}

            {replacementPrompt && (
                <section className="party-hub__confirm" role="dialog" aria-modal="true" aria-labelledby="replace-game-title">
                    <div>
                        <p>Active game</p>
                        <h2 id="replace-game-title">Replace the current game?</h2>
                        <span>{replacementPrompt.message} Starting "{replacementPrompt.game.title}" will close the current room for this party.</span>
                    </div>
                    <div className="party-hub__confirm-actions">
                        <button onClick={confirmReplacement} disabled={startingId === (replacementPrompt.game.localplay_content_id || replacementPrompt.game.game_type)}>
                            {startingId === (replacementPrompt.game.localplay_content_id || replacementPrompt.game.game_type) ? 'Replacing...' : 'Replace and start'}
                        </button>
                        <button className="party-hub__secondary" onClick={() => setReplacementPrompt(null)}>
                            Keep current game
                        </button>
                    </div>
                </section>
            )}

            <section className="party-hub__section">
                <div className="party-hub__section-head">
                    <div>
                        <h2>Create a game</h2>
                        <p>Pick what this party plays next.</p>
                    </div>
                </div>
                {catalogGames.length === 0 ? (
                    <div className="party-hub__empty">No games are available for this party yet.</div>
                ) : (
                    <div className="party-hub__grid party-hub__grid--catalog">
                        {catalogGames.map((game) => {
                            const mode = getGameModeConfig(game.id as Parameters<typeof getGameModeConfig>[0]);
                            const canCreate = Boolean(canEdit && (game.can_create_content || game.embedded_authoring_supported));
                            const canQuickStart = Boolean(canStart && game.can_quick_start);
                            const disabled = (!canCreate && !canQuickStart) || startingId === (game.game_type || game.id);
                            return (
                                <article className="party-hub__card party-hub__catalog-card" key={game.id}>
                                    <div className="party-hub__icon" aria-hidden="true">{mode.icon}</div>
                                    <div>
                                        <h3>{game.title}</h3>
                                        <p>{game.description || mode.description}</p>
                                        <small>{cardMetaForGame(game)}</small>
                                    </div>
                                    <div className="party-hub__actions">
                                        <button onClick={() => createFromCatalog(game)} disabled={disabled}>
                                            {startingId === (game.game_type || game.id)
                                                ? 'Starting...'
                                                : actionLabelForGame(game, canCreate)}
                                        </button>
                                    </div>
                                </article>
                            );
                        })}
                    </div>
                )}
            </section>

            <section className="party-hub__section">
                <div className="party-hub__section-head">
                    <h2>Saved games</h2>
                </div>
                {preparedContent.length === 0 ? (
                    <div className="party-hub__empty">No saved games for this party yet.</div>
                ) : (
                    <div className="party-hub__grid">
                        {preparedContent.map((content) => (
                            <article className="party-hub__card" key={content.localplay_content_id}>
                                {content.thumbnail_url && <img src={content.thumbnail_url} alt="" />}
                                <div>
                                    <span>{content.game_type}</span>
                                    <h3>{content.title}</h3>
                                    <p>{savedContentSummary(content)}</p>
                                </div>
                                <div className="party-hub__actions">
                                    {canStart && (
                                        <button
                                            onClick={() => void startGame({
                                                localplay_content_id: content.localplay_content_id,
                                                game_type: content.game_type,
                                                title: content.title,
                                            })}
                                            disabled={startingId === content.localplay_content_id}
                                        >
                                            {startingId === content.localplay_content_id ? 'Starting...' : 'Start'}
                                        </button>
                                    )}
                                    {canEdit && content.game_type === 'quiz' && (
                                        <button onClick={() => void openAuthoring('edit', content.game_type, content)}>Edit/Open</button>
                                    )}
                                    {canDelete && (
                                        <button className="party-hub__danger" onClick={() => void deleteContent(content)} disabled={startingId === content.localplay_content_id}>
                                            Delete
                                        </button>
                                    )}
                                </div>
                            </article>
                        ))}
                    </div>
                )}
            </section>
        </main>
    );
}
