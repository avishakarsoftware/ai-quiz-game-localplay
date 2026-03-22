import { useState, useEffect, useCallback } from 'react';
import { apiFetch } from '../utils/api';

export interface EntitlementStatus {
    premium: boolean;
    status: string | null;
    games_remaining: number;
    expires_at: string | null;
    free_games_used: number;
    free_games_limit: number;
    pending_purchase: boolean;
}

const DEFAULT: EntitlementStatus = {
    premium: false,
    status: null,
    games_remaining: 0,
    expires_at: null,
    free_games_used: 0,
    free_games_limit: 3,
    pending_purchase: false,
};

function fetchEntitlement(): Promise<EntitlementStatus> {
    return apiFetch('/entitlements/current')
        .then(res => res.ok ? res.json().catch(() => DEFAULT) : DEFAULT)
        .catch(() => DEFAULT);
}

export function useEntitlement() {
    const [entitlement, setEntitlement] = useState<EntitlementStatus>(DEFAULT);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        let cancelled = false;
        fetchEntitlement()
            .then(data => { if (!cancelled) setEntitlement(data); })
            .finally(() => { if (!cancelled) setLoading(false); });
        return () => { cancelled = true; };
    }, []);

    const refresh = useCallback(() => {
        fetchEntitlement().then(setEntitlement);
    }, []);

    return { entitlement, loading, refresh };
}
