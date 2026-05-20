import Avatar from './Avatar';
import type { CSSProperties } from 'react';

type ChipPlayer = {
    name?: string;
    nickname?: string;
    avatar?: string;
};

interface PlayerChipProps {
    player: ChipPlayer;
    you?: boolean;
    style?: CSSProperties;
}

export default function PlayerChip({ player, you = false, style }: PlayerChipProps) {
    const label = player.nickname || player.name || 'Player';

    return (
        <span className={`player-chip ${you ? 'player-chip-you' : ''}`} style={style}>
            <Avatar player={player} size={26} you={you} decorative />
            <span className="player-chip-name">{label}</span>
        </span>
    );
}
