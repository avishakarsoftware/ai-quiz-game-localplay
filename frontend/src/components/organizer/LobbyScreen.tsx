import { QRCodeSVG } from 'qrcode.react';
import CastButton from '../CastButton';

interface LobbyScreenProps {
    roomCode: string;
    joinUrl: string;
    networkIp: string;
    playerCount: number;
    players: string[];
    onStartGame: () => void;
}

export default function LobbyScreen({ roomCode, joinUrl, networkIp, playerCount, players, onStartGame }: LobbyScreenProps) {
    return (
        <div className="min-h-dvh flex flex-col items-center justify-center container-responsive safe-bottom animate-in">
            <p className="text-[--text-tertiary] mb-1">Join at</p>
            <p className="font-medium mb-6">{networkIp}:5173/join</p>

            <div className="qr-container mb-6">
                <QRCodeSVG value={joinUrl} size={180} bgColor="white" fgColor="#000000" level="H" />
            </div>

            <div className="room-code mb-6">{roomCode}</div>

            <div className="card mb-4 w-full text-center py-4">
                <span className="text-4xl font-bold">{playerCount}</span>
                <span className="text-[--text-tertiary] ml-2">player{playerCount !== 1 ? 's' : ''}</span>
            </div>

            {players.length > 0 && (
                <div className="w-full mb-4 max-h-32 overflow-y-auto no-scrollbar">
                    <div className="flex flex-wrap gap-2 justify-center">
                        {players.map((name) => (
                            <span key={name} className="player-chip animate-in">{name}</span>
                        ))}
                    </div>
                </div>
            )}

            <div className="w-full mb-4">
                <CastButton roomCode={roomCode} joinUrl={joinUrl} displayUrl={`${networkIp}:5173/join`} />
            </div>

            <button onClick={onStartGame} disabled={playerCount === 0} className="btn btn-primary w-full">
                Start Game
            </button>
        </div>
    );
}
