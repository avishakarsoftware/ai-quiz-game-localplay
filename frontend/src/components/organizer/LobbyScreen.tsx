import { useState, useRef, useEffect } from 'react';
import { QRCodeSVG } from 'qrcode.react';
import CastButton from '../CastButton';
import { type PlayerInfo } from '../../types';
import { AVATAR_COLORS } from '../LeaderboardBarChart.constants';

interface LobbyScreenProps {
    roomCode: string;
    joinUrl: string;
    playerCount: number;
    players: PlayerInfo[];
    locked: boolean;
    onStartGame: () => void;
    onToggleLock: () => void;
}

export default function LobbyScreen({ roomCode, joinUrl, playerCount, players, locked, onStartGame, onToggleLock }: LobbyScreenProps) {
    const prevCountRef = useRef(playerCount);
    const [justJoined, setJustJoined] = useState(false);
    const [copied, setCopied] = useState(false);

    useEffect(() => {
        if (playerCount > prevCountRef.current) {
            // Flagging a player-join bump — this is derived from a prop change, not a cascading render.
            // eslint-disable-next-line react-hooks/set-state-in-effect
            setJustJoined(true);
            const timer = setTimeout(() => setJustJoined(false), 600);
            prevCountRef.current = playerCount;
            return () => clearTimeout(timer);
        }
        prevCountRef.current = playerCount;
    }, [playerCount]);

    const shareLink = async () => {
        if (navigator.share) {
            try {
                await navigator.share({ title: 'Join my quiz!', url: joinUrl });
                return;
            } catch { /* user cancelled share dialog */ }
        }
        await navigator.clipboard.writeText(joinUrl);
        setCopied(true);
        setTimeout(() => setCopied(false), 2000);
    };

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
            <p className="text-[--text-tertiary] text-sm mb-2 text-center">{new URL(joinUrl).host}{new URL(joinUrl).pathname}</p>

            {/* Share & Lock row */}
            <div style={{ display: 'flex', flexDirection: 'row', gap: 10, alignItems: 'center', justifyContent: 'center', marginBottom: 4 }}>
                <button onClick={shareLink} className="btn btn-secondary" style={{ fontSize: '0.875rem', padding: '8px 20px', height: 40 }}>
                    {copied ? 'Copied!' : 'Share Link'}
                </button>
                <button onClick={onToggleLock} className="btn btn-secondary" style={{ fontSize: '0.875rem', padding: '8px 16px', height: 40, gap: 6 }}>
                    {locked ? '\uD83D\uDD12 Locked' : '\uD83D\uDD13 Open'}
                </button>
            </div>
            <p className="text-[--text-tertiary] mb-6" style={{ fontSize: '0.7rem', textAlign: 'center' }}>
                {locked ? 'Room is locked — no new players can join' : 'Lock the room to stop new players from joining'}
            </p>

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
                <CastButton roomCode={roomCode} />
            </div>

            <button onClick={onStartGame} disabled={playerCount === 0} className="btn btn-primary btn-glow w-full">
                Start Game
            </button>
        </div>
    );
}
