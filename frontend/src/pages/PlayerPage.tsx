import { useState, useRef } from 'react';
import { useSearchParams } from 'react-router-dom';
import { API_URL, WS_URL } from '../config';

type PlayerState = 'JOIN' | 'LOBBY' | 'QUESTION' | 'WAITING' | 'RESULT' | 'PODIUM';

interface Question {
    id: number;
    text: string;
    options: string[];
    image_url?: string;
}

interface LeaderboardEntry {
    nickname: string;
    score: number;
    rank_change?: number;
}

export default function PlayerPage() {
    const [searchParams] = useSearchParams();
    const [state, setState] = useState<PlayerState>('JOIN');
    const [roomCode, setRoomCode] = useState(searchParams.get('room') || '');
    const [nickname, setNickname] = useState('');
    const [currentQuestion, setCurrentQuestion] = useState<Question | null>(null);
    const [questionNumber, setQuestionNumber] = useState(0);
    const [totalQuestions, setTotalQuestions] = useState(0);
    const [timeLimit, setTimeLimit] = useState(15);
    const [timeRemaining, setTimeRemaining] = useState(15);
    const [selectedAnswer, setSelectedAnswer] = useState<number | null>(null);
    const [isCorrect, setIsCorrect] = useState<boolean | null>(null);
    const [pointsEarned, setPointsEarned] = useState(0);
    const [correctAnswer, setCorrectAnswer] = useState<number | null>(null);
    const [leaderboard, setLeaderboard] = useState<LeaderboardEntry[]>([]);
    const [myRank, setMyRank] = useState(0);
    const [error, setError] = useState('');
    const wsRef = useRef<WebSocket | null>(null);

    const answerStyles = ['answer-red', 'answer-blue', 'answer-yellow', 'answer-green'];

    const joinRoom = () => {
        if (!roomCode.trim() || !nickname.trim()) return;
        setError('');

        const clientId = `player-${Date.now()}`;
        const ws = new WebSocket(`${WS_URL}/ws/${roomCode}/${clientId}`);
        wsRef.current = ws;

        ws.onopen = () => ws.send(JSON.stringify({ type: 'JOIN', nickname }));

        ws.onmessage = (event) => {
            const msg = JSON.parse(event.data);
            if (msg.type === 'ERROR') { setError(msg.message); return; }
            if (msg.type === 'JOINED_ROOM') setState('LOBBY');
            if (msg.type === 'GAME_STARTING') setState('LOBBY');
            if (msg.type === 'QUESTION') {
                setCurrentQuestion(msg.question);
                setQuestionNumber(msg.question_number);
                setTotalQuestions(msg.total_questions);
                setTimeLimit(msg.time_limit);
                setTimeRemaining(msg.time_limit);
                setSelectedAnswer(null);
                setIsCorrect(null);
                setPointsEarned(0);
                setCorrectAnswer(null);
                setState('QUESTION');
            }
            if (msg.type === 'TIMER') setTimeRemaining(msg.remaining);
            if (msg.type === 'ANSWER_RESULT') {
                setIsCorrect(msg.correct);
                setPointsEarned(msg.points);
                setState('WAITING');
            }
            if (msg.type === 'QUESTION_OVER') {
                setCorrectAnswer(msg.answer);
                setLeaderboard(msg.leaderboard);
                setMyRank(msg.leaderboard.findIndex((p: LeaderboardEntry) => p.nickname === nickname) + 1);
                // On last question, stay in WAITING until organizer shows podium
                if (msg.is_final) {
                    // Stay in WAITING state - don't show RESULT
                } else {
                    setState('RESULT');
                }
            }
            if (msg.type === 'PODIUM') { setLeaderboard(msg.leaderboard); setState('PODIUM'); }
        };

        ws.onerror = () => setError('Connection failed');
        ws.onclose = () => { if (state === 'JOIN') setError('Room not found'); };
    };

    const submitAnswer = (index: number) => {
        if (selectedAnswer !== null) return;
        setSelectedAnswer(index);
        wsRef.current?.send(JSON.stringify({ type: 'ANSWER', answer_index: index }));
    };

    const timerProgress = (timeRemaining / timeLimit) * 100;

    return (
        <div className="app-container">
            <div className="content-wrapper">

                {/* JOIN */}
                {state === 'JOIN' && (
                    <div className="min-h-dvh flex flex-col items-center justify-center container-responsive safe-bottom animate-in">
                        <h1 className="text-3xl font-bold mb-2">Join Game</h1>
                        <p className="text-[--text-tertiary] mb-8">Enter the game PIN</p>

                        <div className="w-full space-y-4">
                            <input
                                type="text"
                                value={roomCode}
                                onChange={(e) => setRoomCode(e.target.value.toUpperCase())}
                                placeholder="Game PIN"
                                className="input-field text-center text-2xl tracking-widest uppercase"
                                maxLength={6}
                            />

                            <input
                                type="text"
                                value={nickname}
                                onChange={(e) => setNickname(e.target.value)}
                                placeholder="Your nickname"
                                className="input-field text-center"
                                maxLength={20}
                            />

                            {error && (
                                <div className="status-pill status-error w-full justify-center">{error}</div>
                            )}

                            <button
                                onClick={joinRoom}
                                disabled={!roomCode.trim() || !nickname.trim()}
                                className="btn btn-primary w-full"
                            >
                                Join
                            </button>
                        </div>
                    </div>
                )}

                {/* LOBBY */}
                {state === 'LOBBY' && (
                    <div className="min-h-dvh flex flex-col items-center justify-center container-responsive animate-in">
                        <div className="text-5xl mb-4">👋</div>
                        <h2 className="text-2xl font-bold mb-2">You're in!</h2>
                        <p className="text-[--text-tertiary] mb-6">Waiting for host to start</p>

                        <div className="card px-8 py-4">
                            <p className="text-lg font-semibold">{nickname}</p>
                        </div>

                        <div className="flex gap-1.5 mt-8">
                            {[0, 1, 2].map((i) => (
                                <div key={i} className="w-2 h-2 bg-[--accent-primary] rounded-full animate-bounce"
                                    style={{ animationDelay: `${i * 0.15}s` }} />
                            ))}
                        </div>
                    </div>
                )}

                {/* QUESTION */}
                {state === 'QUESTION' && currentQuestion && (
                    <div className="min-h-dvh flex flex-col container-responsive safe-top safe-bottom animate-in">
                        <div className="flex items-center justify-between py-4">
                            <span className="text-[--text-tertiary]">Q{questionNumber}/{totalQuestions}</span>
                            <span className={`timer-display text-3xl ${timeRemaining <= 5 ? 'danger' : timeRemaining <= 10 ? 'warning' : ''}`}>
                                {timeRemaining}
                            </span>
                        </div>

                        <div className="progress-bar mb-4">
                            <div className={`progress-bar-fill ${timeRemaining <= 5 ? 'danger' : timeRemaining <= 10 ? 'warning' : ''}`}
                                style={{ width: `${timerProgress}%` }} />
                        </div>

                        <div className={`question-card mb-6 ${currentQuestion.image_url ? 'has-image' : ''}`}
                            style={currentQuestion.image_url ? { backgroundImage: `url(${API_URL}${currentQuestion.image_url})` } : undefined}>
                            <p className="question-text">{currentQuestion.text}</p>
                        </div>

                        <div className="answer-grid flex-1">
                            {currentQuestion.options.map((opt, i) => {
                                const shapes = ['▲', '◆', '●', '■'];
                                return (
                                    <button
                                        key={i}
                                        onClick={() => submitAnswer(i)}
                                        disabled={selectedAnswer !== null}
                                        className={`answer-btn ${answerStyles[i]} ${selectedAnswer === i ? 'selected' : ''} ${selectedAnswer !== null && selectedAnswer !== i ? 'dimmed' : ''}`}
                                    >
                                        <span className="text-2xl opacity-50 mr-2">{shapes[i]}</span>
                                        <span>{opt}</span>
                                    </button>
                                );
                            })}
                        </div>
                    </div>
                )}

                {/* WAITING */}
                {state === 'WAITING' && (
                    <div className="min-h-dvh flex flex-col items-center justify-center container-responsive animate-in">
                        {isCorrect ? (
                            <>
                                <div className="text-6xl mb-4 animate-score-pop">✓</div>
                                <h2 className="text-3xl font-bold text-[--accent-success] mb-4">Correct!</h2>
                                {pointsEarned > 0 && (
                                    <div className="card px-8 py-4 animate-score-pop">
                                        <span className="text-3xl font-bold text-[--accent-success]">+{pointsEarned}</span>
                                    </div>
                                )}
                            </>
                        ) : (
                            <>
                                <div className="text-6xl mb-4 animate-score-pop">✗</div>
                                <h2 className="text-3xl font-bold text-[--accent-danger] mb-4">Wrong</h2>
                            </>
                        )}
                        <p className="text-[--text-tertiary] mt-6">Waiting for others...</p>
                    </div>
                )}

                {/* RESULT */}
                {state === 'RESULT' && (
                    <div className="min-h-dvh flex flex-col container-responsive safe-top safe-bottom animate-in">
                        <div className="text-center py-6">
                            {isCorrect ? (
                                <h2 className="text-2xl font-bold text-[--accent-success]">✓ Correct!</h2>
                            ) : (
                                <h2 className="text-2xl font-bold text-[--accent-danger]">✗ Wrong</h2>
                            )}
                            {pointsEarned > 0 && (
                                <p className="text-xl font-bold text-[--accent-success] mt-2">+{pointsEarned}</p>
                            )}
                        </div>

                        {myRank > 0 && (
                            <div className="card text-center py-6 mb-4">
                                <p className="text-[--text-tertiary] text-sm mb-1">Your position</p>
                                <p className="text-4xl font-bold">#{myRank}</p>
                            </div>
                        )}

                        <div className="flex-1 space-y-2">
                            {leaderboard.slice(0, 5).map((player, i) => (
                                <div key={player.nickname}
                                    className={`leaderboard-item ${player.nickname === nickname ? 'highlighted' : ''}`}>
                                    <div className="flex items-center gap-3">
                                        <span className={`rank-badge ${i === 0 ? 'rank-1' : i === 1 ? 'rank-2' : i === 2 ? 'rank-3' : 'rank-default'}`}>
                                            {i + 1}
                                        </span>
                                        <span className="font-medium">{player.nickname}</span>
                                    </div>
                                    <span className="font-bold">{player.score}</span>
                                </div>
                            ))}
                        </div>
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

                        {leaderboard.findIndex(p => p.nickname === nickname) >= 3 && (
                            <p className="text-[--text-tertiary] mt-4">
                                You finished #{leaderboard.findIndex(p => p.nickname === nickname) + 1}
                            </p>
                        )}

                        <button onClick={() => window.location.reload()} className="btn btn-primary w-full mt-8">
                            Play Again
                        </button>
                    </div>
                )}

            </div>
        </div>
    );
}
