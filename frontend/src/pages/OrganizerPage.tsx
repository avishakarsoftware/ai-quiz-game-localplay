import { useState, useRef, useEffect } from 'react';
import { API_URL, WS_URL } from '../config';
import { type Quiz, type LeaderboardEntry, type TeamLeaderboardEntry } from '../types';
import { soundManager } from '../utils/sound';
import PromptScreen from '../components/organizer/PromptScreen';
import LoadingScreen from '../components/organizer/LoadingScreen';
import ReviewScreen from '../components/organizer/ReviewScreen';
import ImageGenerationScreen from '../components/organizer/ImageGenerationScreen';
import LobbyScreen from '../components/organizer/LobbyScreen';
import GameQuestionScreen from '../components/organizer/GameQuestionScreen';
import LeaderboardScreen from '../components/organizer/LeaderboardScreen';
import PodiumScreen from '../components/organizer/PodiumScreen';

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
    const [networkIp, setNetworkIp] = useState(window.location.hostname);
    const [players, setPlayers] = useState<string[]>([]);
    const wsRef = useRef<WebSocket | null>(null);

    useEffect(() => {
        fetch(`${API_URL}/sd/status`)
            .then(res => res.json())
            .then(data => setSdAvailable(data.available))
            .catch(() => setSdAvailable(false));
    }, []);

    useEffect(() => {
        fetch(`${API_URL}/system/info`)
            .then(res => res.json())
            .then(data => {
                if (data.ip && data.ip !== '127.0.0.1') {
                    setNetworkIp(data.ip);
                }
            })
            .catch(err => console.error("Failed to fetch system IP", err));
    }, []);

    const generateQuiz = async () => {
        setState('LOADING');
        try {
            const res = await fetch(`${API_URL}/quiz/generate`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ prompt, difficulty, num_questions: numQuestions }),
            });
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

    const exportQuiz = async () => {
        if (!quizId) return;
        try {
            const res = await fetch(`${API_URL}/quiz/${quizId}/export`);
            const data = await res.json();
            const blob = new Blob([JSON.stringify(data.quiz, null, 2)], { type: 'application/json' });
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `${data.quiz.quiz_title || 'quiz'}.json`;
            a.click();
            URL.revokeObjectURL(url);
        } catch {
            alert('Export failed');
        }
    };

    const importQuiz = async () => {
        const input = document.createElement('input');
        input.type = 'file';
        input.accept = '.json';
        input.onchange = async (e) => {
            const file = (e.target as HTMLInputElement).files?.[0];
            if (!file) return;
            try {
                const text = await file.text();
                const quizData = JSON.parse(text);
                const res = await fetch(`${API_URL}/quiz/import`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ quiz: quizData }),
                });
                const data = await res.json();
                if (data.quiz) {
                    setQuiz(data.quiz);
                    setQuizId(data.quiz_id);
                    setTotalQuestions(data.quiz.questions.length);
                    setState('REVIEW');
                }
            } catch {
                alert('Invalid quiz file');
            }
        };
        input.click();
    };

    const createRoom = async () => {
        const res = await fetch(`${API_URL}/room/create`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ quiz_id: quizId, time_limit: timeLimit }),
        });
        const data = await res.json();
        setRoomCode(data.room_code);
        setState('ROOM');

        const clientId = `organizer-${Date.now()}`;
        const ws = new WebSocket(`${WS_URL}/ws/${data.room_code}/${clientId}?organizer=true`);
        wsRef.current = ws;

        ws.onmessage = (event) => {
            const msg = JSON.parse(event.data);
            if (msg.type === 'PLAYER_JOINED') {
                setPlayerCount(msg.player_count);
                setPlayers(msg.players || []);
                soundManager.play('playerJoin');
            }
            else if (msg.type === 'QUESTION') {
                setCurrentQuestion(msg.question_number);
                setTotalQuestions(msg.total_questions);
                setTimeRemaining(msg.time_limit);
                setState('QUESTION');
            }
            else if (msg.type === 'TIMER') setTimeRemaining(msg.remaining);
            else if (msg.type === 'QUESTION_OVER') { setLeaderboard(msg.leaderboard); setState('LEADERBOARD'); }
            else if (msg.type === 'PODIUM') {
                setLeaderboard(msg.leaderboard);
                setTeamLeaderboard(msg.team_leaderboard || []);
                setState('PODIUM');
                soundManager.play('podium');
            }
        };
    };

    const startGame = () => {
        soundManager.play('gameStart');
        wsRef.current?.send(JSON.stringify({ type: 'START_GAME' }));
        wsRef.current?.send(JSON.stringify({ type: 'NEXT_QUESTION' }));
    };

    const nextQuestion = () => wsRef.current?.send(JSON.stringify({ type: 'NEXT_QUESTION' }));

    const joinUrl = `http://${networkIp}:5173/join?room=${roomCode}`;
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
                        onExport={exportQuiz}
                        onImport={importQuiz}
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
                        networkIp={networkIp}
                        playerCount={playerCount}
                        players={players}
                        onStartGame={startGame}
                    />
                )}

                {state === 'QUESTION' && quiz && currentQ && (
                    <GameQuestionScreen
                        question={currentQ}
                        questionNumber={currentQuestion}
                        totalQuestions={totalQuestions}
                        timeRemaining={timeRemaining}
                        timeLimit={timeLimit}
                        imageUrl={currentImageUrl}
                    />
                )}

                {state === 'LEADERBOARD' && (
                    <LeaderboardScreen
                        leaderboard={leaderboard}
                        questionNumber={currentQuestion}
                        totalQuestions={totalQuestions}
                        onNextQuestion={nextQuestion}
                    />
                )}

                {state === 'PODIUM' && (
                    <PodiumScreen
                        leaderboard={leaderboard}
                        teamLeaderboard={teamLeaderboard}
                    />
                )}
            </div>
        </div>
    );
}
