import type { EntitlementStatus } from '../hooks/useEntitlement';

interface QuotaBadgeProps {
    entitlement: EntitlementStatus;
    loading: boolean;
}

function daysRemaining(expiresAt: string | null): number | null {
    if (!expiresAt) return null;
    const expTime = new Date(expiresAt).getTime();
    if (isNaN(expTime)) return null;
    const diff = expTime - Date.now();
    if (diff <= 0) return 0;
    return Math.ceil(diff / (1000 * 60 * 60 * 24));
}

export default function QuotaBadge({ entitlement, loading }: QuotaBadgeProps) {
    if (loading) return null;

    const { premium, games_remaining, expires_at, free_games_used, free_games_limit } = entitlement;

    if (premium) {
        const days = daysRemaining(expires_at);
        const daysText = days !== null ? ` · ${days} day${days !== 1 ? 's' : ''} left` : '';
        return (
            <div className="quota-badge quota-badge-premium">
                <span className="quota-badge-icon">🎟️</span>
                <span>{games_remaining} game{games_remaining !== 1 ? 's' : ''} remaining{daysText}</span>
            </div>
        );
    }

    const remaining = Math.max(0, free_games_limit - free_games_used);

    return (
        <div className={`quota-badge ${remaining === 0 ? 'quota-badge-exhausted' : ''}`}>
            <span className="quota-badge-icon">{remaining === 0 ? '🔒' : '🎮'}</span>
            <span>{free_games_used} of {free_games_limit} free game{free_games_limit !== 1 ? 's' : ''} used</span>
        </div>
    );
}
