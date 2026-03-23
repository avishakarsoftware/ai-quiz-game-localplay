import { useState, useEffect } from 'react';
import { useRemoteConfigContext } from '../context/RemoteConfigContext';
import SparkCoin from './SparkCoin';

interface ErrorModalProps {
  title: string;
  message: string;
  upgradeAvailable?: boolean;
  onDismiss: () => void;
  onUpgrade?: () => void;
}

function useCountdown(expiresIso?: string) {
  const [timeLeft, setTimeLeft] = useState('');
  useEffect(() => {
    if (!expiresIso) return;
    const target = new Date(expiresIso).getTime();
    if (isNaN(target)) return; // Invalid date string
    const tick = () => {
      const diff = target - Date.now();
      if (diff <= 0) { setTimeLeft(''); return; }
      const d = Math.floor(diff / 86400000);
      const h = Math.floor((diff % 86400000) / 3600000);
      const m = Math.floor((diff % 3600000) / 60000);
      setTimeLeft(d > 0 ? `${d}d ${h}h left` : h > 0 ? `${h}h ${m}m left` : `${m}m left`);
    };
    tick();
    const id = setInterval(tick, 60000);
    return () => clearInterval(id);
  }, [expiresIso]);
  return timeLeft;
}

function isPromoExpired(expires?: string): boolean {
  if (!expires) return false;
  const target = new Date(expires).getTime();
  return !isNaN(target) && target <= Date.now();
}

export default function ErrorModal({ title, message, upgradeAvailable, onDismiss, onUpgrade }: ErrorModalProps) {
  const { config } = useRemoteConfigContext();
  const showUpgrade = upgradeAvailable && onUpgrade;
  const promo = config.pricing.promo;
  const hasPromo = !!(promo && promo.id && promo.token_pack_amount > 0 && promo.original_amount > 0 && !isPromoExpired(promo.expires));
  const displayAmount = hasPromo ? promo.token_pack_amount : config.pricing.token_pack_amount;
  const countdown = useCountdown(promo?.expires);

  return (
    <div
      style={{
        position: 'fixed', inset: 0, zIndex: 9000,
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        background: 'rgba(0, 0, 0, 0.85)', padding: '1rem',
      }}
      onClick={onDismiss}
    >
      <div
        style={{
          background: '#1e1e3a', borderRadius: 20,
          padding: '2rem 1.5rem', maxWidth: 380, width: '100%', textAlign: 'center',
          border: upgradeAvailable ? '2px solid rgba(255, 170, 50, 0.4)' : '1px solid rgba(255,255,255,0.1)',
          boxShadow: upgradeAvailable
            ? '0 0 40px rgba(255, 170, 50, 0.15), 0 8px 32px rgba(0,0,0,0.5)'
            : '0 8px 32px rgba(0,0,0,0.5)',
        }}
        onClick={e => e.stopPropagation()}
      >
        <div style={{ fontSize: '3rem', marginBottom: '0.75rem' }}>
          {upgradeAvailable ? '⚡' : '⚠️'}
        </div>
        <h2 style={{ fontSize: '1.4rem', fontWeight: 800, marginBottom: '0.5rem', color: '#fff' }}>
          {title}
        </h2>
        <p style={{ color: 'rgba(255,255,255,0.7)', fontSize: '0.95rem', lineHeight: 1.5, marginBottom: '1.5rem' }}>
          {message}
        </p>
        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
          {showUpgrade && (
            <>
              {hasPromo && (
                <div style={{
                  background: 'linear-gradient(135deg, rgba(255,138,0,0.15), rgba(229,46,113,0.15))',
                  border: '1px solid rgba(255,138,0,0.3)',
                  borderRadius: 10, padding: '8px 12px', marginBottom: 4,
                }}>
                  <div style={{
                    color: '#ff8a00', fontWeight: 800, fontSize: '0.75rem',
                    letterSpacing: '0.05em', textTransform: 'uppercase', marginBottom: 4,
                  }}>
                    {promo.badge}
                  </div>
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6 }}>
                    <span style={{
                      color: 'rgba(255,255,255,0.4)', textDecoration: 'line-through',
                      fontSize: '1rem', fontWeight: 600,
                    }}>
                      {promo.original_amount}
                    </span>
                    <SparkCoin size={18} />
                    <span style={{ color: '#FFD700', fontWeight: 800, fontSize: '1.3rem' }}>
                      {promo.token_pack_amount}
                    </span>
                    <span style={{ color: 'rgba(255,255,255,0.6)', fontSize: '0.85rem' }}>sparks</span>
                  </div>
                  {countdown && (
                    <div style={{ color: '#e52e71', fontSize: '0.7rem', fontWeight: 600, marginTop: 4 }}>
                      {countdown}
                    </div>
                  )}
                </div>
              )}
              <button
                className="btn btn-glow"
                onClick={onUpgrade}
                style={{
                  background: 'linear-gradient(135deg, #ff8a00, #e52e71)',
                  color: '#fff',
                  fontWeight: 700,
                  fontSize: '1.1rem',
                  padding: '14px 24px',
                  borderRadius: 12,
                  border: 'none',
                  cursor: 'pointer',
                }}
              >
                Get {displayAmount} Sparks — {config.pricing.token_pack_price}
              </button>
            </>
          )}
          <button
            className="btn"
            onClick={onDismiss}
            style={{
              background: 'transparent',
              color: 'rgba(255,255,255,0.5)',
              fontWeight: 500,
              fontSize: '0.9rem',
              padding: '10px',
              border: 'none',
              cursor: 'pointer',
            }}
          >
            {showUpgrade ? 'Maybe Later' : 'OK'}
          </button>
        </div>
      </div>
    </div>
  );
}
