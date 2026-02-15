import { useRef, useEffect } from 'react';
import { QRCodeSVG } from 'qrcode.react';
import CastButton from '../CastButton';
import { type PlayerInfo } from '../../types';
import { AVATAR_COLORS } from '../LeaderboardBarChart.constants';

interface LobbyScreenProps {
    roomCode: string;
    joinUrl: string;
    networkIp: string;
    playerCount: number;
    players: PlayerInfo[];
    onStartGame: () => void;
}

export default function LobbyScreen({ roomCode, joinUrl, networkIp, playerCount, players, onStartGame }: LobbyScreenProps) {
    const prevCountRef = useRef(playerCount);
    const justJoined = playerCount > prevCountRef.current;

    useEffect(() => {
        prevCountRef.current = playerCount;
    }, [playerCount]);

    return (
        <div className="min-h-dvh flex flex-col items-center container-responsive safe-top safe-bottom animate-in">
            <p className="text-[--text-tertiary] mb-1">Join at</p>
            <p className="font-medium mb-6">{networkIp}:5173/join</p>

            <div className="qr-container mb-6">
                <QRCodeSVG value={joinUrl} size={180} bgColor="white" fgColor="#000000" level="H" />
            </div>

            <div className="room-code mb-6">{roomCode}</div>

            {/* Players section */}
            <div className="w-full flex-1 flex flex-col mb-4">
                {playerCount === 0 ? (
                    <div className="flex-1 flex flex-col items-center justify-center">
                        <p className="text-[--text-secondary] font-medium mb-3 animate-pulse">Waiting for players...</p>
                        <div className="flex gap-1.5">
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
                        <div className="flex flex-wrap justify-center gap-2">
                            {players.map((player, i) => (
                                <div key={player.nickname} className="flex items-center gap-2 px-3 py-1.5 rounded-full bg-[--bg-secondary]">
                                    <div
                                        className="w-6 h-6 rounded-full flex items-center justify-center flex-shrink-0"
                                        style={{ backgroundColor: AVATAR_COLORS[i % AVATAR_COLORS.length] }}
                                    >
                                        <span style={{ fontSize: '0.85rem', lineHeight: 1 }}>{player.avatar || player.nickname.slice(0, 2).toUpperCase()}</span>
                                    </div>
                                    <span className="text-sm font-medium">{player.nickname}</span>
                                </div>
                            ))}
                        </div>
                    </>
                )}
            </div>

            <div className="w-full mb-4">
                <CastButton roomCode={roomCode} joinUrl={joinUrl} displayUrl={`${networkIp}:5173/join`} />
            </div>

            <button onClick={onStartGame} disabled={playerCount === 0} className="btn btn-primary btn-glow w-full">
                Start Game
            </button>
        </div>
    );
}
