import { useState, useEffect, useCallback } from 'react';
import { apiFetch } from '../utils/api';

export interface TokenStatus {
    balance: number;
    has_purchased: boolean;
    daily_bonus_available: boolean;
    daily_bonus_granted?: boolean;
    bonus_amount?: number;
    cost_generate: number;
    cost_room: number;
    ads_remaining_today?: number;
}

const DEFAULT: TokenStatus = {
    balance: 0,
    has_purchased: false,
    daily_bonus_available: false,
    daily_bonus_granted: false,
    bonus_amount: 0,
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

    return { tokenStatus, loading, refresh };
}
