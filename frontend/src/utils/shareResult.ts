import { apiFetch } from './api';
import { track } from './analytics';
import type { LeaderboardEntry } from '../types';

/** Mint a shareable result card for the finished game and open the OS share sheet (SPEC-SHARE-CARD). */
export async function shareGameResult(gameType: string, leaderboard: LeaderboardEntry[]): Promise<void> {
    const winner = leaderboard?.[0]?.nickname || '';
    const topScore = leaderboard?.[0]?.score ?? 0;
    const playerCount = leaderboard?.length ?? 0;
    try {
        const res = await apiFetch('/share/game', {
            method: 'POST',
            body: JSON.stringify({ game_type: gameType, winner, top_score: topScore, player_count: playerCount }),
        });
        const data = await res.json().catch(() => ({}));
        const url: string | undefined = data.share_url;
        if (!url) return;
        const text = winner
            ? `${winner} won with ${topScore} in Revelry Games!`
            : 'We just played Revelry Games!';
        if (navigator.share) {
            await navigator.share({ title: 'Revelry Games', text, url });
        } else {
            await navigator.clipboard.writeText(`${text} ${url}`);
        }
        track('share_result_clicked', { game_type: gameType });
    } catch {
        /* user cancelled the share sheet, or the request failed — best-effort */
    }
}
