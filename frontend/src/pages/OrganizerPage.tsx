import { useState, useRef, useEffect, useCallback } from 'react';
import { API_URL, WS_URL } from '../config';
import { type Quiz, type MLTGame, type GameType, type LeaderboardEntry, type PlayerInfo, type TeamLeaderboardEntry } from '../types';
import { soundManager } from '../utils/sound';
import { track } from '../utils/analytics';
import { getDeviceId, setCheckoutPending, getCheckoutPending, clearCheckoutPending } from '../utils/storage';
import { apiHeaders, apiUrl, generateIdempotencyKey } from '../utils/api';
import GameSelectScreen from '../components/organizer/GameSelectScreen';
import PromptScreen, { type AIProvider } from '../components/organizer/PromptScreen';
import MLTPromptScreen from '../components/organizer/MLTPromptScreen';
import LoadingScreen from '../components/organizer/LoadingScreen';
import ReviewScreen from '../components/organizer/ReviewScreen';
import MLTReviewScreen from '../components/organizer/MLTReviewScreen';
import ImageGenerationScreen from '../components/organizer/ImageGenerationScreen';
import LobbyScreen from '../components/organizer/LobbyScreen';
import GameQuestionScreen from '../components/organizer/GameQuestionScreen';
import LeaderboardScreen from '../components/organizer/LeaderboardScreen';
import LeaderboardBarChart from '../components/LeaderboardBarChart';
import PodiumScreen from '../components/organizer/PodiumScreen';
import BonusSplash from '../components/BonusSplash';
import ErrorModal from '../components/ErrorModal';
import { useRemoteConfigContext } from '../context/RemoteConfigContext';

type OrganizerState = 'SELECT_GAME' | 'PROMPT' | 'MLT_PROMPT' | 'LOADING' | 'REVIEW' | 'MLT_REVIEW' | 'GENERATING_IMAGES' | 'ROOM' | 'QUESTION' | 'LEADERBOARD' | 'PODIUM';

export default function OrganizerPage() {
    const { config: remoteConfig } = useRemoteConfigContext();
    const [state, setState] = useState<OrganizerState>('SELECT_GAME');
    const [gameType, setGameType] = useState<GameType>('quiz');
    const [prompt, setPrompt] = useState('');
    const [difficulty, setDifficulty] = useState('medium');
    const [numQuestions, setNumQuestions] = useState(10);
    const [quiz, setQuiz] = useState<Quiz | null>(null);
    const [mltGame, setMltGame] = useState<MLTGame | null>(null);
    const [contentId, setContentId] = useState('');
    const [roomCode, setRoomCode] = useState('');
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
    const [players, setPlayers] = useState<PlayerInfo[]>([]);
    const [answeredCount, setAnsweredCount] = useState(0);
    const [provider, setProvider] = useState('ollama');
    const [providers, setProviders] = useState<AIProvider[]>([]);
    const [isBonus, setIsBonus] = useState(false);
    const [showBonusSplash, setShowBonusSplash] = useState(false);
    const [roomLocked, setRoomLocked] = useState(false);
    // WMLT-specific state for organizer question screen
    const [currentStatement, setCurrentStatement] = useState('');
    const [showVotes, setShowVotes] = useState(true);
    const [wmltRoundResult, setWmltRoundResult] = useState<{ winner: string; winners: string[]; round_podium: { nickname: string; avatar: string; vote_count: number; voters: string[] }[]; unanimous: boolean; show_votes: boolean; statement: string } | null>(null);
    const [superlatives, setSuperlatives] = useState<{ title: string; icon: string; winner: string; avatar: string; detail: string }[]>([]);
    const [errorModal, setErrorModal] = useState<{ title: string; message: string; upgradeAvailable?: boolean } | null>(null);
    const wsRef = useRef<WebSocket | null>(null);
    const stateRef = useRef<OrganizerState>('SELECT_GAME');
    const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
    const roomCodeRef = useRef('');
    const organizerTokenRef = useRef('');
    const mountedRef = useRef(true);
    const connectWsRef = useRef<(code: string) => void>(() => {});
    const gameTypeRef = useRef<GameType>('quiz');
    const checkoutPollRef = useRef<ReturnType<typeof setInterval> | null>(null);

    useEffect(() => { stateRef.current = state; }, [state]);
    useEffect(() => { roomCodeRef.current = roomCode; }, [roomCode]);
    useEffect(() => { gameTypeRef.current = gameType; }, [gameType]);
    useEffect(() => {
        if (errorModal?.upgradeAvailable) track('paywall_shown', { source: 'error_modal' });
    }, [errorModal]);

    // Listen for home navigation from hamburger menu
    useEffect(() => {
        const handler = () => {
            if (stateRef.current === 'PROMPT' || stateRef.current === 'MLT_PROMPT' || stateRef.current === 'SELECT_GAME') {
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
        const pending = getCheckoutPending();
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
    }, []);


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
            if (msg.question_number === 1) {
                window.dispatchEvent(new CustomEvent('refresh-sparks'));
            }
            setCurrentQuestion(msg.question_number as number);
            setTotalQuestions(msg.total_questions as number);
            setTimeRemaining(msg.time_limit as number);
            setAnsweredCount(0);
            setIsBonus(msg.is_bonus as boolean || false);
            if (msg.is_bonus) setShowBonusSplash(true);
            // For WMLT, store the statement text
            if (msg.statement) {
                setCurrentStatement((msg.statement as { text: string }).text);
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
            } else {
                setWmltRoundResult(null);
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
            setErrorModal({ title: 'Not Enough Sparks', message: msg.message as string || 'You need more sparks to start a game.', upgradeAvailable: true });
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
                }
            }
            if (msg.state === 'LOBBY' || msg.state === 'INTRO') {
                setState('ROOM');
            } else if (msg.state === 'QUESTION') {
                setCurrentQuestion(msg.question_number as number);
                setTimeRemaining((msg.time_remaining ?? msg.time_limit) as number);
                setAnsweredCount((msg.answered_count ?? msg.voted_count ?? 0) as number);
                setIsBonus(msg.is_bonus as boolean || false);
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
                setRoomCode('');
                setState('SELECT_GAME');
            }
        }
    }, []);

    const handleGameSelect = (type: GameType) => {
        setGameType(type);
        if (type === 'wmlt') setDifficulty('party');
        else setDifficulty('medium');
        setState(type === 'wmlt' ? 'MLT_PROMPT' : 'PROMPT');
    };

    const generateQuiz = async () => {
        if (remoteConfig.operations.kill_generate) {
            setErrorModal({ title: 'Temporarily Unavailable', message: 'Game generation is temporarily disabled. Please try again later.' });
            return;
        }
        setState('LOADING');
        try {
            const res = await fetch(apiUrl('/quiz/generate'), {
                method: 'POST',
                headers: apiHeaders({ 'X-Idempotency-Key': generateIdempotencyKey() }),
                body: JSON.stringify({ prompt, difficulty, num_questions: numQuestions, provider }),
            });
            if (res.status === 402) {
                track('paywall_hit', { source: 'quiz' });
                setErrorModal({ title: 'Not Enough Sparks', message: 'You need more sparks! Buy a spark pack or watch an ad to earn free sparks.', upgradeAvailable: true });
                setState('PROMPT');
                return;
            }
            if (res.status === 503) {
                track('quota_error', { source: 'quiz' });
                setErrorModal({ title: 'Daily Limit Reached', message: 'Daily generation limit reached. Try again tomorrow or buy a spark pack!', upgradeAvailable: true });
                setState('PROMPT');
                return;
            }
            if (res.status === 429) {
                const err = await res.json().catch(() => ({ detail: 'Too many requests. Please wait a minute.' }));
                setErrorModal({ title: 'Rate Limited', message: err.detail || 'Too many requests.' });
                setState('PROMPT');
                return;
            }
            const data = await res.json();
            if (data.quiz) {
                setQuiz(data.quiz);
                setContentId(data.quiz_id);
                setTotalQuestions(data.quiz.questions.length);
                track('quiz_generated', { topic: prompt, difficulty, num_questions: numQuestions, provider });
                window.dispatchEvent(new CustomEvent('refresh-sparks'));
                setState('REVIEW');
            } else {
                setErrorModal({ title: 'Generation Failed', message: 'Failed to generate quiz. Please try a different topic.' });
                setState('PROMPT');
            }
        } catch {
            setErrorModal({ title: 'Connection Error', message: 'Could not reach the server. Check your internet connection.' });
            setState('PROMPT');
        }
    };

    const generateMLT = async () => {
        if (remoteConfig.operations.kill_generate) {
            setErrorModal({ title: 'Temporarily Unavailable', message: 'Game generation is temporarily disabled. Please try again later.' });
            return;
        }
        setState('LOADING');
        try {
            const res = await fetch(apiUrl('/mlt/generate'), {
                method: 'POST',
                headers: apiHeaders({ 'X-Idempotency-Key': generateIdempotencyKey() }),
                body: JSON.stringify({ prompt, difficulty, num_rounds: numQuestions, provider }),
            });
            if (res.status === 402) {
                const err = await res.json().catch(() => ({ detail: 'Not enough sparks.' }));
                track('paywall_hit', { source: 'mlt' });
                setErrorModal({ title: 'Not Enough Sparks', message: 'You need more sparks! Buy a spark pack or watch an ad to earn free sparks.', upgradeAvailable: true });
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
            if (!res.ok) console.error('Failed to save quiz update:', res.status);
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
            if (!res.ok) console.error('Failed to save MLT update:', res.status);
        } catch (err) {
            console.error('Failed to save MLT update:', err);
        }
    };

    const connectWs = useCallback((code: string) => {
        if (wsRef.current) {
            wsRef.current.onclose = null;
            wsRef.current.close();
        }
        const clientId = `organizer-${Date.now()}`;
        const token = encodeURIComponent(organizerTokenRef.current);
        const ws = new WebSocket(`${WS_URL}/ws/${code}/${clientId}?organizer=true&token=${token}`);
        wsRef.current = ws;
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
                    game_type: gameType,
                }));
                return;
            }
        }

        // First-time room creation
        try {
            const body: Record<string, unknown> = {
                time_limit: timeLimit,
                game_type: gameType,
            };
            if (gameType === 'wmlt') {
                body.mlt_id = contentId;
            } else {
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

    // In Capacitor, window.location.origin is capacitor://localhost — use the web URL instead
    const isCapacitor = window.location.protocol === 'capacitor:' || window.location.hostname === 'localhost' && !window.location.port;
    const baseUrl = isCapacitor
        ? (import.meta.env.VITE_WEB_URL || 'https://games.revelryapp.me/quiz/')
        : `${window.location.origin}${import.meta.env.BASE_URL}`;
    const joinUrl = `${baseUrl}join/${roomCode}`;
    const currentQ = quiz?.questions[currentQuestion - 1];
    const currentImageUrl = currentQ ? questionImages[currentQ.id] : undefined;

    return (
        <div className="app-container">
            <div className="content-wrapper">
                {state === 'SELECT_GAME' && (
                    <GameSelectScreen onSelect={handleGameSelect} />
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

                {state === 'LOADING' && <LoadingScreen />}

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
                        onBack={() => setState('PROMPT')}
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
                    gameType === 'wmlt' && wmltRoundResult ? (
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
                        onPlayAgain={playAgain}
                    />
                )}
            </div>

            {errorModal && (
                <ErrorModal
                    title={errorModal.title}
                    message={errorModal.message}
                    upgradeAvailable={errorModal.upgradeAvailable}
                    onDismiss={() => setErrorModal(null)}
                    onUpgrade={async () => {
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
                                    }
                                } catch { /* keep polling */ }
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
