import { useState, useRef, useEffect, useCallback } from 'react';
import { API_URL, WS_URL } from '../config';
import { type Quiz, type LeaderboardEntry, type PlayerInfo, type TeamLeaderboardEntry } from '../types';
import { soundManager } from '../utils/sound';
import PromptScreen, { type AIProvider } from '../components/organizer/PromptScreen';
import LoadingScreen from '../components/organizer/LoadingScreen';
import ReviewScreen from '../components/organizer/ReviewScreen';
import ImageGenerationScreen from '../components/organizer/ImageGenerationScreen';
import LobbyScreen from '../components/organizer/LobbyScreen';
import GameQuestionScreen from '../components/organizer/GameQuestionScreen';
import LeaderboardScreen from '../components/organizer/LeaderboardScreen';
import PodiumScreen from '../components/organizer/PodiumScreen';
import BonusSplash from '../components/BonusSplash';

type OrganizerState = 'PROMPT' | 'LOADING' | 'REVIEW' | 'GENERATING_IMAGES' | 'ROOM' | 'QUESTION' | 'LEADERBOARD' | 'PODIUM';

export default function OrganizerPage() {
    const [state, setState] = useState<OrganizerState>('PROMPT');
    const [prompt, setPrompt] = useState('');
    const [difficulty, setDifficulty] = useState('medium');
    const [numQuestions, setNumQuestions] = useState(10);
    const [quiz, setQuiz] = useState<Quiz | null>(null);
    const [quizId, setQuizId] = useState('');
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
    const wsRef = useRef<WebSocket | null>(null);
    const stateRef = useRef<OrganizerState>('PROMPT');
    const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
    const roomCodeRef = useRef('');
    const organizerTokenRef = useRef('');

    useEffect(() => { stateRef.current = state; }, [state]);
    useEffect(() => { roomCodeRef.current = roomCode; }, [roomCode]);

    useEffect(() => {
        fetch(`${API_URL}/sd/status`)
            .then(res => res.json())
            .then(data => setSdAvailable(data.available))
            .catch(() => setSdAvailable(false));

        fetch(`${API_URL}/providers`)
            .then(res => res.json())
            .then(data => {
                setProviders(data.providers || []);
                const defaultProvider = data.providers?.find((p: AIProvider) => p.available);
                if (defaultProvider) setProvider(defaultProvider.id);
            })
            .catch(() => {});
    }, []);


    const handleWsMessage = useCallback((event: MessageEvent) => {
        let msg: Record<string, unknown>;
        try { msg = JSON.parse(event.data); } catch { return; }
        if (msg.type === 'PLAYER_JOINED') {
            console.log('PLAYER_JOINED', msg);
            setPlayerCount(msg.player_count);
            setPlayers(msg.players || []);
            soundManager.play('playerJoin');
        }
        else if (msg.type === 'QUESTION') {
            setCurrentQuestion(msg.question_number);
            setTotalQuestions(msg.total_questions);
            setTimeRemaining(msg.time_limit);
            setAnsweredCount(0);
            setIsBonus(msg.is_bonus || false);
            if (msg.is_bonus) setShowBonusSplash(true);
            setState('QUESTION');
        }
        else if (msg.type === 'TIMER') setTimeRemaining(msg.remaining);
        else if (msg.type === 'ANSWER_COUNT') setAnsweredCount(msg.answered);
        else if (msg.type === 'QUESTION_OVER') {
            setLeaderboard(msg.leaderboard);
            setState('LEADERBOARD');
        }
        else if (msg.type === 'PODIUM') {
            setLeaderboard(msg.leaderboard);
            setTeamLeaderboard(msg.team_leaderboard || []);
            setState('PODIUM');
            soundManager.play('fanfare');
        }
        else if (msg.type === 'PLAYER_LEFT' || msg.type === 'PLAYER_DISCONNECTED') {
            setPlayerCount(msg.player_count);
            setPlayers(msg.players || []);
        }
        else if (msg.type === 'PLAYER_RECONNECTED') {
            setPlayerCount(msg.player_count);
            setPlayers(msg.players || []);
        }
        else if (msg.type === 'ROOM_RESET') {
            setPlayerCount(msg.player_count);
            setPlayers(msg.players || []);
            setState('ROOM');
        }
        else if (msg.type === 'ORGANIZER_RECONNECTED') {
            setRoomCode(msg.room_code);
            setPlayerCount(msg.player_count);
            setPlayers(msg.players || []);
            setTotalQuestions(msg.total_questions);
            setLeaderboard(msg.leaderboard || []);
            setTeamLeaderboard(msg.team_leaderboard || []);
            setTimeLimit(msg.time_limit);
            if (msg.quiz) {
                setQuiz(msg.quiz);
                setTotalQuestions(msg.quiz.questions.length);
            }
            if (msg.state === 'LOBBY' || msg.state === 'INTRO') {
                setState('ROOM');
            } else if (msg.state === 'QUESTION') {
                setCurrentQuestion(msg.question_number);
                setTimeRemaining(msg.time_remaining ?? msg.time_limit);
                setAnsweredCount(msg.answered_count ?? 0);
                setIsBonus(msg.is_bonus || false);
                setState('QUESTION');
            } else if (msg.state === 'LEADERBOARD') {
                setCurrentQuestion(msg.question_number);
                setState('LEADERBOARD');
            } else if (msg.state === 'PODIUM') {
                setState('PODIUM');
                soundManager.play('fanfare');
            }
        }
        else if (msg.type === 'ERROR') {
            console.error('Organizer error:', msg.message);
            setRoomCode('');
            setState('PROMPT');
        }
    }, []);

    const generateQuiz = async () => {
        setState('LOADING');
        try {
            const res = await fetch(`${API_URL}/quiz/generate`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ prompt, difficulty, num_questions: numQuestions, provider }),
            });
            if (res.status === 429) {
                alert('Too many requests. Please wait a minute before generating another quiz.');
                setState('PROMPT');
                return;
            }
            const data = await res.json();
            if (data.quiz) {
                setQuiz(data.quiz);
                setQuizId(data.quiz_id);
                setTotalQuestions(data.quiz.questions.length);
                setState('REVIEW');
            } else {
                alert('Failed to generate quiz');
                setState('PROMPT');
            }
        } catch {
            alert('Connection error');
            setState('PROMPT');
        }
    };

    const generateImages = async () => {
        if (!sdAvailable || !quizId) return;
        setState('GENERATING_IMAGES');
        setImageProgress(0);

        for (let i = 0; i < (quiz?.questions.length || 0); i++) {
            const question = quiz!.questions[i];
            await fetch(`${API_URL}/quiz/generate-images`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ quiz_id: quizId, question_id: question.id }),
            });
            setImageProgress(i + 1);
            setQuestionImages(prev => ({
                ...prev,
                [question.id]: `${API_URL}/quiz/${quizId}/image/${question.id}`
            }));
        }
        setState('REVIEW');
    };

    const updateQuiz = async (updated: Quiz) => {
        setQuiz(updated);
        setTotalQuestions(updated.questions.length);
        await fetch(`${API_URL}/quiz/${quizId}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(updated),
        });
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
            const activeStates: OrganizerState[] = ['ROOM', 'QUESTION', 'LEADERBOARD', 'PODIUM'];
            if (roomCodeRef.current && activeStates.includes(stateRef.current)) {
                reconnectTimerRef.current = setTimeout(() => connectWs(roomCodeRef.current), 2000);
            }
        };
    }, [handleWsMessage]);

    useEffect(() => {
        return () => { if (reconnectTimerRef.current) clearTimeout(reconnectTimerRef.current); };
    }, []);

    const createRoom = async () => {
        // Play Again path: reuse existing room via RESET_ROOM
        if (roomCode && wsRef.current && wsRef.current.readyState === WebSocket.OPEN && quiz) {
            wsRef.current.send(JSON.stringify({
                type: 'RESET_ROOM',
                quiz_data: quiz,
                time_limit: timeLimit,
            }));
            // State will transition to ROOM when ROOM_RESET message comes back
            return;
        }

        // First-time room creation
        const res = await fetch(`${API_URL}/room/create`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ quiz_id: quizId, time_limit: timeLimit }),
        });
        const data = await res.json();
        setRoomCode(data.room_code);
        organizerTokenRef.current = data.organizer_token || '';
        setState('ROOM');
        connectWs(data.room_code);
    };

    const startGame = () => {
        soundManager.play('gameStart');
        wsRef.current?.send(JSON.stringify({ type: 'START_GAME' }));
        wsRef.current?.send(JSON.stringify({ type: 'NEXT_QUESTION' }));
    };

    const nextQuestion = () => wsRef.current?.send(JSON.stringify({ type: 'NEXT_QUESTION' }));
    const endQuiz = () => wsRef.current?.send(JSON.stringify({ type: 'END_QUIZ' }));

    const playAgain = () => {
        // Go back to PROMPT but keep the WebSocket connection and room alive
        setCurrentQuestion(0);
        setLeaderboard([]);
        setTeamLeaderboard([]);
        setTimeRemaining(timeLimit);
        setQuestionImages({});
        setAnsweredCount(0);
        setPrompt('');
        setState('PROMPT');
    };

    const baseUrl = `${window.location.origin}${import.meta.env.BASE_URL}`;
    const joinUrl = `${baseUrl}join?room=${roomCode}`;
    const currentQ = quiz?.questions[currentQuestion - 1];
    const currentImageUrl = currentQ ? questionImages[currentQ.id] : undefined;

    return (
        <div className="app-container">
            <div className="content-wrapper">
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
                        sdAvailable={sdAvailable}
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

                {state === 'GENERATING_IMAGES' && quiz && (
                    <ImageGenerationScreen quiz={quiz} imageProgress={imageProgress} />
                )}

                {state === 'ROOM' && (
                    <LobbyScreen
                        roomCode={roomCode}
                        joinUrl={joinUrl}
                        playerCount={playerCount}
                        players={players}
                        onStartGame={startGame}
                    />
                )}

                {state === 'QUESTION' && quiz && currentQ && (
                    showBonusSplash ? (
                        <BonusSplash onComplete={() => setShowBonusSplash(false)} />
                    ) : (
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
                    )
                )}

                {state === 'LEADERBOARD' && (
                    <LeaderboardScreen
                        leaderboard={leaderboard}
                        questionNumber={currentQuestion}
                        totalQuestions={totalQuestions}
                        onNextQuestion={nextQuestion}
                        onEndQuiz={endQuiz}
                    />
                )}

                {state === 'PODIUM' && (
                    <PodiumScreen
                        leaderboard={leaderboard}
                        teamLeaderboard={teamLeaderboard}
                        onPlayAgain={playAgain}
                    />
                )}
            </div>
        </div>
    );
}
