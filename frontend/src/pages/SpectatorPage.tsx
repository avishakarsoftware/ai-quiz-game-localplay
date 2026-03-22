import { useState, useEffect, useRef } from 'react';
import { useSearchParams, useParams } from 'react-router-dom';
import { QRCodeCanvas } from 'qrcode.react';
import { WS_URL, API_URL } from '../config';
import { type LeaderboardEntry, type TeamLeaderboardEntry, type PlayerInfo, type GameType, ANSWER_STYLES } from '../types';
import AnimatedNumber from '../components/AnimatedNumber';
import Fireworks from '../components/Fireworks';
import LeaderboardBarChart from '../components/LeaderboardBarChart';
import { AVATAR_COLORS } from '../components/LeaderboardBarChart.constants';
import { soundManager } from '../utils/sound';
import BonusSplash from '../components/BonusSplash';
import '../cast.d.ts';
import { CAST_NAMESPACE, CAST_RECEIVER_SDK_URL } from '../cast-constants';

interface SpectatorQuestion {
    id: number;
    text: string;
    options: string[];
    image_url?: string;
}

export default function SpectatorPage() {
    const [searchParams, setSearchParams] = useSearchParams();
    const { code: routeCode } = useParams<{ code?: string }>();
    const roomFromUrl = routeCode || searchParams.get('room') || '';
    const [roomCode, setRoomCode] = useState(roomFromUrl);
    const [roomInput, setRoomInput] = useState('');
    const [joined, setJoined] = useState(!!roomFromUrl);
    const [gameState, setGameState] = useState(roomFromUrl ? 'CONNECTING' : 'LOBBY');
    const gameStateRef = useRef(gameState);
    const preDisconnectRef = useRef('LOBBY');
    useEffect(() => { gameStateRef.current = gameState; }, [gameState]);
    const [players, setPlayers] = useState<PlayerInfo[]>([]);
    const [playerCount, setPlayerCount] = useState(0);
    const [gameType, setGameType] = useState<GameType>('quiz');
    const [currentStatement, setCurrentStatement] = useState<{ id: number; text: string } | null>(null);
    const [votePlayers, setVotePlayers] = useState<PlayerInfo[]>([]);
    const [question, setQuestion] = useState<SpectatorQuestion | null>(null);
    const [questionNumber, setQuestionNumber] = useState(0);
    const [totalQuestions, setTotalQuestions] = useState(0);
    const [timeRemaining, setTimeRemaining] = useState(0);
    const [timeLimit, setTimeLimit] = useState(15);
    const [leaderboard, setLeaderboard] = useState<LeaderboardEntry[]>([]);
    const [teamLeaderboard, setTeamLeaderboard] = useState<TeamLeaderboardEntry[]>([]);
    const [podiumReveal, setPodiumReveal] = useState(0);
    const [isBonus, setIsBonus] = useState(false);
    const [showBonusSplash, setShowBonusSplash] = useState(false);
    const [showFullscreenPrompt, setShowFullscreenPrompt] = useState(true);
    const [wmltRoundResult, setWmltRoundResult] = useState<{ winner: string; winners: string[]; round_podium: { nickname: string; avatar: string; vote_count: number; voters: string[] }[]; unanimous: boolean; show_votes: boolean; statement: string } | null>(null);
    const [superlatives, setSuperlatives] = useState<{ title: string; icon: string; winner: string; avatar: string; detail: string }[]>([]);
    const wsRef = useRef<WebSocket | null>(null);
    const reconnectDelayRef = useRef(2000);
    const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
    const roomClosedRef = useRef(false);
    const mountedRef = useRef(true);

    // In Capacitor, window.location.origin is capacitor://localhost — use the web URL
    const isCapacitor = window.location.protocol === 'capacitor:' || (window.location.hostname === 'localhost' && !window.location.port);
    const baseUrl = isCapacitor
        ? (import.meta.env.VITE_WEB_URL || 'https://games.revelryapp.me/quiz/')
        : `${window.location.origin}${import.meta.env.BASE_URL}`;
    const joinUrl = `${baseUrl}join?room=${roomCode}`;
    const displayUrl = `${new URL(joinUrl).host}${new URL(joinUrl).pathname}`;

    const handleJoinRoom = () => {
        const code = roomInput.trim().toUpperCase();
        if (code.length < 4) return;
        setRoomCode(code);
        setJoined(true);
        setGameState('CONNECTING');
        setSearchParams({ room: code });
    };

    // Cast Receiver: dynamically load SDK and auto-join when sender sends room code
    const castInitialized = useRef(false);
    useEffect(() => {
        if (castInitialized.current) return;
        castInitialized.current = true;

        const initReceiver = () => {
            try {
                if (typeof cast === 'undefined' || !cast.framework?.CastReceiverContext) return;
                const receiverContext = cast.framework.CastReceiverContext.getInstance();
                if (!receiverContext) return;

                receiverContext.addCustomMessageListener(CAST_NAMESPACE, (event) => {
                    try {
                        const data = typeof event.data === 'string' ? JSON.parse(event.data) : event.data;
                        const code = String(data.roomCode || '').toUpperCase();
                        if (data.type === 'JOIN_ROOM' && /^[A-Z0-9]{4,6}$/.test(code)) {
                            setRoomCode(code);
                            setJoined(true);
                            setGameState('CONNECTING');
                            setSearchParams({ room: code });
                        }
                    } catch (err) {
                        console.error('Cast receiver message parse error:', err);
                    }
                });

                receiverContext.start();
            } catch {
                // Not running as a Cast receiver — normal browser mode
            }
        };

        // Dynamically load receiver SDK only on spectator page
        const script = document.createElement('script');
        script.src = CAST_RECEIVER_SDK_URL;
        script.onload = initReceiver;
        script.onerror = () => {}; // Silently fail if SDK can't load
        document.head.appendChild(script);
    }, [setSearchParams]);

    const connectWs = useRef<() => void>(() => {});
    connectWs.current = () => {
        if (!joined || !roomCode) return;
        const clientId = `spectator-${Date.now()}`;
        const ws = new WebSocket(`${WS_URL}/ws/${roomCode}/${clientId}?spectator=true`);
        wsRef.current = ws;

        ws.onopen = () => {
            reconnectDelayRef.current = 2000; // Reset backoff on success
        };

        ws.onmessage = (event) => {
            let msg: Record<string, unknown>;
            try { msg = JSON.parse(event.data); } catch { return; }
            if (msg.type === 'PING') return; // heartbeat — no action needed
            if (msg.type === 'SPECTATOR_SYNC') {
                setPlayers(msg.players || []);
                setPlayerCount(msg.player_count);
                setQuestionNumber(msg.question_number);
                setTotalQuestions(msg.total_questions);
                setLeaderboard(msg.leaderboard || []);
                if (msg.game_type) setGameType(msg.game_type);
                // Handle mid-question sync
                if (msg.state === 'QUESTION') {
                    if (msg.game_type === 'wmlt' && msg.statement) {
                        setCurrentStatement(msg.statement);
                        setVotePlayers(msg.players || []);
                    } else if (msg.question) {
                        setQuestion(msg.question);
                    }
                    setTimeLimit(msg.time_limit);
                    setTimeRemaining(msg.time_remaining ?? msg.time_limit);
                    setIsBonus(msg.is_bonus || false);
                }
                setGameState(msg.state === 'INTRO' ? 'LOBBY' : msg.state);
            }
            else if (msg.type === 'PLAYER_JOINED') {
                setPlayerCount(msg.player_count);
                setPlayers(msg.players || []);
            }
            else if (msg.type === 'PLAYER_LEFT' || msg.type === 'PLAYER_DISCONNECTED') {
                setPlayerCount(msg.player_count);
                setPlayers(msg.players || []);
            }
            else if (msg.type === 'PLAYER_RECONNECTED') {
                setPlayerCount(msg.player_count);
                setPlayers(msg.players || []);
            }
            else if (msg.type === 'GAME_STARTING') { /* stay on LOBBY until first QUESTION arrives */ }
            else if (msg.type === 'QUESTION') {
                if (msg.game_type) setGameType(msg.game_type);
                setQuestionNumber(msg.question_number);
                setTotalQuestions(msg.total_questions);
                setTimeLimit(msg.time_limit);
                setTimeRemaining(msg.time_limit);
                setIsBonus(msg.is_bonus || false);
                if (msg.game_type === 'wmlt' || msg.statement) {
                    setCurrentStatement(msg.statement);
                    setVotePlayers(msg.players || []);
                } else {
                    setQuestion(msg.question);
                }
                if (msg.is_bonus) setShowBonusSplash(true);
                setGameState('QUESTION');
            }
            else if (msg.type === 'TIMER') setTimeRemaining(msg.remaining);
            else if (msg.type === 'QUESTION_OVER') {
                setLeaderboard(msg.leaderboard);
                if (msg.game_type === 'wmlt') {
                    setWmltRoundResult({
                        winner: msg.winner,
                        winners: msg.winners || [msg.winner],
                        round_podium: msg.round_podium || [],
                        unanimous: msg.unanimous || false,
                        show_votes: msg.show_votes ?? true,
                        statement: msg.statement || '',
                    });
                } else {
                    setWmltRoundResult(null);
                }
                if (!msg.is_final) {
                    setGameState('LEADERBOARD');
                }
                // When is_final, stay on current screen until PODIUM arrives
            }
            else if (msg.type === 'PODIUM') {
                setLeaderboard(msg.leaderboard);
                setTeamLeaderboard(msg.team_leaderboard || []);
                setSuperlatives(msg.superlatives || []);
                setPodiumReveal(0);
                setGameState('PODIUM');
                soundManager.play('fanfare');
            }
            else if (msg.type === 'ORGANIZER_DISCONNECTED') {
                preDisconnectRef.current = gameStateRef.current;
                setGameState('DISCONNECTED');
            }
            else if (msg.type === 'HOST_RECONNECTED') {
                setGameState(preDisconnectRef.current || 'LOBBY');
            }
            else if (msg.type === 'ROOM_CLOSED') {
                roomClosedRef.current = true;
                if (reconnectTimerRef.current) clearTimeout(reconnectTimerRef.current);
                setGameState('DISCONNECTED');
            }
            else if (msg.type === 'ROOM_RESET') {
                setPlayers(msg.players || []);
                setPlayerCount(msg.player_count);
                setIsBonus(false);
                setShowBonusSplash(false);
                setCurrentStatement(null);
                setVotePlayers([]);
                if (msg.game_type) setGameType(msg.game_type);
                setGameState('LOBBY');
            }
        };

        ws.onerror = () => setGameState('ERROR');
        ws.onclose = () => {
            wsRef.current = null;
            if (roomClosedRef.current || !mountedRef.current) return;
            setGameState('DISCONNECTED');
            // Exponential backoff: 2s, 4s, 8s, 16s, capped at 30s
            const delay = reconnectDelayRef.current;
            reconnectDelayRef.current = Math.min(delay * 2, 30000);
            reconnectTimerRef.current = setTimeout(() => connectWs.current(), delay);
        };
    };

    useEffect(() => {
        if (!joined || !roomCode) return;
        roomClosedRef.current = false;
        reconnectDelayRef.current = 2000;
        connectWs.current();
        return () => {
            mountedRef.current = false;
            if (reconnectTimerRef.current) clearTimeout(reconnectTimerRef.current);
            wsRef.current?.close();
            wsRef.current = null;
        };
    }, [joined, roomCode]);

    // Fullscreen is triggered by user gesture (see overlay below)

    // Staggered podium reveal
    useEffect(() => {
        if (gameState !== 'PODIUM') return;
        // Reset before starting the timed reveal sequence.
        // eslint-disable-next-line react-hooks/set-state-in-effect
        setPodiumReveal(0);
        const timers = [
            setTimeout(() => setPodiumReveal(1), 300),
            setTimeout(() => setPodiumReveal(2), 1000),
            setTimeout(() => setPodiumReveal(3), 1700),
            setTimeout(() => setPodiumReveal(4), 2500),
        ];
        return () => timers.forEach(clearTimeout);
    }, [gameState]);

    // Firework pop sounds on reveal
    useEffect(() => {
        if (podiumReveal >= 1 && podiumReveal <= 3) {
            soundManager.play('fireworkPop');
        }
    }, [podiumReveal]);

    if (!joined) {
        return (
            <div className="spectator-root">
            <div className="app-container">
                <div className="content-wrapper" style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '40px 60px' }}>
                    <div className="animate-in text-center" style={{ maxWidth: 500, width: '100%' }}>
                        <div style={{ fontSize: '4rem', marginBottom: 16 }}>📺</div>
                        <h1 className="hero-title" style={{ fontSize: '3rem', marginBottom: 8 }}>TV Mode</h1>
                        <p className="text-[--text-tertiary]" style={{ fontSize: '1.25rem', marginBottom: 40 }}>
                            Enter the room code to spectate
                        </p>
                        <input
                            type="text"
                            value={roomInput}
                            onChange={(e) => setRoomInput(e.target.value.toUpperCase().replace(/[^A-Z0-9]/g, '').slice(0, 6))}
                            onKeyDown={(e) => e.key === 'Enter' && handleJoinRoom()}
                            placeholder="ROOM CODE"
                            autoFocus
                            className="w-full text-center font-extrabold mb-6"
                            style={{
                                fontSize: '3rem',
                                letterSpacing: '0.3em',
                                padding: '20px 24px',
                                borderRadius: 16,
                                border: '2px solid rgba(255, 255, 255, 0.15)',
                                background: 'var(--bg-secondary)',
                                color: 'var(--text-primary)',
                                outline: 'none',
                            }}
                        />
                        <button
                            onClick={handleJoinRoom}
                            disabled={roomInput.trim().length < 4}
                            className="btn btn-primary btn-glow w-full"
                            style={{ fontSize: '1.25rem', padding: '16px 24px' }}
                        >
                            Watch Game
                        </button>
                    </div>
                </div>
            </div>
            </div>
        );
    }

    return (
        <div className="spectator-root">
        <div className="app-container">
            <div className="content-wrapper">
                <div className="spectator-layout" style={{ maxWidth: 1200, margin: '0 auto', padding: '24px 60px 16px' }}>

                    {showFullscreenPrompt && (
                        <div style={{
                            position: 'fixed', inset: 0, zIndex: 100,
                            background: 'rgba(0,0,0,0.85)',
                            display: 'flex', flexDirection: 'column',
                            alignItems: 'center', justifyContent: 'center',
                            cursor: 'pointer',
                        }}
                        onClick={() => {
                            document.documentElement.requestFullscreen?.().catch(() => {});
                            setShowFullscreenPrompt(false);
                        }}>
                            <div style={{ fontSize: '5rem', marginBottom: 24 }}>📺</div>
                            <h1 className="hero-title" style={{ fontSize: '2.5rem', marginBottom: 12 }}>Spectator Mode</h1>
                            <p style={{ fontSize: '1.25rem', color: 'var(--text-secondary)', marginBottom: 32 }}>
                                Tap anywhere to enter fullscreen
                            </p>
                            <button className="btn btn-primary btn-glow" style={{ fontSize: '1.25rem', padding: '16px 48px' }}>
                                Enter Fullscreen
                            </button>
                            <button
                                className="btn btn-secondary mt-4"
                                onClick={(e) => { e.stopPropagation(); setShowFullscreenPrompt(false); }}
                                style={{ fontSize: '1rem' }}
                            >
                                Skip
                            </button>
                        </div>
                    )}

                    {(gameState === 'CONNECTING' || gameState === 'ERROR' || gameState === 'DISCONNECTED') && (
                        <div className="flex-1 flex flex-col items-center justify-center animate-in">
                            <div className="status-screen-icon mb-4" style={{ width: 80, height: 80, fontSize: 36 }}>
                                {gameState === 'CONNECTING' ? '📡' : gameState === 'ERROR' ? '⚠️' : '🔌'}
                            </div>
                            <h1 className="hero-title mb-2">
                                {gameState === 'CONNECTING' ? 'Connecting...' : gameState === 'ERROR' ? 'Connection Error' : roomClosedRef.current ? 'Disconnected' : 'Reconnecting...'}
                            </h1>
                            <p className="text-[--text-tertiary] text-lg">Room: {roomCode}</p>
                            {(gameState === 'CONNECTING' || (gameState === 'DISCONNECTED' && !roomClosedRef.current)) && (
                                <div className="flex gap-1.5 mt-6">
                                    {[0, 1, 2].map((i) => (
                                        <div key={i} className="w-2.5 h-2.5 bg-[--accent-primary] rounded-full animate-bounce"
                                            style={{ animationDelay: `${i * 0.15}s` }} />
                                    ))}
                                </div>
                            )}
                            {(gameState === 'ERROR' || gameState === 'DISCONNECTED') && (
                                <button
                                    onClick={() => { if (reconnectTimerRef.current) clearTimeout(reconnectTimerRef.current); setJoined(false); setRoomInput(''); setSearchParams({}); }}
                                    className="btn btn-secondary mt-6"
                                    style={{ fontSize: '1.125rem' }}
                                >
                                    Try Another Room
                                </button>
                            )}
                        </div>
                    )}

                    {gameState === 'LOBBY' && (
                        <div className="flex-1 flex flex-col items-center justify-center animate-in">
                            <h1 className="hero-title mb-8" style={{ fontSize: '3.5rem' }}>
                                {gameType === 'wmlt' ? 'Join the Game!' : 'Join the Quiz!'}
                            </h1>

                            <div className="flex items-center justify-center gap-12 mb-8">
                                <div className="flex flex-col items-center">
                                    <div className="qr-container mb-2">
                                        <QRCodeCanvas value={joinUrl} size={200} bgColor="white" fgColor="#000000" level="H" />
                                    </div>
                                    <p className="text-[--text-tertiary] text-sm">Scan with your phone</p>
                                </div>

                                <div className="text-[--text-tertiary] text-xl font-medium">or</div>

                                <div className="flex flex-col items-center">
                                    <div className="room-code mb-2" style={{ fontSize: '4rem' }}>{roomCode}</div>
                                    <p className="text-[--text-tertiary] text-lg">{displayUrl}</p>
                                </div>
                            </div>

                            <p className="text-2xl font-bold mb-4">
                                {playerCount} player{playerCount !== 1 ? 's' : ''}
                            </p>
                            {players.length > 0 && (
                                <div className="spectator-player-list" style={{ display: 'flex', flexWrap: 'wrap', justifyContent: 'center', gap: 12, maxWidth: 672 }}>
                                    {players.map((player, i) => (
                                        <div key={player.nickname} style={{ display: 'inline-flex', alignItems: 'center', gap: 10, padding: '10px 20px', borderRadius: 9999, background: 'var(--bg-secondary)' }}>
                                            <div
                                                style={{ width: 44, height: 44, minWidth: 44, borderRadius: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center', backgroundColor: AVATAR_COLORS[i % AVATAR_COLORS.length] }}
                                            >
                                                <span style={{ fontSize: '1.8rem', lineHeight: 1 }}>{player.avatar || player.nickname.slice(0, 2).toUpperCase()}</span>
                                            </div>
                                            <span style={{ fontSize: '1.25rem', fontWeight: 500 }}>{player.nickname}</span>
                                        </div>
                                    ))}
                                </div>
                            )}
                        </div>
                    )}

                    {gameState === 'QUESTION' && (question || currentStatement) && (
                        showBonusSplash ? (
                            <BonusSplash onComplete={() => setShowBonusSplash(false)} />
                        ) : (
                            <div className="flex-1 flex flex-col justify-center" style={{ minHeight: 0, overflow: 'hidden' }}>
                            <div className="py-4" style={{ flexShrink: 0 }}>
                                <div className="flex items-center justify-between mb-2">
                                    <span className="text-2xl font-bold text-[--text-tertiary]">
                                        {gameType === 'wmlt' ? 'Round' : 'Q'}{questionNumber}/{totalQuestions}
                                    </span>
                                    <div className="flex items-center gap-3">
                                        {isBonus && <span className="bonus-badge" style={{ fontSize: 16 }}>2X BONUS</span>}
                                        <span className={`font-extrabold tabular-nums text-3xl ${timeRemaining <= 5 ? 'timer-number-pulse' : ''}`}
                                        style={{ color: timeRemaining <= 5 ? 'var(--accent-danger)' : timeRemaining <= 10 ? 'var(--accent-warning)' : 'var(--accent-primary)' }}>
                                        {timeRemaining}s
                                    </span>
                                    </div>
                                </div>
                                <div className="question-timer-bar" style={{ height: 8 }}>
                                    <div
                                        className="question-timer-fill"
                                        style={{
                                            width: `${(timeRemaining / timeLimit) * 100}%`,
                                            background: timeRemaining <= 5 ? 'var(--accent-danger)' : timeRemaining <= 10 ? 'var(--accent-warning)' : 'var(--accent-primary)',
                                        }}
                                    />
                                </div>
                            </div>

                            {gameType === 'wmlt' && currentStatement ? (
                                <>
                                    <div className="question-card mb-4" style={{ padding: '48px', fontSize: '24px' }}>
                                        <p className="question-text" style={{ fontSize: '36px', fontWeight: 700, textAlign: 'center' }}>
                                            {currentStatement.text}
                                        </p>
                                    </div>
                                    {votePlayers.length > 0 && (
                                        <div style={{ display: 'flex', flexWrap: 'wrap', justifyContent: 'center', gap: 12, marginTop: 8 }}>
                                            {votePlayers.map((p, i) => (
                                                <div key={p.nickname} style={{
                                                    display: 'inline-flex', alignItems: 'center', gap: 10,
                                                    padding: '10px 20px', borderRadius: 9999,
                                                    background: 'var(--bg-secondary)',
                                                }}>
                                                    <div style={{
                                                        width: 40, height: 40, minWidth: 40, borderRadius: '50%',
                                                        display: 'flex', alignItems: 'center', justifyContent: 'center',
                                                        backgroundColor: AVATAR_COLORS[i % AVATAR_COLORS.length],
                                                    }}>
                                                        <span style={{ fontSize: '1.5rem', lineHeight: 1 }}>
                                                            {p.avatar || p.nickname.slice(0, 2).toUpperCase()}
                                                        </span>
                                                    </div>
                                                    <span style={{ fontSize: '1.125rem', fontWeight: 500 }}>{p.nickname}</span>
                                                </div>
                                            ))}
                                        </div>
                                    )}
                                </>
                            ) : question ? (
                                <>
                                    <div className={`question-card mb-4 ${question.image_url ? 'has-image' : ''}`}
                                        style={{ padding: '32px 48px', fontSize: '24px', ...(question.image_url ? { backgroundImage: `url(${API_URL}${question.image_url})` } : {}) }}>
                                        <p className="question-text" style={{ fontSize: '32px', fontWeight: 700 }}>{question.text}</p>
                                    </div>
                                    <div className={question.options.length === 2 ? 'answer-grid-tf' : 'answer-grid'} style={{ gap: '16px' }}>
                                        {question.options.map((opt, i) => (
                                            <div key={i} className={`answer-btn ${ANSWER_STYLES[i].className}`} style={{ height: 100, fontSize: 20, overflow: 'hidden' }}>
                                                <span className="text-5xl opacity-50 mr-4" style={{ flexShrink: 0 }}>{ANSWER_STYLES[i].shape}</span>
                                                <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{opt}</span>
                                            </div>
                                        ))}
                                    </div>
                                </>
                            ) : null}
                            </div>
                        )
                    )}

                    {gameState === 'LEADERBOARD' && (
                        wmltRoundResult ? (
                            /* WMLT: show vote bar chart, no points leaderboard */
                            <div className="flex-1 flex flex-col animate-in" style={{ minHeight: 0, overflow: 'hidden' }}>
                                <div className="text-center" style={{ flexShrink: 0, padding: '16px 0' }}>
                                    <p style={{ color: 'var(--text-tertiary)', fontSize: '1.2rem', marginBottom: 8 }}>Round {questionNumber} of {totalQuestions}</p>
                                    <div style={{ fontSize: '3rem', marginBottom: 4 }}>👑</div>
                                    {wmltRoundResult.winners.length > 1 ? (
                                        <>
                                            <h2 style={{ fontSize: '2.5rem', fontWeight: 800 }}>{wmltRoundResult.winners.join(' & ')}</h2>
                                            <p style={{ color: 'var(--text-secondary)', fontSize: '1.2rem' }}>Tied with {wmltRoundResult.round_podium[0]?.vote_count || 0} votes each!</p>
                                        </>
                                    ) : (
                                        <>
                                            <h2 style={{ fontSize: '2.5rem', fontWeight: 800 }}>{wmltRoundResult.winner}</h2>
                                            {wmltRoundResult.unanimous && <p style={{ color: 'var(--accent-success)', fontWeight: 600, fontSize: '1.2rem' }}>Unanimous!</p>}
                                        </>
                                    )}
                                    <p style={{ color: 'var(--text-tertiary)', fontSize: '1.1rem', marginTop: 8, fontStyle: 'italic' }}>"{wmltRoundResult.statement}"</p>
                                </div>
                                <div className="w-full max-w-3xl mx-auto" style={{ flex: 1, minHeight: 0, overflow: 'hidden' }}>
                                    <LeaderboardBarChart
                                        leaderboard={wmltRoundResult.round_podium.map(p => ({
                                            nickname: p.nickname,
                                            score: p.vote_count,
                                            avatar: p.avatar,
                                        }))}
                                        maxEntries={8}
                                        size="large"
                                    />
                                </div>
                                <p className="text-center" style={{ color: 'var(--text-tertiary)', fontSize: '1rem', padding: '12px 0' }}>Waiting for host...</p>
                            </div>
                        ) : (
                            /* Quiz: show leaderboard bar chart */
                            <div className="flex-1 flex flex-col justify-center animate-in" style={{ minHeight: 0, overflow: 'hidden' }}>
                                <div className="text-center" style={{ flexShrink: 0, padding: '16px 0' }}>
                                    <h1 className="hero-title mb-2" style={{ fontSize: '2.5rem' }}>Leaderboard</h1>
                                    <p className="text-[--text-tertiary] text-xl">After question {questionNumber} of {totalQuestions}</p>
                                </div>
                                <div className="w-full max-w-3xl mx-auto" style={{ flex: 1, minHeight: 0, overflow: 'hidden' }}>
                                    <LeaderboardBarChart leaderboard={leaderboard} maxEntries={8} size="large" />
                                </div>
                            </div>
                        )
                    )}

                    {gameState === 'PODIUM' && (
                        <div className="flex-1 flex flex-col items-center justify-center animate-in"
                             style={{ position: 'relative', overflow: 'hidden', minHeight: 0 }}>
                            <Fireworks duration={15000} maxRockets={4} />

                            <h1 className="hero-title text-center mb-4" style={{ position: 'relative', zIndex: 11, fontSize: '2.5rem' }}>Final Results</h1>

                            {podiumReveal >= 4 && leaderboard[0] && (
                                (() => {
                                    const topScore = leaderboard[0].score;
                                    const tiedCount = leaderboard.filter(p => p.score === topScore).length;
                                    return tiedCount > 1 ? (
                                        <div className="champion-label" style={{ position: 'relative', zIndex: 11, fontSize: 28 }}>
                                            <span className="gold-shimmer">{tiedCount === 2 ? "It's a Tie!" : `${tiedCount}-Way Tie!`}</span>
                                        </div>
                                    ) : (
                                        <div className="champion-label" style={{ position: 'relative', zIndex: 11, fontSize: 28 }}>
                                            <span className="crown-bounce" style={{ fontSize: 36 }}>&#x1F451;</span>
                                            <span className="gold-shimmer">{leaderboard[0].nickname} is the Champion!</span>
                                        </div>
                                    );
                                })()
                            )}

                            <div className="podium-container" style={{ gap: 16, padding: '16px 0', position: 'relative', zIndex: 11 }}>
                                {leaderboard[1] && (
                                    <div className={`podium-place podium-2 ${podiumReveal >= 2 ? '' : 'podium-hidden'}`}>
                                        <div className="w-14 h-14 rounded-full flex items-center justify-center mb-2" style={{ backgroundColor: '#C0C0C0' }}>
                                            <span style={{ fontSize: '2rem', lineHeight: 1 }}>{leaderboard[1].avatar || leaderboard[1].nickname.slice(0, 2).toUpperCase()}</span>
                                        </div>
                                        <p className="podium-name" style={{ fontSize: 18, maxWidth: 120 }}>{leaderboard[1].nickname}</p>
                                        <div className="podium-bar" style={{ width: 120, height: 100 }}>2</div>
                                        <p className="podium-score" style={{ fontSize: 16 }}><AnimatedNumber value={podiumReveal >= 2 ? leaderboard[1].score : 0} /></p>
                                    </div>
                                )}
                                {leaderboard[0] && (
                                    <div className={`podium-place podium-1 ${podiumReveal >= 3 ? '' : 'podium-hidden'} ${podiumReveal >= 4 && leaderboard.filter(p => p.score === leaderboard[0].score).length === 1 ? 'victory-glow' : ''}`}>
                                        {podiumReveal >= 4 && leaderboard.filter(p => p.score === leaderboard[0].score).length === 1 && <span className="crown-bounce" style={{ fontSize: 40, marginBottom: 4 }}>&#x1F451;</span>}
                                        <div className="w-16 h-16 rounded-full flex items-center justify-center mb-2" style={{ backgroundColor: '#FFD700' }}>
                                            <span style={{ fontSize: '2.5rem', lineHeight: 1 }}>{leaderboard[0].avatar || leaderboard[0].nickname.slice(0, 2).toUpperCase()}</span>
                                        </div>
                                        <p className="podium-name" style={{ fontSize: 18, maxWidth: 120 }}>{leaderboard[0].nickname}</p>
                                        <div className="podium-bar" style={{ width: 120, height: 140 }}>1</div>
                                        <p className="podium-score" style={{ fontSize: 16 }}><AnimatedNumber value={podiumReveal >= 3 ? leaderboard[0].score : 0} /></p>
                                    </div>
                                )}
                                {leaderboard[2] && (
                                    <div className={`podium-place podium-3 ${podiumReveal >= 1 ? '' : 'podium-hidden'}`}>
                                        <div className="w-14 h-14 rounded-full flex items-center justify-center mb-2" style={{ backgroundColor: '#CD7F32' }}>
                                            <span style={{ fontSize: '2rem', lineHeight: 1 }}>{leaderboard[2].avatar || leaderboard[2].nickname.slice(0, 2).toUpperCase()}</span>
                                        </div>
                                        <p className="podium-name" style={{ fontSize: 18, maxWidth: 120 }}>{leaderboard[2].nickname}</p>
                                        <div className="podium-bar" style={{ width: 120, height: 70 }}>3</div>
                                        <p className="podium-score" style={{ fontSize: 16 }}><AnimatedNumber value={podiumReveal >= 1 ? leaderboard[2].score : 0} /></p>
                                    </div>
                                )}
                            </div>

                            {podiumReveal >= 4 && superlatives.length > 0 && (
                                <div className="w-full mt-6" style={{ position: 'relative', zIndex: 11, maxWidth: 700 }}>
                                    <h3 className="text-2xl font-extrabold text-center mb-3">Awards</h3>
                                    <div style={{ display: 'flex', justifyContent: 'center', gap: 20, flexWrap: 'wrap' }}>
                                        {superlatives.map((s) => (
                                            <div key={s.title} style={{ textAlign: 'center', padding: '12px 16px', background: 'var(--surface-secondary, rgba(255,255,255,0.05))', borderRadius: 12, minWidth: 130 }}>
                                                <div style={{ fontSize: '2rem' }}>{s.icon}</div>
                                                <div style={{ fontWeight: 700, fontSize: '0.85rem', marginTop: 4 }}>{s.title}</div>
                                                <div style={{ fontSize: '1.3rem', marginTop: 4 }}>{s.avatar || '👤'}</div>
                                                <div style={{ fontWeight: 600 }}>{s.winner}</div>
                                                <div style={{ color: 'var(--text-tertiary)', fontSize: '0.75rem' }}>{s.detail}</div>
                                            </div>
                                        ))}
                                    </div>
                                </div>
                            )}

                            {podiumReveal >= 4 && teamLeaderboard.some(t => t.members > 1) && (
                                <div className="w-full mt-4" style={{ position: 'relative', zIndex: 11, maxWidth: 600 }}>
                                    <h3 className="text-2xl font-extrabold text-center mb-3">Team Standings</h3>
                                    <div className="podium-container" style={{ gap: 16 }}>
                                        {teamLeaderboard[1] && (
                                            <div className="podium-place podium-2">
                                                <p className="podium-name" style={{ fontSize: 18, maxWidth: 120 }}>{teamLeaderboard[1].team}</p>
                                                {teamLeaderboard[1].members > 1 && (
                                                    <p className="text-xs text-[--text-tertiary]">{teamLeaderboard[1].members} members</p>
                                                )}
                                                <div className="podium-bar" style={{ width: 120, height: 80 }}>2</div>
                                                <p className="podium-score" style={{ fontSize: 16 }}><AnimatedNumber value={teamLeaderboard[1].score} /></p>
                                            </div>
                                        )}
                                        {teamLeaderboard[0] && (
                                            <div className="podium-place podium-1 victory-glow">
                                                <p className="podium-name" style={{ fontSize: 18, maxWidth: 120 }}>{teamLeaderboard[0].team}</p>
                                                {teamLeaderboard[0].members > 1 && (
                                                    <p className="text-xs text-[--text-tertiary]">{teamLeaderboard[0].members} members</p>
                                                )}
                                                <div className="podium-bar" style={{ width: 120, height: 110 }}>1</div>
                                                <p className="podium-score" style={{ fontSize: 16 }}><AnimatedNumber value={teamLeaderboard[0].score} /></p>
                                            </div>
                                        )}
                                        {teamLeaderboard[2] && (
                                            <div className="podium-place podium-3">
                                                <p className="podium-name" style={{ fontSize: 18, maxWidth: 120 }}>{teamLeaderboard[2].team}</p>
                                                {teamLeaderboard[2].members > 1 && (
                                                    <p className="text-xs text-[--text-tertiary]">{teamLeaderboard[2].members} members</p>
                                                )}
                                                <div className="podium-bar" style={{ width: 120, height: 50 }}>3</div>
                                                <p className="podium-score" style={{ fontSize: 16 }}><AnimatedNumber value={teamLeaderboard[2].score} /></p>
                                            </div>
                                        )}
                                    </div>
                                </div>
                            )}
                        </div>
                    )}
                </div>
            </div>
        </div>
        </div>
    );
}
