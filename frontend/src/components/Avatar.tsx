type AvatarPlayer = {
    name?: string;
    nickname?: string;
    avatar?: string;
};

interface AvatarProps {
    player: AvatarPlayer;
    size?: number;
    you?: boolean;
    fallbackText?: string;
    decorative?: boolean;
}

function initialsFor(player: AvatarPlayer, fallbackText?: string): string {
    const label = player.nickname || player.name || fallbackText || '?';
    return label
        .trim()
        .split(/\s+/)
        .slice(0, 2)
        .map((part) => part[0]?.toUpperCase() || '')
        .join('') || '?';
}

export default function Avatar({ player, size = 32, you = false, fallbackText, decorative = false }: AvatarProps) {
    const label = player.nickname || player.name || fallbackText || 'Player';
    const value = player.avatar || initialsFor(player, fallbackText);

    return (
        <span
            className={`velvet-avatar ${you ? 'velvet-avatar-you' : ''}`}
            style={{ width: size, height: size, minWidth: size, fontSize: Math.round(size * 0.56) }}
            aria-label={decorative ? undefined : label}
            aria-hidden={decorative ? true : undefined}
            role={decorative ? undefined : 'img'}
        >
            {value}
        </span>
    );
}
