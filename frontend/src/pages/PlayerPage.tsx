import { useState, useRef } from 'react';
import { useSearchParams } from 'react-router-dom';
import { API_URL, WS_URL } from '../config';
import { type LeaderboardEntry, type PowerUps, ANSWER_STYLES } from '../types';
import { soundManager } from '../utils/sound';

type PlayerState = 'JOIN' | 'LOBBY' | 'QUESTION' | 'WAITING' | 'RESULT' | 'PODIUM' | 'RECONNECTING';

interface PlayerQuestion {
    id: number;
    text: string;
    options: string[];
    image_url?: string;
}

export default function PlayerPage() {
    const [searchParams] = useSearchParams();
    const [state, setState] = useState<PlayerState>('JOIN');
    const [roomCode, setRoomCode] = useState(searchParams.get('room') || '');
    const [nickname, setNickname] = useState('');
    const [team, setTeam] = useState('');
    const [currentQuestion, setCurrentQuestion] = useState<PlayerQuestion | null>(null);
    const [questionNumber, setQuestionNumber] = useState(0);
    const [totalQuestions, setTotalQuestions] = useState(0);
    const [timeLimit, setTimeLimit] = useState(15);
    const [timeRemaining, setTimeRemaining] = useState(15);
    const [selectedAnswer, setSelectedAnswer] = useState<number | null>(null);
    const [isCorrect, setIsCorrect] = useState<boolean | null>(null);
    const [pointsEarned, setPointsEarned] = useState(0);
    const [streak, setStreak] = useState(0);
    const [multiplier, setMultiplier] = useState(1.0);
    const [_correctAnswer, setCorrectAnswer] = useState<number | null>(null);
    const [leaderboard, setLeaderboard] = useState<LeaderboardEntry[]>([]);
    const [myRank, setMyRank] = useState(0);
    const [error, setError] = useState('');
    const [lobbyPlayers, setLobbyPlayers] = useState<string[]>([]);
    const [powerUps, setPowerUps] = useState<PowerUps>({ double_points: true, fifty_fifty: true });
    const [hiddenOptions, setHiddenOptions] = useState<number[]>([]);
    const wsRef = useRef<WebSocket | null>(null);

    const joinRoom = () => {
        if (!roomCode.trim() || !nickname.trim()) return;
        setError('');

        const clientId = `player-${Date.now()}`;
        const ws = new WebSocket(`${WS_URL}/ws/${roomCode}/${clientId}`);
        wsRef.current = ws;

        ws.onopen = () => ws.send(JSON.stringify({ type: 'JOIN', nickname, team: team || undefined }));

        ws.onmessage = (event) => {
            const msg = JSON.parse(event.data);
            if (msg.type === 'ERROR') { setError(msg.message); return; }
            if (msg.type === 'JOINED_ROOM') setState('LOBBY');
            if (msg.type === 'RECONNECTED') {
                setQuestionNumber(msg.question_number);
                setTotalQuestions(msg.total_questions);
                if (msg.state === 'QUESTION' && msg.question) {
                    setCurrentQuestion(msg.question);
                    setTimeLimit(msg.time_limit);
                    setTimeRemaining(msg.time_limit);
                    setSelectedAnswer(null);
                    setIsCorrect(null);
                    setPointsEarned(0);
                    setCorrectAnswer(null);
                    setHiddenOptions([]);
                    setState('QUESTION');
                } else {
                    setState('WAITING');
                }
                return;
            }
            if (msg.type === 'PLAYER_JOINED') {
                if (msg.players) setLobbyPlayers(msg.players);
                soundManager.play('playerJoin');
            }
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
                setHiddenOptions([]);
                setState('QUESTION');
            }
            if (msg.type === 'TIMER') {
                setTimeRemaining(msg.remaining);
                if (msg.remaining <= 5 && msg.remaining > 0) soundManager.play('timerTick');
            }
            if (msg.type === 'ANSWER_RESULT') {
                setIsCorrect(msg.correct);
                setPointsEarned(msg.points);
                setStreak(msg.streak || 0);
                setMultiplier(msg.multiplier || 1.0);
                setState('WAITING');
                if (msg.correct) {
                    soundManager.play('correct');
                    soundManager.vibrate(100);
                } else {
                    soundManager.play('wrong');
                    soundManager.vibrate([100, 50, 100]);
                }
            }
            if (msg.type === 'POWER_UP_ACTIVATED') {
                if (msg.power_up === 'double_points') {
                    setPowerUps(prev => ({ ...prev, double_points: false }));
                } else if (msg.power_up === 'fifty_fifty') {
                    setPowerUps(prev => ({ ...prev, fifty_fifty: false }));
                    if (msg.remove_indices) setHiddenOptions(msg.remove_indices);
                }
            }
            if (msg.type === 'QUESTION_OVER') {
                setCorrectAnswer(msg.answer);
                setLeaderboard(msg.leaderboard);
                setMyRank(msg.leaderboard.findIndex((p: LeaderboardEntry) => p.nickname === nickname) + 1);
                if (msg.is_final) {
                    // Stay in WAITING state until organizer shows podium
                } else {
                    setState('RESULT');
                }
            }
            if (msg.type === 'PODIUM') { setLeaderboard(msg.leaderboard); setState('PODIUM'); soundManager.play('podium'); }
        };

        ws.onerror = () => setError('Connection failed');
        ws.onclose = () => {
            setState((current) => {
                if (current !== 'JOIN' && current !== 'PODIUM') {
                    setTimeout(() => joinRoom(), 2000);
                    return 'RECONNECTING';
                }
                if (current === 'JOIN') setError('Room not found');
                return current;
            });
        };
    };

    const submitAnswer = (index: number) => {
        if (selectedAnswer !== null) return;
        setSelectedAnswer(index);
        wsRef.current?.send(JSON.stringify({ type: 'ANSWER', answer_index: index }));
    };

    const usePowerUp = (powerUp: 'double_points' | 'fifty_fifty') => {
        wsRef.current?.send(JSON.stringify({ type: 'USE_POWER_UP', power_up: powerUp }));
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

                            <input
                                type="text"
                                value={team}
                                onChange={(e) => setTeam(e.target.value)}
                                placeholder="Team name (optional)"
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

                        <div className="card px-8 py-4 mb-6">
                            <p className="text-lg font-semibold">{nickname}</p>
                            {team && <p className="text-xs text-[--text-tertiary]">Team: {team}</p>}
                        </div>

                        {lobbyPlayers.length > 0 && (
                            <div className="w-full mb-6 max-h-32 overflow-y-auto no-scrollbar">
                                <p className="text-[--text-tertiary] text-xs text-center mb-2">{lobbyPlayers.length} player{lobbyPlayers.length !== 1 ? 's' : ''} joined</p>
                                <div className="flex flex-wrap gap-2 justify-center">
                                    {lobbyPlayers.map((name) => (
                                        <span key={name} className={`player-chip ${name === nickname ? 'player-chip-self' : ''}`}>{name}</span>
                                    ))}
                                </div>
                            </div>
                        )}

                        <div className="flex gap-1.5 mt-4">
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
                            {streak >= 3 && (
                                <span className="streak-badge">{streak} streak</span>
                            )}
                            <span className={`timer-display text-3xl ${timeRemaining <= 5 ? 'danger' : timeRemaining <= 10 ? 'warning' : ''}`}>
                                {timeRemaining}
                            </span>
                        </div>

                        <div className="progress-bar mb-4">
                            <div className={`progress-bar-fill ${timeRemaining <= 5 ? 'danger' : timeRemaining <= 10 ? 'warning' : ''}`}
                                style={{ width: `${timerProgress}%` }} />
                        </div>

                        <div className={`question-card mb-4 ${currentQuestion.image_url ? 'has-image' : ''}`}
                            style={currentQuestion.image_url ? { backgroundImage: `url(${API_URL}${currentQuestion.image_url})` } : undefined}>
                            <p className="question-text">{currentQuestion.text}</p>
                        </div>

                        {/* Power-ups */}
                        {selectedAnswer === null && (powerUps.double_points || powerUps.fifty_fifty) && (
                            <div className="flex gap-2 mb-4 justify-center">
                                {powerUps.double_points && (
                                    <button onClick={() => usePowerUp('double_points')} className="power-up-btn">
                                        2x Points
                                    </button>
                                )}
                                {powerUps.fifty_fifty && currentQuestion.options.length === 4 && (
                                    <button onClick={() => usePowerUp('fifty_fifty')} className="power-up-btn">
                                        50/50
                                    </button>
                                )}
                            </div>
                        )}

                        <div className={`flex-1 ${currentQuestion.options.length === 2 ? 'answer-grid-tf' : 'answer-grid'}`}>
                            {currentQuestion.options.map((opt, i) => (
                                <button
                                    key={i}
                                    onClick={() => submitAnswer(i)}
                                    disabled={selectedAnswer !== null || hiddenOptions.includes(i)}
                                    className={`answer-btn ${ANSWER_STYLES[i].className} ${selectedAnswer === i ? 'selected' : ''} ${selectedAnswer !== null && selectedAnswer !== i ? 'dimmed' : ''} ${hiddenOptions.includes(i) ? 'hidden-option' : ''}`}
                                >
                                    <span className="text-2xl opacity-50 mr-2">{ANSWER_STYLES[i].shape}</span>
                                    <span>{opt}</span>
                                </button>
                            ))}
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
                                        {multiplier > 1 && (
                                            <span className="text-sm text-[--accent-warning] ml-2">x{multiplier}</span>
                                        )}
                                    </div>
                                )}
                                {streak >= 3 && (
                                    <p className="text-[--accent-warning] mt-3 font-semibold animate-score-pop">
                                        {streak} in a row!
                                    </p>
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

                {/* RECONNECTING */}
                {state === 'RECONNECTING' && (
                    <div className="min-h-dvh flex flex-col items-center justify-center container-responsive animate-in">
                        <div className="text-5xl mb-4 animate-pulse">↻</div>
                        <h2 className="text-2xl font-bold mb-2">Reconnecting...</h2>
                        <p className="text-[--text-tertiary]">Don't worry, your score is saved</p>
                        <div className="flex gap-1.5 mt-6">
                            {[0, 1, 2].map((i) => (
                                <div key={i} className="w-2 h-2 bg-[--accent-primary] rounded-full animate-bounce"
                                    style={{ animationDelay: `${i * 0.15}s` }} />
                            ))}
                        </div>
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
                            {leaderboard[1] && (
                                <div className="podium-place podium-2">
                                    <p className="podium-name">{leaderboard[1].nickname}</p>
                                    <div className="podium-bar">2</div>
                                    <p className="podium-score">{leaderboard[1].score}</p>
                                </div>
                            )}
                            {leaderboard[0] && (
                                <div className="podium-place podium-1">
                                    <p className="text-3xl mb-2">🏆</p>
                                    <p className="podium-name">{leaderboard[0].nickname}</p>
                                    <div className="podium-bar">1</div>
                                    <p className="podium-score">{leaderboard[0].score}</p>
                                </div>
                            )}
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
