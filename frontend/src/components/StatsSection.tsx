import { useEffect, useState } from 'react';
import { apiFetch } from '../utils/api';

interface ByGameType {
    game_type: string;
    game_title: string;
    count: number;
}

interface Stats {
    available: boolean;
    games_hosted: number;
    players_entertained: number;
    distinct_games_played: number;
    favorite_game_type: string;
    favorite_game_title: string;
    last_played_at: number;
    by_game_type: ByGameType[];
}

/**
 * Hosting stats (SPEC-GAME-STATS). These are "games you hosted", not "games you played" —
 * guests join from their phones without wallets, so the host's wallet is the only identity a
 * completed game can be attributed to. The copy says "hosted" so the number is never read as
 * something it isn't.
 *
 * Hidden entirely until the host has finished a game: a wall of zeros is worse than no section.
 */
export default function StatsSection() {
    const [stats, setStats] = useState<Stats | null>(null);

    useEffect(() => {
        let cancelled = false;
        apiFetch('/stats')
            .then(res => (res.ok ? res.json() : null))
            .then(data => { if (!cancelled && data) setStats(data); })
            .catch(() => { /* best-effort; stay hidden on failure */ });
        return () => { cancelled = true; };
    }, []);

    // `available: false` means the backend couldn't read stats (e.g. table not applied yet).
    if (!stats || !stats.available || stats.games_hosted === 0) return null;

    const top = stats.by_game_type.slice(0, 3);

    return (
        <div className="settings-drawer-row" style={{ flexDirection: 'column', alignItems: 'stretch', gap: 8 }}>
            <div style={{ fontWeight: 700, fontSize: 14 }}>Your parties</div>

            <div style={{ display: 'flex', gap: 8 }}>
                <Tile value={stats.games_hosted} label={stats.games_hosted === 1 ? 'game hosted' : 'games hosted'} />
                <Tile value={stats.players_entertained} label="players" />
                <Tile value={stats.distinct_games_played} label="game types" />
            </div>

            {stats.favorite_game_title && (
                <div style={{ fontSize: 13, opacity: 0.75 }}>
                    Favourite: <strong>{stats.favorite_game_title}</strong>
                </div>
            )}

            {top.length > 1 && (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                    {top.map(row => (
                        <div key={row.game_type} style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, opacity: 0.7 }}>
                            <span>{row.game_title || row.game_type}</span>
                            <span>{row.count}</span>
                        </div>
                    ))}
                </div>
            )}
        </div>
    );
}

function Tile({ value, label }: { value: number; label: string }) {
    return (
        <div
            style={{
                flex: 1,
                textAlign: 'center',
                padding: '10px 6px',
                borderRadius: 10,
                background: 'rgba(255,255,255,0.05)',
            }}
        >
            <div style={{ fontWeight: 700, fontSize: 18 }}>{value}</div>
            <div style={{ fontSize: 11, opacity: 0.65 }}>{label}</div>
        </div>
    );
}
