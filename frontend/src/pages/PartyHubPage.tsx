import { Search } from 'lucide-react';
import { type CSSProperties, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { API_URL } from '../config';
import { getGameModeConfig } from '../gameModes';
import GameRulesModal from '../components/GameRulesModal';
import { type GameRules } from '../gameRules';
import { returnToHostApp } from '../utils/hostAppReturn';

type LaunchContext = {
    external_container_title?: string;
    return_url?: string;
    parent_origin?: string;
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
    time_limit?: number;
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
        launch_routes?: Record<string, { path?: string; url?: string; scope?: string }>;
        feed_card?: {
            title?: string;
            body?: string;
        };
    } | null;
    catalog?: CatalogGame[];
};

type ReplacementPrompt = {
    game: StartableGame;
    sessionId: string;
    message: string;
    activeTitle?: string;
    activeGameType?: string;
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
    supports_ai_generation?: boolean;
    creation_modes?: string[];
    embedded_authoring_supported?: boolean;
    rules?: GameRules;
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

type SetupDraft = {
    game: CatalogGame;
    contentId?: string;
    title: string;
    promptsText: string;
    timeLimit?: number;
};

const PROMPT_COUNT_OPTIONS = [5, 8, 10, 15, 20];
type PartyHubGameCategory = 'all' | 'quiz' | 'creative' | 'bingo_housie' | 'cards';

const PARTY_HUB_CATEGORY_OPTIONS: Array<{ id: PartyHubGameCategory; label: string }> = [
    { id: 'all', label: 'All' },
    { id: 'quiz', label: 'Quiz/Trivia' },
    { id: 'creative', label: 'Creative' },
    { id: 'bingo_housie', label: 'Bingo/Housie' },
    { id: 'cards', label: 'Cards' },
];

const PARTY_HUB_CATEGORY_BY_ID: Record<string, PartyHubGameCategory> = {
    quiz: 'quiz',
    rebus: 'quiz',
    emoji_charades: 'quiz',
    fact_fiction: 'quiz',
    timeline: 'quiz',
    odd_one_out: 'quiz',
    wmlt: 'creative',
    drawing: 'creative',
    musical_chairs: 'creative',
    two_truths: 'creative',
    story_chain: 'creative',
    common_ground: 'creative',
    find_someone: 'creative',
    housie: 'bingo_housie',
    bingo: 'bingo_housie',
    baby_bingo: 'bingo_housie',
    bluff: 'cards',
};

function gameSortTitle(game: { title?: string; game_type?: string; id?: string }) {
    return (game.title || game.game_type || game.id || '').toLowerCase();
}

function categoryForCatalogGame(game: CatalogGame): PartyHubGameCategory {
    return PARTY_HUB_CATEGORY_BY_ID[game.id] || PARTY_HUB_CATEGORY_BY_ID[game.game_type || ''] || 'creative';
}

function hasCapability(context: LaunchContext | null, capability: string): boolean {
    return Boolean(context?.capabilities?.includes(capability) || context?.capabilities?.includes('manage_games'));
}

function actionLabelForGame(game: CatalogGame, canCreate: boolean): string {
    const gameType = game.game_type || game.id;
    if (canCreate) {
        if (gameType === 'quiz') return 'Create quiz';
        if (gameType === 'wmlt') return 'Set up round';
        if (gameType === 'drawing') return 'Set up drawing';
        return `Set up ${game.title}`;
    }
    if (gameType === 'wmlt') return 'Start a round';
    if (gameType === 'drawing') return 'Start drawing';
    return 'Start now';
}

function cardMetaForGame(game: CatalogGame): string {
    const gameType = game.game_type || game.id;
    const modes = new Set(game.creation_modes || []);
    const creationCopy = game.supports_ai_generation || modes.has('ai')
        ? gameType === 'quiz'
            ? 'Write your own or use AI'
            : 'Ready-made or AI prompts'
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
    const unit = content.game_type === 'housie'
        ? `${count || 'Saved'} prize${count === 1 ? '' : 's'}`
        : content.game_type === 'quiz'
        ? `${count} question${count === 1 ? '' : 's'}`
        : `${count || 'Saved'} prompt${count === 1 ? '' : 's'}`;
    return `${unit} · ${content.status}`;
}

function defaultPromptsForGame(gameType: string): string {
    if (gameType === 'wmlt') {
        return [
            'Most likely to start the dance floor',
            'Most likely to remember every tiny detail',
            'Most likely to make everyone laugh',
        ].join('\n');
    }
    if (gameType === 'drawing') {
        return ['birthday cake', 'dance party', 'confetti'].join('\n');
    }
    if (gameType === 'housie') {
        return '';
    }
    return '';
}

function setupCopyForGame(gameType: string): { heading: string; promptLabel: string; help: string } {
    if (gameType === 'wmlt') {
        return {
            heading: 'Set up Most Likely To',
            promptLabel: 'Prompts',
            help: 'Add one “most likely to” prompt per line.',
        };
    }
    if (gameType === 'drawing') {
        return {
            heading: 'Set up Drawing Game',
            promptLabel: 'Drawing prompts',
            help: 'Add one drawable prompt per line.',
        };
    }
    if (gameType === 'housie') {
        return {
            heading: 'Set up Housie',
            promptLabel: 'Prizes',
            help: 'Classic 90-ball Housie with Quick 5, rows, corners, and full house prizes.',
        };
    }
    return {
        heading: 'Set up game',
        promptLabel: 'Prompts',
        help: 'Add one prompt per line.',
    };
}

function promptLinesFromPayload(gameType: string, payload: Record<string, unknown>): string[] {
    const gamePayload = payload?.game && typeof payload.game === 'object'
        ? payload.game as Record<string, unknown>
        : payload || {};
    if (gameType === 'housie') {
        return [];
    }
    return gameType === 'wmlt'
        ? ((gamePayload.statements as Array<{ text?: string }> | undefined) || []).map((item) => item.text || '').filter(Boolean)
        : ((gamePayload.prompts as Array<{ text?: string }> | undefined) || []).map((item) => item.text || '').filter(Boolean);
}

function contentPayloadFromDraft(draft: SetupDraft) {
    const gameType = draft.game.game_type || draft.game.id;
    const prompts = draft.promptsText
        .split('\n')
        .map((line) => line.trim())
        .filter(Boolean)
        .slice(0, 50);
    if (gameType === 'wmlt') {
        return {
            game: {
                game_title: draft.title,
                statements: prompts.map((text, index) => ({ id: index + 1, text })),
            },
        };
    }
    if (gameType === 'drawing') {
        return {
            game: {
                game_title: draft.title,
                prompts: prompts.map((text, index) => ({
                    id: index + 1,
                    text,
                    aliases: [],
                    difficulty: 'medium',
                })),
            },
            time_limit: draft.timeLimit || 30,
        };
    }
    if (gameType === 'housie') {
        return {
            game: {
                game_title: draft.title,
                pattern_ids: ['quick_5', 'four_corners', 'top_row', 'middle_row', 'bottom_row', 'full_house'],
                play_mode: 'beginner',
                caller_mode: 'manual',
                auto_interval_seconds: 8,
                auto_pause_on_claim: true,
            },
        };
    }
    return { game: { game_title: draft.title, prompts } };
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
    const [setupDraft, setSetupDraft] = useState<SetupDraft | null>(null);
    const [savingSetup, setSavingSetup] = useState(false);
    const [generatingPrompts, setGeneratingPrompts] = useState(false);
    const [aiPrompt, setAiPrompt] = useState('');
    const [aiPromptCount, setAiPromptCount] = useState(10);
    const [aiDifficulty, setAiDifficulty] = useState('medium');
    const [error, setError] = useState('');
    const [openingSessionScope, setOpeningSessionScope] = useState('');
    const [replacementPrompt, setReplacementPrompt] = useState<ReplacementPrompt | null>(null);
    const [catalogCategory, setCatalogCategory] = useState<PartyHubGameCategory>('all');
    const [catalogSearch, setCatalogSearch] = useState('');
    const [activeRules, setActiveRules] = useState<GameRules | null>(null);
    const autoStartRef = useRef('');
    const setupSectionRef = useRef<HTMLElement | null>(null);
    const savedGamesSectionRef = useRef<HTMLElement | null>(null);
    const [setupScrollNonce, setSetupScrollNonce] = useState(0);
    const [savedGamesScrollNonce, setSavedGamesScrollNonce] = useState(0);

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
    const canManageGames = canStart || canEdit || canDelete;

    const preparedContent = useMemo(
        () => [...(workspace?.prepared_content || [])].sort((a, b) => gameSortTitle(a).localeCompare(gameSortTitle(b))),
        [workspace],
    );
    const activeSession = workspace?.active_session || null;
    const catalogGames = useMemo(
        () => [...(workspace?.catalog || [])]
            .filter((game) => game.launchable !== false)
            .sort((a, b) => gameSortTitle(a).localeCompare(gameSortTitle(b))),
        [workspace],
    );
    const filteredCatalogGames = useMemo(() => {
        const query = catalogSearch.trim().toLowerCase();
        return catalogGames.filter((game) => {
            if (catalogCategory !== 'all' && categoryForCatalogGame(game) !== catalogCategory) return false;
            if (!query) return true;
            const mode = getGameModeConfig(game.id as Parameters<typeof getGameModeConfig>[0]);
            return [
                game.title,
                game.description,
                mode.title,
                mode.description,
                game.game_type,
                game.runtime_type,
            ].filter(Boolean).join(' ').toLowerCase().includes(query);
        });
    }, [catalogCategory, catalogGames, catalogSearch]);

    useEffect(() => {
        if (setupScrollNonce === 0) return;
        const raf = window.requestAnimationFrame || ((callback: FrameRequestCallback) => window.setTimeout(callback, 0));
        raf(() => {
            setupSectionRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' });
        });
    }, [setupScrollNonce]);

    useEffect(() => {
        if (savedGamesScrollNonce === 0) return;
        const raf = window.requestAnimationFrame || ((callback: FrameRequestCallback) => window.setTimeout(callback, 0));
        raf(() => {
            savedGamesSectionRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' });
        });
    }, [savedGamesScrollNonce]);

    async function openActiveSession(scope: 'organizer' | 'player' | 'spectator') {
        if (!activeSession) return;
        const route = scope === 'organizer' ? 'organizer' : scope === 'player' ? 'join' : 'spectate';
        setOpeningSessionScope(scope);
        setError('');
        try {
            const res = await fetch(`${API_URL}/integrations/revelry/party-games/launch-token`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    party_games_token: partyGamesToken,
                    session_id: activeSession.session_id,
                    scope,
                    route,
                    embed: true,
                }),
            });
            if (!res.ok) throw new Error('launch_failed');
            const data = await res.json();
            window.location.href = data.launch_url;
        } catch {
            setError('Could not open that game. Please try again.');
        } finally {
            setOpeningSessionScope('');
        }
    }

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
                        activeTitle: detail.game_title,
                        activeGameType: detail.game_type,
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

    function openSetup(game: CatalogGame, content?: PreparedContent, payload?: Record<string, unknown>) {
        const gameType = game.game_type || game.id;
        const prompts = promptLinesFromPayload(gameType, payload || {});
        const timeLimit = Number((payload?.time_limit as number | undefined) || content?.time_limit || game.config_schema?.time_limit?.default || 30);
        const fallbackPrompt = launchContext?.external_container_title
            ? `${launchContext.external_container_title} ${game.title}`
            : game.title;
        setSetupDraft({
            game,
            contentId: content?.localplay_content_id,
            title: content?.title || game.title,
            promptsText: prompts.length ? prompts.join('\n') : defaultPromptsForGame(gameType),
            timeLimit: Number.isFinite(timeLimit) ? timeLimit : 30,
        });
        setAiPrompt(fallbackPrompt);
        setAiPromptCount(gameType === 'wmlt' ? 8 : 10);
        setAiDifficulty(gameType === 'wmlt' ? 'party' : 'medium');
        setSetupScrollNonce((value) => value + 1);
    }

    function createFromCatalog(game: CatalogGame) {
        if (game.can_create_content || game.embedded_authoring_supported) {
            if ((game.game_type || game.id) !== 'quiz') {
                openSetup(game);
                return;
            }
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

    async function editSavedContent(content: PreparedContent) {
        if (content.game_type === 'quiz') {
            void openAuthoring('edit', content.game_type, content);
            return;
        }
        const game = catalogGames.find((item) => (item.game_type || item.id) === content.game_type);
        if (!game) {
            setError('That game type is not available for this party.');
            return;
        }
        setStartingId(content.localplay_content_id);
        setError('');
        try {
            const res = await fetch(`${API_URL}/integrations/revelry/party-games/content/${encodeURIComponent(content.localplay_content_id)}?party_games_token=${encodeURIComponent(partyGamesToken)}&include_payload=true`);
            if (!res.ok) throw new Error('load_failed');
            const data = await res.json();
            openSetup(game, content, data.content_payload || {});
        } catch {
            setError('Could not open that setup. Please try again.');
        } finally {
            setStartingId('');
        }
    }

    async function saveSetup(startAfterSave = false) {
        if (!setupDraft) return;
        const gameType = setupDraft.game.game_type || setupDraft.game.id;
        const payload = contentPayloadFromDraft(setupDraft);
        const promptCount = gameType === 'housie'
            ? 1
            : gameType === 'wmlt'
            ? (payload.game.statements || []).length
            : (payload.game.prompts || []).length;
        if (!setupDraft.title.trim() || promptCount < 1) {
            setError('Add a title and at least one prompt.');
            return;
        }
        setSavingSetup(true);
        setError('');
        try {
            const res = await fetch(`${API_URL}/integrations/revelry/party-games/content`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    party_games_token: partyGamesToken,
                    game_type: gameType,
                    title: setupDraft.title.trim(),
                    content_id: setupDraft.contentId,
                    content_payload: payload,
                    status: 'ready',
                }),
            });
            if (!res.ok) throw new Error('save_failed');
            const data = await res.json();
            setWorkspace(data.workspace);
            setSetupDraft(null);
            if (startAfterSave) {
                const saved = data.content || {};
                void startGame({
                    localplay_content_id: data.localplay_content_id,
                    game_type: saved.game_type || gameType,
                    title: saved.title || setupDraft.title,
                    time_limit: saved.time_limit || setupDraft.timeLimit,
                });
            } else {
                setSavedGamesScrollNonce((value) => value + 1);
            }
        } catch {
            setError('Could not save that game. Please try again.');
        } finally {
            setSavingSetup(false);
        }
    }

    async function generateSetupPrompts() {
        if (!setupDraft) return;
        const gameType = setupDraft.game.game_type || setupDraft.game.id;
        setGeneratingPrompts(true);
        setError('');
        try {
            const res = await fetch(`${API_URL}/integrations/revelry/party-games/prompts/generate`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    party_games_token: partyGamesToken,
                    game_type: gameType,
                    prompt: aiPrompt.trim() || title,
                    difficulty: aiDifficulty,
                    num_prompts: aiPromptCount,
                }),
            });
            if (!res.ok) throw new Error('generate_failed');
            const data = await res.json();
            const lines = promptLinesFromPayload(gameType, data.content_payload || {});
            if (lines.length < 1) throw new Error('empty_generation');
            setSetupDraft({
                ...setupDraft,
                title: (data.content_payload?.game?.game_title as string | undefined) || setupDraft.title,
                promptsText: lines.join('\n'),
            });
            setSetupScrollNonce((value) => value + 1);
        } catch {
            setError('Could not generate prompts. Try a different theme or edit the prompts manually.');
        } finally {
            setGeneratingPrompts(false);
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
            returnToHostApp(launchContext.return_url, { parentOrigin: launchContext.parent_origin });
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
                    <span>{activeSession ? `Active room ${activeSession.room_code}` : 'Party game hub'}</span>
                </div>
                {launchContext?.return_url && (
                    <button className="party-hub__return" onClick={returnToRevelry}>
                        {display.return_label || 'Back to Revelry'}
                    </button>
                )}
            </header>

            {error && <div className="party-hub__error">{error}</div>}

            {activeSession && (
                <section className="party-hub__section">
                    <div className="party-hub__section-head">
                        <div>
                            <h2>Game in progress</h2>
                            <p>
                                {activeSession.joinable
                                    ? 'Join the current game or open the watch view.'
                                    : activeSession.feed_card?.body || 'This game is no longer joinable.'}
                            </p>
                        </div>
                    </div>
                    <article className="party-hub__card party-hub__active-card">
                        <div>
                            <span>{activeSession.status}</span>
                            <h3>{activeSession.feed_card?.title || `Room ${activeSession.room_code}`}</h3>
                            <p>{activeSession.joinable ? `Room code ${activeSession.room_code}` : 'Completed or closed'}</p>
                        </div>
                        <div className="party-hub__actions">
                            {canStart && activeSession.joinable && (
                                <button onClick={() => openActiveSession('organizer')} disabled={openingSessionScope === 'organizer'}>
                                    {openingSessionScope === 'organizer' ? 'Opening...' : 'Host game'}
                                </button>
                            )}
                            {activeSession.joinable && (
                                <button onClick={() => openActiveSession('player')} disabled={openingSessionScope === 'player'}>
                                    {openingSessionScope === 'player' ? 'Opening...' : 'Join to play'}
                                </button>
                            )}
                            <button className="party-hub__secondary" onClick={() => openActiveSession('spectator')} disabled={openingSessionScope === 'spectator'}>
                                {openingSessionScope === 'spectator' ? 'Opening...' : 'Join to watch'}
                            </button>
                        </div>
                    </article>
                </section>
            )}

            {!activeSession && !canManageGames && (
                <section className="party-hub__section">
                    <div className="party-hub__empty party-hub__guest-empty">
                        <h2>Waiting for the host to start a game</h2>
                        <p>When a game starts, you will be able to join or watch from here.</p>
                    </div>
                </section>
            )}

            {replacementPrompt && (
                <section className="party-hub__confirm" role="dialog" aria-modal="true" aria-labelledby="replace-game-title">
                    <div>
                        <p>Active game</p>
                        <h2 id="replace-game-title">Replace the current game?</h2>
                        <span>
                            {replacementPrompt.message}
                            {' '}
                            {replacementPrompt.activeTitle
                                ? `Current game: "${replacementPrompt.activeTitle}".`
                                : replacementPrompt.activeGameType
                                    ? `Current game type: ${replacementPrompt.activeGameType}.`
                                    : ''}
                            {' '}
                            Starting "{replacementPrompt.game.title}" will close the current room for this party.
                        </span>
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

            {canManageGames && (
                <section className="party-hub__section">
                    <div className="party-hub__section-head">
                        <div>
                            <h2>Create a game</h2>
                            <p>Pick what this party plays next.</p>
                        </div>
                    </div>
                    <div className="party-hub__catalog-tools" role="search">
                        <label className="game-search party-hub__search">
                            <Search size={18} aria-hidden="true" />
                            <span className="sr-only">Search games</span>
                            <input
                                type="search"
                                value={catalogSearch}
                                onChange={(event) => setCatalogSearch(event.target.value)}
                                placeholder="Search games"
                            />
                        </label>
                        <div className="game-category-tabs party-hub__category-tabs" aria-label="Filter games by category">
                            {PARTY_HUB_CATEGORY_OPTIONS.map((category) => (
                                <button
                                    key={category.id}
                                    type="button"
                                    className={`game-category-tab ${catalogCategory === category.id ? 'active' : ''}`}
                                    onClick={() => setCatalogCategory(category.id)}
                                    aria-pressed={catalogCategory === category.id}
                                >
                                    {category.label}
                                </button>
                            ))}
                        </div>
                    </div>
                    {catalogGames.length === 0 ? (
                        <div className="party-hub__empty">No games are available for this party yet.</div>
                    ) : filteredCatalogGames.length === 0 ? (
                        <div className="party-hub__empty party-hub__filtered-empty">
                            <span>No games match that search.</span>
                            <button type="button" className="party-hub__secondary" onClick={() => { setCatalogSearch(''); setCatalogCategory('all'); }}>
                                Clear search
                            </button>
                        </div>
                    ) : (
                        <div className="party-hub__grid party-hub__grid--catalog">
                            {filteredCatalogGames.map((game) => {
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
                                            {game.rules && (
                                                <button type="button" className="party-hub__secondary" onClick={() => setActiveRules(game.rules || null)}>
                                                    Rules
                                                </button>
                                            )}
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
            )}

            {setupDraft && (
                <section ref={setupSectionRef} className="party-hub__section party-hub__setup">
                    <div className="party-hub__section-head">
                        <div>
                            <h2>{setupCopyForGame(setupDraft.game.game_type || setupDraft.game.id).heading}</h2>
                            <p>{setupCopyForGame(setupDraft.game.game_type || setupDraft.game.id).help}</p>
                        </div>
                    </div>
                    <label>
                        <span>Title</span>
                        <input
                            value={setupDraft.title}
                            onChange={(event) => setSetupDraft({ ...setupDraft, title: event.target.value })}
                        />
                    </label>
                    {(setupDraft.game.game_type || setupDraft.game.id) === 'housie' ? (
                        <div className="party-hub__empty">Default prizes: Quick 5, Four Corners, Top Row, Middle Row, Bottom Row, Full House.</div>
                    ) : (
                        <label>
                            <span>{setupCopyForGame(setupDraft.game.game_type || setupDraft.game.id).promptLabel}</span>
                            <textarea
                                value={setupDraft.promptsText}
                                rows={7}
                                onChange={(event) => setSetupDraft({ ...setupDraft, promptsText: event.target.value })}
                            />
                        </label>
                    )}
                    {setupDraft.game.supports_ai_generation && (
                        <div className="party-hub__ai-box">
                            <div>
                                <strong>Generate prompts with AI</strong>
                                <span>Use the party theme, then edit anything before saving.</span>
                            </div>
                            <label>
                                <span>Theme</span>
                                <input
                                    value={aiPrompt}
                                    onChange={(event) => setAiPrompt(event.target.value)}
                                    placeholder="Christmas party, baby shower, game night..."
                                    maxLength={140}
                                />
                            </label>
                            <div className="party-hub__setup-row">
                                <label>
                                    <span>Prompts</span>
                                    <select value={aiPromptCount} onChange={(event) => setAiPromptCount(Number(event.target.value))}>
                                        {PROMPT_COUNT_OPTIONS.map((count) => (
                                            <option key={count} value={count}>{count}</option>
                                        ))}
                                    </select>
                                </label>
                                <label>
                                    <span>{(setupDraft.game.game_type || setupDraft.game.id) === 'wmlt' ? 'Vibe' : 'Difficulty'}</span>
                                    <select value={aiDifficulty} onChange={(event) => setAiDifficulty(event.target.value)}>
                                        {(setupDraft.game.game_type || setupDraft.game.id) === 'wmlt' ? (
                                            <>
                                                <option value="party">Party</option>
                                                <option value="wholesome">Wholesome</option>
                                                <option value="spicy">Spicy</option>
                                                <option value="work">Work-safe</option>
                                            </>
                                        ) : (
                                            <>
                                                <option value="easy">Easy</option>
                                                <option value="medium">Medium</option>
                                                <option value="hard">Hard</option>
                                            </>
                                        )}
                                    </select>
                                </label>
                            </div>
                            <button className="party-hub__secondary" onClick={() => void generateSetupPrompts()} disabled={generatingPrompts}>
                                {generatingPrompts ? 'Generating...' : 'Generate prompts'}
                            </button>
                        </div>
                    )}
                    {(setupDraft.game.game_type || setupDraft.game.id) === 'drawing' && (
                        <label>
                            <span>Round timer</span>
                            <input
                                type="number"
                                min={5}
                                max={60}
                                value={setupDraft.timeLimit || 30}
                                onChange={(event) => setSetupDraft({ ...setupDraft, timeLimit: Number(event.target.value) })}
                            />
                        </label>
                    )}
                    <div className="party-hub__actions">
                        <button onClick={() => void saveSetup(false)} disabled={savingSetup}>
                            {savingSetup ? 'Saving...' : 'Save'}
                        </button>
                        {canStart && (
                            <button onClick={() => void saveSetup(true)} disabled={savingSetup}>
                                {savingSetup ? 'Saving...' : 'Save and start'}
                            </button>
                        )}
                        <button className="party-hub__secondary" onClick={() => setSetupDraft(null)} disabled={savingSetup}>
                            Cancel
                        </button>
                    </div>
                </section>
            )}

            {canManageGames && (
                <section ref={savedGamesSectionRef} className="party-hub__section">
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
                                    {canEdit && (
                                        <button onClick={() => void editSavedContent(content)}>Edit/Open</button>
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
            )}
            <GameRulesModal rules={activeRules} onClose={() => setActiveRules(null)} />
        </main>
    );
}
