import { useTokenBalance } from '../hooks/useTokenBalance';

/**
 * First-party grace banner (REVIEW-2026-08 P1).
 *
 * The economy used to paywall a new host at ~game 2 — mid-party. Rooms are now free for the
 * host's first evening (PARTY_GRACE_HOURS server-side), and this banner is how they find out:
 * once on the catalog before their first room ("your first party's on us"), then with the
 * live deadline while the window is open. States other than available/active render nothing —
 * veterans and post-window hosts see the normal spark economy with no clutter.
 */
export default function PartyGraceBanner() {
    const { tokenStatus } = useTokenBalance();
    const grace = tokenStatus.party_grace;
    if (!grace || (grace.state !== 'available' && grace.state !== 'active')) return null;

    const message = grace.state === 'available'
        ? 'Your first party’s on us — game rooms are free for your first evening.'
        : `Free game rooms until ${new Date(grace.until * 1000).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })} — enjoy the party!`;

    return (
        <div
            data-testid="party-grace-banner"
            role="status"
            style={{
                margin: '0.75rem auto 0', maxWidth: 560, padding: '10px 14px',
                borderRadius: 10, textAlign: 'center', fontSize: '0.88rem', fontWeight: 600,
                color: 'var(--accent-warning)', border: '1px solid rgba(255, 199, 107, 0.45)',
                background: 'rgba(255, 199, 107, 0.08)',
            }}
        >
            🎉 {message}
        </div>
    );
}
