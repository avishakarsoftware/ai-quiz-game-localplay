import { useRef, useEffect } from 'react';
import { QRCodeSVG } from 'qrcode.react';
import CastButton from '../CastButton';
import { type PlayerInfo } from '../../types';
import { AVATAR_COLORS } from '../LeaderboardBarChart.constants';

interface LobbyScreenProps {
    roomCode: string;
    joinUrl: string;
    playerCount: number;
    players: PlayerInfo[];
    onStartGame: () => void;
}

export default function LobbyScreen({ roomCode, joinUrl, playerCount, players, onStartGame }: LobbyScreenProps) {
    const prevCountRef = useRef(playerCount);
    const justJoined = playerCount > prevCountRef.current;

    useEffect(() => {
        prevCountRef.current = playerCount;
    }, [playerCount]);

    return (
        <div className="min-h-dvh flex flex-col items-center justify-center container-responsive safe-top safe-bottom animate-in">
            <div className="screen-hero">
                <h1 className="hero-title">Game Lobby</h1>
                <p className="hero-subtitle">Share the code below to invite players</p>
            </div>

            <div className="text-center mb-4">
                <div className="qr-container">
                    <QRCodeSVG value={joinUrl} size={180} bgColor="white" fgColor="#000000" level="H" />
                </div>
            </div>

            <div className="room-code mb-2 text-center">{roomCode}</div>
            <p className="text-[--text-tertiary] text-sm mb-6 text-center">{new URL(joinUrl).host}{new URL(joinUrl).pathname}</p>

            {/* Players section */}
            <div className="w-full mb-3">
                {playerCount === 0 ? (
                    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', padding: '8px 0' }}>
                        <p className="text-[--text-secondary] font-medium mb-3 animate-pulse">Waiting for players...</p>
                        <div style={{ display: 'flex', gap: 6 }}>
                            {[0, 1, 2].map((i) => (
                                <div key={i} className="w-2 h-2 bg-[--text-tertiary] rounded-full animate-bounce"
                                    style={{ animationDelay: `${i * 0.15}s` }} />
                            ))}
                        </div>
                    </div>
                ) : (
                    <>
                        <p className={`text-center mb-3 ${justJoined ? 'lobby-count-bump' : ''}`} key={playerCount}>
                            <span className="text-2xl font-bold">{playerCount}</span>{' '}
                            <span className="text-[--text-secondary] font-medium">player{playerCount !== 1 ? 's' : ''}</span>
                        </p>
                        <div style={{ display: 'flex', flexWrap: 'wrap', justifyContent: 'center', gap: 8 }}>
                            {players.map((player, i) => (
                                <div key={player.nickname} style={{ display: 'inline-flex', alignItems: 'center', gap: 8, padding: '8px 16px', borderRadius: 9999, background: 'var(--bg-secondary)' }}>
                                    <div
                                        style={{ width: 36, height: 36, minWidth: 36, borderRadius: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center', backgroundColor: AVATAR_COLORS[i % AVATAR_COLORS.length] }}
                                    >
                                        <span style={{ fontSize: '1.25rem', lineHeight: 1 }}>{player.avatar || player.nickname.slice(0, 2).toUpperCase()}</span>
                                    </div>
                                    <span style={{ fontSize: '1rem', fontWeight: 500 }}>{player.nickname}</span>
                                </div>
                            ))}
                        </div>
                    </>
                )}
            </div>

            <div className="w-full mb-4">
                <CastButton roomCode={roomCode} joinUrl={joinUrl} />
            </div>

            <button onClick={onStartGame} disabled={playerCount === 0} className="btn btn-primary btn-glow w-full">
                Start Game
            </button>
        </div>
    );
}
