import { useState, useRef, useEffect } from 'react';
import { QRCodeSVG } from 'qrcode.react';
import CastButton from '../components/CastButton';
import { API_URL, WS_URL } from '../config';

interface Question {
    id: number;
    text: string;
    options: string[];
    answer_index: number;
    image_prompt: string;
    image_url?: string;
}

interface Quiz {
    quiz_title: string;
    questions: Question[];
}

interface LeaderboardEntry {
    nickname: string;
    score: number;
    rank_change?: number;
}

type OrganizerState = 'PROMPT' | 'LOADING' | 'REVIEW' | 'GENERATING_IMAGES' | 'ROOM' | 'QUESTION' | 'LEADERBOARD' | 'PODIUM';

export default function OrganizerPage() {
    const [state, setState] = useState<OrganizerState>('PROMPT');
    const [prompt, setPrompt] = useState('');
    const [quiz, setQuiz] = useState<Quiz | null>(null);
    const [quizId, setQuizId] = useState('');
    const [roomCode, setRoomCode] = useState('');
    const [timeLimit, setTimeLimit] = useState(15);
    const [playerCount, setPlayerCount] = useState(0);
    const [currentQuestion, setCurrentQuestion] = useState(0);
    const [totalQuestions, setTotalQuestions] = useState(0);
    const [timeRemaining, setTimeRemaining] = useState(15);
    const [leaderboard, setLeaderboard] = useState<LeaderboardEntry[]>([]);
    const [sdAvailable, setSdAvailable] = useState(false);
    const [imageProgress, setImageProgress] = useState(0);
    const [questionImages, setQuestionImages] = useState<Record<number, string>>({});
    const wsRef = useRef<WebSocket | null>(null);

    useEffect(() => {
        fetch(`${API_URL}/sd/status`)
            .then(res => res.json())
            .then(data => setSdAvailable(data.available))
            .catch(() => setSdAvailable(false));
    }, []);

    const generateQuiz = async () => {
        setState('LOADING');
        try {
            const res = await fetch(`${API_URL}/quiz/generate`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ prompt }),
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
            if (msg.type === 'PLAYER_JOINED') setPlayerCount(msg.player_count);
            else if (msg.type === 'QUESTION') {
                setCurrentQuestion(msg.question_number);
                setTotalQuestions(msg.total_questions);
                setTimeRemaining(msg.time_limit);
                setState('QUESTION');
            }
            else if (msg.type === 'TIMER') setTimeRemaining(msg.remaining);
            else if (msg.type === 'QUESTION_OVER') { setLeaderboard(msg.leaderboard); setState('LEADERBOARD'); }
            else if (msg.type === 'PODIUM') { setLeaderboard(msg.leaderboard); setState('PODIUM'); }
        };
    };

    const startGame = () => {
        wsRef.current?.send(JSON.stringify({ type: 'START_GAME' }));
        wsRef.current?.send(JSON.stringify({ type: 'NEXT_QUESTION' }));
    };

    const nextQuestion = () => wsRef.current?.send(JSON.stringify({ type: 'NEXT_QUESTION' }));

    const [networkIp, setNetworkIp] = useState(window.location.hostname);

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

    const joinUrl = `http://${networkIp}:5173/join?room=${roomCode}`;
    const timerProgress = (timeRemaining / timeLimit) * 100;
    const currentQ = quiz?.questions[currentQuestion - 1];
    const currentImageUrl = currentQ ? questionImages[currentQ.id] : undefined;

    return (
        <div className="app-container">
            <div className="content-wrapper">

                {/* PROMPT */}
                {state === 'PROMPT' && (
                    <div className="min-h-dvh flex flex-col container-responsive safe-top safe-bottom animate-in">
                        <div className="flex-1 flex flex-col justify-center py-8">
                            <h1 className="text-3xl font-bold text-center mb-2">Create Quiz</h1>
                            <p className="text-center text-[--text-tertiary] mb-8">Describe what you want to quiz about</p>

                            <div className="space-y-4">
                                <textarea
                                    value={prompt}
                                    onChange={(e) => setPrompt(e.target.value)}
                                    placeholder="e.g., 10 questions about the solar system..."
                                    className="input-field input-large"
                                />

                                {sdAvailable ? (
                                    <div className="status-pill status-success">
                                        <span>●</span> Image generation ready
                                    </div>
                                ) : (
                                    <div className="status-pill status-warning">
                                        <span>●</span> Images unavailable
                                    </div>
                                )}
                            </div>
                        </div>

                        <div className="mt-auto pb-4">
                            <button
                                onClick={generateQuiz}
                                disabled={!prompt.trim()}
                                className="btn btn-primary w-full"
                            >
                                Generate Quiz
                            </button>
                        </div>
                    </div>
                )}

                {/* LOADING */}
                {state === 'LOADING' && (
                    <div className="min-h-dvh flex flex-col items-center justify-center container-responsive animate-in">
                        <div className="w-12 h-12 border-4 border-[--bg-tertiary] border-t-[--accent-primary] rounded-full animate-spin mb-6" />
                        <p className="text-lg font-semibold">Generating quiz...</p>
                        <p className="text-[--text-tertiary] mt-2">This may take a moment</p>
                    </div>
                )}

                {/* REVIEW */}
                {state === 'REVIEW' && quiz && (
                    <div className="min-h-dvh flex flex-col container-responsive safe-top safe-bottom animate-in">
                        <div className="py-4">
                            <h2 className="text-xl font-bold text-center">{quiz.quiz_title}</h2>
                            <p className="text-center text-[--text-tertiary] text-sm">{quiz.questions.length} questions</p>
                        </div>

                        <div className="space-y-3 mb-4">
                            <div className="settings-row">
                                <div>
                                    <p className="font-medium">Time per question</p>
                                    <p className="text-xs text-[--text-tertiary]">5-60 seconds</p>
                                </div>
                                <div className="flex items-center gap-2">
                                    <input
                                        type="number"
                                        value={timeLimit}
                                        onChange={(e) => setTimeLimit(Math.max(5, Math.min(60, parseInt(e.target.value) || 15)))}
                                        className="settings-input"
                                    />
                                    <span className="text-[--text-tertiary]">s</span>
                                </div>
                            </div>

                            {sdAvailable && Object.keys(questionImages).length === 0 && (
                                <button onClick={generateImages} className="btn btn-secondary w-full">
                                    Generate Images
                                </button>
                            )}

                            {Object.keys(questionImages).length > 0 && (
                                <div className="status-pill status-success">
                                    ✓ {Object.keys(questionImages).length} images ready
                                </div>
                            )}
                        </div>

                        <div className="flex-1 overflow-y-auto no-scrollbar space-y-3 mb-4">
                            {quiz.questions.map((q, i) => (
                                <div key={q.id} className="card">
                                    <div className="p-4">
                                        <div className="flex items-start gap-3 mb-3">
                                            <span className="rank-badge rank-default flex-shrink-0">{i + 1}</span>
                                            <p className="text-sm font-medium">{q.text}</p>
                                        </div>
                                        <div className="grid grid-cols-2 gap-2 ml-10">
                                            {q.options.map((opt, j) => {
                                                const styles = [
                                                    { bg: '#FF3B30', shape: '▲' },  // Red triangle
                                                    { bg: '#007AFF', shape: '◆' },  // Blue diamond
                                                    { bg: '#FF9500', shape: '●' },  // Orange circle
                                                    { bg: '#34C759', shape: '■' },  // Green square
                                                ];
                                                const style = styles[j];
                                                const isCorrect = j === q.answer_index;
                                                return (
                                                    <div
                                                        key={j}
                                                        className={`flex items-center gap-2 px-3 py-2 rounded-lg text-xs text-white font-medium ${isCorrect ? 'ring-2 ring-white ring-offset-2 ring-offset-[--bg-secondary]' : 'opacity-60'}`}
                                                        style={{ backgroundColor: style.bg }}
                                                    >
                                                        <span className="text-base">{style.shape}</span>
                                                        <span className="truncate">{opt}</span>
                                                    </div>
                                                );
                                            })}
                                        </div>
                                    </div>
                                </div>
                            ))}
                        </div>

                        <div className="flex gap-3 pb-4">
                            <button onClick={() => setState('PROMPT')} className="btn btn-secondary flex-1">Back</button>
                            <button onClick={createRoom} className="btn btn-primary flex-1">Create Room</button>
                        </div>
                    </div>
                )}

                {/* GENERATING IMAGES */}
                {state === 'GENERATING_IMAGES' && quiz && (
                    <div className="min-h-dvh flex flex-col items-center justify-center container-responsive animate-in">
                        <p className="text-lg font-semibold mb-4">Generating Images</p>
                        <div className="w-full max-w-xs">
                            <div className="progress-bar mb-2">
                                <div className="progress-bar-fill" style={{ width: `${(imageProgress / quiz.questions.length) * 100}%` }} />
                            </div>
                            <p className="text-center text-[--text-tertiary]">{imageProgress} / {quiz.questions.length}</p>
                        </div>
                    </div>
                )}

                {/* ROOM */}
                {state === 'ROOM' && (
                    <div className="min-h-dvh flex flex-col items-center justify-center container-responsive safe-bottom animate-in">
                        <p className="text-[--text-tertiary] mb-1">Join at</p>
                        <p className="font-medium mb-6">{networkIp}:5173/join</p>

                        <div className="qr-container mb-6">
                            <QRCodeSVG value={joinUrl} size={180} bgColor="white" fgColor="#000000" level="H" />
                        </div>

                        <div className="room-code mb-6">{roomCode}</div>

                        <div className="card mb-6 w-full text-center py-4">
                            <span className="text-4xl font-bold">{playerCount}</span>
                            <span className="text-[--text-tertiary] ml-2">player{playerCount !== 1 ? 's' : ''}</span>
                        </div>

                        <div className="w-full mb-4">
                            <CastButton roomCode={roomCode} joinUrl={joinUrl} displayUrl={`${networkIp}:5173/join`} />
                        </div>

                        <button onClick={startGame} disabled={playerCount === 0} className="btn btn-primary w-full">
                            Start Game
                        </button>
                    </div>
                )}

                {/* QUESTION */}
                {state === 'QUESTION' && quiz && currentQ && (
                    <div className="min-h-dvh flex flex-col container-responsive safe-top safe-bottom animate-in">
                        <div className="flex items-center justify-between py-4">
                            <span className="text-[--text-tertiary]">Q{currentQuestion}/{totalQuestions}</span>
                            <span className={`timer-display ${timeRemaining <= 5 ? 'danger' : timeRemaining <= 10 ? 'warning' : ''}`}>
                                {timeRemaining}
                            </span>
                        </div>

                        <div className="progress-bar mb-6">
                            <div className={`progress-bar-fill ${timeRemaining <= 5 ? 'danger' : timeRemaining <= 10 ? 'warning' : ''}`}
                                style={{ width: `${timerProgress}%` }} />
                        </div>

                        <div className={`question-card mb-6 ${currentImageUrl ? 'has-image' : ''}`}
                            style={currentImageUrl ? { backgroundImage: `url(${currentImageUrl})` } : undefined}>
                            <p className="question-text">{currentQ.text}</p>
                        </div>

                        <div className="answer-grid">
                            {currentQ.options.map((opt, i) => {
                                const shapes = ['▲', '◆', '●', '■'];
                                return (
                                    <div key={i} className={`answer-btn ${['answer-red', 'answer-blue', 'answer-yellow', 'answer-green'][i]}`}>
                                        <span className="text-2xl opacity-50 mr-2">{shapes[i]}</span>
                                        <span>{opt}</span>
                                    </div>
                                );
                            })}
                        </div>
                    </div>
                )}

                {/* LEADERBOARD */}
                {state === 'LEADERBOARD' && (
                    <div className="min-h-dvh flex flex-col container-responsive safe-top safe-bottom animate-in">
                        <div className="text-center py-6">
                            <h2 className="text-xl font-bold">Leaderboard</h2>
                            <p className="text-[--text-tertiary] text-sm">After question {currentQuestion}</p>
                        </div>

                        <div className="flex-1 space-y-2 mb-6">
                            {leaderboard.map((player, i) => (
                                <div key={player.nickname} className="leaderboard-item">
                                    <div className="flex items-center gap-3">
                                        <span className={`rank-badge ${i === 0 ? 'rank-1' : i === 1 ? 'rank-2' : i === 2 ? 'rank-3' : 'rank-default'}`}>
                                            {i + 1}
                                        </span>
                                        <span className="font-medium">{player.nickname}</span>
                                        {player.rank_change !== undefined && player.rank_change !== 0 && (
                                            <span className={`text-xs ${player.rank_change > 0 ? 'text-[--accent-success]' : 'text-[--accent-danger]'}`}>
                                                {player.rank_change > 0 ? `↑${player.rank_change}` : `↓${Math.abs(player.rank_change)}`}
                                            </span>
                                        )}
                                    </div>
                                    <span className="font-bold">{player.score.toLocaleString()}</span>
                                </div>
                            ))}
                        </div>

                        <button onClick={nextQuestion} className="btn btn-primary w-full">
                            {currentQuestion >= totalQuestions ? 'Show Results' : 'Next Question'}
                        </button>
                    </div>
                )}

                {/* PODIUM */}
                {state === 'PODIUM' && (
                    <div className="min-h-dvh flex flex-col items-center justify-center container-responsive safe-bottom animate-in">
                        <h2 className="text-2xl font-bold mb-2">Final Results</h2>

                        <div className="podium-container">
                            {/* 2nd Place */}
                            {leaderboard[1] && (
                                <div className="podium-place podium-2">
                                    <p className="podium-name">{leaderboard[1].nickname}</p>
                                    <div className="podium-bar">2</div>
                                    <p className="podium-score">{leaderboard[1].score}</p>
                                </div>
                            )}
                            {/* 1st Place */}
                            {leaderboard[0] && (
                                <div className="podium-place podium-1">
                                    <p className="text-3xl mb-2">🏆</p>
                                    <p className="podium-name">{leaderboard[0].nickname}</p>
                                    <div className="podium-bar">1</div>
                                    <p className="podium-score">{leaderboard[0].score}</p>
                                </div>
                            )}
                            {/* 3rd Place */}
                            {leaderboard[2] && (
                                <div className="podium-place podium-3">
                                    <p className="podium-name">{leaderboard[2].nickname}</p>
                                    <div className="podium-bar">3</div>
                                    <p className="podium-score">{leaderboard[2].score}</p>
                                </div>
                            )}
                        </div>

                        <button onClick={() => window.location.reload()} className="btn btn-primary w-full mt-8">
                            Play Again
                        </button>
                    </div>
                )}

            </div>
        </div>
    );
}
