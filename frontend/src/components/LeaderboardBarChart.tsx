import { useId } from 'react';
import { BarChart, Bar, XAxis, YAxis, Cell, LabelList, ResponsiveContainer } from 'recharts';
import { AVATAR_COLORS, BAR_COLORS } from './LeaderboardBarChart.constants';
import type { LeaderboardEntry } from '../types';

type ChartSize = 'compact' | 'large';

interface LeaderboardBarChartProps {
    leaderboard: LeaderboardEntry[];
    maxEntries?: number;
    size?: ChartSize;
    highlightNickname?: string;
    animate?: boolean;
}

const SIZE_CONFIG = {
    compact: {
        rowHeight: 56,
        barSize: 20,
        rankBadgeSize: 28,
        avatarSize: 28,
        nameFontSize: 14,
        nameMaxWidth: 80,
        scoreFontSize: 14,
        tickWidth: 160,
        barRadius: 10,
        rightMargin: 50,
    },
    large: {
        rowHeight: 72,
        barSize: 26,
        rankBadgeSize: 36,
        avatarSize: 40,
        nameFontSize: 18,
        nameMaxWidth: 120,
        scoreFontSize: 18,
        tickWidth: 230,
        barRadius: 12,
        rightMargin: 60,
    },
} as const;

interface TickPayload {
    value: string;
    index: number;
}

interface CustomTickProps {
    x?: number;
    y?: number;
    payload?: TickPayload;
    config: (typeof SIZE_CONFIG)[ChartSize];
    biggestMoverNickname: string | null;
    biggestMoverChange: number;
    highlightNickname?: string;
    avatarMap: Record<string, string>;
}

function CustomYAxisTick({ x: _x, y, payload, config, biggestMoverNickname, biggestMoverChange, highlightNickname, avatarMap }: CustomTickProps) {
    if (!payload) return null;
    const index = payload.index;
    const nickname = payload.value;
    const isMover = nickname === biggestMoverNickname;
    const isHighlighted = nickname === highlightNickname;

    const height = config.rankBadgeSize + 12;

    return (
        <foreignObject
            x={0}
            y={(y ?? 0) - height / 2}
            width={config.tickWidth}
            height={height}
        >
            <div style={{
                display: 'flex',
                alignItems: 'center',
                gap: 8,
                height: '100%',
                paddingLeft: 4,
            }}>
                <span
                    className={`rank-badge ${index === 0 ? 'rank-1' : index === 1 ? 'rank-2' : index === 2 ? 'rank-3' : 'rank-default'}`}
                    style={{ width: config.rankBadgeSize, height: config.rankBadgeSize, fontSize: config.rankBadgeSize * 0.5 }}
                >
                    {index + 1}
                </span>
                <div style={{
                    width: config.avatarSize,
                    height: config.avatarSize,
                    borderRadius: '50%',
                    backgroundColor: AVATAR_COLORS[index % AVATAR_COLORS.length],
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    fontSize: avatarMap[nickname] ? config.avatarSize * 0.55 : config.avatarSize * 0.35,
                    fontWeight: 700,
                    color: 'white',
                    flexShrink: 0,
                    lineHeight: 1,
                }}>
                    {avatarMap[nickname] || nickname.slice(0, 2).toUpperCase()}
                </div>
                <span style={{
                    fontWeight: isHighlighted ? 700 : 500,
                    fontSize: config.nameFontSize,
                    maxWidth: config.nameMaxWidth,
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
                    whiteSpace: 'nowrap',
                    color: isHighlighted ? 'var(--accent-primary)' : 'var(--text-primary)',
                }}>
                    {nickname}
                </span>
                {isMover && biggestMoverChange !== 0 && (
                    <span style={{
                        fontSize: config.nameFontSize * 0.8,
                        fontWeight: 700,
                        color: biggestMoverChange > 0 ? 'var(--accent-success)' : 'var(--accent-danger)',
                    }}>
                        {biggestMoverChange > 0 ? `↑${biggestMoverChange}` : `↓${Math.abs(biggestMoverChange)}`}
                    </span>
                )}
            </div>
        </foreignObject>
    );
}

interface ScoreLabelProps {
    x?: number;
    y?: number;
    width?: number;
    height?: number;
    value?: number;
    config: (typeof SIZE_CONFIG)[ChartSize];
}

function CustomScoreLabel({ x, y, width, height, value, config }: ScoreLabelProps) {
    return (
        <text
            x={(x ?? 0) + (width ?? 0) + 8}
            y={(y ?? 0) + (height ?? 0) / 2}
            dominantBaseline="central"
            fill="var(--text-primary)"
            fontWeight={700}
            fontSize={config.scoreFontSize}
            style={{ fontVariantNumeric: 'tabular-nums' }}
        >
            {value}
        </text>
    );
}

export default function LeaderboardBarChart({
    leaderboard,
    maxEntries = 10,
    size = 'compact',
    highlightNickname,
    animate = true,
}: LeaderboardBarChartProps) {
    const gid = useId();
    const config = SIZE_CONFIG[size];
    const entries = leaderboard.slice(0, maxEntries);
    const maxScore = Math.max(...entries.map(p => p.score), 1);

    // Find biggest mover
    let biggestMoverNickname: string | null = null;
    let biggestMoverChange = 0;
    let biggestAbs = 0;
    entries.forEach((p) => {
        const abs = Math.abs(p.rank_change || 0);
        if (abs > biggestAbs) {
            biggestAbs = abs;
            biggestMoverNickname = p.nickname;
            biggestMoverChange = p.rank_change || 0;
        }
    });

    const avatarMap: Record<string, string> = {};
    entries.forEach((p) => { if (p.avatar) avatarMap[p.nickname] = p.avatar; });

    const chartData = entries.map((player) => ({
        nickname: player.nickname,
        score: player.score,
    }));

    const chartHeight = entries.length * config.rowHeight;

    function getBarFill(index: number): string {
        if (index === 0) return `url(#gold-${gid})`;
        if (index === 1) return `url(#silver-${gid})`;
        if (index === 2) return `url(#bronze-${gid})`;
        return `url(#accent-${gid})`;
    }

    return (
        <ResponsiveContainer width="100%" height={chartHeight}>
            <BarChart
                layout="vertical"
                data={chartData}
                margin={{ top: 0, right: config.rightMargin, bottom: 0, left: 0 }}
            >
                <defs>
                    <linearGradient id={`gold-${gid}`} x1="0" y1="0" x2="1" y2="0">
                        <stop offset="0%" stopColor={BAR_COLORS.gold[0]} />
                        <stop offset="100%" stopColor={BAR_COLORS.gold[1]} />
                    </linearGradient>
                    <linearGradient id={`silver-${gid}`} x1="0" y1="0" x2="1" y2="0">
                        <stop offset="0%" stopColor={BAR_COLORS.silver[0]} />
                        <stop offset="100%" stopColor={BAR_COLORS.silver[1]} />
                    </linearGradient>
                    <linearGradient id={`bronze-${gid}`} x1="0" y1="0" x2="1" y2="0">
                        <stop offset="0%" stopColor={BAR_COLORS.bronze[0]} />
                        <stop offset="100%" stopColor={BAR_COLORS.bronze[1]} />
                    </linearGradient>
                    <linearGradient id={`accent-${gid}`} x1="0" y1="0" x2="1" y2="0">
                        <stop offset="0%" stopColor="var(--accent-primary)" />
                        <stop offset="100%" stopColor="var(--accent-secondary)" />
                    </linearGradient>
                </defs>
                <XAxis type="number" domain={[0, maxScore]} hide />
                <YAxis
                    type="category"
                    dataKey="nickname"
                    width={config.tickWidth}
                    tick={(props: Record<string, unknown>) => (
                        <CustomYAxisTick
                            {...(props as unknown as CustomTickProps)}
                            config={config}
                            biggestMoverNickname={biggestMoverNickname}
                            biggestMoverChange={biggestMoverChange}
                            highlightNickname={highlightNickname}
                            avatarMap={avatarMap}
                        />
                    )}
                    tickLine={false}
                    axisLine={false}
                />
                <Bar
                    dataKey="score"
                    barSize={config.barSize}
                    radius={[0, config.barRadius, config.barRadius, 0]}
                    background={{ fill: 'rgba(255,255,255,0.08)', radius: config.barRadius }}
                    isAnimationActive={animate}
                    animationDuration={800}
                    animationEasing="ease-out"
                    animationBegin={300}
                >
                    {chartData.map((_entry, i) => (
                        <Cell key={i} fill={getBarFill(i)} />
                    ))}
                    <LabelList
                        dataKey="score"
                        position="right"
                        content={(props) => <CustomScoreLabel {...(props as ScoreLabelProps)} config={config} />}
                    />
                </Bar>
            </BarChart>
        </ResponsiveContainer>
    );
}
