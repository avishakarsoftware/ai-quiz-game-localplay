import { useState, useRef, useEffect } from 'react';
import { useSearchParams, useParams } from 'react-router-dom';
import { WS_URL } from '../config';
import { type GameType, type LeaderboardEntry, type TeamLeaderboardEntry, type PlayerInfo, type PowerUps, type DrawOperation, type HousiePattern, type HousieTicket, type HousieWinner, type MusicalChairsState, type BluffState, type TwoTruthsState, type StoryChainState, type CommonGroundState, ANSWER_STYLES, AVATAR_EMOJIS } from '../types';
import { soundManager } from '../utils/sound';
import { track } from '../utils/analytics';
import AnimatedNumber from '../components/AnimatedNumber';
import Fireworks from '../components/Fireworks';
import BonusSplash from '../components/BonusSplash';
import LeaderboardBarChart from '../components/LeaderboardBarChart';
import { AVATAR_COLORS } from '../components/LeaderboardBarChart.constants';
import PlayerChip from '../components/PlayerChip';
import Avatar from '../components/Avatar';
import DrawingCanvas from '../components/DrawingCanvas';
import GameImage from '../components/media/GameImage';
import { HousieClaimButtons, HousieTicketGrid, HousieWinners } from '../components/HousieBoard';
import { BingoCallOverlay, BingoCardGrid, BingoCalledList, BingoClaimButtons } from '../components/BingoBoard';
import { mediaUrl } from '../utils/media';
import { apiUrl } from '../utils/api';
import { returnToHostApp } from '../utils/hostAppReturn';
import MusicalChairsPlayer from '../components/player/MusicalChairsPlayer';
import BluffTable from '../components/BluffTable';
import TwoTruthsGame from '../components/TwoTruthsGame';
import StoryChainGame from '../components/StoryChainGame';
import CommonGroundGame from '../components/CommonGroundGame';

type PlayerState = 'JOIN' | 'LOBBY' | 'INTRO' | 'QUESTION' | 'BINGO' | 'MUSICAL_CHAIRS' | 'BLUFF' | 'TWO_TRUTHS' | 'STORY_CHAIN' | 'COMMON_GROUND' | 'WAITING' | 'RESULT' | 'PODIUM' | 'RECONNECTING' | 'GAME_IN_PROGRESS';

interface PlayerQuestion {
    id: number;
    text: string;
    options: string[];
    image_url?: string;
}

function getSavedSession() {
    try {
        const raw = sessionStorage.getItem('localplay_session');
        if (raw) return JSON.parse(raw) as { roomCode: string; nickname: string; team: string; avatar: string; sessionToken?: string };
    } catch { /* corrupted session data */ }
    return null;
}

function normalizeRoomCode(value: string | null | undefined): string {
    return String(value || '').toUpperCase().replace(/[^A-Z0-9]/g, '').slice(0, 6);
}

export default function PlayerPage() {
    const [searchParams] = useSearchParams();
    const { code: urlCode } = useParams();
    const saved = getSavedSession();
    const hostAppMode = searchParams.get('embed') === '1' || searchParams.has('launch_token') || searchParams.has('session_id');
    const savedSession = hostAppMode ? null : saved;
    const [state, setState] = useState<PlayerState>('JOIN');
    const [roomCode, setRoomCode] = useState(normalizeRoomCode(urlCode || searchParams.get('room') || savedSession?.roomCode || ''));
    const [nickname, setNickname] = useState(savedSession?.nickname || '');
    const [team, setTeam] = useState(savedSession?.team || '');
    const [avatar, setAvatar] = useState(() => savedSession?.avatar || AVATAR_EMOJIS[Math.floor(Math.random() * AVATAR_EMOJIS.length)]);
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
    const [, setCorrectAnswer] = useState<number | null>(null);
    const [leaderboard, setLeaderboard] = useState<LeaderboardEntry[]>([]);
    const [teamLeaderboard, setTeamLeaderboard] = useState<TeamLeaderboardEntry[]>([]);
    const [myRank, setMyRank] = useState(0);
    const [error, setError] = useState('');
    const [hostAppReturnUrl, setHostAppReturnUrl] = useState('');
    const [hostAppTerminalError, setHostAppTerminalError] = useState(false);
    const [launchResolving, setLaunchResolving] = useState(() => searchParams.has('launch_token'));
    const [introCount, setIntroCount] = useState(3);
    const [lobbyPlayers, setLobbyPlayers] = useState<PlayerInfo[]>([]);
    const [powerUps, setPowerUps] = useState<PowerUps>({ double_points: true, fifty_fifty: true });

    useEffect(() => {
        const launchToken = searchParams.get('launch_token');
        if (!launchToken) return;
        let cancelled = false;
        setLaunchResolving(true);
        (async () => {
            try {
                const res = await fetch(apiUrl(`/integrations/revelry/launch-token/resolve?scope=player&launch_token=${encodeURIComponent(launchToken)}`));
                if (!res.ok) throw new Error('Launch token rejected');
                const data = await res.json();
                if (!data.room_code) throw new Error('Launch token missing room code');
                if (!cancelled && data.room_code) {
                    setRoomCode(data.room_code);
                    setHostAppReturnUrl(data.launch_context?.return_url || data.return_url || '');
                    setHostAppTerminalError(false);
                    setError('');
                }
            } catch {
                if (!cancelled) {
                    setHostAppTerminalError(true);
                    setError('This game link expired. Return to Revelry and reopen it.');
                }
            } finally {
                if (!cancelled) setLaunchResolving(false);
            }
        })();
        return () => { cancelled = true; };
    }, [searchParams]);
    const [hiddenOptions, setHiddenOptions] = useState<number[]>([]);
    const [isBonus, setIsBonus] = useState(false);
    const [showBonusSplash, setShowBonusSplash] = useState(false);
    // WMLT state
    const [gameType, setGameType] = useState<GameType>('quiz');
    const [currentStatement, setCurrentStatement] = useState('');
    const [votePlayers, setVotePlayers] = useState<PlayerInfo[]>([]);
    const [selectedVote, setSelectedVote] = useState<string | null>(null);
    const [voteResult, setVoteResult] = useState<{ winner: string; winners: string[]; winner_votes: number; votes: Record<string, string[]>; unanimous: boolean; round_podium: { nickname: string; avatar: string; vote_count: number; voters: string[] }[]; show_votes: boolean } | null>(null);
    const [superlatives, setSuperlatives] = useState<{ title: string; icon: string; winner: string; avatar: string; detail: string }[]>([]);
    // DrawingGame state
    const [drawingPrompt, setDrawingPrompt] = useState('');
    const [drawingDrawer, setDrawingDrawer] = useState('');
    const [isDrawer, setIsDrawer] = useState(false);
    const [drawingOps, setDrawingOps] = useState<DrawOperation[]>([]);
    const [guess, setGuess] = useState('');
    const [correctGuessers, setCorrectGuessers] = useState<string[]>([]);
    const [guessLog, setGuessLog] = useState<{ nickname: string; guess: string; correct?: boolean }[]>([]);
    const [drawingRoundPrompt, setDrawingRoundPrompt] = useState('');
    const [housieTicket, setHousieTicket] = useState<HousieTicket | null>(null);
    const [housieCalled, setHousieCalled] = useState<Array<{ value: number | string; display: string }>>([]);
    const [housieLatest, setHousieLatest] = useState<{ value: number | string; display: string } | null>(null);
    const [housiePatterns, setHousiePatterns] = useState<HousiePattern[]>([]);
    const [housieWinners, setHousieWinners] = useState<HousieWinner[]>([]);
    const [housiePlayMode, setHousiePlayMode] = useState<'beginner' | 'pro'>('beginner');
    const [housieCallFlash, setHousieCallFlash] = useState<{ item: { value?: number | string; display: string; kind?: string; image_url?: string; alt_text?: string }; key: number } | null>(null);
    const [housieAnnouncement, setHousieAnnouncement] = useState<{ text: string; personal: boolean; key: number; winningNumber?: string } | null>(null);
    const [markedNumbers, setMarkedNumbers] = useState<Set<string>>(new Set());
    const [musicalChairsState, setMusicalChairsState] = useState<MusicalChairsState | null>(null);
    const [mcGrabbed, setMcGrabbed] = useState(false);
    const [mcEliminated, setMcEliminated] = useState(false);
    const [mcReactionMs, setMcReactionMs] = useState<number | null>(null);
    const [bluffState, setBluffState] = useState<BluffState | null>(null);
    const [selectedBluffCards, setSelectedBluffCards] = useState<Set<string>>(new Set());
    const [twoTruthsState, setTwoTruthsState] = useState<TwoTruthsState | null>(null);
    const [storyChainState, setStoryChainState] = useState<StoryChainState | null>(null);
    const [commonGroundState, setCommonGroundState] = useState<CommonGroundState | null>(null);
    const wsRef = useRef<WebSocket | null>(null);
    const autoJoinedRef = useRef(false);
    const submittedRef = useRef(false);
    const kickedRef = useRef(false);
    const mountedRef = useRef(true);
    const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
    useEffect(() => () => {
        mountedRef.current = false;
        if (reconnectTimerRef.current) clearTimeout(reconnectTimerRef.current);
        wsRef.current?.close();
        wsRef.current = null;
    }, []);

    const applyBingoState = (bingo?: {
        ticket?: HousieTicket;
        called_items?: Array<{ value: number | string; display: string }>;
        latest_item?: { value: number | string; display: string } | null;
        patterns?: HousiePattern[];
        winners?: HousieWinner[];
        play_mode?: 'beginner' | 'pro';
    }, nextGameType: GameType = 'housie') => {
        setGameType(nextGameType);
        setHousieTicket(bingo?.ticket || null);
        setHousieCalled(bingo?.called_items || []);
        setHousieLatest(bingo?.latest_item || null);
        setHousiePatterns(bingo?.patterns || []);
        setHousieWinners(bingo?.winners || []);
        if (bingo?.play_mode) setHousiePlayMode(bingo.play_mode);
        setState('BINGO');
    };

    useEffect(() => {
        if (state !== 'INTRO') return;
        setIntroCount(3);
        const timers = [1, 2].map((tick) => window.setTimeout(() => setIntroCount(3 - tick), tick * 1000));
        return () => timers.forEach(window.clearTimeout);
    }, [state]);

    // Auto-rejoin if we have a saved session (e.g. page refresh)
    useEffect(() => {
        if (savedSession && !autoJoinedRef.current && !wsRef.current) {
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
        setHostAppTerminalError(false);
        kickedRef.current = false;

        const clientId = `player-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`;
        const ws = new WebSocket(`${WS_URL}/ws/${roomCode}/${clientId}`);
        wsRef.current = ws;

        ws.onopen = () => {
            track('player_joined', { room_code: roomCode, nickname, has_team: !!team });
            const savedSession = getSavedSession();
            ws.send(JSON.stringify({ type: 'JOIN', nickname, team: team || undefined, avatar, session_token: savedSession?.sessionToken || '' }));
        };

        ws.onmessage = (event) => {
            // eslint-disable-next-line @typescript-eslint/no-explicit-any
            let msg: any;
            try { msg = JSON.parse(event.data); } catch { return; }
            if (msg.type === 'ERROR') {
                setError(msg.message as string);
                // If room doesn't exist, stop reconnection attempts
                if (msg.message === 'Room not found' || msg.message === 'Room is full' || msg.message === 'Room is locked by the host' || msg.message === 'Nickname is taken') {
                    if (hostAppMode && msg.message !== 'Nickname is taken') {
                        setHostAppTerminalError(true);
                    }
                    kickedRef.current = true;
                    wsRef.current?.close();
                    wsRef.current = null;
                    sessionStorage.removeItem('localplay_session');
                    setState('JOIN');
                }
                return;
            }
            if (msg.type === 'GAME_IN_PROGRESS') {
                setQuestionNumber(msg.question_number as number);
                setTotalQuestions(msg.total_questions as number);
                setState('GAME_IN_PROGRESS');
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
                sessionStorage.setItem('localplay_session', JSON.stringify({ roomCode, nickname, team, avatar, sessionToken: msg.session_token || '' }));
                setState('LOBBY');
            }
            if (msg.type === 'RECONNECTED') {
                const token = (msg.session_token as string) || getSavedSession()?.sessionToken || '';
                sessionStorage.setItem('localplay_session', JSON.stringify({ roomCode, nickname, team, avatar, sessionToken: token }));
                setQuestionNumber(msg.question_number as number);
                setTotalQuestions(msg.total_questions as number);
                if (msg.game_type) setGameType(msg.game_type as GameType);
                if (msg.power_ups) setPowerUps(msg.power_ups as PowerUps);
                if (msg.state === 'LOBBY') {
                    setState('LOBBY');
                } else if (msg.game_type === 'housie' || msg.game_type === 'bingo' || msg.state === 'BINGO_CALLING') {
                    applyBingoState(msg.bingo as Parameters<typeof applyBingoState>[0], (msg.game_type as GameType) || 'housie');
                } else if (msg.game_type === 'musical_chairs' && msg.musical_chairs) {
                    setGameType('musical_chairs');
                    setMusicalChairsState(msg.musical_chairs as MusicalChairsState);
                    setState('MUSICAL_CHAIRS');
                } else if (msg.game_type === 'bluff' && msg.bluff) {
                    setGameType('bluff');
                    setBluffState(msg.bluff as BluffState);
                    setSelectedBluffCards(new Set());
                    setState('BLUFF');
                } else if (msg.game_type === 'two_truths' && msg.two_truths) {
                    setGameType('two_truths');
                    setTwoTruthsState(msg.two_truths as TwoTruthsState);
                    setState('TWO_TRUTHS');
                } else if (msg.game_type === 'story_chain' && msg.story_chain) {
                    setGameType('story_chain');
                    setStoryChainState(msg.story_chain as StoryChainState);
                    setState('STORY_CHAIN');
                } else if (msg.game_type === 'common_ground' && msg.common_ground) {
                    setGameType('common_ground');
                    setCommonGroundState(msg.common_ground as CommonGroundState);
                    setState('COMMON_GROUND');
                } else if (msg.state === 'QUESTION') {
                    if (msg.game_type === 'drawing') {
                        setGameType('drawing');
                        const promptData = msg.drawing_prompt as { text?: string } | undefined;
                        setDrawingPrompt(promptData?.text || '');
                        setDrawingDrawer(msg.drawer as string || '');
                        setIsDrawer(Boolean(msg.is_drawer));
                        setDrawingOps((msg.drawing_ops as DrawOperation[]) || []);
                        setCorrectGuessers((msg.correct_guessers as string[]) || []);
                        setGuessLog((msg.guess_log as { nickname: string; guess: string; correct?: boolean }[]) || []);
                    } else if (msg.statement) {
                        // WMLT reconnection
                        setCurrentStatement((msg.statement as { text: string }).text);
                        setVotePlayers(msg.players as PlayerInfo[] || []);
                        setSelectedVote(null);
                    } else if (msg.question) {
                        setCurrentQuestion(msg.question as PlayerQuestion);
                        setHiddenOptions(msg.remove_indices ? (msg.remove_indices as number[]) : []);
                    }
                    setTimeLimit(msg.time_limit as number);
                    setTimeRemaining((msg.time_remaining ?? msg.time_limit) as number);
                    setSelectedAnswer(null);
                    submittedRef.current = false;
                    setIsCorrect(null);
                    setPointsEarned(0);
                    setCorrectAnswer(null);
                    setIsBonus(msg.is_bonus as boolean || false);
                    setState('QUESTION');
                } else if (msg.state === 'LEADERBOARD') {
                    setState('RESULT');
                } else if (msg.state === 'PODIUM') {
                    setState('PODIUM');
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
            if (msg.type === 'GAME_STARTING') {
                if (msg.game_type === 'housie' || msg.game_type === 'bingo') {
                    setGameType(msg.game_type as GameType);
                    setState('BINGO');
                } else if (msg.game_type === 'musical_chairs') {
                    setGameType('musical_chairs');
                    setMcGrabbed(false);
                    setMcEliminated(false);
                    setMcReactionMs(null);
                    setState('MUSICAL_CHAIRS');
                } else if (msg.game_type === 'bluff') {
                    setGameType('bluff');
                    setState('BLUFF');
                } else if (msg.game_type === 'two_truths') {
                    setGameType('two_truths');
                    setState('TWO_TRUTHS');
                } else if (msg.game_type === 'story_chain') {
                    setGameType('story_chain');
                    setState('STORY_CHAIN');
                } else if (msg.game_type === 'common_ground') {
                    setGameType('common_ground');
                    setState('COMMON_GROUND');
                }
                else setState('INTRO');
            }
            if (msg.type === 'BINGO_SYNC') {
                applyBingoState(msg.bingo as Parameters<typeof applyBingoState>[0], (msg.game_type as GameType) || 'housie');
            }
            if (msg.type === 'BINGO_CALL') {
                setGameType((msg.game_type as GameType) || 'housie');
                setHousieCalled(msg.called_items as Array<{ value: number | string; display: string }> || []);
                setHousieLatest(msg.item as { value: number | string; display: string });
                const callItem = msg.item as { value?: number | string; display?: string; kind?: string; image_url?: string; alt_text?: string };
                setHousieCallFlash({ item: { ...callItem, display: String(callItem?.display || '') }, key: Date.now() });
                setState('BINGO');
                soundManager.play('timerTick');
            }
            if (msg.type === 'BINGO_CLAIM_ACCEPTED') {
                setHousieWinners(msg.winners as HousieWinner[] || []);
                setLeaderboard(msg.leaderboard as LeaderboardEntry[] || []);
                const winner = msg.winner as HousieWinner | undefined;
                if (winner) {
                    const personal = winner.nickname === nickname;
                    setHousieAnnouncement({
                        text: personal ? `You won ${winner.label}!` : `${winner.nickname} won ${winner.label}`,
                        personal,
                        key: Date.now(),
                        winningNumber: winner.winning_number != null ? String(winner.winning_number) : undefined,
                    });
                }
                soundManager.play('fanfare');
            }
            if (msg.type === 'BINGO_CLAIM_REJECTED') {
                setError((msg.message as string) || 'Claim rejected');
            }
            if (msg.type === 'BINGO_COMPLETE') {
                setHousieWinners(msg.winners as HousieWinner[] || []);
                setLeaderboard(msg.leaderboard as LeaderboardEntry[] || []);
            }
            if (msg.type === 'MC_SYNC' || msg.type === 'MC_ROUND_START' || msg.type === 'MC_GRAB_COUNT' || msg.type === 'MC_ROUND_OVER') {
                setGameType('musical_chairs');
                setMusicalChairsState(msg.musical_chairs as MusicalChairsState);
                if (msg.type === 'MC_ROUND_START') {
                    setMcGrabbed(false);
                    setMcReactionMs(null);
                }
                setState('MUSICAL_CHAIRS');
            }
            if (msg.type === 'MC_MUSIC_STOP') {
                setGameType('musical_chairs');
                setMusicalChairsState(msg.musical_chairs as MusicalChairsState);
                setMcGrabbed(false);
                setMcReactionMs(null);
                setState('MUSICAL_CHAIRS');
                soundManager.play('timerTick');
                soundManager.hapticsSelect();
            }
            if (msg.type === 'MC_GRAB_CONFIRMED') {
                setMcGrabbed(true);
                setMcReactionMs((msg.reaction_ms as number | null) ?? null);
                soundManager.play('correct');
                soundManager.hapticsCorrect();
            }
            if (msg.type === 'MC_ELIMINATED') {
                setMcEliminated(true);
                setMcReactionMs((msg.reaction_ms as number | null) ?? null);
                soundManager.play('wrong');
            }
            if (msg.type === 'MC_WINNER') {
                setGameType('musical_chairs');
            }
            if (msg.type === 'BLUFF_SYNC') {
                setError('');
                setGameType('bluff');
                setBluffState(msg.bluff as BluffState);
                setSelectedBluffCards(new Set());
                setState('BLUFF');
            }
            if (msg.type === 'TT_SYNC') {
                setError('');
                setGameType('two_truths');
                setTwoTruthsState(msg.two_truths as TwoTruthsState);
                setLeaderboard(msg.leaderboard as LeaderboardEntry[] || []);
                setState('TWO_TRUTHS');
            }
            if (msg.type === 'STORY_SYNC') {
                setError('');
                setGameType('story_chain');
                setStoryChainState(msg.story_chain as StoryChainState);
                setLeaderboard(msg.leaderboard as LeaderboardEntry[] || []);
                setState('STORY_CHAIN');
            }
            if (msg.type === 'COMMON_SYNC') {
                setError('');
                setGameType('common_ground');
                setCommonGroundState(msg.common_ground as CommonGroundState);
                setLeaderboard(msg.leaderboard as LeaderboardEntry[] || []);
                setState('COMMON_GROUND');
            }
            if (msg.type === 'QUESTION') {
                if (msg.game_type === 'drawing') {
                    setGameType('drawing');
                    const promptData = msg.drawing_prompt as { text?: string } | undefined;
                    setDrawingPrompt(promptData?.text || '');
                    setDrawingDrawer(msg.drawer as string || '');
                    setIsDrawer(Boolean(msg.is_drawer));
                    setDrawingOps((msg.drawing_ops as DrawOperation[]) || []);
                    setCorrectGuessers((msg.correct_guessers as string[]) || []);
                    setGuessLog((msg.guess_log as { nickname: string; guess: string; correct?: boolean }[]) || []);
                    setGuess('');
                } else if (msg.game_type === 'wmlt' || msg.statement) {
                    setGameType('wmlt');
                    setCurrentStatement((msg.statement as { text: string }).text);
                    setVotePlayers(msg.players as PlayerInfo[] || []);
                    setSelectedVote(null);
                    setVoteResult(null);
                } else {
                    setGameType('quiz');
                    setCurrentQuestion(msg.question as PlayerQuestion);
                }
                setQuestionNumber(msg.question_number as number);
                setTotalQuestions(msg.total_questions as number);
                setTimeLimit(msg.time_limit as number);
                setTimeRemaining(msg.time_limit as number);
                setSelectedAnswer(null);
                setSelectedVote(null);
                submittedRef.current = false;
                setIsCorrect(null);
                setPointsEarned(0);
                setCorrectAnswer(null);
                setHiddenOptions([]);
                setIsBonus(msg.is_bonus as boolean || false);
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
                    soundManager.hapticsCorrect();
                } else {
                    soundManager.play('wrong');
                    soundManager.hapticsWrong();
                }
            }
            if (msg.type === 'DRAW_OP') {
                const op = msg.op as DrawOperation;
                if (!op) return;
                if (op.kind === 'clear') setDrawingOps([]);
                else if (op.kind === 'undo') setDrawingOps(prev => prev.slice(0, -1));
                else setDrawingOps(prev => [...prev, op].slice(-500));
            }
            if (msg.type === 'GUESS_RESULT') {
                if (msg.correct) {
                    setPointsEarned((msg.points as number) || 0);
                    setIsCorrect(true);
                    setState('WAITING');
                    soundManager.play('correct');
                    soundManager.hapticsCorrect();
                } else {
                    setError('Not quite. Keep guessing!');
                    window.setTimeout(() => setError(''), 1200);
                }
            }
            if (msg.type === 'GUESS_ACCEPTED') {
                setCorrectGuessers((msg.correct_guessers as string[]) || []);
            }
            if (msg.type === 'GUESS_LOG') {
                setGuessLog((msg.guess_log as { nickname: string; guess: string; correct?: boolean }[]) || []);
            }
            if (msg.type === 'VOTE_CONFIRMED') {
                setSelectedVote(msg.voted_for as string);
                setState('WAITING');
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
                if (msg.game_type === 'drawing') {
                    setDrawingRoundPrompt(msg.prompt as string || '');
                    setCorrectGuessers((msg.correct_guessers as string[]) || []);
                } else if (msg.game_type === 'wmlt') {
                    setVoteResult({
                        winner: msg.winner as string,
                        winners: (msg.winners as string[]) || [msg.winner as string],
                        winner_votes: msg.winner_votes as number,
                        votes: msg.votes as Record<string, string[]>,
                        unanimous: msg.unanimous as boolean,
                        round_podium: (msg.round_podium as { nickname: string; avatar: string; vote_count: number; voters: string[] }[]) || [],
                        show_votes: msg.show_votes as boolean ?? true,
                    });
                } else {
                    setCorrectAnswer(msg.answer as number);
                }
                setLeaderboard(msg.leaderboard as LeaderboardEntry[]);
                setMyRank((msg.leaderboard as LeaderboardEntry[]).findIndex((p) => p.nickname === nickname) + 1);
                setState('RESULT');
            }
            if (msg.type === 'PODIUM') {
                const lb = msg.leaderboard as LeaderboardEntry[];
                const rank = lb.findIndex((p) => p.nickname === nickname) + 1;
                track('player_game_finished', { room_code: roomCode, nickname, rank, total_players: lb.length });
                setLeaderboard(msg.leaderboard); setTeamLeaderboard(msg.team_leaderboard || []); setSuperlatives(msg.superlatives || []); setState('PODIUM'); soundManager.play('fanfare');
            }
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
                if (hostAppMode) setHostAppTerminalError(true);
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
                setSelectedVote(null);
                setVoteResult(null);
                setCurrentStatement('');
                setDrawingPrompt('');
                setDrawingDrawer('');
                setIsDrawer(false);
                setDrawingOps([]);
                setGuess('');
                setCorrectGuessers([]);
                setGuessLog([]);
                setDrawingRoundPrompt('');
                setMusicalChairsState(null);
                setBluffState(null);
                setTwoTruthsState(null);
                setStoryChainState(null);
                setCommonGroundState(null);
                setMcGrabbed(false);
                setMcEliminated(false);
                setMcReactionMs(null);
                if (msg.game_type) setGameType(msg.game_type as GameType);
                if (msg.players) setLobbyPlayers(msg.players as PlayerInfo[]);
                setState('LOBBY');
                soundManager.play('playerJoin');
            }
        };

        ws.onerror = () => setError('Connection failed');
        ws.onclose = () => {
            if (kickedRef.current) { kickedRef.current = false; return; }
            if (!mountedRef.current) return;
            setState((current) => {
                if (current !== 'JOIN' && current !== 'PODIUM') {
                    reconnectTimerRef.current = setTimeout(() => joinRoom(), 2000);
                    return 'RECONNECTING';
                }
                if (current === 'JOIN') setError('Unable to connect. Check your internet and try again.');
                return current;
            });
        };
    };

    useEffect(() => {
        const reconnectAfterWake = () => {
            if (document.visibilityState === 'hidden') return;
            if (!getSavedSession() || kickedRef.current || state === 'PODIUM') return;
            const ws = wsRef.current;
            if (ws?.readyState === WebSocket.OPEN) {
                try {
                    ws.send(JSON.stringify({ type: 'PING' }));
                } catch {
                    // The close handler will schedule the real reconnect.
                }
                return;
            }
            if (ws && (ws.readyState === WebSocket.CONNECTING || ws.readyState === WebSocket.CLOSING)) {
                return;
            }
            wsRef.current = null;
            joinRoom();
        };

        window.addEventListener('pageshow', reconnectAfterWake);
        window.addEventListener('focus', reconnectAfterWake);
        window.addEventListener('online', reconnectAfterWake);
        document.addEventListener('visibilitychange', reconnectAfterWake);
        return () => {
            window.removeEventListener('pageshow', reconnectAfterWake);
            window.removeEventListener('focus', reconnectAfterWake);
            window.removeEventListener('online', reconnectAfterWake);
            document.removeEventListener('visibilitychange', reconnectAfterWake);
        };
    // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [state]);

    const submitAnswer = (index: number) => {
        if (selectedAnswer !== null || submittedRef.current) return;
        submittedRef.current = true;
        soundManager.hapticsSelect();
        setSelectedAnswer(index);
        wsRef.current?.send(JSON.stringify({ type: 'ANSWER', answer_index: index }));
    };

    const submitVote = (votedFor: string) => {
        if (selectedVote !== null || submittedRef.current) return;
        submittedRef.current = true;
        soundManager.hapticsSelect();
        setSelectedVote(votedFor);
        wsRef.current?.send(JSON.stringify({ type: 'VOTE', voted_for: votedFor }));
    };

    const sendDrawOp = (op: DrawOperation) => {
        wsRef.current?.send(JSON.stringify({ type: 'DRAW_OP', op }));
    };

    const submitGuess = () => {
        const value = guess.trim();
        if (!value) return;
        wsRef.current?.send(JSON.stringify({ type: 'GUESS', guess: value }));
        setGuess('');
    };

    const toggleHousieMark = (value: number | string) => {
        const key = String(value);
        setMarkedNumbers((current) => {
            const next = new Set(current);
            if (next.has(key)) next.delete(key);
            else next.add(key);
            return next;
        });
    };

    const submitHousieClaim = (patternId: string) => {
        setError('');
        soundManager.hapticsSelect();
        wsRef.current?.send(JSON.stringify({ type: 'BINGO_CLAIM', pattern_id: patternId }));
    };

    const submitMusicalChairsGrab = () => {
        if (mcGrabbed || mcEliminated) return;
        soundManager.hapticsSelect();
        wsRef.current?.send(JSON.stringify({ type: 'MC_GRAB' }));
    };

    const toggleBluffCard = (cardId: string) => {
        setSelectedBluffCards((current) => {
            const next = new Set(current);
            if (next.has(cardId)) next.delete(cardId);
            else next.add(cardId);
            return next;
        });
    };

    const playBluffCards = () => {
        const cardIds = Array.from(selectedBluffCards);
        if (!cardIds.length) return;
        soundManager.hapticsSelect();
        wsRef.current?.send(JSON.stringify({ type: 'BLUFF_PLAY', card_ids: cardIds }));
        setSelectedBluffCards(new Set());
    };

    const passBluffTurn = () => {
        soundManager.hapticsSelect();
        wsRef.current?.send(JSON.stringify({ type: 'BLUFF_PASS' }));
    };

    const challengeBluff = () => {
        soundManager.hapticsSelect();
        wsRef.current?.send(JSON.stringify({ type: 'BLUFF_CHALLENGE' }));
    };

    const continueBluff = () => wsRef.current?.send(JSON.stringify({ type: 'BLUFF_CONTINUE' }));
    const submitTwoTruths = (statements: Array<{ text: string; is_lie: boolean }>) => {
        soundManager.hapticsSelect();
        wsRef.current?.send(JSON.stringify({ type: 'TT_SUBMIT_STATEMENTS', statements }));
    };
    const voteTwoTruths = (statementId: string) => {
        soundManager.hapticsSelect();
        wsRef.current?.send(JSON.stringify({ type: 'TT_VOTE', statement_id: statementId }));
    };
    const submitStorySentence = (text: string) => {
        soundManager.hapticsSelect();
        wsRef.current?.send(JSON.stringify({ type: 'STORY_SUBMIT_SENTENCE', text }));
    };
    const submitCommonFact = (text: string) => {
        soundManager.hapticsSelect();
        wsRef.current?.send(JSON.stringify({ type: 'COMMON_SUBMIT_FACT', text }));
    };
    const voteCommonGround = (submissionId: string) => {
        soundManager.hapticsSelect();
        wsRef.current?.send(JSON.stringify({ type: 'COMMON_VOTE', submission_id: submissionId }));
    };

    const activatePowerUp = (powerUp: 'double_points' | 'fifty_fifty') => {
        soundManager.hapticsSelect();
        wsRef.current?.send(JSON.stringify({ type: 'USE_POWER_UP', power_up: powerUp }));
    };

    const handleReturnToHostApp = () => {
        if (hostAppReturnUrl) {
            returnToHostApp(hostAppReturnUrl);
        }
    };

    return (
        <div className="app-container">
            <div className="content-wrapper">

                {/* JOIN */}
                {state === 'JOIN' && (
                    <div className="container-responsive safe-bottom animate-in" style={{ minHeight: '100dvh', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center' }}>
                        {hostAppMode && launchResolving ? (
                            <>
                                <div className="hero-icon mb-4" style={{ background: 'none', boxShadow: 'none' }}>
                                    <img src={`${import.meta.env.BASE_URL}icons/icon-192.png`} alt="Revelry Games" style={{ width: '100%', height: '100%', borderRadius: '20px' }} />
                                </div>
                                <h1 className="hero-title mb-3">Opening game...</h1>
                                <p className="text-[--text-tertiary] mb-6 text-center">Checking this Revelry game link.</p>
                            </>
                        ) : hostAppMode && hostAppTerminalError ? (
                            <>
                                <div className="hero-icon mb-4" style={{ background: 'none', boxShadow: 'none' }}>
                                    <img src={`${import.meta.env.BASE_URL}icons/icon-192.png`} alt="Revelry Games" style={{ width: '100%', height: '100%', borderRadius: '20px' }} />
                                </div>
                                <h1 className="hero-title mb-3">Game Unavailable</h1>
                                <p className="text-[--text-tertiary] mb-6 text-center">{error || 'Open this game from Revelry again.'}</p>
                                {hostAppReturnUrl && (
                                    <button onClick={handleReturnToHostApp} className="btn btn-primary w-full">
                                        Back to Revelry Games
                                    </button>
                                )}
                            </>
                        ) : (
                            <>
                        <div className="hero-icon mb-4" style={{ background: 'none', boxShadow: 'none' }}>
                            <img src={`${import.meta.env.BASE_URL}icons/icon-192.png`} alt="Revelry Games" style={{ width: '100%', height: '100%', borderRadius: '20px' }} />
                        </div>
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
                            </>
                        )}
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
                                            <PlayerChip
                                                key={player.nickname}
                                                player={player}
                                                you={isSelf}
                                                style={{ animationDelay: `${i * 0.06}s` }}
                                            />
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

                {/* INTRO */}
                {state === 'INTRO' && (
                    <div className="intro-screen animate-in">
                        <div className="intro-kicker">Room {roomCode}</div>
                        <h1 className="intro-title">Get Ready</h1>
                        <div className="intro-count" aria-live="polite">{introCount}</div>
                    </div>
                )}

                {state === 'BINGO' && (
                    <div className="housie-player-screen container-responsive safe-top safe-bottom animate-in">
                        {housieCallFlash && (gameType === 'bingo'
                            ? <BingoCallOverlay key={housieCallFlash.key} item={housieCallFlash.item} />
                            : <div key={housieCallFlash.key} className="housie-call-overlay">{housieCallFlash.item.display}</div>)}
                        {housieAnnouncement && (
                            <div key={housieAnnouncement.key} className={`housie-win-overlay ${housieAnnouncement.personal ? 'personal' : ''}`}>
                                <div className="housie-confetti" aria-hidden="true">{Array.from({ length: housieAnnouncement.personal ? 26 : 12 }, (_, index) => <i key={index} />)}</div>
                                <p>{housieAnnouncement.text}</p>
                            </div>
                        )}
                        <div className="housie-runtime-header">
                            <p>{gameType === 'bingo' ? 'Bingo' : 'Housie'}</p>
                            <h1 className="hero-title">{housieLatest ? housieLatest.display : 'Waiting for first call'}</h1>
                            <span>{gameType === 'bingo' ? `${housieCalled.length} items called` : housiePlayMode === 'pro' ? 'Pro mode · mark manually' : `${housieCalled.length} numbers called`}</span>
                        </div>
                        {housieTicket && (
                            <div className="housie-ticket-wrap">
                                {gameType === 'bingo' ? (
                                    <BingoCardGrid
                                        ticket={housieTicket}
                                        calledValues={new Set(housieCalled.flatMap((item) => [String(item.value), String((item as { id?: string }).id || '')]))}
                                        marked={markedNumbers}
                                        winningValues={housieAnnouncement?.winningNumber ? new Set([housieAnnouncement.winningNumber]) : undefined}
                                        onToggle={(cell) => toggleHousieMark(cell.id || cell.item_id || cell.value)}
                                    />
                                ) : (
                                    <HousieTicketGrid
                                        ticket={housieTicket}
                                        calledValues={new Set(housieCalled.map((item) => String(item.value)))}
                                        marked={markedNumbers}
                                        playMode={housiePlayMode}
                                        winningValues={housieAnnouncement?.winningNumber ? new Set([housieAnnouncement.winningNumber]) : undefined}
                                        onToggle={(cell) => toggleHousieMark(cell.value)}
                                    />
                                )}
                            </div>
                        )}
                        <div className="housie-runtime-panel">
                            <h2>Claim a prize</h2>
                            {error && (
                                <div className="status-pill status-error animate-shake">{error}</div>
                            )}
                            {gameType === 'bingo'
                                ? <BingoClaimButtons patterns={housiePatterns} winners={housieWinners} onClaim={submitHousieClaim} />
                                : <HousieClaimButtons patterns={housiePatterns} winners={housieWinners} onClaim={submitHousieClaim} />}
                        </div>
                        {gameType === 'bingo' && (
                            <div className="housie-runtime-panel">
                                <h2>Called</h2>
                                <BingoCalledList items={housieCalled} />
                            </div>
                        )}
                        <div className="housie-runtime-panel">
                            <h2>Winners</h2>
                            <HousieWinners winners={housieWinners} />
                        </div>
                    </div>
                )}

                {state === 'MUSICAL_CHAIRS' && (
                    <MusicalChairsPlayer
                        state={musicalChairsState}
                        grabbed={mcGrabbed}
                        eliminated={mcEliminated}
                        reactionMs={mcReactionMs}
                        onGrab={submitMusicalChairsGrab}
                    />
                )}

                {state === 'BLUFF' && (
                    <>
                        {error && <div className="status-pill status-error animate-shake player-runtime-error">{error}</div>}
                        <BluffTable
                            state={bluffState}
                            viewerName={nickname}
                            controls="player"
                            selectedCardIds={selectedBluffCards}
                            onToggleCard={toggleBluffCard}
                            onPlay={playBluffCards}
                            onPass={passBluffTurn}
                            onChallenge={challengeBluff}
                            onContinue={continueBluff}
                        />
                    </>
                )}

                {state === 'TWO_TRUTHS' && (
                    <>
                        {error && <div className="status-pill status-error animate-shake player-runtime-error">{error}</div>}
                        <TwoTruthsGame
                            state={twoTruthsState}
                            viewerName={nickname}
                            controls="player"
                            onSubmitStatements={submitTwoTruths}
                            onVote={voteTwoTruths}
                        />
                    </>
                )}

                {state === 'STORY_CHAIN' && (
                    <>
                        {error && <div className="status-pill status-error animate-shake player-runtime-error">{error}</div>}
                        <StoryChainGame
                            state={storyChainState}
                            viewerName={nickname}
                            controls="player"
                            onSubmitSentence={submitStorySentence}
                        />
                    </>
                )}

                {state === 'COMMON_GROUND' && (
                    <>
                        {error && <div className="status-pill status-error animate-shake player-runtime-error">{error}</div>}
                        <CommonGroundGame
                            state={commonGroundState}
                            viewerName={nickname}
                            controls="player"
                            onSubmitFact={submitCommonFact}
                            onVote={voteCommonGround}
                        />
                    </>
                )}

                {/* QUESTION */}
                {state === 'QUESTION' && (
                    showBonusSplash ? (
                        <BonusSplash onComplete={() => setShowBonusSplash(false)} />
                    ) : gameType === 'drawing' ? (
                    <div className="min-h-dvh flex flex-col container-responsive safe-top safe-bottom">
                        <div className="py-4 stagger-in" style={{ animationDelay: '0s' }}>
                            <div className="flex items-center justify-between mb-2">
                                <span className="text-[--text-tertiary] text-sm">Round {questionNumber}/{totalQuestions}</span>
                                <span className={`font-bold tabular-nums ${timeRemaining <= 5 ? 'timer-number-pulse' : ''}`}
                                    style={{ color: timeRemaining <= 5 ? 'var(--accent-danger)' : timeRemaining <= 10 ? 'var(--accent-warning)' : 'var(--accent-primary)' }}>
                                    {timeRemaining}s
                                </span>
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

                        <div className="mb-3 text-center">
                            {isDrawer ? (
                                <>
                                    <p className="text-[--text-tertiary] text-sm">You are drawing</p>
                                    <h2 className="text-2xl font-extrabold">{drawingPrompt}</h2>
                                </>
                            ) : (
                                <>
                                    <p className="text-[--text-tertiary] text-sm">Guess what <strong>{drawingDrawer}</strong> is drawing</p>
                                    <p className="text-[--accent-success] text-sm">{correctGuessers.length} correct</p>
                                </>
                            )}
                        </div>

                        <DrawingCanvas ops={drawingOps} drawable={isDrawer} onDrawOp={sendDrawOp} height={Math.min(420, Math.max(300, window.innerHeight * 0.42))} />

                        {!isDrawer && (
                            <div className="mt-4 flex gap-2">
                                <input
                                    value={guess}
                                    onChange={(event) => setGuess(event.target.value)}
                                    onKeyDown={(event) => { if (event.key === 'Enter') submitGuess(); }}
                                    placeholder="Type your guess"
                                    className="input-field"
                                    maxLength={80}
                                />
                                <button type="button" onClick={submitGuess} className="btn btn-primary">Guess</button>
                            </div>
                        )}

                        {guessLog.length > 0 && (
                            <div className="mt-3 text-center text-[--text-tertiary] text-sm">
                                {guessLog.slice(-3).map((item, index) => (
                                    <div key={`${item.nickname}-${item.guess}-${index}`}>{item.nickname}: {item.guess}</div>
                                ))}
                            </div>
                        )}
                    </div>
                    ) : gameType === 'wmlt' ? (
                    /* WMLT Voting UI */
                    <div className="min-h-dvh flex flex-col container-responsive safe-top safe-bottom">
                        <div className="py-4 stagger-in" style={{ animationDelay: '0s' }}>
                            <div className="flex items-center justify-between mb-2">
                                <span className="text-[--text-tertiary] text-sm">Round {questionNumber}/{totalQuestions}</span>
                                <div className="flex items-center gap-2">
                                    {isBonus && <span className="bonus-badge">2X BONUS</span>}
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

                        <div className="question-card mb-4 question-enter">
                            <p className="question-text">{currentStatement}</p>
                        </div>

                        {/* Player voting grid */}
                        <div className="flex-1" style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: 12, alignContent: 'start' }}>
                            {votePlayers.map((player, i) => {
                                const isSelf = player.nickname === nickname;
                                const isSelected = selectedVote === player.nickname;
                                return (
                                    <button
                                        key={player.nickname}
                                        onClick={() => submitVote(player.nickname)}
                                        disabled={selectedVote !== null}
                                        className={`answer-stagger ${isSelected ? 'vote-selected' : ''} ${selectedVote !== null && !isSelected ? 'dimmed' : ''}`}
                                        style={{
                                            animationDelay: `${0.15 + i * 0.06}s`,
                                            display: 'flex',
                                            flexDirection: 'column',
                                            alignItems: 'center',
                                            gap: 8,
                                            padding: '16px 12px',
                                            borderRadius: 16,
                                            border: isSelected ? '2px solid var(--accent-primary)' : '1px solid var(--border-primary)',
                                            background: isSelected ? 'rgba(var(--accent-primary-rgb, 99,102,241), 0.15)' : 'var(--bg-secondary)',
                                            cursor: selectedVote !== null ? 'default' : 'pointer',
                                            opacity: selectedVote !== null && !isSelected ? 0.4 : 1,
                                            transition: 'all 0.2s ease',
                                        }}
                                    >
                                        <div
                                            style={{
                                                width: 48, height: 48, borderRadius: '50%',
                                                display: 'flex', alignItems: 'center', justifyContent: 'center',
                                                backgroundColor: AVATAR_COLORS[i % AVATAR_COLORS.length],
                                                fontSize: '1.5rem',
                                            }}
                                        >
                                            {player.avatar || player.nickname.slice(0, 2).toUpperCase()}
                                        </div>
                                        <span style={{ fontSize: '0.875rem', fontWeight: 600, color: isSelf ? 'var(--accent-primary)' : 'var(--text-primary)' }}>
                                            {player.nickname}{isSelf ? ' (you)' : ''}
                                        </span>
                                    </button>
                                );
                            })}
                        </div>
                    </div>
                    ) : currentQuestion ? (
                    /* Quiz answer UI */
                    <div className="min-h-dvh flex flex-col container-responsive safe-top safe-bottom">
                        <div className="py-4 stagger-in" style={{ animationDelay: '0s' }}>
                            <div className="flex items-center justify-between mb-2">
                                <span className="text-[--text-tertiary] text-sm">Q{questionNumber}/{totalQuestions}</span>
                                <div className="flex items-center gap-2">
                                    {isBonus && <span className="bonus-badge">2X BONUS</span>}
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

                        <div className={`question-card mb-4 question-enter ${currentQuestion.image_url ? 'has-image' : ''}`}>
                            {currentQuestion.image_url && (
                                <GameImage src={mediaUrl(currentQuestion.image_url)} alt={currentQuestion.text} mode="question" />
                            )}
                            <p className="question-text">{currentQuestion.text}</p>
                        </div>

                        {/* Power-ups */}
                        {selectedAnswer === null && (powerUps.double_points || powerUps.fifty_fifty) && (
                            <div className="flex gap-2 mb-4 justify-center stagger-in" style={{ animationDelay: '0.2s' }}>
                                {powerUps.double_points && (
                                    <button onClick={() => activatePowerUp('double_points')} className="power-up-btn">
                                        2x Points
                                    </button>
                                )}
                                {powerUps.fifty_fifty && currentQuestion?.options?.length === 4 && (
                                    <button onClick={() => activatePowerUp('fifty_fifty')} className="power-up-btn">
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
                                    <span className="answer-label">{String.fromCharCode(65 + i)}</span>
                                    <span className="min-w-0" style={{ fontSize: opt.length > 50 ? 13 : opt.length > 30 ? 14 : 16 }}>{opt}</span>
                                </button>
                            ))}
                        </div>
                    </div>
                    ) : null
                )}

                {/* WAITING */}
                {state === 'WAITING' && (
                    <div className="min-h-dvh flex flex-col items-center justify-center container-responsive animate-in">
                        {gameType === 'wmlt' && selectedVote ? (
                            <>
                                <div className="hero-icon mb-4">🗳️</div>
                                <h2 className="hero-title mb-2">Vote Cast!</h2>
                                <p className="text-[--text-secondary] text-lg">You voted for <strong>{selectedVote}</strong></p>
                            </>
                        ) : isCorrect ? (
                            <div className="celebration-container">
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

                {/* GAME IN PROGRESS */}
                {state === 'GAME_IN_PROGRESS' && (
                    <div className="min-h-dvh flex flex-col items-center justify-center container-responsive animate-in">
                        <div className="status-screen-icon">&#9881;</div>
                        <h2 className="text-2xl font-extrabold mb-2">Game in Progress</h2>
                        <p className="text-[--text-secondary] text-center mb-4">
                            Question {questionNumber} of {totalQuestions}
                        </p>
                        <p className="text-[--text-tertiary] text-center">
                            Wait for the next round to join!
                        </p>
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
                            {gameType === 'drawing' ? (
                                <>
                                    <div style={{ fontSize: '2.5rem', marginBottom: 4 }}>🎨</div>
                                    <p className="text-[--text-tertiary] text-sm">The prompt was</p>
                                    <h2 className="text-2xl font-extrabold">{drawingRoundPrompt}</h2>
                                    <p className="text-[--text-secondary] text-sm mt-2">
                                        {correctGuessers.length ? `${correctGuessers.join(', ')} guessed it` : 'No correct guesses'}
                                    </p>
                                </>
                            ) : gameType === 'wmlt' && voteResult ? (
                                <>
                                    {/* Crown + winner(s) */}
                                    <div style={{ fontSize: '2.5rem', marginBottom: 4 }}>👑</div>
                                    {voteResult.winners.length > 1 ? (
                                        <>
                                            <h2 className="text-2xl font-extrabold">{voteResult.winners.join(' & ')}</h2>
                                            <p className="text-[--text-secondary] text-sm mt-1">
                                                Tied with {voteResult.winner_votes} vote{voteResult.winner_votes !== 1 ? 's' : ''} each!
                                            </p>
                                        </>
                                    ) : (
                                        <>
                                            <h2 className="text-2xl font-extrabold">{voteResult.winner}</h2>
                                            <p className="text-[--text-secondary] text-sm mt-1">
                                                {voteResult.winner_votes} vote{voteResult.winner_votes !== 1 ? 's' : ''}
                                                {voteResult.unanimous ? ' — Unanimous!' : ''}
                                            </p>
                                        </>
                                    )}

                                    {/* Your vote feedback */}
                                    <div style={{ marginTop: 8 }}>
                                        {selectedVote && voteResult.winners.includes(selectedVote) ? (
                                            <p className="text-[--accent-success] font-bold text-sm">You voted with the majority!</p>
                                        ) : selectedVote ? (
                                            <p className="text-[--text-tertiary] text-sm">You voted for {selectedVote}</p>
                                        ) : (
                                            <p className="text-[--accent-danger] text-sm">You didn't vote</p>
                                        )}
                                    </div>
                                </>
                            ) : (
                                <>
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
                                </>
                            )}
                        </div>

                        {/* WMLT: vote bar chart instead of points leaderboard */}
                        {gameType === 'wmlt' && voteResult ? (
                            <div className="flex-1 w-full">
                                <LeaderboardBarChart
                                    leaderboard={voteResult.round_podium.map(p => ({
                                        nickname: p.nickname,
                                        score: p.vote_count,
                                        avatar: p.avatar,
                                    }))}
                                    maxEntries={8}
                                    size="compact"
                                    highlightNickname={nickname}
                                />
                            </div>
                        ) : (
                            <>
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
                            </>
                        )}
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
                                    <div className="mb-2"><Avatar player={leaderboard[1]} size={44} decorative /></div>
                                    <p className="podium-name">{leaderboard[1].nickname}</p>
                                    <div className="podium-bar">2</div>
                                    <p className="podium-score"><AnimatedNumber value={leaderboard[1].score} /></p>
                                </div>
                            )}
                            {leaderboard[0] && (
                                <div className="podium-place podium-1 victory-glow">
                                    <span className="crown-bounce text-2xl" style={{ marginBottom: 4 }}>&#x1F451;</span>
                                    <div className="mb-2"><Avatar player={leaderboard[0]} size={54} you decorative /></div>
                                    <p className="podium-name">{leaderboard[0].nickname}</p>
                                    <div className="podium-bar">1</div>
                                    <p className="podium-score"><AnimatedNumber value={leaderboard[0].score} /></p>
                                </div>
                            )}
                            {leaderboard[2] && (
                                <div className="podium-place podium-3">
                                    <div className="mb-2"><Avatar player={leaderboard[2]} size={44} decorative /></div>
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

                        {superlatives.length > 0 && (
                            <div className="w-full mt-6" style={{ position: 'relative', zIndex: 11 }}>
                                <h3 className="text-lg font-semibold text-center mb-3">Awards</h3>
                                <div style={{ display: 'flex', justifyContent: 'center', gap: 12, flexWrap: 'wrap' }}>
                                    {superlatives.map((s) => (
                                        <div key={s.title} style={{ textAlign: 'center', padding: '10px 12px', background: 'var(--paper)', border: '1px solid var(--rule)', borderRadius: 8, minWidth: 100, maxWidth: 140 }}>
                                            <div style={{ fontSize: '1.5rem' }}>{s.icon}</div>
                                            <div style={{ fontWeight: 700, fontSize: '0.7rem', marginTop: 2 }}>{s.title}</div>
                                            <div style={{ fontSize: '1.1rem', marginTop: 2 }}>{s.avatar || '👤'}</div>
                                            <div style={{ fontWeight: 600, fontSize: '0.8rem' }}>{s.winner}</div>
                                            <div style={{ color: 'var(--text-tertiary)', fontSize: '0.65rem' }}>{s.detail}</div>
                                        </div>
                                    ))}
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
