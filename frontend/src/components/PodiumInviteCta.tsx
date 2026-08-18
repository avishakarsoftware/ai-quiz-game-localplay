import { useCallback, useEffect, useState } from 'react';
import { apiUrl } from '../utils/api';
import { track } from '../utils/analytics';

/**
 * "Host your own party" invite, shown to GUESTS on the podium (REVIEW-2026-08 P2).
 *
 * The referral loop existed but was only surfaced in the host's SettingsDrawer, so the people best
 * placed to act on it never saw it. A guest at the final scoreboard has just had a good time and is
 * the most likely next host — and if they start with this host's code, both sides get sparks. That
 * makes the podium the highest-intent moment in the product, and it was empty.
 *
 * Deliberately quiet: it renders NOTHING unless the backend says an invite is available (referrals
 * enabled, room known, host wallet present). A podium is a celebration; a broken or pushy CTA there
 * is worse than no CTA, so every failure path is silence.
 */
interface InvitePayload {
    available: boolean;
    code?: string;
    reward?: number;
    share_url?: string;
}

export default function PodiumInviteCta({ roomCode }: { roomCode: string }) {
    const [invite, setInvite] = useState<InvitePayload | null>(null);
    const [copied, setCopied] = useState(false);

    useEffect(() => {
        if (!roomCode) return;
        let cancelled = false;
        fetch(apiUrl(`/room/${encodeURIComponent(roomCode)}/invite`))
            .then((res) => (res.ok ? res.json() : null))
            .then((data: InvitePayload | null) => {
                if (!cancelled && data?.available && data.code) setInvite(data);
            })
            .catch(() => { /* stay silent — the podium must not depend on this */ });
        return () => { cancelled = true; };
    }, [roomCode]);

    const share = useCallback(async () => {
        if (!invite?.code) return;
        const reward = invite.reward ?? 0;
        const text = `I just played Revelry Games! Host your own party — use code ${invite.code}`
            + (reward ? ` and we both get ${reward} sparks.` : '.');
        const url = invite.share_url || '';
        try {
            if (navigator.share) {
                await navigator.share({ title: 'Revelry Games', text, url });
            } else {
                await navigator.clipboard.writeText(`${text} ${url}`.trim());
                setCopied(true);
            }
            track('podium_invite_shared', { source: 'player_podium' });
        } catch {
            /* the user dismissed the share sheet — not an error */
        }
    }, [invite]);

    if (!invite?.code) return null;

    return (
        <div
            data-testid="podium-invite-cta"
            style={{
                position: 'relative', zIndex: 11, marginTop: '1.25rem', maxWidth: 420,
                padding: '12px 16px', borderRadius: 12, textAlign: 'center',
                border: '1px solid rgba(255, 199, 107, 0.4)', background: 'rgba(255, 199, 107, 0.08)',
            }}
        >
            <p style={{ color: 'var(--text-secondary)', fontSize: '0.9rem', marginBottom: 8 }}>
                Want to host the next one?
            </p>
            <p style={{ color: 'var(--text-tertiary)', fontSize: '0.82rem', marginBottom: 10 }}>
                Start with code{' '}
                <strong data-testid="podium-invite-code" style={{ color: 'var(--accent-warning)' }}>
                    {invite.code}
                </strong>
                {invite.reward ? ` — you both get ${invite.reward} sparks.` : '.'}
            </p>
            <button type="button" className="btn" onClick={share} data-testid="podium-invite-share">
                {copied ? 'Copied!' : 'Share the invite'}
            </button>
        </div>
    );
}
