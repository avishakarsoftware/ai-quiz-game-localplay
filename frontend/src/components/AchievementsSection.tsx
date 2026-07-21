import { useEffect, useState } from 'react';
import { apiFetch } from '../utils/api';

interface Badge {
    id: string;
    emoji: string;
    name: string;
    description: string;
    earned: boolean;
    awarded_at: number | null;
}

/**
 * Achievements / badges (SPEC-ACHIEVEMENTS). The backend owns the catalog and returns every badge
 * with an `earned` flag, so this component just renders what it's told — earned badges lit, the rest
 * dimmed as "locked" hints of what's available.
 */
export default function AchievementsSection() {
    const [badges, setBadges] = useState<Badge[] | null>(null);

    useEffect(() => {
        let cancelled = false;
        apiFetch('/achievements')
            .then(res => (res.ok ? res.json() : null))
            .then(data => { if (!cancelled && Array.isArray(data?.badges)) setBadges(data.badges); })
            .catch(() => { /* best-effort; stay hidden on failure */ });
        return () => { cancelled = true; };
    }, []);

    if (!badges || badges.length === 0) return null;
    const earnedCount = badges.filter(b => b.earned).length;

    return (
        <div className="settings-drawer-row" style={{ flexDirection: 'column', alignItems: 'stretch', gap: 8 }}>
            <div style={{ fontWeight: 700, fontSize: 14 }}>
                Badges <span style={{ opacity: 0.6, fontWeight: 400 }}>({earnedCount}/{badges.length})</span>
            </div>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
                {badges.map(badge => (
                    <div
                        key={badge.id}
                        title={`${badge.name} — ${badge.description}`}
                        aria-label={`${badge.name}: ${badge.earned ? 'earned' : 'locked'}`}
                        data-earned={badge.earned}
                        style={{
                            display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 2,
                            width: 64, padding: '6px 4px', borderRadius: 10,
                            opacity: badge.earned ? 1 : 0.35,
                            filter: badge.earned ? 'none' : 'grayscale(1)',
                        }}
                    >
                        <span style={{ fontSize: 24 }}>{badge.emoji}</span>
                        <span style={{ fontSize: 10, textAlign: 'center', lineHeight: 1.1 }}>{badge.name}</span>
                    </div>
                ))}
            </div>
        </div>
    );
}
