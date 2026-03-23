import type { TokenStatus } from '../hooks/useTokenBalance';
import SparkCoin from './SparkCoin';

interface TokenBadgeProps {
    tokenStatus: TokenStatus;
    loading: boolean;
}

export default function TokenBadge({ tokenStatus, loading }: TokenBadgeProps) {
    if (loading) return null;

    const { balance } = tokenStatus;
    const isLow = balance > 0 && balance < 10;
    const isEmpty = balance === 0;

    const className = `quota-badge ${isEmpty ? 'quota-badge-exhausted' : isLow ? 'quota-badge-warning' : 'quota-badge-premium'}`;

    return (
        <div className={className}>
            <span className="spark-coin-icon"><SparkCoin size={18} /></span>
            <span>{balance} spark{balance !== 1 ? 's' : ''}</span>
        </div>
    );
}
