import { type CSSProperties, useEffect, useMemo, useState } from 'react';
import { API_URL } from '../config';

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
    catalog?: { id: string; title: string; launchable: boolean }[];
};

function hasCapability(context: LaunchContext | null, capability: string): boolean {
    return Boolean(context?.capabilities?.includes(capability) || context?.capabilities?.includes('manage_games'));
}

export default function PartyHubPage() {
    const params = new URLSearchParams(window.location.search);
    const partyGamesToken = params.get('party_games_token') || '';
    const [launchContext, setLaunchContext] = useState<LaunchContext | null>(null);
    const [workspace, setWorkspace] = useState<Workspace | null>(null);
    const [loading, setLoading] = useState(true);
    const [startingId, setStartingId] = useState('');
    const [error, setError] = useState('');

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

    async function startGame(content: PreparedContent, replacement?: { confirmed: boolean; sessionId?: string }) {
        setStartingId(content.localplay_content_id);
        setError('');
        try {
            const res = await fetch(`${API_URL}/integrations/revelry/party-games/start`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    party_games_token: partyGamesToken,
                    content_id: content.localplay_content_id,
                    game_type: content.game_type,
                    replacement_confirmed: replacement?.confirmed || false,
                    replace_session_id: replacement?.sessionId,
                }),
            });
            if (res.status === 409) {
                const detail = (await res.json()).detail;
                if (detail?.code === 'active_session_exists') {
                    const confirmed = window.confirm('A LocalPlay game is already active for this party. Start this game and close the old one?');
                    if (confirmed) {
                        await startGame(content, { confirmed: true, sessionId: detail.session_id });
                    }
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
    }

    async function openAuthoring(mode: 'create' | 'edit', content?: PreparedContent) {
        setError('');
        try {
            const res = await fetch(`${API_URL}/integrations/revelry/party-games/authoring-link`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    party_games_token: partyGamesToken,
                    game_type: 'quiz',
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
            window.location.href = launchContext.return_url;
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

            <section className="party-hub__section">
                <div className="party-hub__section-head">
                    <h2>Saved games</h2>
                    {canEdit && <button onClick={() => void openAuthoring('create')}>Create quiz</button>}
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
                                    <p>{content.question_count || 0} questions · {content.status}</p>
                                </div>
                                <div className="party-hub__actions">
                                    {canStart && (
                                        <button onClick={() => startGame(content)} disabled={startingId === content.localplay_content_id}>
                                            {startingId === content.localplay_content_id ? 'Starting...' : 'Start'}
                                        </button>
                                    )}
                                    {canEdit && content.game_type === 'quiz' && (
                                        <button onClick={() => void openAuthoring('edit', content)}>Edit/Open</button>
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
