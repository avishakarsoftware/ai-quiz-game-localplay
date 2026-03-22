import type { EntitlementStatus } from '../hooks/useEntitlement';

interface QuotaBadgeProps {
    entitlement: EntitlementStatus;
    loading: boolean;
}

export default function QuotaBadge({ entitlement, loading }: QuotaBadgeProps) {
    if (loading) return null;

    const { premium, games_remaining, free_games_used, free_games_limit } = entitlement;

    if (premium) {
        return (
            <div className="quota-badge quota-badge-premium">
                <span className="quota-badge-icon">🎟️</span>
                <span>{games_remaining} game{games_remaining !== 1 ? 's' : ''} remaining</span>
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
