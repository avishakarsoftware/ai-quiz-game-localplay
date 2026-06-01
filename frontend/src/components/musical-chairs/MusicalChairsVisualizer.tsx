import { type CSSProperties } from 'react';
import { type MusicalChairsPlayer } from '../../types';

export default function MusicalChairsVisualizer({
    players,
    intensity = 0.35,
    phase,
}: {
    players: MusicalChairsPlayer[];
    intensity?: number;
    phase: string;
}) {
    const pulseMs = Math.max(520, 1300 - intensity * 700);
    return (
        <div className={`mc-visualizer ${phase === 'MC_GRAB' ? 'grab' : ''}`} style={{ '--mc-pulse-ms': `${pulseMs}ms` } as CSSProperties}>
            <div className="mc-visualizer-core">
                <span>{phase === 'MC_GRAB' ? 'GRAB!' : '♪'}</span>
            </div>
            {players.slice(0, 12).map((player, index) => {
                const angle = (index / Math.max(players.length, 1)) * Math.PI * 2;
                const radius = 45;
                return (
                    <div
                        key={player.nickname}
                        className="mc-player-orbit"
                        style={{
                            left: `${50 + Math.cos(angle) * radius}%`,
                            top: `${50 + Math.sin(angle) * radius}%`,
                            animationDelay: `${index * 70}ms`,
                        }}
                    >
                        <span>{player.avatar || player.nickname.slice(0, 2).toUpperCase()}</span>
                    </div>
                );
            })}
        </div>
    );
}
