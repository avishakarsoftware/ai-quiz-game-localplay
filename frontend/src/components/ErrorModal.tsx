import { useRemoteConfigContext } from '../context/RemoteConfigContext';

interface ErrorModalProps {
  title: string;
  message: string;
  upgradeAvailable?: boolean;
  onDismiss: () => void;
  onUpgrade?: () => void;
}

export default function ErrorModal({ title, message, upgradeAvailable, onDismiss, onUpgrade }: ErrorModalProps) {
  const { config } = useRemoteConfigContext();
  const showUpgrade = upgradeAvailable && onUpgrade;

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
              {config.pricing.games} Games for {Math.floor(config.pricing.duration_hours / 24)} Days — {config.pricing.pass_price}
            </button>
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
