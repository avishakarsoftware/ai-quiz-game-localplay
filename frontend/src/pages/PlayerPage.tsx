import { useState, useRef, useEffect } from 'react';
import { useSearchParams } from 'react-router-dom';
import { API_URL, WS_URL } from '../config';
import { type LeaderboardEntry, type TeamLeaderboardEntry, type PlayerInfo, type PowerUps, ANSWER_STYLES, AVATAR_EMOJIS } from '../types';
import { soundManager } from '../utils/sound';
import AnimatedNumber from '../components/AnimatedNumber';
import Fireworks from '../components/Fireworks';
import BonusSplash from '../components/BonusSplash';
import LeaderboardBarChart from '../components/LeaderboardBarChart';
import { AVATAR_COLORS } from '../components/LeaderboardBarChart.constants';

type PlayerState = 'JOIN' | 'LOBBY' | 'QUESTION' | 'WAITING' | 'RESULT' | 'PODIUM' | 'RECONNECTING';

interface PlayerQuestion {
    id: number;
    text: string;
    options: string[];
    image_url?: string;
}

function getSavedSession() {
    try {
        const raw = sessionStorage.getItem('localplay_session');
        if (raw) return JSON.parse(raw) as { roomCode: string; nickname: string; team: string; avatar: string };
    } catch {}
    return null;
}

export default function PlayerPage() {
    const [searchParams] = useSearchParams();
    const saved = getSavedSession();
    const [state, setState] = useState<PlayerState>('JOIN');
    const [roomCode, setRoomCode] = useState(searchParams.get('room') || saved?.roomCode || '');
    const [nickname, setNickname] = useState(saved?.nickname || '');
    const [team, setTeam] = useState(saved?.team || '');
    const [avatar, setAvatar] = useState(() => saved?.avatar || AVATAR_EMOJIS[Math.floor(Math.random() * AVATAR_EMOJIS.length)]);
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
    const [teamLeaderboard, setTeamLeaderboard] = useState<TeamLeaderboardEntry[]>([]);
    const [myRank, setMyRank] = useState(0);
    const [error, setError] = useState('');
    const [lobbyPlayers, setLobbyPlayers] = useState<PlayerInfo[]>([]);
    const [powerUps, setPowerUps] = useState<PowerUps>({ double_points: true, fifty_fifty: true });
    const [hiddenOptions, setHiddenOptions] = useState<number[]>([]);
    const [isBonus, setIsBonus] = useState(false);
    const [showBonusSplash, setShowBonusSplash] = useState(false);
    const wsRef = useRef<WebSocket | null>(null);
    const autoJoinedRef = useRef(false);
    const kickedRef = useRef(false);

    // Auto-rejoin if we have a saved session (e.g. page refresh)
    useEffect(() => {
        if (saved && !autoJoinedRef.current && !wsRef.current) {
            autoJoinedRef.current = true;
            // Small delay to let state settle
            const timer = setTimeout(() => joinRoom(), 100);
            return () => clearTimeout(timer);
        }
    // eslint-disable-next-line react-hooks/exhaustive-deps
    }, []);

    const joinRoom = () => {
        if (!roomCode.trim() || !nickname.trim()) return;
        setError('');
        kickedRef.current = false;

        const clientId = `player-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`;
        const ws = new WebSocket(`${WS_URL}/ws/${roomCode}/${clientId}`);
        wsRef.current = ws;

        ws.onopen = () => ws.send(JSON.stringify({ type: 'JOIN', nickname, team: team || undefined, avatar }));

        ws.onmessage = (event) => {
            let msg: Record<string, unknown>;
            try { msg = JSON.parse(event.data); } catch { return; }
            if (msg.type === 'ERROR') {
                setError(msg.message as string);
                // If room doesn't exist, stop reconnection attempts
                if (msg.message === 'Room not found' || msg.message === 'Room is full') {
                    kickedRef.current = true;
                    wsRef.current?.close();
                    wsRef.current = null;
                    sessionStorage.removeItem('localplay_session');
                    setState('JOIN');
                }
                return;
            }
            if (msg.type === 'KICKED') {
                // Another tab/device took over this nickname
                kickedRef.current = true;
                wsRef.current = null;
                setState('JOIN');
                setError('You joined from another device');
                return;
            }
            if (msg.type === 'JOINED_ROOM') {
                sessionStorage.setItem('localplay_session', JSON.stringify({ roomCode, nickname, team, avatar }));
                setState('LOBBY');
            }
            if (msg.type === 'RECONNECTED') {
                sessionStorage.setItem('localplay_session', JSON.stringify({ roomCode, nickname, team, avatar }));
                setQuestionNumber(msg.question_number);
                setTotalQuestions(msg.total_questions);
                if (msg.state === 'LOBBY') {
                    setState('LOBBY');
                } else if (msg.state === 'QUESTION' && msg.question) {
                    setCurrentQuestion(msg.question);
                    setTimeLimit(msg.time_limit);
                    setTimeRemaining(msg.time_limit);
                    setSelectedAnswer(null);
                    setIsCorrect(null);
                    setPointsEarned(0);
                    setCorrectAnswer(null);
                    setHiddenOptions([]);
                    setIsBonus(msg.is_bonus || false);
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
            if (msg.type === 'PLAYER_LEFT' || msg.type === 'PLAYER_DISCONNECTED' || msg.type === 'PLAYER_RECONNECTED') {
                if (msg.players) setLobbyPlayers(msg.players);
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
                setIsBonus(msg.is_bonus || false);
                if (msg.is_bonus) setShowBonusSplash(true);
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
                    setState('WAITING');
                } else {
                    setState('RESULT');
                }
            }
            if (msg.type === 'PODIUM') { setLeaderboard(msg.leaderboard); setTeamLeaderboard(msg.team_leaderboard || []); setState('PODIUM'); soundManager.play('fanfare'); }
            if (msg.type === 'ORGANIZER_DISCONNECTED') {
                // Host disconnected — show warning but stay connected (they may reconnect)
                setError('The host has disconnected. Waiting for them to return...');
                return;
            }
            if (msg.type === 'ROOM_CLOSED') {
                // Host didn't reconnect — room is gone
                wsRef.current?.close();
                wsRef.current = null;
                kickedRef.current = true; // prevent auto-reconnect
                sessionStorage.removeItem('localplay_session');
                setState('JOIN');
                setError('The host has left and the room was closed');
                return;
            }
            if (msg.type === 'HOST_RECONNECTED') {
                setError('');
                return;
            }
            if (msg.type === 'ROOM_RESET') {
                setCurrentQuestion(null);
                setQuestionNumber(0);
                setTotalQuestions(0);
                setSelectedAnswer(null);
                setIsCorrect(null);
                setPointsEarned(0);
                setStreak(0);
                setMultiplier(1.0);
                setCorrectAnswer(null);
                setLeaderboard([]);
                setTeamLeaderboard([]);
                setMyRank(0);
                setHiddenOptions([]);
                setPowerUps({ double_points: true, fifty_fifty: true });
                setIsBonus(false);
                setShowBonusSplash(false);
                if (msg.players) setLobbyPlayers(msg.players);
                setState('LOBBY');
                soundManager.play('playerJoin');
            }
        };

        ws.onerror = () => setError('Connection failed');
        ws.onclose = () => {
            if (kickedRef.current) { kickedRef.current = false; return; }
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

    return (
        <div className="app-container">
            <div className="content-wrapper">

                {/* JOIN */}
                {state === 'JOIN' && (
                    <div className="container-responsive safe-bottom animate-in" style={{ minHeight: '100dvh', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center' }}>
                        <div className="hero-icon mb-4">🎮</div>
                        <h1 className="hero-title mb-2">Join Game</h1>
                        <p className="text-[--text-tertiary] mb-8">Enter the game PIN to play</p>

                        <div className="w-full space-y-4">
                            <div className="stagger-in" style={{ animationDelay: '0.05s' }}>
                                <input
                                    type="text"
                                    value={roomCode}
                                    onChange={(e) => setRoomCode(e.target.value.toUpperCase().replace(/[^A-Z0-9]/g, ''))}
                                    placeholder="Game PIN"
                                    className="input-field text-center text-2xl tracking-widest uppercase"
                                    maxLength={6}
                                />
                            </div>

                            <div className="stagger-in" style={{ animationDelay: '0.1s' }}>
                                <input
                                    type="text"
                                    value={nickname}
                                    onChange={(e) => setNickname(e.target.value)}
                                    placeholder="Your nickname"
                                    className="input-field text-center"
                                    maxLength={20}
                                />
                            </div>

                            <div className="stagger-in" style={{ animationDelay: '0.15s' }}>
                                <input
                                    type="text"
                                    value={team}
                                    onChange={(e) => setTeam(e.target.value)}
                                    placeholder="Team name (optional)"
                                    className="input-field text-center"
                                    maxLength={20}
                                />
                            </div>

                            <div className="stagger-in" style={{ animationDelay: '0.18s' }}>
                                <p className="text-[--text-secondary] text-sm font-medium text-center mb-2">Choose your avatar</p>
                                <div
                                    style={{
                                        display: 'flex',
                                        gap: 8,
                                        overflowX: 'auto',
                                        padding: '8px 4px',
                                        scrollSnapType: 'x mandatory',
                                        WebkitOverflowScrolling: 'touch',
                                        scrollbarWidth: 'none',
                                        msOverflowStyle: 'none',
                                    }}
                                    className="no-scrollbar"
                                >
                                    {AVATAR_EMOJIS.map((emoji) => (
                                        <button
                                            key={emoji}
                                            type="button"
                                            onClick={() => setAvatar(emoji)}
                                            style={{
                                                flex: '0 0 auto',
                                                width: 48,
                                                height: 48,
                                                padding: 0,
                                                borderRadius: 12,
                                                border: 'none',
                                                cursor: 'pointer',
                                                display: 'flex',
                                                alignItems: 'center',
                                                justifyContent: 'center',
                                                fontSize: '2rem',
                                                scrollSnapAlign: 'start',
                                                transition: 'transform 0.15s, box-shadow 0.15s',
                                                backgroundColor: avatar === emoji ? 'var(--accent-primary)' : 'var(--bg-secondary)',
                                                transform: avatar === emoji ? 'scale(1.15)' : 'scale(1)',
                                                boxShadow: avatar === emoji ? '0 0 0 2px var(--accent-primary), 0 4px 12px rgba(0,0,0,0.2)' : 'none',
                                            }}
                                        >
                                            {emoji}
                                        </button>
                                    ))}
                                </div>
                            </div>

                            {error && (
                                <div className="status-pill status-error w-full justify-center animate-shake">{error}</div>
                            )}

                            <div className="stagger-in" style={{ animationDelay: '0.2s' }}>
                                <button
                                    onClick={joinRoom}
                                    disabled={!roomCode.trim() || !nickname.trim()}
                                    className="btn btn-primary btn-glow w-full"
                                >
                                    Join
                                </button>
                            </div>
                        </div>
                    </div>
                )}

                {/* LOBBY */}
                {state === 'LOBBY' && (
                    <div className="container-responsive animate-in" style={{ minHeight: '100dvh', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center' }}>
                        <div className="screen-hero">
                            <div className="hero-icon mb-4">👋</div>
                            <h1 className="hero-title">You're in!</h1>
                            <p className="hero-subtitle">Waiting for host to start</p>
                        </div>

                        {lobbyPlayers.length > 0 ? (
                            <div className="w-full mb-6">
                                <p className="text-center mb-3">
                                    <span className="text-2xl font-bold">{lobbyPlayers.length}</span>{' '}
                                    <span className="text-[--text-secondary] font-medium">player{lobbyPlayers.length !== 1 ? 's' : ''}</span>
                                </p>
                                <div style={{ display: 'flex', flexWrap: 'wrap', justifyContent: 'center', gap: 8 }}>
                                    {lobbyPlayers.map((player, i) => {
                                        const isSelf = player.nickname === nickname;
                                        return (
                                            <div key={player.nickname} style={{ display: 'inline-flex', alignItems: 'center', gap: 8, padding: '8px 16px', borderRadius: 9999, background: isSelf ? 'rgba(var(--accent-primary-rgb, 99,102,241), 0.2)' : 'var(--bg-secondary)', boxShadow: isSelf ? 'inset 0 0 0 1px var(--accent-primary)' : 'none' }}>
                                                <div
                                                    style={{ width: 36, height: 36, minWidth: 36, borderRadius: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center', backgroundColor: AVATAR_COLORS[i % AVATAR_COLORS.length] }}
                                                >
                                                    <span style={{ fontSize: '1.25rem', lineHeight: 1 }}>{player.avatar || player.nickname.slice(0, 2).toUpperCase()}</span>
                                                </div>
                                                <span style={{ fontSize: '1rem', fontWeight: isSelf ? 700 : 500, color: isSelf ? 'var(--accent-primary)' : undefined }}>
                                                    {player.nickname}{isSelf ? ' \u2605' : ''}
                                                </span>
                                            </div>
                                        );
                                    })}
                                </div>
                            </div>
                        ) : (
                            <div className="card px-8 py-4 mb-6">
                                <p className="text-lg font-semibold">{nickname}</p>
                                {team && <p className="text-xs text-[--text-tertiary]">Team: {team}</p>}
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
                    showBonusSplash ? (
                        <BonusSplash onComplete={() => setShowBonusSplash(false)} />
                    ) : (
                    <div className="min-h-dvh flex flex-col container-responsive safe-top safe-bottom">
                        <div className="py-4 stagger-in" style={{ animationDelay: '0s' }}>
                            <div className="flex items-center justify-between mb-2">
                                <div className="flex items-center gap-2">
                                    <span className="text-[--text-tertiary] text-sm">Q{questionNumber}/{totalQuestions}</span>
                                    {isBonus && <span className="bonus-badge">2X BONUS</span>}
                                </div>
                                <div className="flex items-center gap-2">
                                    {streak >= 3 && (
                                        <span className="streak-fire">{streak} streak</span>
                                    )}
                                    <span className={`font-bold tabular-nums ${timeRemaining <= 5 ? 'timer-number-pulse' : ''}`}
                                        style={{ color: timeRemaining <= 5 ? 'var(--accent-danger)' : timeRemaining <= 10 ? 'var(--accent-warning)' : 'var(--accent-primary)' }}>
                                        {timeRemaining}s
                                    </span>
                                </div>
                            </div>
                            <div className="question-timer-bar">
                                <div
                                    className="question-timer-fill"
                                    style={{
                                        width: `${(timeRemaining / timeLimit) * 100}%`,
                                        background: timeRemaining <= 5 ? 'var(--accent-danger)' : timeRemaining <= 10 ? 'var(--accent-warning)' : 'var(--accent-primary)',
                                    }}
                                />
                            </div>
                        </div>

                        <div className={`question-card mb-4 question-enter ${currentQuestion.image_url ? 'has-image' : ''}`}
                            style={currentQuestion.image_url ? { backgroundImage: `url(${API_URL}${currentQuestion.image_url})` } : undefined}>
                            <p className="question-text">{currentQuestion.text}</p>
                        </div>

                        {/* Power-ups */}
                        {selectedAnswer === null && (powerUps.double_points || powerUps.fifty_fifty) && (
                            <div className="flex gap-2 mb-4 justify-center stagger-in" style={{ animationDelay: '0.2s' }}>
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
                                    className={`answer-btn answer-stagger ${ANSWER_STYLES[i].className} ${selectedAnswer === i ? 'selected' : ''} ${selectedAnswer !== null && selectedAnswer !== i ? 'dimmed' : ''} ${hiddenOptions.includes(i) ? 'hidden-option' : ''}`}
                                    style={{ animationDelay: `${0.15 + i * 0.08}s` }}
                                >
                                    <span className="text-4xl opacity-50 mr-3 flex-shrink-0">{ANSWER_STYLES[i].shape}</span>
                                    <span className="min-w-0" style={{ fontSize: opt.length > 50 ? 13 : opt.length > 30 ? 14 : 16 }}>{opt}</span>
                                </button>
                            ))}
                        </div>
                    </div>
                    )
                )}

                {/* WAITING */}
                {state === 'WAITING' && (
                    <div className="min-h-dvh flex flex-col items-center justify-center container-responsive animate-in">
                        {isCorrect ? (
                            <div className="celebration-container">
                                {/* Particle burst */}
                                <div className="celebration-burst">
                                    {Array.from({ length: 12 }).map((_, i) => (
                                        <span key={i} className="burst-particle" style={{
                                            '--angle': `${i * 30}deg`,
                                            '--delay': `${i * 0.03}s`,
                                            '--color': ['#34C759', '#FFD700', '#007AFF', '#FF9500'][i % 4],
                                        } as React.CSSProperties} />
                                    ))}
                                </div>
                                <div className="result-icon result-icon-correct animate-score-pop">✓</div>
                                <h2 className="hero-title text-[--accent-success] mb-4" style={{ WebkitTextFillColor: 'var(--accent-success)' }}>Correct!</h2>
                                {pointsEarned > 0 && (
                                    <div className="card px-8 py-4 points-glow animate-score-pop" style={{ animationDelay: '0.15s' }}>
                                        <span className="text-3xl font-bold text-[--accent-success]">+{pointsEarned}</span>
                                        {multiplier > 1 && (
                                            <span className="text-sm text-[--accent-warning] ml-2">x{multiplier}</span>
                                        )}
                                    </div>
                                )}
                                {streak >= 3 && (
                                    <p className="streak-fire mt-3 animate-score-pop" style={{ animationDelay: '0.3s' }}>
                                        {streak} in a row!
                                    </p>
                                )}
                            </div>
                        ) : (
                            <>
                                <div className="result-icon result-icon-wrong wrong-shake">✗</div>
                                <h2 className="hero-title text-[--accent-danger] mb-4" style={{ WebkitTextFillColor: 'var(--accent-danger)' }}>Wrong</h2>
                            </>
                        )}
                        <p className="text-[--text-tertiary] mt-6">Waiting for others...</p>
                        <div className="flex gap-1.5 mt-4">
                            {[0, 1, 2].map((i) => (
                                <div key={i} className="w-2 h-2 bg-[--accent-primary] rounded-full animate-bounce"
                                    style={{ animationDelay: `${i * 0.15}s` }} />
                            ))}
                        </div>
                    </div>
                )}

                {/* RECONNECTING */}
                {state === 'RECONNECTING' && (
                    <div className="min-h-dvh flex flex-col items-center justify-center container-responsive animate-in">
                        <div className="status-screen-icon animate-pulse">↻</div>
                        <h2 className="text-2xl font-extrabold mb-2">Reconnecting...</h2>
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
                    <div className="min-h-dvh flex flex-col items-center container-responsive safe-top safe-bottom animate-in">
                        <div className="text-center py-6">
                            {isCorrect ? (
                                <div className="result-icon result-icon-correct mb-2" style={{ width: 56, height: 56, fontSize: 28 }}>✓</div>
                            ) : (
                                <div className="result-icon result-icon-wrong mb-2" style={{ width: 56, height: 56, fontSize: 28 }}>✗</div>
                            )}
                            <h2 className="text-2xl font-extrabold" style={{ color: isCorrect ? 'var(--accent-success)' : 'var(--accent-danger)' }}>
                                {isCorrect ? 'Correct!' : 'Wrong'}
                            </h2>
                            {pointsEarned > 0 && (
                                <p className="text-xl font-bold text-[--accent-success] mt-2">+{pointsEarned}</p>
                            )}
                        </div>

                        {myRank > 0 && (
                            <div className="card text-center py-6 mb-4 w-full">
                                <p className="text-[--text-tertiary] text-sm mb-1">Your position</p>
                                <p className="text-4xl font-bold">#{myRank}</p>
                            </div>
                        )}

                        <div className="flex-1 w-full">
                            <LeaderboardBarChart
                                leaderboard={leaderboard}
                                maxEntries={5}
                                size="compact"
                                highlightNickname={nickname}
                            />
                        </div>
                    </div>
                )}

                {/* PODIUM */}
                {state === 'PODIUM' && (
                    <div className="min-h-dvh flex flex-col items-center justify-center container-responsive safe-bottom animate-in"
                         style={{ position: 'relative', overflow: 'hidden' }}>
                        <Fireworks duration={10000} maxRockets={2} />

                        <h1 className="hero-title text-center mb-4" style={{ position: 'relative', zIndex: 11 }}>Final Results</h1>

                        {leaderboard[0] && (
                            <div className="champion-label" style={{ position: 'relative', zIndex: 11 }}>
                                <span className="crown-bounce text-xl">&#x1F451;</span>
                                <span className="gold-shimmer text-lg">{leaderboard[0].nickname} wins!</span>
                            </div>
                        )}

                        <div className="podium-container" style={{ position: 'relative', zIndex: 11 }}>
                            {leaderboard[1] && (
                                <div className="podium-place podium-2">
                                    <div className="w-10 h-10 rounded-full flex items-center justify-center mb-2" style={{ backgroundColor: '#C0C0C0' }}>
                                        <span style={{ fontSize: '1.25rem', lineHeight: 1 }}>{leaderboard[1].avatar || leaderboard[1].nickname.slice(0, 2).toUpperCase()}</span>
                                    </div>
                                    <p className="podium-name">{leaderboard[1].nickname}</p>
                                    <div className="podium-bar">2</div>
                                    <p className="podium-score"><AnimatedNumber value={leaderboard[1].score} /></p>
                                </div>
                            )}
                            {leaderboard[0] && (
                                <div className="podium-place podium-1 victory-glow">
                                    <span className="crown-bounce text-2xl" style={{ marginBottom: 4 }}>&#x1F451;</span>
                                    <div className="w-12 h-12 rounded-full flex items-center justify-center mb-2" style={{ backgroundColor: '#FFD700' }}>
                                        <span style={{ fontSize: '1.5rem', lineHeight: 1 }}>{leaderboard[0].avatar || leaderboard[0].nickname.slice(0, 2).toUpperCase()}</span>
                                    </div>
                                    <p className="podium-name">{leaderboard[0].nickname}</p>
                                    <div className="podium-bar">1</div>
                                    <p className="podium-score"><AnimatedNumber value={leaderboard[0].score} /></p>
                                </div>
                            )}
                            {leaderboard[2] && (
                                <div className="podium-place podium-3">
                                    <div className="w-10 h-10 rounded-full flex items-center justify-center mb-2" style={{ backgroundColor: '#CD7F32' }}>
                                        <span style={{ fontSize: '1.25rem', lineHeight: 1 }}>{leaderboard[2].avatar || leaderboard[2].nickname.slice(0, 2).toUpperCase()}</span>
                                    </div>
                                    <p className="podium-name">{leaderboard[2].nickname}</p>
                                    <div className="podium-bar">3</div>
                                    <p className="podium-score"><AnimatedNumber value={leaderboard[2].score} /></p>
                                </div>
                            )}
                        </div>

                        {leaderboard.findIndex(p => p.nickname === nickname) >= 3 && (
                            <p className="text-[--text-tertiary] mt-4" style={{ position: 'relative', zIndex: 11 }}>
                                You finished #{leaderboard.findIndex(p => p.nickname === nickname) + 1}
                            </p>
                        )}

                        {teamLeaderboard.some(t => t.members > 1) && (
                            <div className="w-full mt-6" style={{ position: 'relative', zIndex: 11 }}>
                                <h3 className="text-lg font-semibold text-center mb-3">Team Standings</h3>
                                <div className="podium-container">
                                    {teamLeaderboard[1] && (
                                        <div className="podium-place podium-2">
                                            <p className="podium-name">{teamLeaderboard[1].team}</p>
                                            {teamLeaderboard[1].members > 1 && (
                                                <p className="text-xs text-[--text-tertiary]">{teamLeaderboard[1].members} members</p>
                                            )}
                                            <div className="podium-bar">2</div>
                                            <p className="podium-score"><AnimatedNumber value={teamLeaderboard[1].score} /></p>
                                        </div>
                                    )}
                                    {teamLeaderboard[0] && (
                                        <div className="podium-place podium-1 victory-glow">
                                            <p className="podium-name">{teamLeaderboard[0].team}</p>
                                            {teamLeaderboard[0].members > 1 && (
                                                <p className="text-xs text-[--text-tertiary]">{teamLeaderboard[0].members} members</p>
                                            )}
                                            <div className="podium-bar">1</div>
                                            <p className="podium-score"><AnimatedNumber value={teamLeaderboard[0].score} /></p>
                                        </div>
                                    )}
                                    {teamLeaderboard[2] && (
                                        <div className="podium-place podium-3">
                                            <p className="podium-name">{teamLeaderboard[2].team}</p>
                                            {teamLeaderboard[2].members > 1 && (
                                                <p className="text-xs text-[--text-tertiary]">{teamLeaderboard[2].members} members</p>
                                            )}
                                            <div className="podium-bar">3</div>
                                            <p className="podium-score"><AnimatedNumber value={teamLeaderboard[2].score} /></p>
                                        </div>
                                    )}
                                </div>
                            </div>
                        )}

                        <p className="text-[--text-tertiary] mt-8 text-center" style={{ position: 'relative', zIndex: 11 }}>
                            Waiting for host to start a new game...
                        </p>
                        <div className="flex gap-1.5 mt-4" style={{ position: 'relative', zIndex: 11 }}>
                            {[0, 1, 2].map((i) => (
                                <div key={i} className="w-2 h-2 bg-[--accent-primary] rounded-full animate-bounce"
                                    style={{ animationDelay: `${i * 0.15}s` }} />
                            ))}
                        </div>
                    </div>
                )}

            </div>
        </div>
    );
}
