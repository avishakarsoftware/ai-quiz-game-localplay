import { useEffect, useRef, useState } from 'react';
import { apiUrl, apiHeaders } from '../utils/api';
import { getDeviceId, setCheckoutPending, clearCheckoutPending } from '../utils/storage';
import { getPlatform } from '../utils/platform';
import { isIAPConfigured, getNativePrices, buySparksNative } from '../utils/iap';
import { SPARK_PACKS } from '../utils/sparkPacks';
import { track } from '../utils/analytics';
import SparkCoin from './SparkCoin';

interface SparkPurchaseModalProps {
    /** Called after sparks are credited (web poll or native balance bump). `added` may be null on native. */
    onSuccess: (added: number | null) => void;
    onClose: () => void;
}

const WEB_POLL_MS = 2000;
const WEB_POLL_MAX = 30;     // ~60s for the Stripe redirect to complete
const NATIVE_POLL_MS = 2000;
const NATIVE_POLL_MAX = 8;   // ~16s for the webhook to credit

/**
 * Tier-selection + purchase modal for Spark packs (SPEC-IAP §6.3).
 * Web → Stripe checkout (opens a tab, polls /checkout/token). Native → RevenueCat purchase, then
 * polls /tokens/balance because fulfillment is webhook-driven. Hides buying when native+unconfigured.
 */
export default function SparkPurchaseModal({ onSuccess, onClose }: SparkPurchaseModalProps) {
    const platform = getPlatform();
    const isWeb = platform === 'web';
    const nativeReady = isIAPConfigured();
    const canBuy = isWeb || nativeReady;

    const [prices, setPrices] = useState<Record<string, string>>({});
    const [busySku, setBusySku] = useState<string | null>(null);
    const [status, setStatus] = useState('');
    const [error, setError] = useState('');
    const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
    const mountedRef = useRef(true);

    useEffect(() => {
        mountedRef.current = true;
        if (nativeReady) getNativePrices().then((p) => { if (mountedRef.current) setPrices(p); });
        return () => {
            mountedRef.current = false;
            if (pollRef.current) clearInterval(pollRef.current);
        };
    }, [nativeReady]);

    const stopPoll = () => {
        if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null; }
    };

    const finishSuccess = (added: number | null) => {
        stopPoll();
        if (!mountedRef.current) return;
        setBusySku(null);
        onSuccess(added);
    };

    const fetchBalance = async (): Promise<number | null> => {
        try {
            const res = await fetch(apiUrl('/tokens/balance'), { headers: apiHeaders() });
            if (!res.ok) return null;
            const data = await res.json();
            return typeof data.balance === 'number' ? data.balance : null;
        } catch {
            return null;
        }
    };

    const webCheckout = async (sku: string) => {
        setError('');
        setBusySku(sku);
        try {
            const res = await fetch(apiUrl('/checkout/create'), {
                method: 'POST',
                headers: apiHeaders(),
                body: JSON.stringify({ device_id: getDeviceId(), sku }),
            });
            if (res.status === 403) {
                setBusySku(null);
                setError('Please use the in-app purchase option on this device.');
                return;
            }
            if (!res.ok) {
                setBusySku(null);
                setError('Payments are not available right now. Try again later.');
                return;
            }
            const { checkout_url, session_id } = await res.json();
            setCheckoutPending(session_id);
            window.open(checkout_url, '_blank');
            track('checkout_started', { source: 'spark_modal', sku });
            setStatus('Waiting for payment…');

            let attempts = 0;
            stopPoll();
            pollRef.current = setInterval(async () => {
                attempts++;
                if (attempts > WEB_POLL_MAX || !mountedRef.current) {
                    stopPoll();
                    if (mountedRef.current) { setBusySku(null); setStatus(''); }
                    return;
                }
                try {
                    const tokenRes = await fetch(apiUrl('/checkout/token'), { headers: apiHeaders() });
                    if (tokenRes.ok) {
                        const data = await tokenRes.json();
                        clearCheckoutPending();
                        track('tokens_purchased', { source: 'spark_modal', sku, tokens_added: data.tokens_added });
                        finishSuccess(typeof data.tokens_added === 'number' ? data.tokens_added : null);
                    } else if (tokenRes.status >= 500) {
                        clearCheckoutPending();
                        stopPoll();
                        if (mountedRef.current) {
                            setBusySku(null);
                            setStatus('');
                            setError('Payment is safe — sparks will appear shortly.');
                        }
                    }
                } catch { /* network blip — keep polling */ }
            }, WEB_POLL_MS);
        } catch {
            setBusySku(null);
            setError('Could not reach the server.');
        }
    };

    const nativeCheckout = async (sku: string) => {
        setError('');
        setBusySku(sku);
        const baseline = (await fetchBalance()) ?? 0;
        const result = await buySparksNative(sku as never);
        if (!mountedRef.current) return;
        if (result.status === 'cancelled') { setBusySku(null); return; }
        if (result.status === 'error') {
            setBusySku(null);
            setError(result.message || 'Purchase failed.');
            return;
        }
        track('checkout_started', { source: 'spark_modal_native', sku });
        setStatus('Confirming purchase…');

        let attempts = 0;
        stopPoll();
        pollRef.current = setInterval(async () => {
            attempts++;
            const balance = await fetchBalance();
            if (balance !== null && balance > baseline) {
                track('tokens_purchased', { source: 'spark_modal_native', sku, tokens_added: balance - baseline });
                finishSuccess(balance - baseline);
                return;
            }
            if (attempts > NATIVE_POLL_MAX || !mountedRef.current) {
                stopPoll();
                if (mountedRef.current) {
                    setBusySku(null);
                    setStatus('');
                    // Purchase went through; webhook may still be in flight.
                    onSuccess(null);
                }
            }
        }, NATIVE_POLL_MS);
    };

    const buy = (sku: string) => {
        if (busySku) return;
        if (isWeb) webCheckout(sku); else nativeCheckout(sku);
    };

    return (
        <div
            style={{
                position: 'fixed', inset: 0, zIndex: 9000,
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                background: 'rgba(10, 6, 18, 0.86)', padding: '1rem',
            }}
            onClick={busySku ? undefined : onClose}
        >
            <div
                style={{
                    background: 'var(--paper)', borderRadius: 8,
                    padding: '1.75rem 1.5rem', maxWidth: 400, width: '100%',
                    border: '1px solid rgba(255, 199, 107, 0.45)',
                    boxShadow: 'var(--shadow), 0 0 36px rgba(255, 199, 107, 0.18)',
                }}
                onClick={(e) => e.stopPropagation()}
            >
                <div style={{ textAlign: 'center', marginBottom: '1.25rem' }}>
                    <div style={{ fontSize: '2.5rem', marginBottom: '0.4rem' }}>⚡</div>
                    <h2 style={{ fontSize: '1.35rem', fontWeight: 800, color: 'var(--ink)', marginBottom: '0.35rem' }}>
                        Get Sparks
                    </h2>
                    <p style={{ color: 'var(--ink-2)', fontSize: '0.9rem', lineHeight: 1.5 }}>
                        Sparks are used to generate quizzes and host games.
                    </p>
                </div>

                {!canBuy ? (
                    <p style={{ color: 'var(--ink-mute)', fontSize: '0.9rem', textAlign: 'center', margin: '1rem 0' }}>
                        Purchases aren’t available in this build.
                    </p>
                ) : (
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '0.6rem' }}>
                        {SPARK_PACKS.map((pack) => {
                            const price = prices[pack.sku] || pack.priceLabel;
                            const isBusy = busySku === pack.sku;
                            const disabled = !!busySku;
                            return (
                                <button
                                    key={pack.sku}
                                    className="btn"
                                    onClick={() => buy(pack.sku)}
                                    disabled={disabled}
                                    style={{
                                        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                                        gap: 10, padding: '14px 16px', borderRadius: 10,
                                        border: '1px solid var(--rule)', background: 'var(--paper-2, rgba(255,255,255,0.03))',
                                        cursor: disabled ? 'default' : 'pointer', opacity: disabled && !isBusy ? 0.55 : 1,
                                    }}
                                >
                                    <span style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                                        <SparkCoin size={20} />
                                        <span style={{ fontWeight: 800, fontSize: '1.15rem', color: 'var(--ink)' }}>
                                            {pack.sparks}
                                        </span>
                                        <span style={{ color: 'var(--ink-mute)', fontSize: '0.85rem' }}>sparks</span>
                                        {pack.badge && (
                                            <span style={{
                                                color: 'var(--gold)', fontSize: '0.65rem', fontWeight: 800,
                                                textTransform: 'uppercase', letterSpacing: '0.04em',
                                                border: '1px solid rgba(255,199,107,0.4)', borderRadius: 6, padding: '2px 6px',
                                            }}>
                                                {pack.badge}
                                            </span>
                                        )}
                                    </span>
                                    <span style={{ fontWeight: 700, color: 'var(--accent)' }}>
                                        {isBusy ? '…' : price}
                                    </span>
                                </button>
                            );
                        })}
                    </div>
                )}

                {status && (
                    <p style={{ color: 'var(--ink-2)', fontSize: '0.82rem', textAlign: 'center', marginTop: '0.9rem' }}>
                        {status}
                    </p>
                )}
                {error && (
                    <p style={{ color: 'var(--accent)', fontSize: '0.82rem', textAlign: 'center', marginTop: '0.9rem' }}>
                        {error}
                    </p>
                )}

                <button
                    className="btn"
                    onClick={onClose}
                    disabled={!!busySku}
                    style={{
                        width: '100%', background: 'transparent', color: 'var(--ink-mute)',
                        fontWeight: 500, fontSize: '0.9rem', padding: '10px', border: 'none',
                        cursor: busySku ? 'default' : 'pointer', marginTop: '0.75rem',
                    }}
                >
                    {busySku ? 'Processing…' : 'Maybe Later'}
                </button>
            </div>
        </div>
    );
}
