import { useState, useEffect, useCallback } from 'react';
import { apiFetch } from '../utils/api';
import { track } from '../utils/analytics';

interface ReferralInfo {
    code: string;
    share_url: string;
    reward: number;
}

/** Read a ?ref=CODE param from the launch URL (referral deep link), if present. */
function pendingRefFromUrl(): string {
    try {
        return (new URLSearchParams(window.location.search).get('ref') || '').trim().toUpperCase();
    } catch {
        return '';
    }
}

export default function ReferralSection() {
    const [info, setInfo] = useState<ReferralInfo | null>(null);
    const [redeemCode, setRedeemCode] = useState(pendingRefFromUrl());
    const [msg, setMsg] = useState('');
    const [busy, setBusy] = useState(false);

    useEffect(() => {
        let cancelled = false;
        apiFetch('/referral/code')
            .then(res => (res.ok ? res.json() : null))
            .then(data => { if (!cancelled && data?.code) setInfo(data); })
            .catch(() => { /* referral is best-effort; stay hidden on failure */ });
        return () => { cancelled = true; };
    }, []);

    const share = useCallback(async () => {
        if (!info) return;
        const text = `Join me on Revelry Games — use my code ${info.code} and we both get ${info.reward} sparks!`;
        try {
            if (navigator.share) {
                await navigator.share({ title: 'Revelry Games', text, url: info.share_url });
            } else {
                await navigator.clipboard.writeText(`${text} ${info.share_url}`);
                setMsg('Invite copied to clipboard!');
            }
            track('referral_shared');
        } catch { /* user cancelled share sheet */ }
    }, [info]);

    const redeem = useCallback(async () => {
        const code = redeemCode.trim().toUpperCase();
        if (!code || busy) return;
        setBusy(true);
        setMsg('');
        try {
            const res = await apiFetch('/referral/redeem', {
                method: 'POST',
                body: JSON.stringify({ code }),
            });
            const data = await res.json().catch(() => ({}));
            if (res.ok && data.redeemed) {
                setMsg(`🎉 +${data.reward} sparks!`);
                setRedeemCode('');
                window.dispatchEvent(new CustomEvent('refresh-sparks'));
                track('referral_redeemed_client');
            } else {
                setMsg(data.detail || "Couldn't redeem that code.");
            }
        } catch {
            setMsg('Network error — try again.');
        } finally {
            setBusy(false);
        }
    }, [redeemCode, busy]);

    if (!info) return null;

    return (
        <div className="settings-drawer-row" style={{ flexDirection: 'column', alignItems: 'stretch', gap: 8 }}>
            <div style={{ fontWeight: 700, fontSize: 14 }}>Invite friends</div>
            <div style={{ fontSize: 12, opacity: 0.8 }}>
                Share your code — you both get {info.reward} sparks.
            </div>
            <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                <code style={{ fontSize: 16, fontWeight: 800, letterSpacing: 2, flex: 1 }}>{info.code}</code>
                <button type="button" onClick={share} className="settings-share-btn"
                        style={{ padding: '6px 12px', borderRadius: 8, cursor: 'pointer', fontWeight: 600 }}>
                    Share
                </button>
            </div>
            <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginTop: 4 }}>
                <input
                    value={redeemCode}
                    onChange={e => setRedeemCode(e.target.value.toUpperCase())}
                    placeholder="Have a code?"
                    maxLength={8}
                    aria-label="Referral code"
                    style={{ flex: 1, padding: '6px 10px', borderRadius: 8, textTransform: 'uppercase' }}
                />
                <button type="button" onClick={redeem} disabled={busy || !redeemCode.trim()}
                        style={{ padding: '6px 12px', borderRadius: 8, cursor: 'pointer', fontWeight: 600 }}>
                    Redeem
                </button>
            </div>
            {msg && <div style={{ fontSize: 12, opacity: 0.9 }}>{msg}</div>}
        </div>
    );
}
