interface TimerRingProps {
    remaining: number;
    total: number;
    size?: number;
}

export default function TimerRing({ remaining, total, size = 80 }: TimerRingProps) {
    const strokeWidth = 4;
    const radius = (size - strokeWidth) / 2;
    const circumference = 2 * Math.PI * radius;
    const progress = remaining / total;
    const dashOffset = circumference * (1 - progress);

    const color = remaining <= 5 ? 'var(--accent-danger)'
        : remaining <= 10 ? 'var(--accent-warning)'
        : 'var(--accent-primary)';

    const critical = remaining <= 5 && remaining > 0;

    return (
        <div
            className={`relative inline-flex items-center justify-center ${critical ? 'timer-critical' : ''}`}
            style={{ width: size, height: size }}
        >
            <svg width={size} height={size} className="transform -rotate-90">
                <circle
                    cx={size / 2}
                    cy={size / 2}
                    r={radius}
                    fill="none"
                    stroke="var(--bg-tertiary)"
                    strokeWidth={strokeWidth}
                />
                <circle
                    cx={size / 2}
                    cy={size / 2}
                    r={radius}
                    fill="none"
                    stroke={color}
                    strokeWidth={strokeWidth}
                    strokeLinecap="round"
                    strokeDasharray={circumference}
                    strokeDashoffset={dashOffset}
                    style={{ transition: 'stroke-dashoffset 1s linear, stroke 0.3s ease' }}
                />
            </svg>
            <span
                className={`absolute font-bold tabular-nums ${critical ? 'timer-number-pulse' : ''}`}
                style={{ fontSize: size * 0.35, color }}
            >
                {remaining}
            </span>
        </div>
    );
}
