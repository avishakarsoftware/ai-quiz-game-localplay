import { useState, useEffect, useRef } from 'react';
import { useSearchParams, useParams } from 'react-router-dom';
import { QRCodeCanvas } from 'qrcode.react';
import { WS_URL } from '../config';
import { type LeaderboardEntry, type TeamLeaderboardEntry, type PlayerInfo, type GameType, type DrawOperation, type HousieWinner, type MusicalChairsState, type BluffState, type TwoTruthsState, ANSWER_STYLES } from '../types';
import AnimatedNumber from '../components/AnimatedNumber';
import Fireworks from '../components/Fireworks';
import LeaderboardBarChart from '../components/LeaderboardBarChart';
import { AVATAR_COLORS } from '../components/LeaderboardBarChart.constants';
import { soundManager } from '../utils/sound';
import BonusSplash from '../components/BonusSplash';
import PlayerChip from '../components/PlayerChip';
import Avatar from '../components/Avatar';
import DrawingCanvas from '../components/DrawingCanvas';
import GameImage from '../components/media/GameImage';
import { HousieCalledBoard, HousieWinners } from '../components/HousieBoard';
import { BingoCalledList, BingoCallOverlay } from '../components/BingoBoard';
import { mediaUrl } from '../utils/media';
import { apiUrl } from '../utils/api';
import { returnToHostApp } from '../utils/hostAppReturn';
import MusicalChairsVisualizer from '../components/musical-chairs/MusicalChairsVisualizer';
import BluffTable from '../components/BluffTable';
import TwoTruthsGame from '../components/TwoTruthsGame';
import '../cast.d.ts';
import { CAST_NAMESPACE, CAST_RECEIVER_SDK_URL } from '../cast-constants';

interface SpectatorQuestion {
    id: number;
    text: string;
    options: string[];
    image_url?: string;
}

function normalizeRoomCode(value: string | null | undefined): string {
    return String(value || '').toUpperCase().replace(/[^A-Z0-9]/g, '').slice(0, 6);
}

export default function SpectatorPage() {
    const [searchParams, setSearchParams] = useSearchParams();
    const { code: routeCode } = useParams<{ code?: string }>();
    const roomFromUrl = normalizeRoomCode(routeCode || searchParams.get('room') || '');
    const [roomCode, setRoomCode] = useState(roomFromUrl);
    const [roomInput, setRoomInput] = useState('');
    const [joined, setJoined] = useState(!!roomFromUrl);
    const [gameState, setGameState] = useState(roomFromUrl ? 'CONNECTING' : 'LOBBY');
    const hostAppMode = searchParams.get('embed') === '1' || searchParams.has('launch_token') || searchParams.has('session_id');
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
    const [connectionError, setConnectionError] = useState('');
    const [hostAppReturnUrl, setHostAppReturnUrl] = useState('');
    const [launchResolving, setLaunchResolving] = useState(() => searchParams.has('launch_token'));

    useEffect(() => {
        const launchToken = searchParams.get('launch_token');
        if (!launchToken) return;
        let cancelled = false;
        setLaunchResolving(true);
        (async () => {
            try {
                const res = await fetch(apiUrl(`/integrations/revelry/launch-token/resolve?scope=spectator&launch_token=${encodeURIComponent(launchToken)}`));
                if (!res.ok) throw new Error('Launch token rejected');
                const data = await res.json();
                if (!data.room_code) throw new Error('Launch token missing room code');
                if (!cancelled && data.room_code) {
                    setRoomCode(data.room_code);
                    setHostAppReturnUrl(data.launch_context?.return_url || data.return_url || '');
                    setJoined(true);
                    setConnectionError('');
                    setGameState('CONNECTING');
                }
            } catch {
                if (!cancelled) {
                    setConnectionError('This spectator link expired. Open it from Revelry again.');
                    setGameState('ERROR');
                }
            } finally {
                if (!cancelled) setLaunchResolving(false);
            }
        })();
        return () => { cancelled = true; };
    }, [searchParams]);
    const [drawingDrawer, setDrawingDrawer] = useState('');
    const [drawingOps, setDrawingOps] = useState<DrawOperation[]>([]);
    const [correctGuessers, setCorrectGuessers] = useState<string[]>([]);
    const [guessLog, setGuessLog] = useState<{ nickname: string; guess: string; correct?: boolean }[]>([]);
    const [drawingRoundPrompt, setDrawingRoundPrompt] = useState('');
    const [housieCalled, setHousieCalled] = useState<Array<{ value: number | string; display: string }>>([]);
    const [housieLatest, setHousieLatest] = useState<{ value: number | string; display: string } | null>(null);
    const [housieWinners, setHousieWinners] = useState<HousieWinner[]>([]);
    const [housieCallFlash, setHousieCallFlash] = useState<{ item: { value?: number | string; display: string; kind?: string; image_url?: string; alt_text?: string }; key: number } | null>(null);
    const [housieAnnouncement, setHousieAnnouncement] = useState<{ text: string; key: number } | null>(null);
    const [musicalChairsState, setMusicalChairsState] = useState<MusicalChairsState | null>(null);
    const [bluffState, setBluffState] = useState<BluffState | null>(null);
    const [twoTruthsState, setTwoTruthsState] = useState<TwoTruthsState | null>(null);
    const wsRef = useRef<WebSocket | null>(null);
    const reconnectDelayRef = useRef(2000);
    const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
    const roomClosedRef = useRef(false);
    const [roomClosed, setRoomClosed] = useState(false);
    const mountedRef = useRef(true);
    const terminalConnectionErrorRef = useRef(false);

    useEffect(() => {
        mountedRef.current = true;
        return () => {
            mountedRef.current = false;
        };
    }, []);

    // In Capacitor, window.location.origin is capacitor://localhost — use the web URL
    const isCapacitor = window.location.protocol === 'capacitor:' || (window.location.hostname === 'localhost' && !window.location.port);
    const baseUrl = isCapacitor
        ? (import.meta.env.VITE_WEB_URL || 'https://games.revelryapp.me/')
        : `${window.location.origin}${import.meta.env.BASE_URL}`;
    const joinUrl = `${baseUrl}join?room=${roomCode}`;
    const displayUrl = `${new URL(joinUrl).host}${new URL(joinUrl).pathname}`;

    const handleJoinRoom = () => {
        const code = roomInput.trim().toUpperCase();
        if (code.length < 4) return;
        setRoomCode(code);
        setJoined(true);
        setConnectionError('');
        terminalConnectionErrorRef.current = false;
        setGameState('CONNECTING');
        setSearchParams({ room: code });
    };

    const handleReturnToHostApp = () => {
        if (hostAppReturnUrl) {
            returnToHostApp(hostAppReturnUrl);
        }
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
                            setConnectionError('');
                            terminalConnectionErrorRef.current = false;
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
    const connectWsImpl = () => {
        if (!joined || !roomCode) return;
        setConnectionError('');
        terminalConnectionErrorRef.current = false;
        const clientId = `spectator-${Date.now()}`;
        const ws = new WebSocket(`${WS_URL}/ws/${roomCode}/${clientId}?spectator=true`);
        wsRef.current = ws;

        ws.onopen = () => {
            reconnectDelayRef.current = 2000; // Reset backoff on success
        };

        ws.onmessage = (event) => {
            // eslint-disable-next-line @typescript-eslint/no-explicit-any
            let msg: any;
            try { msg = JSON.parse(event.data); } catch { return; }
            if (msg.type === 'PING') return; // heartbeat — no action needed
            if (msg.type === 'ERROR') {
                terminalConnectionErrorRef.current = true;
                setConnectionError(String(msg.message || 'Unable to connect to this room.'));
                setGameState('ERROR');
                return;
            }
            if (msg.type === 'SPECTATOR_SYNC') {
                setPlayers(msg.players || []);
                setPlayerCount(msg.player_count);
                setQuestionNumber(msg.question_number);
                setTotalQuestions(msg.total_questions);
                setLeaderboard(msg.leaderboard || []);
                if (msg.game_type) setGameType(msg.game_type);
                if ((msg.game_type === 'housie' || msg.game_type === 'bingo') && msg.bingo) {
                    setHousieCalled(msg.bingo.called_items || []);
                    setHousieLatest(msg.bingo.latest_item || null);
                    setHousieWinners(msg.bingo.winners || []);
                    setGameState(String(msg.state || 'BINGO_CALLING'));
                    return;
                }
                if (msg.game_type === 'musical_chairs' && msg.musical_chairs) {
                    setMusicalChairsState(msg.musical_chairs);
                    setGameState('MUSICAL_CHAIRS');
                    return;
                }
                if (msg.game_type === 'bluff' && msg.bluff) {
                    setBluffState(msg.bluff);
                    setGameState('BLUFF');
                    return;
                }
                if (msg.game_type === 'two_truths' && msg.two_truths) {
                    setTwoTruthsState(msg.two_truths);
                    setGameState('TWO_TRUTHS');
                    return;
                }
                // Handle mid-question sync
                if (msg.state === 'QUESTION') {
                    if (msg.game_type === 'drawing') {
                        setDrawingDrawer(msg.drawer || '');
                        setDrawingOps(msg.drawing_ops || []);
                        setCorrectGuessers(msg.correct_guessers || []);
                        setGuessLog(msg.guess_log || []);
                    } else if (msg.game_type === 'wmlt' && msg.statement) {
                        setCurrentStatement(msg.statement);
                        setVotePlayers(msg.players || []);
                    } else if (msg.question) {
                        setQuestion(msg.question);
                    }
                    setTimeLimit(msg.time_limit);
                    setTimeRemaining(msg.time_remaining ?? msg.time_limit);
                    setIsBonus(msg.is_bonus || false);
                }
                setGameState(String(msg.state || 'LOBBY'));
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
            else if (msg.type === 'GAME_STARTING') {
                if (msg.game_type === 'housie' || msg.game_type === 'bingo') {
                    setGameType(msg.game_type);
                    setGameState('BINGO_CALLING');
                } else if (msg.game_type === 'musical_chairs') {
                    setGameType('musical_chairs');
                    setGameState('MUSICAL_CHAIRS');
                } else if (msg.game_type === 'two_truths') {
                    setGameType('two_truths');
                    setGameState('TWO_TRUTHS');
                }
                else setGameState('INTRO');
            }
            else if (msg.type === 'BINGO_SYNC') {
                setGameType(msg.game_type || 'housie');
                setHousieCalled(msg.bingo?.called_items || []);
                setHousieLatest(msg.bingo?.latest_item || null);
                setHousieWinners(msg.bingo?.winners || []);
                setGameState('BINGO_CALLING');
            }
            else if (msg.type === 'BINGO_CALL') {
                setGameType(msg.game_type || 'housie');
                setHousieCalled(msg.called_items || []);
                setHousieLatest(msg.item || null);
                setHousieCallFlash({ item: { ...msg.item, display: String(msg.item?.display || '') }, key: Date.now() });
                setGameState('BINGO_CALLING');
                soundManager.play('timerTick');
            }
            else if (msg.type === 'BINGO_CLAIM_ACCEPTED') {
                setHousieWinners(msg.winners || []);
                setLeaderboard(msg.leaderboard || []);
                const winner = msg.winner as HousieWinner | undefined;
                if (winner) setHousieAnnouncement({ text: `${winner.nickname} won ${winner.label}${winner.winning_number ? ` on ${winner.winning_number}` : ''}`, key: Date.now() });
                soundManager.play('fanfare');
            }
            else if (msg.type === 'BINGO_COMPLETE') {
                setHousieWinners(msg.winners || []);
                setLeaderboard(msg.leaderboard || []);
            }
            else if (msg.type === 'MC_SYNC' || msg.type === 'MC_ROUND_START' || msg.type === 'MC_MUSIC_STOP' || msg.type === 'MC_GRAB_COUNT' || msg.type === 'MC_ROUND_OVER') {
                setGameType('musical_chairs');
                setMusicalChairsState(msg.musical_chairs || null);
                setGameState('MUSICAL_CHAIRS');
            }
            else if (msg.type === 'BLUFF_SYNC') {
                setGameType('bluff');
                setBluffState(msg.bluff || null);
                setGameState('BLUFF');
            }
            else if (msg.type === 'TT_SYNC') {
                setGameType('two_truths');
                setTwoTruthsState(msg.two_truths || null);
                setLeaderboard(msg.leaderboard || []);
                setGameState('TWO_TRUTHS');
            }
            else if (msg.type === 'MC_WINNER') {
                setGameType('musical_chairs');
            }
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
                } else if (msg.game_type === 'drawing') {
                    setDrawingDrawer(msg.drawer || '');
                    setDrawingOps(msg.drawing_ops || []);
                    setCorrectGuessers(msg.correct_guessers || []);
                    setGuessLog(msg.guess_log || []);
                } else {
                    setQuestion(msg.question);
                }
                if (msg.is_bonus) setShowBonusSplash(true);
                setGameState('QUESTION');
            }
            else if (msg.type === 'TIMER') setTimeRemaining(msg.remaining);
            else if (msg.type === 'DRAW_OP') {
                const op = msg.op as DrawOperation;
                if (op.kind === 'clear') setDrawingOps([]);
                else if (op.kind === 'undo') setDrawingOps(prev => prev.slice(0, -1));
                else setDrawingOps(prev => [...prev, op].slice(-500));
            }
            else if (msg.type === 'GUESS_ACCEPTED') {
                setCorrectGuessers(msg.correct_guessers || []);
            }
            else if (msg.type === 'GUESS_LOG') {
                setGuessLog(msg.guess_log || []);
            }
            else if (msg.type === 'QUESTION_OVER') {
                setLeaderboard(msg.leaderboard);
                if (msg.game_type === 'drawing') {
                    setDrawingRoundPrompt(msg.prompt || '');
                    setCorrectGuessers(msg.correct_guessers || []);
                    setWmltRoundResult(null);
                } else if (msg.game_type === 'wmlt') {
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
                setRoomClosed(true);
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
                setDrawingDrawer('');
                setDrawingOps([]);
                setCorrectGuessers([]);
                setGuessLog([]);
                setDrawingRoundPrompt('');
                setHousieCalled([]);
                setHousieLatest(null);
                setHousieWinners([]);
                setMusicalChairsState(null);
                if (msg.game_type) setGameType(msg.game_type);
                setGameState('LOBBY');
            }
        };

        ws.onerror = () => {
            setConnectionError('Unable to connect to the room.');
            setGameState('ERROR');
        };
        ws.onclose = () => {
            wsRef.current = null;
            if (roomClosedRef.current || !mountedRef.current || terminalConnectionErrorRef.current) return;
            setGameState('DISCONNECTED');
            // Exponential backoff: 2s, 4s, 8s, 16s, capped at 30s
            const delay = reconnectDelayRef.current;
            reconnectDelayRef.current = Math.min(delay * 2, 30000);
            reconnectTimerRef.current = setTimeout(() => connectWs.current(), delay);
        };
    };

    useEffect(() => { connectWs.current = connectWsImpl; });

    useEffect(() => {
        if (!joined || !roomCode) return;
        roomClosedRef.current = false;
        setRoomClosed(false);
        reconnectDelayRef.current = 2000;
        connectWs.current();
        return () => {
            if (reconnectTimerRef.current) clearTimeout(reconnectTimerRef.current);
            wsRef.current?.close();
            wsRef.current = null;
        };
    }, [joined, roomCode]);

    // Fullscreen is triggered by user gesture (see overlay below)

    // Staggered podium reveal
    useEffect(() => {
        if (gameState !== 'PODIUM') return;
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

    if (hostAppMode && launchResolving) {
        return (
            <div className="spectator-root">
                <div className="app-container">
                    <div className="content-wrapper" style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '40px 60px' }}>
                        <div className="animate-in text-center" style={{ maxWidth: 500, width: '100%' }}>
                            <div className="hero-icon mb-4" style={{ background: 'none', boxShadow: 'none', marginLeft: 'auto', marginRight: 'auto' }}>
                                <img src={`${import.meta.env.BASE_URL}icons/icon-192.png`} alt="Revelry Games" style={{ width: '100%', height: '100%', borderRadius: '20px' }} />
                            </div>
                            <h1 className="hero-title" style={{ fontSize: '3rem', marginBottom: 8 }}>Opening TV view...</h1>
                            <p className="text-[--text-tertiary]" style={{ fontSize: '1.25rem' }}>
                                Checking this Revelry game link.
                            </p>
                        </div>
                    </div>
                </div>
            </div>
        );
    }

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
                                {gameState === 'CONNECTING' ? 'Connecting...' : gameState === 'ERROR' ? 'Connection Error' : roomClosed ? 'Disconnected' : 'Reconnecting...'}
                            </h1>
                            <p className="text-[--text-tertiary] text-lg">{connectionError || `Room: ${roomCode}`}</p>
                            {(gameState === 'CONNECTING' || (gameState === 'DISCONNECTED' && !roomClosed)) && (
                                <div className="flex gap-1.5 mt-6">
                                    {[0, 1, 2].map((i) => (
                                        <div key={i} className="w-2.5 h-2.5 bg-[--accent-primary] rounded-full animate-bounce"
                                            style={{ animationDelay: `${i * 0.15}s` }} />
                                    ))}
                                </div>
                            )}
                            {(gameState === 'ERROR' || gameState === 'DISCONNECTED') && (
                                hostAppMode && hostAppReturnUrl ? (
                                    <button
                                        onClick={handleReturnToHostApp}
                                        className="btn btn-secondary mt-6"
                                        style={{ fontSize: '1.125rem' }}
                                    >
                                        Back to Revelry Games
                                    </button>
                                ) : (
                                    <button
                                        onClick={() => {
                                            if (reconnectTimerRef.current) clearTimeout(reconnectTimerRef.current);
                                            terminalConnectionErrorRef.current = false;
                                            setConnectionError('');
                                            setJoined(false);
                                            setRoomInput('');
                                            setSearchParams({});
                                        }}
                                        className="btn btn-secondary mt-6"
                                        style={{ fontSize: '1.125rem' }}
                                    >
                                        Try Another Room
                                    </button>
                                )
                            )}
                        </div>
                    )}

                    {gameState === 'LOBBY' && (
                        <div className="flex-1 flex flex-col items-center justify-center animate-in">
                            <h1 className="hero-title mb-8" style={{ fontSize: '3.5rem' }}>
                                {gameType === 'drawing' ? 'Join the Drawing Game!' : gameType === 'wmlt' ? 'Join the Game!' : 'Join the Quiz!'}
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
                                        <PlayerChip
                                            key={player.nickname}
                                            player={player}
                                            style={{ animationDelay: `${i * 0.05}s` }}
                                        />
                                    ))}
                                </div>
                            )}
                        </div>
                    )}

                    {gameState === 'INTRO' && (
                        <div className="intro-screen animate-in">
                            <div className="intro-kicker">Room {roomCode}</div>
                            <h1 className="intro-title">{gameType === 'drawing' ? 'Draw Incoming' : gameType === 'wmlt' ? 'Round Incoming' : 'Quiz Incoming'}</h1>
                            <div className="intro-count" aria-label="Starting soon">3</div>
                        </div>
                    )}

                    {gameState === 'BINGO_CALLING' && (
                        <div className="flex-1 flex flex-col justify-center animate-in">
                            {housieCallFlash && (gameType === 'bingo'
                                ? <BingoCallOverlay key={housieCallFlash.key} item={housieCallFlash.item} />
                                : <div key={housieCallFlash.key} className="housie-call-overlay">{housieCallFlash.item.display}</div>)}
                            {housieAnnouncement && (
                                <div key={housieAnnouncement.key} className="housie-win-overlay">
                                    <div className="housie-confetti" aria-hidden="true">{Array.from({ length: 26 }, (_, index) => <i key={index} />)}</div>
                                    <p>{housieAnnouncement.text}</p>
                                </div>
                            )}
                            <div className="text-center mb-8">
                                <p className="text-[--text-tertiary] text-xl">{gameType === 'bingo' ? 'Bingo' : 'Housie'}</p>
                                <h1 className="hero-title" style={{ fontSize: '5rem' }}>{housieLatest ? housieLatest.display : 'Waiting for first call'}</h1>
                                <p className="text-[--text-secondary] text-2xl">{housieCalled.length} {gameType === 'bingo' ? 'items' : 'numbers'} called</p>
                            </div>
                            <div className="card mb-6">
                                {gameType === 'bingo' ? (
                                    <BingoCalledList items={housieCalled} />
                                ) : (
                                    <HousieCalledBoard
                                        calledValues={new Set(housieCalled.map((item) => String(item.value)))}
                                        latestValue={housieLatest?.value}
                                    />
                                )}
                            </div>
                            <div className="card">
                                <h2 className="font-extrabold text-2xl mb-4">Winners</h2>
                                <HousieWinners winners={housieWinners} />
                            </div>
                        </div>
                    )}

                    {gameState === 'MUSICAL_CHAIRS' && (
                        <div className="flex-1 flex flex-col justify-center animate-in">
                            <div className="text-center mb-8">
                                <p className="text-[--text-tertiary] text-xl">Musical Chairs</p>
                                <h1 className="hero-title" style={{ fontSize: '4rem' }}>{musicalChairsState?.game_title || 'Musical Chairs'}</h1>
                                <p className="text-[--text-secondary] text-2xl">
                                    Round {musicalChairsState?.round_number || 0} of {musicalChairsState?.total_rounds || '-'} · {musicalChairsState?.active_players.length || 0} players standing
                                </p>
                                <p className="text-[--text-tertiary] text-lg mt-2">
                                    {musicalChairsState?.gameplay_mode === 'physical' ? 'Physical chairs mode' : 'Phone tap mode'}
                                </p>
                            </div>
                            <div style={{ maxWidth: 560, width: '100%', margin: '0 auto 28px' }}>
                                <MusicalChairsVisualizer
                                    players={musicalChairsState?.active_players || []}
                                    intensity={musicalChairsState?.intensity || 0.35}
                                    phase={musicalChairsState?.phase || gameState}
                                />
                            </div>
                            <div className="mc-status-card" style={{ maxWidth: 720, width: '100%', margin: '0 auto' }}>
                                {musicalChairsState?.phase === 'MC_MUSIC' && <h2>Music is playing</h2>}
                                {musicalChairsState?.phase === 'MC_GRAB' && <h2>Grab a chair: {musicalChairsState.grabbed}/{musicalChairsState.active_players.length}</h2>}
                                {musicalChairsState?.phase === 'MC_PHYSICAL_ELIMINATION' && <h2>Find a real chair!</h2>}
                                {(!musicalChairsState || musicalChairsState.phase === 'MC_BETWEEN_ROUNDS') && <h2>Waiting for the host</h2>}
                                {musicalChairsState?.phase === 'MC_REVEAL' && (
                                    <h2>{musicalChairsState.eliminated_players[musicalChairsState.eliminated_players.length - 1]?.nickname || 'Someone'} is out</h2>
                                )}
                                <p>{musicalChairsState?.chairs || 0} chair{musicalChairsState?.chairs === 1 ? '' : 's'} available</p>
                            </div>
                            {musicalChairsState?.active_players.length ? (
                                <div className="mc-player-list" style={{ justifyContent: 'center', marginTop: 24 }}>
                                    {musicalChairsState.active_players.map((player) => (
                                        <span key={player.nickname} className="mc-player-chip">{player.avatar || '🎵'} {player.nickname}</span>
                                    ))}
                                </div>
                            ) : null}
                        </div>
                    )}

                    {gameState === 'BLUFF' && (
                        <BluffTable state={bluffState} controls="spectator" />
                    )}

                    {gameState === 'TWO_TRUTHS' && (
                        <TwoTruthsGame state={twoTruthsState} controls="spectator" />
                    )}

                    {gameState === 'QUESTION' && (question || currentStatement || gameType === 'drawing') && (
                        showBonusSplash ? (
                            <BonusSplash onComplete={() => setShowBonusSplash(false)} />
                        ) : (
                            <div className="flex-1 flex flex-col justify-center" style={{ minHeight: 0, overflow: 'hidden' }}>
                            <div className="py-4" style={{ flexShrink: 0 }}>
                                <div className="flex items-center justify-between mb-2">
                                    <span className="text-2xl font-bold text-[--text-tertiary]">
                                        {gameType === 'wmlt' || gameType === 'drawing' ? 'Round' : 'Q'}{questionNumber}/{totalQuestions}
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

                            {gameType === 'drawing' ? (
                                <>
                                    <div className="text-center mb-4">
                                        <p className="text-[--text-tertiary] text-xl">Drawing now</p>
                                        <h2 className="text-4xl font-extrabold">{drawingDrawer}</h2>
                                        <p className="text-[--accent-success] text-lg mt-2">{correctGuessers.length} correct guess{correctGuessers.length === 1 ? '' : 'es'}</p>
                                    </div>
                                    <DrawingCanvas ops={drawingOps} height={Math.min(560, Math.max(380, window.innerHeight * 0.58))} />
                                    {guessLog.length > 0 && (
                                        <div className="text-center text-[--text-tertiary] text-lg mt-4">
                                            {guessLog.slice(-4).map((item, index) => (
                                                <span key={`${item.nickname}-${item.guess}-${index}`} style={{ margin: '0 10px' }}>
                                                    {item.nickname}: {item.guess}
                                                </span>
                                            ))}
                                        </div>
                                    )}
                                </>
                            ) : gameType === 'wmlt' && currentStatement ? (
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
                                        style={{ padding: '32px 48px', fontSize: '24px' }}>
                                        {question.image_url && (
                                            <GameImage src={mediaUrl(question.image_url)} alt={question.text} mode="tv" />
                                        )}
                                        <p className="question-text" style={{ fontSize: '32px', fontWeight: 700 }}>{question.text}</p>
                                    </div>
                                    <div className={question.options.length === 2 ? 'answer-grid-tf' : 'answer-grid'} style={{ gap: '16px' }}>
                                        {question.options.map((opt, i) => (
                                            <div key={i} className={`answer-btn ${ANSWER_STYLES[i].className}`} style={{ height: 100, fontSize: 20, overflow: 'hidden' }}>
                                                <span className="answer-label">{String.fromCharCode(65 + i)}</span>
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
                        gameType === 'drawing' ? (
                            <div className="flex-1 flex flex-col animate-in" style={{ minHeight: 0, overflow: 'hidden' }}>
                                <div className="text-center" style={{ flexShrink: 0, padding: '16px 0' }}>
                                    <p style={{ color: 'var(--text-tertiary)', fontSize: '1.2rem', marginBottom: 8 }}>Round {questionNumber} of {totalQuestions}</p>
                                    <div style={{ fontSize: '3rem', marginBottom: 4 }}>🎨</div>
                                    <h2 style={{ fontSize: '2.8rem', fontWeight: 800 }}>{drawingRoundPrompt}</h2>
                                    <p style={{ color: 'var(--text-secondary)', fontSize: '1.2rem' }}>
                                        {correctGuessers.length ? `${correctGuessers.join(', ')} guessed it` : 'No correct guesses'}
                                    </p>
                                </div>
                                <div className="w-full max-w-3xl mx-auto" style={{ flex: 1, minHeight: 0, overflow: 'hidden' }}>
                                    <LeaderboardBarChart leaderboard={leaderboard} maxEntries={8} size="large" />
                                </div>
                                <p className="text-center" style={{ color: 'var(--text-tertiary)', fontSize: '1rem', padding: '12px 0' }}>Waiting for host...</p>
                            </div>
                        ) : wmltRoundResult ? (
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
                                        <div className="mb-2"><Avatar player={leaderboard[1]} size={56} decorative /></div>
                                        <p className="podium-name" style={{ fontSize: 18, maxWidth: 120 }}>{leaderboard[1].nickname}</p>
                                        <div className="podium-bar" style={{ width: 120, height: 100 }}>2</div>
                                        <p className="podium-score" style={{ fontSize: 16 }}><AnimatedNumber value={podiumReveal >= 2 ? leaderboard[1].score : 0} /></p>
                                    </div>
                                )}
                                {leaderboard[0] && (
                                    <div className={`podium-place podium-1 ${podiumReveal >= 3 ? '' : 'podium-hidden'} ${podiumReveal >= 4 && leaderboard.filter(p => p.score === leaderboard[0].score).length === 1 ? 'victory-glow' : ''}`}>
                                        {podiumReveal >= 4 && leaderboard.filter(p => p.score === leaderboard[0].score).length === 1 && <span className="crown-bounce" style={{ fontSize: 40, marginBottom: 4 }}>&#x1F451;</span>}
                                        <div className="mb-2"><Avatar player={leaderboard[0]} size={68} you decorative /></div>
                                        <p className="podium-name" style={{ fontSize: 18, maxWidth: 120 }}>{leaderboard[0].nickname}</p>
                                        <div className="podium-bar" style={{ width: 120, height: 140 }}>1</div>
                                        <p className="podium-score" style={{ fontSize: 16 }}><AnimatedNumber value={podiumReveal >= 3 ? leaderboard[0].score : 0} /></p>
                                    </div>
                                )}
                                {leaderboard[2] && (
                                    <div className={`podium-place podium-3 ${podiumReveal >= 1 ? '' : 'podium-hidden'}`}>
                                        <div className="mb-2"><Avatar player={leaderboard[2]} size={56} decorative /></div>
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
                                            <div key={s.title} style={{ textAlign: 'center', padding: '12px 16px', background: 'var(--paper)', border: '1px solid var(--rule)', borderRadius: 8, minWidth: 130 }}>
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
