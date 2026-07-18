import { useEffect, useRef, useState } from 'react';
import { apiUrl, apiHeaders } from '../utils/api';

interface DeleteAccountDialogProps {
    /** Called after the account is deleted, so the caller can sign out + refresh. */
    onDeleted: () => void;
    onClose: () => void;
}

/**
 * Account deletion confirmation (SPEC-ACCOUNT-DELETION §4.2).
 *
 * Required by App Store Review Guideline 5.1.1(v): an app that supports account creation must
 * let users delete the account from inside the app.
 *
 * The balance is fetched fresh on open rather than read from a cached value, so the figure here
 * can never contradict the badge the user is looking at (§4.2.1).
 */
export default function DeleteAccountDialog({ onDeleted, onClose }: DeleteAccountDialogProps) {
    const [balance, setBalance] = useState<number | null>(null);
    const [balanceLoaded, setBalanceLoaded] = useState(false);
    const [confirmText, setConfirmText] = useState('');
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState('');
    const mountedRef = useRef(true);

    useEffect(() => {
        mountedRef.current = true;
        (async () => {
            try {
                const res = await fetch(apiUrl('/tokens/balance'), { headers: apiHeaders() });
                const data = res.ok ? await res.json() : null;
                if (!mountedRef.current) return;
                setBalance(typeof data?.balance === 'number' ? data.balance : null);
            } catch {
                if (mountedRef.current) setBalance(null);
            } finally {
                // Loaded-but-null means "we tried and couldn't" -> non-numeric fallback copy,
                // rather than silently omitting the warning as if the balance were zero.
                if (mountedRef.current) setBalanceLoaded(true);
            }
        })();
        return () => { mountedRef.current = false; };
    }, []);

    const handleDelete = async () => {
        if (confirmText !== 'DELETE' || busy) return;
        setBusy(true);
        setError('');
        try {
            const res = await fetch(apiUrl('/account'), {
                method: 'DELETE',
                headers: { ...apiHeaders(), 'Content-Type': 'application/json' },
                body: JSON.stringify({ confirm: 'DELETE' }),
            });
            if (res.ok || res.status === 410) {
                // 410 = already deleted. From the user's point of view that is success, so
                // don't strand them in the dialog with a scary error.
                onDeleted();
                return;
            }
            setBusy(false);
            setError(res.status === 401
                ? 'Your session expired. Please sign in again.'
                : 'Could not delete your account. Please try again.');
        } catch {
            setBusy(false);
            setError('Could not reach the server. Please try again.');
        }
    };

    const hasSparks = balance !== null && balance > 0;
    const sparkWord = balance === 1 ? 'Spark' : 'Sparks';

    return (
        <div
            style={{
                position: 'fixed', inset: 0, zIndex: 9500,
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                background: 'rgba(10, 6, 18, 0.88)', padding: '1rem',
            }}
            onClick={busy ? undefined : onClose}
        >
            <div
                data-testid="delete-account-dialog"
                role="dialog"
                aria-modal="true"
                aria-labelledby="delete-account-title"
                style={{
                    background: 'var(--paper)', borderRadius: 10,
                    padding: '1.6rem 1.4rem', maxWidth: 420, width: '100%',
                    border: '1px solid rgba(255, 90, 120, 0.45)',
                    boxShadow: 'var(--shadow)',
                    maxHeight: '90vh', overflowY: 'auto',
                }}
                onClick={(e) => e.stopPropagation()}
            >
                <h2
                    id="delete-account-title"
                    style={{ fontSize: '1.25rem', fontWeight: 800, color: 'var(--ink)', marginBottom: '0.6rem' }}
                >
                    Delete account?
                </h2>

                {/* Unspent Sparks are the most consequential and least obvious loss, so this
                    leads — but only when there is actually something to lose. Warning about
                    losing nothing trains people to skip the dialog. */}
                {balanceLoaded && hasSparks && (
                    <div
                        data-testid="delete-account-spark-warning"
                        style={{
                            background: 'rgba(255, 199, 107, 0.10)',
                            border: '1px solid rgba(255, 199, 107, 0.45)',
                            borderRadius: 8, padding: '0.7rem 0.8rem', marginBottom: '0.9rem',
                        }}
                    >
                        <p style={{ color: 'var(--gold)', fontWeight: 700, fontSize: '0.95rem', marginBottom: 4 }}>
                            ⚡ You still have {balance} {sparkWord}.
                        </p>
                        <p style={{ color: 'var(--ink-2)', fontSize: '0.82rem', lineHeight: 1.45 }}>
                            They will be permanently destroyed and cannot be recovered, refunded, or moved
                            to another account — including if you sign in again with the same account.
                        </p>
                    </div>
                )}
                {balanceLoaded && balance === null && (
                    <p
                        data-testid="delete-account-spark-warning-fallback"
                        style={{ color: 'var(--ink-2)', fontSize: '0.85rem', marginBottom: '0.9rem' }}
                    >
                        Any unspent Sparks will be permanently destroyed.
                    </p>
                )}

                <p style={{ color: 'var(--ink-2)', fontSize: '0.88rem', lineHeight: 1.55, marginBottom: '0.6rem' }}>
                    This permanently deletes:
                </p>
                <ul style={{ color: 'var(--ink-2)', fontSize: '0.85rem', lineHeight: 1.6, marginBottom: '0.9rem', paddingLeft: '1.1rem' }}>
                    <li>your account and email address</li>
                    <li>your Spark balance and purchase access</li>
                    <li>quizzes and game content you created</li>
                </ul>
                <p style={{ color: 'var(--ink-mute)', fontSize: '0.8rem', lineHeight: 1.5, marginBottom: '1rem' }}>
                    Signing in again creates a brand-new account — previous purchases cannot be restored.
                    This cannot be undone.
                </p>

                <label
                    htmlFor="delete-confirm-input"
                    style={{ display: 'block', color: 'var(--ink-2)', fontSize: '0.82rem', marginBottom: 6 }}
                >
                    Type <strong>DELETE</strong> to confirm
                </label>
                <input
                    id="delete-confirm-input"
                    data-testid="delete-account-confirm-input"
                    value={confirmText}
                    onChange={(e) => setConfirmText(e.target.value)}
                    disabled={busy}
                    autoComplete="off"
                    autoCapitalize="characters"
                    style={{
                        width: '100%', padding: '10px 12px', borderRadius: 8,
                        border: '1px solid var(--rule)', background: 'var(--paper-2, rgba(255,255,255,0.04))',
                        color: 'var(--ink)', fontSize: '1rem', marginBottom: '1rem',
                    }}
                />

                {error && (
                    <p style={{ color: 'var(--accent)', fontSize: '0.82rem', marginBottom: '0.8rem' }}>{error}</p>
                )}

                <button
                    data-testid="delete-account-confirm"
                    onClick={handleDelete}
                    disabled={confirmText !== 'DELETE' || busy}
                    className="btn"
                    style={{
                        width: '100%', padding: '12px', borderRadius: 8, border: 'none',
                        background: confirmText === 'DELETE' && !busy ? 'var(--accent)' : 'var(--rule)',
                        color: confirmText === 'DELETE' && !busy ? 'var(--accent-ink)' : 'var(--ink-mute)',
                        fontWeight: 700, fontSize: '0.95rem',
                        cursor: confirmText === 'DELETE' && !busy ? 'pointer' : 'default',
                    }}
                >
                    {busy ? 'Deleting…' : 'Delete my account'}
                </button>
                <button
                    onClick={onClose}
                    disabled={busy}
                    className="btn"
                    style={{
                        width: '100%', background: 'transparent', color: 'var(--ink-mute)',
                        fontWeight: 500, fontSize: '0.9rem', padding: '10px', border: 'none',
                        cursor: busy ? 'default' : 'pointer', marginTop: '0.4rem',
                    }}
                >
                    Cancel
                </button>
            </div>
        </div>
    );
}
