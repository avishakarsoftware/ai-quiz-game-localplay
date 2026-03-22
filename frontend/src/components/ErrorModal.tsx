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
  const showUpgrade = upgradeAvailable && config.feature_flags.show_upgrade_button && onUpgrade;

  return (
    <div
      style={{
        position: 'fixed', inset: 0, zIndex: 9000,
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        background: 'rgba(0, 0, 0, 0.6)', padding: '1rem',
      }}
      onClick={onDismiss}
    >
      <div
        style={{
          background: 'var(--bg-secondary)', borderRadius: 16,
          padding: '2rem', maxWidth: 380, width: '100%', textAlign: 'center',
        }}
        onClick={e => e.stopPropagation()}
      >
        <div style={{ fontSize: '2.5rem', marginBottom: '0.75rem' }}>
          {upgradeAvailable ? '⚡' : '⚠️'}
        </div>
        <h2 style={{ fontSize: '1.25rem', fontWeight: 700, marginBottom: '0.5rem' }}>
          {title}
        </h2>
        <p style={{ color: 'var(--text-secondary)', fontSize: '0.9rem', marginBottom: '1.5rem' }}>
          {message}
        </p>
        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
          {showUpgrade && (
            <button className="btn btn-primary btn-glow" onClick={onUpgrade}>
              Get {config.pricing.label} — {config.pricing.pass_price}
            </button>
          )}
          <button className="btn btn-secondary" onClick={onDismiss}>
            {showUpgrade ? 'Maybe Later' : 'OK'}
          </button>
        </div>
      </div>
    </div>
  );
}
