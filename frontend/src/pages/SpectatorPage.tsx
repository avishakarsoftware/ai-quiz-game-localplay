import { useState, useEffect } from 'react';
import { useSearchParams } from 'react-router-dom';
import { QRCodeSVG } from 'qrcode.react';
import { WS_URL } from '../config';
import { type LeaderboardEntry, type TeamLeaderboardEntry, type PlayerInfo, ANSWER_STYLES } from '../types';
import AnimatedNumber from '../components/AnimatedNumber';
import Fireworks from '../components/Fireworks';
import LeaderboardBarChart from '../components/LeaderboardBarChart';
import { AVATAR_COLORS } from '../components/LeaderboardBarChart.constants';
import { soundManager } from '../utils/sound';
import BonusSplash from '../components/BonusSplash';

interface SpectatorQuestion {
    id: number;
    text: string;
    options: string[];
}

export default function SpectatorPage() {
    const [searchParams] = useSearchParams();
    const roomCode = searchParams.get('room') || '';
    const [gameState, setGameState] = useState('CONNECTING');
    const [players, setPlayers] = useState<PlayerInfo[]>([]);
    const [playerCount, setPlayerCount] = useState(0);
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

    const joinUrl = `http://${window.location.hostname}:5173/join?room=${roomCode}`;
    const displayUrl = `${window.location.hostname}:5173/join`;

    useEffect(() => {
        if (!roomCode) return;
        const clientId = `spectator-${Date.now()}`;
        const ws = new WebSocket(`${WS_URL}/ws/${roomCode}/${clientId}?spectator=true`);

        ws.onmessage = (event) => {
            const msg = JSON.parse(event.data);
            if (msg.type === 'SPECTATOR_SYNC') {
                setGameState(msg.state);
                setPlayers(msg.players || []);
                setPlayerCount(msg.player_count);
                setQuestionNumber(msg.question_number);
                setTotalQuestions(msg.total_questions);
                setLeaderboard(msg.leaderboard || []);
            }
            else if (msg.type === 'PLAYER_JOINED') {
                setPlayerCount(msg.player_count);
                setPlayers(msg.players || []);
                setGameState('LOBBY');
            }
            else if (msg.type === 'GAME_STARTING') setGameState('INTRO');
            else if (msg.type === 'QUESTION') {
                setQuestion(msg.question);
                setQuestionNumber(msg.question_number);
                setTotalQuestions(msg.total_questions);
                setTimeLimit(msg.time_limit);
                setTimeRemaining(msg.time_limit);
                setIsBonus(msg.is_bonus || false);
                if (msg.is_bonus) setShowBonusSplash(true);
                setGameState('QUESTION');
            }
            else if (msg.type === 'TIMER') setTimeRemaining(msg.remaining);
            else if (msg.type === 'QUESTION_OVER') {
                setLeaderboard(msg.leaderboard);
                if (!msg.is_final) {
                    setGameState('LEADERBOARD');
                }
                // When is_final, stay on current screen until PODIUM arrives
            }
            else if (msg.type === 'PODIUM') {
                setLeaderboard(msg.leaderboard);
                setTeamLeaderboard(msg.team_leaderboard || []);
                setPodiumReveal(0);
                setGameState('PODIUM');
                soundManager.play('fanfare');
            }
            else if (msg.type === 'ROOM_RESET') {
                setPlayers(msg.players || []);
                setPlayerCount(msg.player_count);
                setIsBonus(false);
                setShowBonusSplash(false);
                setGameState('LOBBY');
            }
        };

        ws.onerror = () => setGameState('ERROR');
        ws.onclose = () => setGameState('DISCONNECTED');

        return () => ws.close();
    }, [roomCode]);

    // Auto-fullscreen for spectator/TV view
    useEffect(() => {
        if (document.fullscreenElement) return;
        document.documentElement.requestFullscreen?.().catch(() => {});
    }, []);

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

    if (!roomCode) {
        return (
            <div className="min-h-dvh flex items-center justify-center">
                <p className="text-[--text-tertiary]">Add ?room=CODE to the URL</p>
            </div>
        );
    }

    return (
        <div className="app-container">
            <div className="content-wrapper">
                <div className="min-h-dvh flex flex-col justify-center" style={{ maxWidth: '100%', padding: '40px 60px' }}>

                    {(gameState === 'CONNECTING' || gameState === 'ERROR' || gameState === 'DISCONNECTED') && (
                        <div className="flex-1 flex flex-col items-center justify-center animate-in">
                            <div className="status-screen-icon mb-4" style={{ width: 80, height: 80, fontSize: 36 }}>
                                {gameState === 'CONNECTING' ? '📡' : gameState === 'ERROR' ? '⚠️' : '🔌'}
                            </div>
                            <h1 className="hero-title mb-2">
                                {gameState === 'CONNECTING' ? 'Connecting...' : gameState === 'ERROR' ? 'Connection Error' : 'Disconnected'}
                            </h1>
                            <p className="text-[--text-tertiary] text-lg">Room: {roomCode}</p>
                            {gameState === 'CONNECTING' && (
                                <div className="flex gap-1.5 mt-6">
                                    {[0, 1, 2].map((i) => (
                                        <div key={i} className="w-2.5 h-2.5 bg-[--accent-primary] rounded-full animate-bounce"
                                            style={{ animationDelay: `${i * 0.15}s` }} />
                                    ))}
                                </div>
                            )}
                        </div>
                    )}

                    {gameState === 'LOBBY' && (
                        <div className="flex-1 flex flex-col items-center justify-center animate-in">
                            <h1 className="hero-title mb-8" style={{ fontSize: '3.5rem' }}>Join the Quiz!</h1>

                            <div className="flex items-center justify-center gap-12 mb-8">
                                <div className="flex flex-col items-center">
                                    <div className="qr-container mb-2">
                                        <QRCodeSVG value={joinUrl} size={200} bgColor="white" fgColor="#000000" level="H" />
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
                                <div style={{ display: 'flex', flexWrap: 'wrap', justifyContent: 'center', gap: 12, maxWidth: 672 }}>
                                    {players.map((player, i) => (
                                        <div key={player.nickname} style={{ display: 'inline-flex', alignItems: 'center', gap: 8, padding: '8px 16px', borderRadius: 9999, background: 'var(--bg-secondary)' }}>
                                            <div
                                                style={{ width: 40, height: 40, minWidth: 40, borderRadius: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center', backgroundColor: AVATAR_COLORS[i % AVATAR_COLORS.length] }}
                                            >
                                                <span style={{ fontSize: '1.4rem', lineHeight: 1 }}>{player.avatar || player.nickname.slice(0, 2).toUpperCase()}</span>
                                            </div>
                                            <span style={{ fontSize: '1.125rem', fontWeight: 500 }}>{player.nickname}</span>
                                        </div>
                                    ))}
                                </div>
                            )}
                        </div>
                    )}

                    {gameState === 'QUESTION' && question && (
                        showBonusSplash ? (
                            <BonusSplash onComplete={() => setShowBonusSplash(false)} />
                        ) : (
                            <div className="flex-1 flex flex-col justify-center">
                            <div className="py-4">
                                <div className="flex items-center justify-between mb-2">
                                    <div className="flex items-center gap-3">
                                        <span className="text-2xl font-bold text-[--text-tertiary]">Q{questionNumber}/{totalQuestions}</span>
                                        {isBonus && <span className="bonus-badge" style={{ fontSize: 16 }}>2X BONUS</span>}
                                    </div>
                                    <span className={`font-extrabold tabular-nums text-3xl ${timeRemaining <= 5 ? 'timer-number-pulse' : ''}`}
                                        style={{ color: timeRemaining <= 5 ? 'var(--accent-danger)' : timeRemaining <= 10 ? 'var(--accent-warning)' : 'var(--accent-primary)' }}>
                                        {timeRemaining}s
                                    </span>
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
                            <div className="question-card mb-8" style={{ padding: '48px', fontSize: '24px' }}>
                                <p className="question-text" style={{ fontSize: '32px', fontWeight: 700 }}>{question.text}</p>
                            </div>
                            <div className={question.options.length === 2 ? 'answer-grid-tf' : 'answer-grid'} style={{ gap: '16px' }}>
                                {question.options.map((opt, i) => (
                                    <div key={i} className={`answer-btn ${ANSWER_STYLES[i].className}`} style={{ height: 100, fontSize: 20 }}>
                                        <span className="text-5xl opacity-50 mr-4">{ANSWER_STYLES[i].shape}</span>
                                        <span>{opt}</span>
                                    </div>
                                ))}
                            </div>
                            </div>
                        )
                    )}

                    {gameState === 'LEADERBOARD' && (
                        <div className="flex-1 flex flex-col justify-center animate-in">
                            <div className="text-center py-8">
                                <h1 className="hero-title mb-2" style={{ fontSize: '2.5rem' }}>Leaderboard</h1>
                                <p className="text-[--text-tertiary] text-xl">After question {questionNumber} of {totalQuestions}</p>
                            </div>
                            <div className="w-full max-w-3xl mx-auto">
                                <LeaderboardBarChart leaderboard={leaderboard} maxEntries={10} size="large" />
                            </div>
                        </div>
                    )}

                    {gameState === 'PODIUM' && (
                        <div className="flex-1 flex flex-col items-center justify-center animate-in"
                             style={{ position: 'relative', overflow: 'hidden' }}>
                            <Fireworks duration={15000} maxRockets={4} />

                            <h1 className="hero-title text-center mb-6" style={{ position: 'relative', zIndex: 11, fontSize: '3rem' }}>Final Results</h1>

                            {podiumReveal >= 4 && leaderboard[0] && (
                                <div className="champion-label" style={{ position: 'relative', zIndex: 11, fontSize: 28 }}>
                                    <span className="crown-bounce" style={{ fontSize: 36 }}>&#x1F451;</span>
                                    <span className="gold-shimmer">{leaderboard[0].nickname} is the Champion!</span>
                                </div>
                            )}

                            <div className="podium-container" style={{ gap: 16, padding: '40px 0', position: 'relative', zIndex: 11 }}>
                                {leaderboard[1] && (
                                    <div className={`podium-place podium-2 ${podiumReveal >= 2 ? '' : 'podium-hidden'}`}>
                                        <div className="w-14 h-14 rounded-full flex items-center justify-center mb-2" style={{ backgroundColor: '#C0C0C0' }}>
                                            <span style={{ fontSize: '2rem', lineHeight: 1 }}>{leaderboard[1].avatar || leaderboard[1].nickname.slice(0, 2).toUpperCase()}</span>
                                        </div>
                                        <p className="podium-name" style={{ fontSize: 18, maxWidth: 120 }}>{leaderboard[1].nickname}</p>
                                        <div className="podium-bar" style={{ width: 120, height: 120 }}>2</div>
                                        <p className="podium-score" style={{ fontSize: 16 }}><AnimatedNumber value={podiumReveal >= 2 ? leaderboard[1].score : 0} /></p>
                                    </div>
                                )}
                                {leaderboard[0] && (
                                    <div className={`podium-place podium-1 ${podiumReveal >= 3 ? '' : 'podium-hidden'} ${podiumReveal >= 4 ? 'victory-glow' : ''}`}>
                                        {podiumReveal >= 4 && <span className="crown-bounce" style={{ fontSize: 40, marginBottom: 4 }}>&#x1F451;</span>}
                                        <div className="w-16 h-16 rounded-full flex items-center justify-center mb-2" style={{ backgroundColor: '#FFD700' }}>
                                            <span style={{ fontSize: '2.5rem', lineHeight: 1 }}>{leaderboard[0].avatar || leaderboard[0].nickname.slice(0, 2).toUpperCase()}</span>
                                        </div>
                                        <p className="podium-name" style={{ fontSize: 18, maxWidth: 120 }}>{leaderboard[0].nickname}</p>
                                        <div className="podium-bar" style={{ width: 120, height: 160 }}>1</div>
                                        <p className="podium-score" style={{ fontSize: 16 }}><AnimatedNumber value={podiumReveal >= 3 ? leaderboard[0].score : 0} /></p>
                                    </div>
                                )}
                                {leaderboard[2] && (
                                    <div className={`podium-place podium-3 ${podiumReveal >= 1 ? '' : 'podium-hidden'}`}>
                                        <div className="w-14 h-14 rounded-full flex items-center justify-center mb-2" style={{ backgroundColor: '#CD7F32' }}>
                                            <span style={{ fontSize: '2rem', lineHeight: 1 }}>{leaderboard[2].avatar || leaderboard[2].nickname.slice(0, 2).toUpperCase()}</span>
                                        </div>
                                        <p className="podium-name" style={{ fontSize: 18, maxWidth: 120 }}>{leaderboard[2].nickname}</p>
                                        <div className="podium-bar" style={{ width: 120, height: 80 }}>3</div>
                                        <p className="podium-score" style={{ fontSize: 16 }}><AnimatedNumber value={podiumReveal >= 1 ? leaderboard[2].score : 0} /></p>
                                    </div>
                                )}
                            </div>

                            {podiumReveal >= 4 && teamLeaderboard.length > 1 && (
                                <div className="w-full mt-8" style={{ position: 'relative', zIndex: 11, maxWidth: 600 }}>
                                    <h3 className="text-3xl font-extrabold text-center mb-4">Team Standings</h3>
                                    <div className="podium-container" style={{ gap: 16 }}>
                                        {teamLeaderboard[1] && (
                                            <div className="podium-place podium-2">
                                                <p className="podium-name" style={{ fontSize: 18, maxWidth: 120 }}>{teamLeaderboard[1].team}</p>
                                                {teamLeaderboard[1].members > 1 && (
                                                    <p className="text-xs text-[--text-tertiary]">{teamLeaderboard[1].members} members</p>
                                                )}
                                                <div className="podium-bar" style={{ width: 120, height: 100 }}>2</div>
                                                <p className="podium-score" style={{ fontSize: 16 }}><AnimatedNumber value={teamLeaderboard[1].score} /></p>
                                            </div>
                                        )}
                                        {teamLeaderboard[0] && (
                                            <div className="podium-place podium-1 victory-glow">
                                                <p className="podium-name" style={{ fontSize: 18, maxWidth: 120 }}>{teamLeaderboard[0].team}</p>
                                                {teamLeaderboard[0].members > 1 && (
                                                    <p className="text-xs text-[--text-tertiary]">{teamLeaderboard[0].members} members</p>
                                                )}
                                                <div className="podium-bar" style={{ width: 120, height: 140 }}>1</div>
                                                <p className="podium-score" style={{ fontSize: 16 }}><AnimatedNumber value={teamLeaderboard[0].score} /></p>
                                            </div>
                                        )}
                                        {teamLeaderboard[2] && (
                                            <div className="podium-place podium-3">
                                                <p className="podium-name" style={{ fontSize: 18, maxWidth: 120 }}>{teamLeaderboard[2].team}</p>
                                                {teamLeaderboard[2].members > 1 && (
                                                    <p className="text-xs text-[--text-tertiary]">{teamLeaderboard[2].members} members</p>
                                                )}
                                                <div className="podium-bar" style={{ width: 120, height: 60 }}>3</div>
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
    );
}
