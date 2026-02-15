import { useState, useEffect } from 'react';
import { useSearchParams } from 'react-router-dom';
import { WS_URL } from '../config';
import { type LeaderboardEntry, ANSWER_STYLES } from '../types';

interface SpectatorQuestion {
    id: number;
    text: string;
    options: string[];
}

export default function SpectatorPage() {
    const [searchParams] = useSearchParams();
    const roomCode = searchParams.get('room') || '';
    const [gameState, setGameState] = useState('CONNECTING');
    const [players, setPlayers] = useState<string[]>([]);
    const [playerCount, setPlayerCount] = useState(0);
    const [question, setQuestion] = useState<SpectatorQuestion | null>(null);
    const [questionNumber, setQuestionNumber] = useState(0);
    const [totalQuestions, setTotalQuestions] = useState(0);
    const [timeRemaining, setTimeRemaining] = useState(0);
    const [timeLimit, setTimeLimit] = useState(15);
    const [leaderboard, setLeaderboard] = useState<LeaderboardEntry[]>([]);

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
                setGameState('QUESTION');
            }
            else if (msg.type === 'TIMER') setTimeRemaining(msg.remaining);
            else if (msg.type === 'QUESTION_OVER') {
                setLeaderboard(msg.leaderboard);
                setGameState('LEADERBOARD');
            }
            else if (msg.type === 'PODIUM') {
                setLeaderboard(msg.leaderboard);
                setGameState('PODIUM');
            }
        };

        ws.onerror = () => setGameState('ERROR');
        ws.onclose = () => setGameState('DISCONNECTED');

        return () => ws.close();
    }, [roomCode]);

    const timerProgress = (timeRemaining / timeLimit) * 100;

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
                <div className="min-h-dvh flex flex-col" style={{ maxWidth: '100%', padding: '24px 40px' }}>

                    {(gameState === 'CONNECTING' || gameState === 'ERROR' || gameState === 'DISCONNECTED') && (
                        <div className="flex-1 flex flex-col items-center justify-center animate-in">
                            <p className="text-2xl font-bold mb-2">
                                {gameState === 'CONNECTING' ? 'Connecting...' : gameState === 'ERROR' ? 'Connection Error' : 'Disconnected'}
                            </p>
                            <p className="text-[--text-tertiary]">Room: {roomCode}</p>
                        </div>
                    )}

                    {gameState === 'LOBBY' && (
                        <div className="flex-1 flex flex-col items-center justify-center animate-in">
                            <h1 className="text-4xl font-bold mb-2">Waiting for Players</h1>
                            <p className="room-code mb-8">{roomCode}</p>
                            <p className="text-2xl mb-6">{playerCount} player{playerCount !== 1 ? 's' : ''}</p>
                            <div className="flex flex-wrap gap-3 justify-center max-w-2xl">
                                {players.map((name) => (
                                    <span key={name} className="player-chip" style={{ fontSize: 16, padding: '8px 20px' }}>{name}</span>
                                ))}
                            </div>
                        </div>
                    )}

                    {gameState === 'QUESTION' && question && (
                        <>
                            <div className="flex items-center justify-between py-4">
                                <span className="text-xl text-[--text-tertiary]">Q{questionNumber}/{totalQuestions}</span>
                                <span className={`timer-display ${timeRemaining <= 5 ? 'danger' : timeRemaining <= 10 ? 'warning' : ''}`}>
                                    {timeRemaining}
                                </span>
                            </div>
                            <div className="progress-bar mb-8">
                                <div className={`progress-bar-fill ${timeRemaining <= 5 ? 'danger' : timeRemaining <= 10 ? 'warning' : ''}`}
                                    style={{ width: `${timerProgress}%` }} />
                            </div>
                            <div className="question-card mb-8" style={{ padding: '40px', fontSize: '24px' }}>
                                <p className="question-text" style={{ fontSize: '28px' }}>{question.text}</p>
                            </div>
                            <div className={question.options.length === 2 ? 'answer-grid-tf' : 'answer-grid'} style={{ gap: '16px' }}>
                                {question.options.map((opt, i) => (
                                    <div key={i} className={`answer-btn ${ANSWER_STYLES[i].className}`} style={{ height: 100, fontSize: 20 }}>
                                        <span className="text-3xl opacity-50 mr-3">{ANSWER_STYLES[i].shape}</span>
                                        <span>{opt}</span>
                                    </div>
                                ))}
                            </div>
                        </>
                    )}

                    {gameState === 'LEADERBOARD' && (
                        <div className="flex-1 flex flex-col items-center justify-center animate-in">
                            <h2 className="text-3xl font-bold mb-2">Leaderboard</h2>
                            <p className="text-[--text-tertiary] text-lg mb-8">After question {questionNumber}</p>
                            <div className="w-full max-w-xl space-y-3">
                                {leaderboard.slice(0, 10).map((player, i) => (
                                    <div key={player.nickname} className="leaderboard-item" style={{ padding: '16px 24px' }}>
                                        <div className="flex items-center gap-4">
                                            <span className={`rank-badge ${i === 0 ? 'rank-1' : i === 1 ? 'rank-2' : i === 2 ? 'rank-3' : 'rank-default'}`}
                                                style={{ width: 36, height: 36, fontSize: 16 }}>
                                                {i + 1}
                                            </span>
                                            <span className="font-medium text-lg">{player.nickname}</span>
                                        </div>
                                        <span className="font-bold text-lg">{player.score.toLocaleString()}</span>
                                    </div>
                                ))}
                            </div>
                        </div>
                    )}

                    {gameState === 'PODIUM' && (
                        <div className="flex-1 flex flex-col items-center justify-center animate-in">
                            <h2 className="text-4xl font-bold mb-4">Final Results</h2>
                            <div className="podium-container" style={{ gap: 16, padding: '40px 0' }}>
                                {leaderboard[1] && (
                                    <div className="podium-place podium-2">
                                        <p className="podium-name" style={{ fontSize: 18, maxWidth: 120 }}>{leaderboard[1].nickname}</p>
                                        <div className="podium-bar" style={{ width: 120, height: 120 }}>2</div>
                                        <p className="podium-score" style={{ fontSize: 16 }}>{leaderboard[1].score}</p>
                                    </div>
                                )}
                                {leaderboard[0] && (
                                    <div className="podium-place podium-1">
                                        <p className="text-5xl mb-2">🏆</p>
                                        <p className="podium-name" style={{ fontSize: 18, maxWidth: 120 }}>{leaderboard[0].nickname}</p>
                                        <div className="podium-bar" style={{ width: 120, height: 160 }}>1</div>
                                        <p className="podium-score" style={{ fontSize: 16 }}>{leaderboard[0].score}</p>
                                    </div>
                                )}
                                {leaderboard[2] && (
                                    <div className="podium-place podium-3">
                                        <p className="podium-name" style={{ fontSize: 18, maxWidth: 120 }}>{leaderboard[2].nickname}</p>
                                        <div className="podium-bar" style={{ width: 120, height: 80 }}>3</div>
                                        <p className="podium-score" style={{ fontSize: 16 }}>{leaderboard[2].score}</p>
                                    </div>
                                )}
                            </div>
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
}
