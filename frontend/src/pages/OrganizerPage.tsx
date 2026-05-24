import { useState, useRef, useEffect, useCallback, useMemo } from 'react';
import { API_URL, WS_URL } from '../config';
import { type Quiz, type QuizPack, type MLTGame, type DrawingGame, type GameType, type LeaderboardEntry, type PlayerInfo, type TeamLeaderboardEntry, type Question } from '../types';
import { soundManager } from '../utils/sound';
import { track } from '../utils/analytics';
import { getDeviceId, setCheckoutPending, getCheckoutPending, clearCheckoutPending } from '../utils/storage';
import { apiHeaders, apiUrl, generateIdempotencyKey } from '../utils/api';
import { mediaUrl } from '../utils/media';
import GameSelectScreen from '../components/organizer/GameSelectScreen';
import PromptScreen, { type AIProvider } from '../components/organizer/PromptScreen';
import QuizVariantPromptScreen from '../components/organizer/QuizVariantPromptScreen';
import CustomQuizEditor from '../components/organizer/CustomQuizEditor';
import MLTPromptScreen from '../components/organizer/MLTPromptScreen';
import DrawingPromptScreen from '../components/organizer/DrawingPromptScreen';
import LoadingScreen, { PREPARING_MESSAGES } from '../components/organizer/LoadingScreen';
import ReviewScreen from '../components/organizer/ReviewScreen';
import MLTReviewScreen from '../components/organizer/MLTReviewScreen';
import DrawingReviewScreen from '../components/organizer/DrawingReviewScreen';
import ImageGenerationScreen from '../components/organizer/ImageGenerationScreen';
import LobbyScreen from '../components/organizer/LobbyScreen';
import GameQuestionScreen from '../components/organizer/GameQuestionScreen';
import LeaderboardScreen from '../components/organizer/LeaderboardScreen';
import LeaderboardBarChart from '../components/LeaderboardBarChart';
import PodiumScreen from '../components/organizer/PodiumScreen';
import BonusSplash from '../components/BonusSplash';
import ErrorModal from '../components/ErrorModal';
import { useRemoteConfigContext } from '../context/RemoteConfigContext';
import { getGameModeConfig, isQuizRuntimeGame, runtimeGameType } from '../gameModes';

type OrganizerState = 'SELECT_GAME' | 'PROMPT' | 'QUIZ_VARIANT_PROMPT' | 'CUSTOM_QUIZ' | 'QUIZ_LIBRARY' | 'MLT_PROMPT' | 'DRAWING_PROMPT' | 'LOADING' | 'REVIEW' | 'MLT_REVIEW' | 'DRAWING_REVIEW' | 'GENERATING_IMAGES' | 'ROOM' | 'QUESTION' | 'LEADERBOARD' | 'PODIUM';

function defaultTimeLimitForGame(type: GameType): number {
    return type === 'drawing' ? 30 : 15;
}

export default function OrganizerPage() {
    const { config: remoteConfig } = useRemoteConfigContext();
    const [state, setState] = useState<OrganizerState>('SELECT_GAME');
    const [gameType, setGameType] = useState<GameType>('quiz');
    const [prompt, setPrompt] = useState('');
    const [difficulty, setDifficulty] = useState('medium');
    const [numQuestions, setNumQuestions] = useState(10);
    const [quiz, setQuiz] = useState<Quiz | null>(null);
    const [quizOrigin, setQuizOrigin] = useState<'ai' | 'custom'>('ai');
    const [editingPackId, setEditingPackId] = useState<string | undefined>(undefined);
    const [libraryPacks, setLibraryPacks] = useState<QuizPack[]>([]);
    const [libraryLoading, setLibraryLoading] = useState(false);
    const [mltGame, setMltGame] = useState<MLTGame | null>(null);
    const [drawingGame, setDrawingGame] = useState<DrawingGame | null>(null);
    const [contentId, setContentId] = useState('');
    const [roomCode, setRoomCode] = useState('');
    const [hostAppJoinUrl, setHostAppJoinUrl] = useState('');
    const [hostAppJoinLabel, setHostAppJoinLabel] = useState('Scan to join from Revelry');
    const [hostAppReturnUrl, setHostAppReturnUrl] = useState('');
    const [hostAppPartyHubUrl, setHostAppPartyHubUrl] = useState('');
    const [timeLimit, setTimeLimit] = useState(15);
    const [playerCount, setPlayerCount] = useState(0);
    const [currentQuestion, setCurrentQuestion] = useState(0);
    const [totalQuestions, setTotalQuestions] = useState(0);
    const [timeRemaining, setTimeRemaining] = useState(15);
    const [leaderboard, setLeaderboard] = useState<LeaderboardEntry[]>([]);
    const [teamLeaderboard, setTeamLeaderboard] = useState<TeamLeaderboardEntry[]>([]);
    const [sdAvailable, setSdAvailable] = useState(false);
    const [imageProgress, setImageProgress] = useState(0);
    const [questionImages, setQuestionImages] = useState<Record<number, string>>({});
    const [liveQuestion, setLiveQuestion] = useState<Question | null>(null);
    const [players, setPlayers] = useState<PlayerInfo[]>([]);
    const [answeredCount, setAnsweredCount] = useState(0);
    const [provider, setProvider] = useState('ollama');
    const [providers, setProviders] = useState<AIProvider[]>([]);
    const [loadingCopy, setLoadingCopy] = useState<{ title: string; messages?: string[] }>({ title: 'Generating Quiz' });
    const [isBonus, setIsBonus] = useState(false);
    const [showBonusSplash, setShowBonusSplash] = useState(false);
    const [roomLocked, setRoomLocked] = useState(false);
    // WMLT-specific state for organizer question screen
    const [currentStatement, setCurrentStatement] = useState('');
    const [showVotes, setShowVotes] = useState(true);
    const [wmltRoundResult, setWmltRoundResult] = useState<{ winner: string; winners: string[]; round_podium: { nickname: string; avatar: string; vote_count: number; voters: string[] }[]; unanimous: boolean; show_votes: boolean; statement: string } | null>(null);
    const [drawingRoundResult, setDrawingRoundResult] = useState<{ prompt: string; drawer: string; correct_guessers: string[] } | null>(null);
    const [superlatives, setSuperlatives] = useState<{ title: string; icon: string; winner: string; avatar: string; detail: string }[]>([]);
    const [errorModal, setErrorModal] = useState<{ title: string; message: string; upgradeAvailable?: boolean; returnToHostApp?: boolean } | null>(null);
    const wsRef = useRef<WebSocket | null>(null);
    const stateRef = useRef<OrganizerState>('SELECT_GAME');
    const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
    const roomCodeRef = useRef('');
    const organizerTokenRef = useRef('');
    const flowEpochRef = useRef(0);
    const mountedRef = useRef(true);
    const connectWsRef = useRef<(code: string) => void>(() => {});
    const gameTypeRef = useRef<GameType>('quiz');
    const checkoutPollRef = useRef<ReturnType<typeof setInterval> | null>(null);
    const hostAppMode = useMemo(() => {
        const params = new URLSearchParams(window.location.search);
        return params.get('embed') === '1' || params.has('launch_token') || params.has('session_id');
    }, []);

    useEffect(() => { stateRef.current = state; }, [state]);
    useEffect(() => { roomCodeRef.current = roomCode; }, [roomCode]);
    useEffect(() => { gameTypeRef.current = gameType; }, [gameType]);
    useEffect(() => {
        if (!hostAppMode && errorModal?.upgradeAvailable) track('paywall_shown', { source: 'error_modal' });
    }, [errorModal, hostAppMode]);

    // Listen for home navigation from hamburger menu
    useEffect(() => {
        const handler = () => {
            const homeSafeStates: OrganizerState[] = [
                'SELECT_GAME',
                'PROMPT',
                'QUIZ_VARIANT_PROMPT',
                'CUSTOM_QUIZ',
                'QUIZ_LIBRARY',
                'MLT_PROMPT',
                'DRAWING_PROMPT',
                'LOADING',
                'REVIEW',
                'MLT_REVIEW',
                'DRAWING_REVIEW',
            ];
            if (homeSafeStates.includes(stateRef.current)) {
                flowEpochRef.current += 1;
                setQuiz(null);
                setMltGame(null);
                setDrawingGame(null);
                setEditingPackId(undefined);
                setContentId('');
                setQuestionImages({});
                setState('SELECT_GAME');
            }
        };
        window.addEventListener('navigate-home', handler);
        return () => window.removeEventListener('navigate-home', handler);
    }, []);

    useEffect(() => {
        fetch(`${API_URL}/sd/status`)
            .then(res => res.ok ? res.json() : Promise.reject())
            .then(data => setSdAvailable(data?.available ?? false))
            .catch(() => setSdAvailable(false));

        fetch(`${API_URL}/providers`)
            .then(res => res.ok ? res.json() : Promise.reject())
            .then(data => {
                setProviders(data?.providers || []);
                const defaultProvider = data?.providers?.find((p: AIProvider) => p.available);
                if (defaultProvider) setProvider(defaultProvider.id);
            })
            .catch(() => {});

        // Resume pending checkout: if a previous checkout was interrupted, poll for token
        const pending = hostAppMode ? { pending: false } : getCheckoutPending();
        let poll: ReturnType<typeof setInterval> | null = null;
        if (pending.pending) {
            let attempts = 0;
            poll = setInterval(async () => {
                attempts++;
                if (attempts > 30) { clearInterval(poll!); poll = null; clearCheckoutPending(); return; }
                try {
                    const tokenRes = await fetch(apiUrl('/checkout/token'), { headers: apiHeaders() });
                    if (tokenRes.ok) {
                        const data = await tokenRes.json();
                        clearCheckoutPending();
                        clearInterval(poll!); poll = null;
                        track('tokens_purchased', { source: 'resume', tokens_added: data.tokens_added });
                        window.dispatchEvent(new CustomEvent('refresh-sparks'));
                        setErrorModal({ title: 'Sparks Added!', message: `+${data.tokens_added} sparks added to your balance. Enjoy!` });
                    }
                } catch { /* keep polling */ }
            }, 2000);
        }
        return () => { if (poll) clearInterval(poll); };
    }, [hostAppMode]);


    const handleWsMessage = useCallback((event: MessageEvent) => {
        let msg: Record<string, unknown>;
        try { msg = JSON.parse(event.data); } catch { return; }
        if (msg.type === 'PLAYER_JOINED') {
            setPlayerCount(msg.player_count as number);
            setPlayers(msg.players as PlayerInfo[] || []);
            soundManager.play('playerJoin');
        }
        else if (msg.type === 'QUESTION') {
            // First question means game just started (sparks were charged)
            if (!hostAppMode && msg.question_number === 1) {
                window.dispatchEvent(new CustomEvent('refresh-sparks'));
            }
            setCurrentQuestion(msg.question_number as number);
            setTotalQuestions(msg.total_questions as number);
            setTimeRemaining(msg.time_limit as number);
            setAnsweredCount(0);
            setIsBonus(msg.is_bonus as boolean || false);
            setLiveQuestion((msg.question as Question | undefined) || null);
            if (msg.is_bonus) setShowBonusSplash(true);
            // For WMLT, store the statement text
            if (msg.statement) {
                setCurrentStatement((msg.statement as { text: string }).text);
            }
            if (msg.game_type === 'drawing') {
                setGameType('drawing');
                setAnsweredCount(0);
            }
            setState('QUESTION');
        }
        else if (msg.type === 'TIMER') setTimeRemaining(msg.remaining as number);
        else if (msg.type === 'ANSWER_COUNT') setAnsweredCount(msg.answered as number);
        else if (msg.type === 'VOTE_COUNT') setAnsweredCount(msg.voted as number);
        else if (msg.type === 'QUESTION_OVER') {
            setLeaderboard(msg.leaderboard as LeaderboardEntry[]);
            if (msg.game_type === 'wmlt') {
                setWmltRoundResult({
                    winner: msg.winner as string,
                    winners: (msg.winners as string[]) || [msg.winner as string],
                    round_podium: (msg.round_podium as { nickname: string; avatar: string; vote_count: number; voters: string[] }[]) || [],
                    unanimous: msg.unanimous as boolean || false,
                    show_votes: msg.show_votes as boolean ?? true,
                    statement: msg.statement as string || '',
                });
                setDrawingRoundResult(null);
            } else if (msg.game_type === 'drawing') {
                setDrawingRoundResult({
                    prompt: msg.prompt as string || '',
                    drawer: msg.drawer as string || '',
                    correct_guessers: (msg.correct_guessers as string[]) || [],
                });
                setWmltRoundResult(null);
            } else {
                setWmltRoundResult(null);
                setDrawingRoundResult(null);
            }
            setState('LEADERBOARD');
        }
        else if (msg.type === 'PODIUM') {
            setLeaderboard(msg.leaderboard as LeaderboardEntry[]);
            setTeamLeaderboard(msg.team_leaderboard as TeamLeaderboardEntry[] || []);
            setSuperlatives((msg.superlatives as { title: string; icon: string; winner: string; avatar: string; detail: string }[]) || []);
            track('game_completed', { room_code: roomCodeRef.current, game_type: gameTypeRef.current, player_count: (msg.leaderboard as LeaderboardEntry[])?.length || 0, winner: (msg.leaderboard as LeaderboardEntry[])?.[0]?.nickname });
            setState('PODIUM');
            soundManager.play('fanfare');
        }
        else if (msg.type === 'PLAYER_LEFT' || msg.type === 'PLAYER_DISCONNECTED') {
            setPlayerCount(msg.player_count as number);
            setPlayers(msg.players as PlayerInfo[] || []);
        }
        else if (msg.type === 'PLAYER_RECONNECTED') {
            setPlayerCount(msg.player_count as number);
            setPlayers(msg.players as PlayerInfo[] || []);
        }
        else if (msg.type === 'ROOM_RESET') {
            setPlayerCount(msg.player_count as number);
            setPlayers(msg.players as PlayerInfo[] || []);
            setRoomLocked(false);
            setState('ROOM');
        }
        else if (msg.type === 'INSUFFICIENT_SPARKS') {
            setErrorModal({
                title: hostAppMode ? 'Game Unavailable' : 'Not Enough Sparks',
                message: hostAppMode ? 'This Revelry-managed game could not be started. Please return to Revelry and try again.' : msg.message as string || 'You need more sparks to start a game.',
                upgradeAvailable: !hostAppMode,
            });
        }
        else if (msg.type === 'ROOM_LOCK_STATUS') {
            setRoomLocked(msg.locked as boolean);
        }
        else if (msg.type === 'ORGANIZER_RECONNECTED') {
            setRoomCode(msg.room_code as string);
            setPlayerCount(msg.player_count as number);
            setPlayers(msg.players as PlayerInfo[] || []);
            setTotalQuestions(msg.total_questions as number);
            setLeaderboard(msg.leaderboard as LeaderboardEntry[] || []);
            setTeamLeaderboard(msg.team_leaderboard as TeamLeaderboardEntry[] || []);
            setTimeLimit(msg.time_limit as number);
            setRoomLocked(msg.locked as boolean ?? false);
            if (msg.game_type) setGameType(msg.game_type as GameType);
            if (msg.quiz) {
                const quizData = msg.quiz as Record<string, unknown>;
                if (quizData.questions) {
                    setQuiz(quizData as unknown as Quiz);
                    setTotalQuestions((quizData.questions as unknown[]).length);
                } else if (quizData.statements) {
                    setMltGame(quizData as unknown as MLTGame);
                    setTotalQuestions((quizData.statements as unknown[]).length);
                } else if (quizData.prompts) {
                    setDrawingGame(quizData as unknown as DrawingGame);
                    setTotalQuestions((quizData.prompts as unknown[]).length);
                }
            }
            if (msg.state === 'LOBBY' || msg.state === 'INTRO') {
                setState('ROOM');
            } else if (msg.state === 'QUESTION') {
                setCurrentQuestion(msg.question_number as number);
                setTimeRemaining((msg.time_remaining ?? msg.time_limit) as number);
                setAnsweredCount((msg.answered_count ?? msg.voted_count ?? 0) as number);
                setIsBonus(msg.is_bonus as boolean || false);
                setLiveQuestion((msg.question as Question | undefined) || null);
                if (msg.statement) {
                    setCurrentStatement((msg.statement as { text: string }).text);
                }
                setState('QUESTION');
            } else if (msg.state === 'LEADERBOARD') {
                setCurrentQuestion(msg.question_number as number);
                setState('LEADERBOARD');
            } else if (msg.state === 'PODIUM') {
                setState('PODIUM');
                soundManager.play('fanfare');
            }
        }
        else if (msg.type === 'ERROR') {
            const message = msg.message as string || 'Unknown error';
            console.error('Organizer error:', message);
            // Non-fatal errors (e.g. min players) — show alert, stay in current state
            if (message.includes('players')) {
                alert(message);
            } else {
                if (hostAppMode) {
                    setErrorModal({
                        title: 'Game Unavailable',
                        message: 'This Revelry-managed game is no longer available. Return to Revelry Games to start another one.',
                        returnToHostApp: true,
                    });
                } else {
                    setRoomCode('');
                    setState('SELECT_GAME');
                }
            }
        }
    }, [hostAppMode]);

    const handleGameSelect = (type: GameType) => {
        window.dispatchEvent(new CustomEvent('close-settings'));
        setGameType(type);
        setTimeLimit(defaultTimeLimitForGame(type));
        if (type === 'wmlt') setDifficulty('party');
        else setDifficulty('medium');
        if (type === 'wmlt') setState('MLT_PROMPT');
        else if (type === 'drawing') setState('DRAWING_PROMPT');
        else if (type === 'quiz') setState('PROMPT');
        else setState('QUIZ_VARIANT_PROMPT');
    };

    const generateQuiz = async () => {
        if (remoteConfig.operations.kill_generate) {
            setErrorModal({ title: 'Temporarily Unavailable', message: 'Game generation is temporarily disabled. Please try again later.' });
            return;
        }
        setLoadingCopy({ title: 'Generating Quiz' });
        setState('LOADING');
        try {
            const res = await fetch(apiUrl('/quiz/generate'), {
                method: 'POST',
                headers: apiHeaders({ 'X-Idempotency-Key': generateIdempotencyKey() }),
                body: JSON.stringify({
                    prompt,
                    difficulty,
                    num_questions: numQuestions,
                    provider,
                    mode: getGameModeConfig(gameType).mode || 'classic',
                }),
            });
            if (res.status === 402) {
                track('paywall_hit', { source: 'quiz' });
                setErrorModal({ title: 'Not Enough Sparks', message: 'You need more sparks! Buy a spark pack or watch an ad to earn free sparks.', upgradeAvailable: !hostAppMode });
                setState(gameType === 'quiz' ? 'PROMPT' : 'QUIZ_VARIANT_PROMPT');
                return;
            }
            if (res.status === 503) {
                track('quota_error', { source: 'quiz' });
                setErrorModal({ title: 'Daily Limit Reached', message: 'Daily generation limit reached. Try again tomorrow or buy a spark pack!', upgradeAvailable: true });
                setState(gameType === 'quiz' ? 'PROMPT' : 'QUIZ_VARIANT_PROMPT');
                return;
            }
            if (res.status === 429) {
                const err = await res.json().catch(() => ({ detail: 'Too many requests. Please wait a minute.' }));
                setErrorModal({ title: 'Rate Limited', message: err.detail || 'Too many requests.' });
                setState(gameType === 'quiz' ? 'PROMPT' : 'QUIZ_VARIANT_PROMPT');
                return;
            }
            const data = await res.json();
            if (data.quiz) {
                setQuizOrigin('ai');
                setQuiz(data.quiz);
                setContentId(data.quiz_id);
                setTotalQuestions(data.quiz.questions.length);
                track('quiz_generated', { topic: prompt, difficulty, num_questions: numQuestions, provider, mode: getGameModeConfig(gameType).mode || 'classic' });
                window.dispatchEvent(new CustomEvent('refresh-sparks'));
                setState('REVIEW');
            } else {
                setErrorModal({ title: 'Generation Failed', message: 'Failed to generate quiz. Please try a different topic.' });
                setState(gameType === 'quiz' ? 'PROMPT' : 'QUIZ_VARIANT_PROMPT');
            }
        } catch {
            setErrorModal({ title: 'Connection Error', message: 'Could not reach the server. Check your internet connection.' });
            setState(gameType === 'quiz' ? 'PROMPT' : 'QUIZ_VARIANT_PROMPT');
        }
    };

    const importCustomQuiz = async (customQuiz: Quiz) => {
        setLoadingCopy({ title: 'Preparing Quiz', messages: PREPARING_MESSAGES });
        setState('LOADING');
        try {
            const res = await fetch(apiUrl('/quiz/import'), {
                method: 'POST',
                headers: apiHeaders(),
                body: JSON.stringify({ quiz: customQuiz }),
            });
            if (!res.ok) {
                const err = await res.json().catch(() => ({ detail: 'Could not prepare this quiz.' }));
                setErrorModal({ title: 'Quiz Error', message: err.detail || `Server error (${res.status})` });
                setState('CUSTOM_QUIZ');
                return;
            }
            const data = await res.json();
            setGameType('quiz');
            setQuizOrigin('custom');
            setQuiz(customQuiz);
            setContentId(data.quiz_id);
            setTotalQuestions(customQuiz.questions.length);
            setQuestionImages({});
            track('custom_quiz_imported', { num_questions: customQuiz.questions.length });
            setState('REVIEW');
        } catch {
            setErrorModal({ title: 'Connection Error', message: 'Could not reach the server. Check your internet connection.' });
            setState('CUSTOM_QUIZ');
        }
    };

    const saveCustomQuizPack = async (customQuiz: Quiz, packId?: string) => {
        const res = await fetch(apiUrl('/quiz-packs'), {
            method: 'POST',
            headers: apiHeaders(),
            body: JSON.stringify({ pack_id: packId, quiz: customQuiz }),
        });
        if (!res.ok) throw new Error('save_failed');
        const data = await res.json();
        setEditingPackId(data.pack.id);
        track('custom_quiz_saved', { num_questions: customQuiz.questions.length });
        return data.pack.id as string;
    };

    const loadQuizLibrary = async () => {
        setLibraryLoading(true);
        try {
            const res = await fetch(apiUrl('/quiz-packs'), { headers: apiHeaders() });
            if (!res.ok) throw new Error('load_failed');
            const data = await res.json();
            setLibraryPacks(data.packs || []);
        } catch {
            setErrorModal({ title: 'Quiz Library', message: 'Could not load your saved quizzes.' });
        } finally {
            setLibraryLoading(false);
        }
    };

    const openQuizLibrary = () => {
        setGameType('quiz');
        setState('QUIZ_LIBRARY');
        void loadQuizLibrary();
    };

    const editQuizPack = async (packId: string) => {
        setLibraryLoading(true);
        try {
            const res = await fetch(apiUrl(`/quiz-packs/${packId}`), { headers: apiHeaders() });
            if (!res.ok) throw new Error('load_failed');
            const data = await res.json();
            setEditingPackId(packId);
            setQuiz(data.quiz);
            setQuizOrigin('custom');
            setState('CUSTOM_QUIZ');
        } catch {
            setErrorModal({ title: 'Quiz Library', message: 'Could not open that quiz.' });
        } finally {
            setLibraryLoading(false);
        }
    };

    const startQuizPack = async (packId: string) => {
        const flowEpoch = ++flowEpochRef.current;
        setLoadingCopy({ title: 'Preparing Quiz', messages: PREPARING_MESSAGES });
        setState('LOADING');
        try {
            const res = await fetch(apiUrl(`/quiz-packs/${packId}/materialize`), {
                method: 'POST',
                headers: apiHeaders(),
            });
            if (!res.ok) throw new Error('start_failed');
            const data = await res.json();
            const fullRes = await fetch(apiUrl(`/quiz-packs/${packId}`), { headers: apiHeaders() });
            const fullData = fullRes.ok ? await fullRes.json() : null;
            const customQuiz = fullData?.quiz || data.quiz;
            if (flowEpoch !== flowEpochRef.current) return;
            setGameType('quiz');
            setQuizOrigin('custom');
            setQuiz(customQuiz);
            setContentId(data.quiz_id);
            setTotalQuestions(customQuiz.questions.length);
            setQuestionImages({});
            setEditingPackId(packId);
            setState('REVIEW');
        } catch {
            if (flowEpoch !== flowEpochRef.current) return;
            setErrorModal({ title: 'Quiz Library', message: 'Could not start that quiz.' });
            setState('QUIZ_LIBRARY');
        }
    };

    const deleteQuizPack = async (packId: string) => {
        try {
            const res = await fetch(apiUrl(`/quiz-packs/${packId}`), {
                method: 'DELETE',
                headers: apiHeaders(),
            });
            if (!res.ok) throw new Error('delete_failed');
            setLibraryPacks((packs) => packs.filter((pack) => pack.id !== packId));
        } catch {
            setErrorModal({ title: 'Quiz Library', message: 'Could not delete that quiz.' });
        }
    };

    const generateMLT = async () => {
        if (remoteConfig.operations.kill_generate) {
            setErrorModal({ title: 'Temporarily Unavailable', message: 'Game generation is temporarily disabled. Please try again later.' });
            return;
        }
        setLoadingCopy({ title: 'Generating Game' });
        setState('LOADING');
        try {
            const res = await fetch(apiUrl('/mlt/generate'), {
                method: 'POST',
                headers: apiHeaders({ 'X-Idempotency-Key': generateIdempotencyKey() }),
                body: JSON.stringify({ prompt, difficulty, num_rounds: numQuestions, provider }),
            });
            if (res.status === 402) {
                track('paywall_hit', { source: 'mlt' });
                setErrorModal({ title: 'Not Enough Sparks', message: 'You need more sparks! Buy a spark pack or watch an ad to earn free sparks.', upgradeAvailable: !hostAppMode });
                setState('MLT_PROMPT');
                return;
            }
            if (res.status === 503) {
                track('quota_error', { source: 'mlt' });
                setErrorModal({ title: 'Daily Limit Reached', message: 'Daily generation limit reached. Try again tomorrow or buy a spark pack!', upgradeAvailable: true });
                setState('MLT_PROMPT');
                return;
            }
            if (res.status === 429) {
                const err = await res.json().catch(() => ({ detail: 'Too many requests. Please wait a minute.' }));
                setErrorModal({ title: 'Rate Limited', message: err.detail || 'Too many requests.' });
                setState('MLT_PROMPT');
                return;
            }
            const data = await res.json();
            if (data.game) {
                setMltGame(data.game);
                setContentId(data.scenario_id);
                setTotalQuestions(data.game.statements.length);
                track('mlt_generated', { topic: prompt, difficulty, num_rounds: numQuestions, provider });
                window.dispatchEvent(new CustomEvent('refresh-sparks'));
                setState('MLT_REVIEW');
            } else {
                setErrorModal({ title: 'Generation Failed', message: 'Failed to generate statements. Please try a different topic.' });
                setState('MLT_PROMPT');
            }
        } catch {
            setErrorModal({ title: 'Connection Error', message: 'Could not reach the server. Check your internet connection.' });
            setState('MLT_PROMPT');
        }
    };

    const generateDrawing = async () => {
        if (remoteConfig.operations.kill_generate) {
            setErrorModal({ title: 'Temporarily Unavailable', message: 'Game generation is temporarily disabled. Please try again later.' });
            return;
        }
        setLoadingCopy({ title: 'Generating Prompts' });
        setState('LOADING');
        try {
            const res = await fetch(apiUrl('/drawing/generate'), {
                method: 'POST',
                headers: apiHeaders({ 'X-Idempotency-Key': generateIdempotencyKey() }),
                body: JSON.stringify({ prompt, difficulty, num_prompts: numQuestions, provider }),
            });
            if (res.status === 402) {
                track('paywall_hit', { source: 'drawing' });
                setErrorModal({ title: 'Not Enough Sparks', message: 'You need more sparks! Buy a spark pack or watch an ad to earn free sparks.', upgradeAvailable: !hostAppMode });
                setState('DRAWING_PROMPT');
                return;
            }
            if (res.status === 503) {
                track('quota_error', { source: 'drawing' });
                setErrorModal({ title: 'Daily Limit Reached', message: 'Daily generation limit reached. Try again tomorrow or buy a spark pack!', upgradeAvailable: true });
                setState('DRAWING_PROMPT');
                return;
            }
            if (res.status === 429) {
                const err = await res.json().catch(() => ({ detail: 'Too many requests. Please wait a minute.' }));
                setErrorModal({ title: 'Rate Limited', message: err.detail || 'Too many requests.' });
                setState('DRAWING_PROMPT');
                return;
            }
            const data = await res.json();
            if (data.game) {
                setDrawingGame(data.game);
                setContentId(data.drawing_id);
                setTotalQuestions(data.game.prompts.length);
                track('drawing_generated', { topic: prompt, difficulty, num_prompts: numQuestions, provider });
                window.dispatchEvent(new CustomEvent('refresh-sparks'));
                setState('DRAWING_REVIEW');
            } else {
                setErrorModal({ title: 'Generation Failed', message: 'Failed to generate drawing prompts. Please try a different topic.' });
                setState('DRAWING_PROMPT');
            }
        } catch {
            setErrorModal({ title: 'Connection Error', message: 'Could not reach the server. Check your internet connection.' });
            setState('DRAWING_PROMPT');
        }
    };

    const generateImages = async () => {
        if (!sdAvailable || !contentId) return;
        setState('GENERATING_IMAGES');
        setImageProgress(0);

        let failures = 0;
        for (let i = 0; i < (quiz?.questions.length || 0); i++) {
            const question = quiz?.questions[i];
            if (!question) continue;
            try {
                const res = await fetch(`${API_URL}/quiz/generate-images`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ quiz_id: contentId, question_id: question.id }),
                });
                if (res.ok) {
                    setQuestionImages(prev => ({
                        ...prev,
                        [question.id]: `${API_URL}/quiz/${contentId}/image/${question.id}`
                    }));
                } else {
                    failures++;
                }
            } catch {
                failures++;
            }
            setImageProgress(i + 1);
        }
        if (failures > 0) {
            setErrorModal({ title: 'Image Generation', message: `${failures} image(s) failed to generate. You can still play without them.` });
        }
        setState('REVIEW');
    };

    const updateQuiz = async (updated: Quiz) => {
        setQuiz(updated);
        setTotalQuestions(updated.questions.length);
        try {
            const res = await fetch(apiUrl(`/quiz/${contentId}`), {
                method: 'PUT',
                headers: apiHeaders(),
                body: JSON.stringify(updated),
            });
            if (res.status === 403) {
                setErrorModal({ title: 'Permission Denied', message: "You don't have permission to modify this content." });
            } else if (!res.ok) {
                console.error('Failed to save quiz update:', res.status);
            }
        } catch (err) {
            console.error('Failed to save quiz update:', err);
        }
    };

    const updateMLTGame = async (updated: MLTGame) => {
        setMltGame(updated);
        setTotalQuestions(updated.statements.length);
        try {
            const res = await fetch(apiUrl(`/mlt/${contentId}`), {
                method: 'PUT',
                headers: apiHeaders(),
                body: JSON.stringify(updated),
            });
            if (res.status === 403) {
                setErrorModal({ title: 'Permission Denied', message: "You don't have permission to modify this content." });
            } else if (!res.ok) {
                console.error('Failed to save MLT update:', res.status);
            }
        } catch (err) {
            console.error('Failed to save MLT update:', err);
        }
    };

    const updateDrawingGame = async (updated: DrawingGame) => {
        setDrawingGame(updated);
        setTotalQuestions(updated.prompts.length);
        try {
            const res = await fetch(apiUrl(`/drawing/${contentId}`), {
                method: 'PUT',
                headers: apiHeaders(),
                body: JSON.stringify(updated),
            });
            if (res.status === 403) {
                setErrorModal({ title: 'Permission Denied', message: "You don't have permission to modify this content." });
            } else if (!res.ok) {
                console.error('Failed to save DrawingGame update:', res.status);
            }
        } catch (err) {
            console.error('Failed to save DrawingGame update:', err);
        }
    };

    const connectWs = useCallback((code: string) => {
        if (wsRef.current) {
            wsRef.current.onclose = null;
            wsRef.current.close();
        }
        const clientId = `organizer-${Date.now()}`;
        const ws = new WebSocket(`${WS_URL}/ws/${code}/${clientId}?organizer=true`);
        wsRef.current = ws;
        ws.onopen = () => {
            // First-frame auth: send token as first message instead of query string
            ws.send(JSON.stringify({ type: 'AUTH', token: organizerTokenRef.current }));
        };
        ws.onmessage = handleWsMessage;
        ws.onclose = () => {
            wsRef.current = null;
            if (!mountedRef.current) return;
            const activeStates: OrganizerState[] = ['ROOM', 'QUESTION', 'LEADERBOARD', 'PODIUM'];
            if (roomCodeRef.current && activeStates.includes(stateRef.current)) {
                if (reconnectTimerRef.current) clearTimeout(reconnectTimerRef.current);
                reconnectTimerRef.current = setTimeout(() => connectWsRef.current(roomCodeRef.current), 2000);
            }
        };
    }, [handleWsMessage]);
    useEffect(() => { connectWsRef.current = connectWs; }, [connectWs]);

    useEffect(() => {
        const params = new URLSearchParams(window.location.search);
        const launchToken = params.get('launch_token');
        if (!launchToken) return;
        let cancelled = false;
        (async () => {
            try {
                const res = await fetch(apiUrl(`/integrations/revelry/launch-token/resolve?scope=organizer&launch_token=${encodeURIComponent(launchToken)}`));
                if (!res.ok) throw new Error('Launch token rejected');
                const data = await res.json();
                if (cancelled) return;
                const display = data.launch_context?.display || {};
                setRoomCode(data.room_code);
                setHostAppJoinUrl(display.guest_join_url || data.launch_context?.guest_join_url || '');
                setHostAppJoinLabel(display.guest_join_label || 'Scan to join from Revelry');
                setHostAppReturnUrl(data.launch_context?.return_url || data.return_url || '');
                setHostAppPartyHubUrl(data.launch_context?.party_hub_url || '');
                organizerTokenRef.current = data.organizer_token || '';
                setState('ROOM');
                connectWsRef.current(data.room_code);
            } catch {
                if (!cancelled) {
                    setErrorModal({ title: 'Launch Expired', message: 'This game link expired. Return to Revelry and reopen the game.', returnToHostApp: true });
                }
            }
        })();
        return () => { cancelled = true; };
    }, []);

    useEffect(() => {
        return () => {
            mountedRef.current = false;
            if (reconnectTimerRef.current) clearTimeout(reconnectTimerRef.current);
            if (checkoutPollRef.current) { clearInterval(checkoutPollRef.current); checkoutPollRef.current = null; }
            wsRef.current?.close();
            wsRef.current = null;
        };
    }, []);

    const createRoom = async () => {
        // Play Again path: reuse existing room via RESET_ROOM
        if (roomCode && wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
            if (contentId) {
                wsRef.current.send(JSON.stringify({
                    type: 'RESET_ROOM',
                    content_id: contentId,
                    time_limit: timeLimit,
                    game_type: runtimeGameType(gameType),
                }));
                return;
            }
        }

        // First-time room creation
        try {
            const body: Record<string, unknown> = {
                time_limit: timeLimit,
                game_type: runtimeGameType(gameType),
            };
            if (gameType === 'wmlt') {
                body.mlt_id = contentId;
            } else if (gameType === 'drawing') {
                body.drawing_id = contentId;
            } else if (isQuizRuntimeGame(gameType)) {
                body.quiz_id = contentId;
            }

            const res = await fetch(apiUrl('/room/create'), {
                method: 'POST',
                headers: apiHeaders(),
                body: JSON.stringify(body),
            });
            if (!res.ok) {
                const err = await res.json().catch(() => ({ detail: 'Failed to create room' }));
                setErrorModal({ title: 'Room Error', message: err.detail || `Server error (${res.status})` });
                return;
            }
            const data = await res.json();
            setRoomCode(data.room_code);
            organizerTokenRef.current = data.organizer_token || '';
            track('room_created', { room_code: data.room_code, game_type: gameType, time_limit: timeLimit });
            setState('ROOM');
            connectWs(data.room_code);
        } catch {
            setErrorModal({ title: 'Connection Error', message: 'Could not reach the server. Check your internet connection.' });
        }
    };

    const startGame = () => {
        soundManager.play('gameStart');
        track('game_started', { room_code: roomCode, game_type: gameType, player_count: playerCount, num_questions: totalQuestions });
        if (gameType === 'wmlt') {
            wsRef.current?.send(JSON.stringify({ type: 'SET_SHOW_VOTES', show_votes: showVotes }));
        }
        wsRef.current?.send(JSON.stringify({ type: 'START_GAME' }));
        wsRef.current?.send(JSON.stringify({ type: 'NEXT_QUESTION' }));
    };

    const nextQuestion = () => wsRef.current?.send(JSON.stringify({ type: 'NEXT_QUESTION' }));
    const endQuiz = () => wsRef.current?.send(JSON.stringify({ type: 'END_QUIZ' }));

    const playAgain = () => {
        setCurrentQuestion(0);
        setLeaderboard([]);
        setTeamLeaderboard([]);
        setTimeRemaining(timeLimit);
        setQuestionImages({});
        setAnsweredCount(0);
        setPrompt('');
        setCurrentStatement('');
        setState('SELECT_GAME');
    };

    const returnToHostApp = () => {
        if (hostAppPartyHubUrl) {
            window.location.assign(hostAppPartyHubUrl);
            return;
        }
        if (hostAppReturnUrl) {
            window.location.assign(hostAppReturnUrl);
            return;
        }
        setErrorModal({
            title: 'Back to Revelry',
            message: 'Open this party from Revelry to start another game.',
        });
    };

    // In Capacitor, window.location.origin is capacitor://localhost — use the web URL instead
    const isCapacitor = window.location.protocol === 'capacitor:' || window.location.hostname === 'localhost' && !window.location.port;
    const baseUrl = isCapacitor
        ? (import.meta.env.VITE_WEB_URL || 'https://games.revelryapp.me/quiz/')
        : `${window.location.origin}${import.meta.env.BASE_URL}`;
    const joinUrl = `${baseUrl}join/${roomCode}`;
    const currentQ = liveQuestion || quiz?.questions[currentQuestion - 1];
    const currentImageUrl = currentQ?.image_url ? mediaUrl(currentQ.image_url) : (currentQ ? questionImages[currentQ.id] : undefined);

    return (
        <div className="app-container">
            <div className="content-wrapper">
                {state === 'SELECT_GAME' && (
                    hostAppMode ? (
                        <div className="min-h-dvh flex flex-col items-center justify-center container-responsive safe-bottom animate-in text-center">
                            <h1 className="hero-title mb-3">Open From Revelry</h1>
                            <p className="text-[--text-tertiary] mb-6">This organizer view needs an active Revelry game launch.</p>
                            {(hostAppPartyHubUrl || hostAppReturnUrl) && (
                                <button className="btn btn-primary w-full" onClick={returnToHostApp}>
                                    Back to Revelry Games
                                </button>
                            )}
                        </div>
                    ) : (
                        <GameSelectScreen onSelect={handleGameSelect} />
                    )
                )}

                {state === 'PROMPT' && (
                    <PromptScreen
                        prompt={prompt}
                        setPrompt={setPrompt}
                        difficulty={difficulty}
                        setDifficulty={setDifficulty}
                        numQuestions={numQuestions}
                        setNumQuestions={setNumQuestions}
                        provider={provider}
                        setProvider={setProvider}
                        providers={providers}
                        onGenerate={generateQuiz}
                        onCreateCustom={() => {
                            setGameType('quiz');
                            setQuiz(null);
                            setEditingPackId(undefined);
                            setState('CUSTOM_QUIZ');
                        }}
                        onOpenLibrary={openQuizLibrary}
                    />
                )}

                {state === 'CUSTOM_QUIZ' && (
                    <CustomQuizEditor
                        onBack={() => setState('PROMPT')}
                        onReview={importCustomQuiz}
                        onSave={saveCustomQuizPack}
                        initialQuiz={quizOrigin === 'custom' ? quiz : null}
                        packId={editingPackId}
                    />
                )}

                {state === 'QUIZ_LIBRARY' && (
                    <div className="min-h-dvh flex flex-col container-responsive safe-top safe-bottom animate-in">
                        <div className="text-center py-5">
                            <div className="hero-icon mb-3">📚</div>
                            <h1 className="hero-title">My Quizzes</h1>
                            <p className="text-[--text-tertiary] mt-2">Saved custom quiz packs</p>
                        </div>
                        <div className="space-y-3 flex-1 overflow-y-auto no-scrollbar pb-4">
                            {libraryLoading && <div className="review-question-card"><div className="p-4 text-center text-[--text-tertiary]">Loading...</div></div>}
                            {!libraryLoading && libraryPacks.length === 0 && (
                                <div className="review-question-card">
                                    <div className="p-4 text-center">
                                        <p className="font-semibold mb-2">No saved quizzes yet</p>
                                        <button
                                            className="btn btn-primary"
                                            onClick={() => {
                                                setQuiz(null);
                                                setEditingPackId(undefined);
                                                setState('CUSTOM_QUIZ');
                                            }}
                                        >
                                            Create Quiz
                                        </button>
                                    </div>
                                </div>
                            )}
                            {libraryPacks.map((pack) => (
                                <div key={pack.id} className="quiz-library-card">
                                    <div className="quiz-library-card__content">
                                        <div className="quiz-library-card__meta">
                                            <p className="quiz-library-card__title">{pack.title}</p>
                                            <p className="quiz-library-card__subtitle">{pack.question_count} questions</p>
                                        </div>
                                        <div className="quiz-library-actions">
                                            <button className="btn btn-primary quiz-library-action" onClick={() => void startQuizPack(pack.id)}>
                                                Start
                                            </button>
                                            <button className="btn btn-secondary quiz-library-action" onClick={() => void editQuizPack(pack.id)}>
                                                Edit
                                            </button>
                                            <button className="btn btn-secondary quiz-library-action quiz-library-action--danger" onClick={() => void deleteQuizPack(pack.id)}>
                                                Delete
                                            </button>
                                        </div>
                                    </div>
                                </div>
                            ))}
                        </div>
                        <div className="pb-4" style={{ display: 'flex', gap: 8 }}>
                            <button onClick={() => setState('PROMPT')} className="btn btn-secondary" style={{ flexShrink: 0, paddingLeft: 16, paddingRight: 16 }}>
                                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                                    <polyline points="15 18 9 12 15 6" />
                                </svg>
                            </button>
                            <button
                                className="btn btn-primary"
                                style={{ flex: 1 }}
                                onClick={() => {
                                    setQuiz(null);
                                    setEditingPackId(undefined);
                                    setState('CUSTOM_QUIZ');
                                }}
                            >
                                New Quiz
                            </button>
                        </div>
                    </div>
                )}

                {state === 'QUIZ_VARIANT_PROMPT' && (
                    <QuizVariantPromptScreen
                        config={getGameModeConfig(gameType)}
                        prompt={prompt}
                        setPrompt={setPrompt}
                        difficulty={difficulty}
                        setDifficulty={setDifficulty}
                        numQuestions={numQuestions}
                        setNumQuestions={setNumQuestions}
                        provider={provider}
                        setProvider={setProvider}
                        providers={providers}
                        onGenerate={generateQuiz}
                        onBack={() => setState('SELECT_GAME')}
                    />
                )}

                {state === 'MLT_PROMPT' && (
                    <MLTPromptScreen
                        prompt={prompt}
                        setPrompt={setPrompt}
                        difficulty={difficulty}
                        setDifficulty={setDifficulty}
                        numRounds={numQuestions}
                        setNumRounds={setNumQuestions}
                        provider={provider}
                        setProvider={setProvider}
                        providers={providers}
                        onGenerate={generateMLT}
                        onBack={() => setState('SELECT_GAME')}
                    />
                )}

                {state === 'DRAWING_PROMPT' && (
                    <DrawingPromptScreen
                        prompt={prompt}
                        setPrompt={setPrompt}
                        difficulty={difficulty}
                        setDifficulty={setDifficulty}
                        numPrompts={numQuestions}
                        setNumPrompts={setNumQuestions}
                        provider={provider}
                        setProvider={setProvider}
                        providers={providers}
                        onGenerate={generateDrawing}
                        onBack={() => setState('SELECT_GAME')}
                    />
                )}

                {state === 'LOADING' && <LoadingScreen title={loadingCopy.title} messages={loadingCopy.messages} />}

                {state === 'REVIEW' && quiz && (
                    <ReviewScreen
                        quiz={quiz}
                        timeLimit={timeLimit}
                        setTimeLimit={setTimeLimit}
                        sdAvailable={sdAvailable}
                        questionImages={questionImages}
                        onGenerateImages={generateImages}
                        onCreateRoom={createRoom}
                        onUpdateQuiz={updateQuiz}
                        onBack={() => setState(quizOrigin === 'custom' ? 'CUSTOM_QUIZ' : gameType === 'quiz' ? 'PROMPT' : 'QUIZ_VARIANT_PROMPT')}
                    />
                )}

                {state === 'MLT_REVIEW' && mltGame && (
                    <MLTReviewScreen
                        game={mltGame}
                        timeLimit={timeLimit}
                        setTimeLimit={setTimeLimit}
                        showVotes={showVotes}
                        setShowVotes={setShowVotes}
                        onCreateRoom={createRoom}
                        onUpdateGame={updateMLTGame}
                        onBack={() => setState('MLT_PROMPT')}
                    />
                )}

                {state === 'DRAWING_REVIEW' && drawingGame && (
                    <DrawingReviewScreen
                        game={drawingGame}
                        timeLimit={timeLimit}
                        setTimeLimit={setTimeLimit}
                        onCreateRoom={createRoom}
                        onUpdateGame={updateDrawingGame}
                        onBack={() => setState('DRAWING_PROMPT')}
                    />
                )}

                {state === 'GENERATING_IMAGES' && quiz && (
                    <ImageGenerationScreen quiz={quiz} imageProgress={imageProgress} />
                )}

                {state === 'ROOM' && (
                    <LobbyScreen
                        roomCode={roomCode}
                        joinUrl={joinUrl}
                        playerCount={playerCount}
                        players={players}
                        locked={roomLocked}
                        hostAppMode={hostAppMode}
                        hostAppJoinUrl={hostAppJoinUrl}
                        hostAppJoinLabel={hostAppJoinLabel}
                        onStartGame={startGame}
                        onToggleLock={() => wsRef.current?.send(JSON.stringify({ type: 'TOGGLE_LOCK' }))}
                    />
                )}

                {state === 'QUESTION' && (
                    showBonusSplash ? (
                        <BonusSplash onComplete={() => setShowBonusSplash(false)} />
                    ) : gameType === 'wmlt' ? (
                        <GameQuestionScreen
                            questionNumber={currentQuestion}
                            totalQuestions={totalQuestions}
                            timeRemaining={timeRemaining}
                            timeLimit={timeLimit}
                            answeredCount={answeredCount}
                            playerCount={playerCount}
                            isBonus={isBonus}
                            onNextQuestion={nextQuestion}
                            onEndQuiz={endQuiz}
                            gameType="wmlt"
                            statementText={currentStatement}
                        />
                    ) : gameType === 'drawing' ? (
                        <GameQuestionScreen
                            questionNumber={currentQuestion}
                            totalQuestions={totalQuestions}
                            timeRemaining={timeRemaining}
                            timeLimit={timeLimit}
                            answeredCount={answeredCount}
                            playerCount={Math.max(0, playerCount - 1)}
                            isBonus={false}
                            onNextQuestion={nextQuestion}
                            onEndQuiz={endQuiz}
                            gameType="drawing"
                            statementText="Drawing round in progress"
                        />
                    ) : currentQ ? (
                        <GameQuestionScreen
                            question={currentQ}
                            questionNumber={currentQuestion}
                            totalQuestions={totalQuestions}
                            timeRemaining={timeRemaining}
                            timeLimit={timeLimit}
                            imageUrl={currentImageUrl}
                            answeredCount={answeredCount}
                            playerCount={playerCount}
                            isBonus={isBonus}
                            onNextQuestion={nextQuestion}
                            onEndQuiz={endQuiz}
                        />
                    ) : null
                )}

                {state === 'LEADERBOARD' && (
                    gameType === 'drawing' && drawingRoundResult ? (
                        <div className="min-h-dvh flex flex-col container-responsive safe-top safe-bottom animate-in">
                            <div className="flex-1 flex flex-col justify-center text-center">
                                <div className="hero-icon mb-4">🎨</div>
                                <p className="text-[--text-tertiary] text-sm mb-2">Round {currentQuestion} of {totalQuestions}</p>
                                <h2 className="hero-title mb-4">{drawingRoundResult.prompt}</h2>
                                <p className="text-[--text-secondary] mb-2">Drawer: <strong>{drawingRoundResult.drawer}</strong></p>
                                <p className="text-[--text-secondary]">
                                    {drawingRoundResult.correct_guessers.length
                                        ? `${drawingRoundResult.correct_guessers.join(', ')} guessed it`
                                        : 'No correct guesses this round'}
                                </p>
                            </div>
                            <div className="pb-4 space-y-2">
                                <button onClick={nextQuestion} className="btn btn-primary btn-glow w-full">
                                    {currentQuestion >= totalQuestions ? 'Show Results' : 'Next Round'}
                                </button>
                                <button onClick={endQuiz} className="btn btn-secondary w-full">
                                    End Game
                                </button>
                            </div>
                        </div>
                    ) : gameType === 'wmlt' && wmltRoundResult ? (
                        <div className="min-h-dvh flex flex-col container-responsive safe-top safe-bottom animate-in">
                            <div className="flex-1 flex flex-col py-6">
                                <div className="text-center mb-4">
                                    <p className="text-[--text-tertiary] text-sm mb-2">Round {currentQuestion} of {totalQuestions}</p>
                                    <div style={{ fontSize: '2.5rem', marginBottom: 4 }}>👑</div>
                                    {wmltRoundResult.winners.length > 1 ? (
                                        <>
                                            <h2 className="text-2xl font-extrabold">{wmltRoundResult.winners.join(' & ')}</h2>
                                            <p className="text-[--text-secondary] text-sm mt-1">Tied with {wmltRoundResult.round_podium[0]?.vote_count || 0} votes each!</p>
                                        </>
                                    ) : (
                                        <>
                                            <h2 className="text-2xl font-extrabold">{wmltRoundResult.winner}</h2>
                                            {wmltRoundResult.unanimous && <p className="text-[--accent-success] font-semibold mt-1">Unanimous!</p>}
                                        </>
                                    )}
                                    <p className="text-xs text-[--text-tertiary] mt-2 italic">"{wmltRoundResult.statement}"</p>
                                </div>

                                <div className="flex-1">
                                    <LeaderboardBarChart
                                        leaderboard={wmltRoundResult.round_podium.map(p => ({
                                            nickname: p.nickname,
                                            score: p.vote_count,
                                            avatar: p.avatar,
                                        }))}
                                        maxEntries={8}
                                        size="compact"
                                    />
                                </div>
                            </div>

                            <div className="pb-4 space-y-2">
                                <button onClick={nextQuestion} className="btn btn-primary btn-glow w-full">
                                    {currentQuestion >= totalQuestions ? 'Show Results' : 'Next Question'}
                                </button>
                                <button onClick={endQuiz} className="btn btn-secondary w-full">
                                    End Game
                                </button>
                            </div>
                        </div>
                    ) : (
                        <LeaderboardScreen
                            leaderboard={leaderboard}
                            questionNumber={currentQuestion}
                            totalQuestions={totalQuestions}
                            onNextQuestion={nextQuestion}
                            onEndQuiz={endQuiz}
                        />
                    )
                )}

                {state === 'PODIUM' && (
                    <PodiumScreen
                        leaderboard={leaderboard}
                        teamLeaderboard={teamLeaderboard}
                        superlatives={superlatives}
                        onPlayAgain={hostAppMode ? returnToHostApp : playAgain}
                        playAgainLabel={hostAppMode ? 'Back to Revelry Games' : 'Play Again'}
                    />
                )}
            </div>

            {errorModal && (
                <ErrorModal
                    title={errorModal.title}
                    message={errorModal.message}
                    upgradeAvailable={!hostAppMode && errorModal.upgradeAvailable}
                    onDismiss={() => {
                        const shouldReturn = errorModal.returnToHostApp;
                        setErrorModal(null);
                        if (hostAppMode && shouldReturn) returnToHostApp();
                    }}
                    onUpgrade={async () => {
                        if (hostAppMode) return;
                        track('upgrade_clicked', { source: 'error_modal' });
                        setErrorModal(null);
                        if (checkoutPollRef.current) return; // Prevent double-click
                        if (remoteConfig.operations.kill_payments) {
                            setErrorModal({ title: 'Payments Unavailable', message: 'Payments are temporarily disabled. Please try again later.' });
                            return;
                        }
                        try {
                            const res = await fetch(apiUrl('/checkout/create'), {
                                method: 'POST',
                                headers: apiHeaders(),
                                body: JSON.stringify({ device_id: getDeviceId(), promo_id: remoteConfig.pricing.promo?.id || '' }),
                            });
                            if (res.status === 403) {
                                setErrorModal({ title: 'Use In-App Purchase', message: 'Please use the in-app purchase option on iOS.' });
                                return;
                            }
                            if (!res.ok) {
                                setErrorModal({ title: 'Oops', message: 'Payments are not available yet. Try again later!' });
                                return;
                            }
                            const { checkout_url, session_id } = await res.json();
                            setCheckoutPending(session_id);
                            window.open(checkout_url, '_blank');
                            // Poll for token after Stripe redirect
                            let attempts = 0;
                            if (checkoutPollRef.current) clearInterval(checkoutPollRef.current);
                            checkoutPollRef.current = setInterval(async () => {
                                attempts++;
                                if (attempts > 30 || !mountedRef.current) {
                                    if (checkoutPollRef.current) clearInterval(checkoutPollRef.current);
                                    checkoutPollRef.current = null;
                                    return;
                                }
                                try {
                                    const tokenRes = await fetch(apiUrl('/checkout/token'), { headers: apiHeaders() });
                                    if (tokenRes.ok) {
                                        const data = await tokenRes.json();
                                        clearCheckoutPending();
                                        if (checkoutPollRef.current) clearInterval(checkoutPollRef.current);
                                        checkoutPollRef.current = null;
                                        track('tokens_purchased', { source: 'stripe', tokens_added: data.tokens_added });
                                        window.dispatchEvent(new CustomEvent('refresh-sparks'));
                                        setErrorModal({ title: 'Sparks Added!', message: `+${data.tokens_added} sparks added to your balance. Enjoy!` });
                                    } else if (tokenRes.status >= 500) {
                                        // Server error — stop polling, don't wait 60s
                                        clearCheckoutPending();
                                        if (checkoutPollRef.current) clearInterval(checkoutPollRef.current);
                                        checkoutPollRef.current = null;
                                        setErrorModal({ title: 'Checkout Issue', message: 'There was a server error processing your purchase. Your payment is safe — sparks will be added shortly.' });
                                    }
                                } catch { /* network error — keep polling */ }
                            }, 2000);
                        } catch {
                            setErrorModal({ title: 'Connection Error', message: 'Could not reach the server.' });
                        }
                    }}
                />
            )}
        </div>
    );
}
