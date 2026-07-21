import { useCallback, useRef, useState } from 'react';
import { apiFetch } from '../utils/api';
import { track } from '../utils/analytics';

/**
 * Spark gifting (SPEC-GIFTING). Send sparks to a friend by their code (their referral/"friend"
 * code, shown in the invite section). One idempotency key is held per in-flight attempt so a retry
 * after a network blip never double-sends; it rotates only after a confirmed success.
 */
export default function GiftSection() {
    const [code, setCode] = useState('');
    const [amount, setAmount] = useState('');
    const [msg, setMsg] = useState('');
    const [busy, setBusy] = useState(false);
    const keyRef = useRef<string>(crypto.randomUUID());

    const send = useCallback(async () => {
        const recipient = code.trim().toUpperCase();
        const n = parseInt(amount, 10);
        if (busy || !recipient || !Number.isFinite(n) || n <= 0) return;
        setBusy(true);
        setMsg('');
        try {
            const res = await apiFetch('/tokens/gift', {
                method: 'POST',
                body: JSON.stringify({ code: recipient, amount: n, idempotency_key: keyRef.current }),
            });
            const data = await res.json().catch(() => ({}));
            if (res.ok && data.sent) {
                setMsg(data.duplicate ? 'Already sent — no charge.' : `🎁 Sent ${data.amount} sparks!`);
                setCode('');
                setAmount('');
                keyRef.current = crypto.randomUUID();   // next gift is a distinct transaction
                window.dispatchEvent(new CustomEvent('refresh-sparks'));
                if (!data.duplicate) track('spark_sent_client', { amount: data.amount });
            } else {
                // Keep the same idempotency key so a retry of this same attempt is deduped.
                setMsg(data.detail || "Couldn't send that gift.");
            }
        } catch {
            setMsg('Network error — try again.');
        } finally {
            setBusy(false);
        }
    }, [code, amount, busy]);

    return (
        <div className="settings-drawer-row" style={{ flexDirection: 'column', alignItems: 'stretch', gap: 8 }}>
            <div style={{ fontWeight: 700, fontSize: 14 }}>Gift sparks</div>
            <div style={{ fontSize: 12, opacity: 0.8 }}>
                Send sparks to a friend using their code.
            </div>
            <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                <input
                    value={code}
                    onChange={e => setCode(e.target.value.toUpperCase())}
                    placeholder="Friend's code"
                    maxLength={8}
                    aria-label="Friend's code"
                    style={{ flex: 2, padding: '6px 10px', borderRadius: 8, textTransform: 'uppercase' }}
                />
                <input
                    value={amount}
                    onChange={e => setAmount(e.target.value.replace(/[^0-9]/g, ''))}
                    placeholder="Amount"
                    inputMode="numeric"
                    aria-label="Amount"
                    style={{ flex: 1, padding: '6px 10px', borderRadius: 8, width: 60 }}
                />
                <button type="button" onClick={send} disabled={busy || !code.trim() || !amount.trim()}
                        style={{ padding: '6px 12px', borderRadius: 8, cursor: 'pointer', fontWeight: 600 }}>
                    Send
                </button>
            </div>
            {msg && <div style={{ fontSize: 12, opacity: 0.9 }}>{msg}</div>}
        </div>
    );
}
