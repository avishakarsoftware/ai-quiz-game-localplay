import { useState, useEffect, useCallback } from 'react';
import { apiFetch } from '../utils/api';

export interface TokenStatus {
    balance: number;
    has_purchased: boolean;
    daily_bonus_available: boolean;
    daily_bonus_granted?: boolean;
    bonus_amount?: number;
    bonus_streak?: number;
    streak_next_reward?: number;
    cost_generate: number;
    cost_room: number;
    ads_remaining_today?: number;
    max_balance?: number;
    /** First-party grace (REVIEW-2026-08 P1): free rooms for a new host's first evening. */
    party_grace?: {
        state: 'available' | 'active' | 'expired' | 'ineligible';
        until: number;
        rooms_used: number;
    };
}

const DEFAULT: TokenStatus = {
    balance: 0,
    has_purchased: false,
    daily_bonus_available: false,
    daily_bonus_granted: false,
    bonus_amount: 0,
    bonus_streak: 0,
    streak_next_reward: 10,
    cost_generate: 1,
    cost_room: 10,
    ads_remaining_today: 5,
};

function fetchTokenBalance(): Promise<TokenStatus> {
    return apiFetch('/tokens/balance')
        .then(res => res.ok ? res.json().catch(() => DEFAULT) : DEFAULT)
        .catch(() => DEFAULT);
}

export function useTokenBalance() {
    const [tokenStatus, setTokenStatus] = useState<TokenStatus>(DEFAULT);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        let cancelled = false;
        fetchTokenBalance()
            .then(data => { if (!cancelled) setTokenStatus(data); })
            .finally(() => { if (!cancelled) setLoading(false); });
        return () => { cancelled = true; };
    }, []);

    const refresh = useCallback(() => {
        fetchTokenBalance().then(setTokenStatus);
    }, []);

    // Listen for global refresh events (e.g. after spending sparks)
    useEffect(() => {
        const handler = () => refresh();
        window.addEventListener('refresh-sparks', handler);
        return () => window.removeEventListener('refresh-sparks', handler);
    }, [refresh]);

    return { tokenStatus, loading, refresh };
}
