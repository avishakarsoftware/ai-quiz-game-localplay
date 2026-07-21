interface ErrorModalProps {
  title: string;
  message: string;
  upgradeAvailable?: boolean;
  onDismiss: () => void;
  onUpgrade?: () => void;
}

export default function ErrorModal({ title, message, upgradeAvailable, onDismiss, onUpgrade }: ErrorModalProps) {
  const showUpgrade = upgradeAvailable && onUpgrade;

  return (
    <div
      style={{
        position: 'fixed', inset: 0, zIndex: 9000,
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        background: 'rgba(10, 6, 18, 0.86)', padding: '1rem',
      }}
      onClick={onDismiss}
    >
      <div
        style={{
          background: 'var(--paper)', borderRadius: 8,
          padding: '2rem 1.5rem', maxWidth: 380, width: '100%', textAlign: 'center',
          border: upgradeAvailable ? '1px solid rgba(255, 199, 107, 0.45)' : '1px solid var(--rule)',
          boxShadow: upgradeAvailable
            ? 'var(--shadow), 0 0 36px rgba(255, 199, 107, 0.18)'
            : 'var(--shadow)',
        }}
        onClick={e => e.stopPropagation()}
      >
        <div style={{ fontSize: '3rem', marginBottom: '0.75rem' }}>
          {upgradeAvailable ? '⚡' : '⚠️'}
        </div>
        <h2 style={{ fontSize: '1.4rem', fontWeight: 800, marginBottom: '0.5rem', color: 'var(--ink)' }}>
          {title}
        </h2>
        <p style={{ color: 'var(--ink-2)', fontSize: '0.95rem', lineHeight: 1.5, marginBottom: '1.5rem' }}>
          {message}
        </p>
        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
          {showUpgrade && (
            <>
              <button
                className="btn btn-glow"
                onClick={onUpgrade}
                style={{
                  background: 'var(--accent)',
                  color: 'var(--accent-ink)',
                  fontWeight: 700,
                  fontSize: '1.1rem',
                  padding: '14px 24px',
                  borderRadius: 8,
                  border: 'none',
                  cursor: 'pointer',
                }}
              >
                {/* No amount/price here: SparkPurchaseModal owns the tier ladder, and on
                    native RevenueCat returns store-localized prices, so any figure quoted
                    here is wrong in every non-USD storefront. */}
                Get Sparks
              </button>
            </>
          )}
          <button
            className="btn"
            onClick={onDismiss}
            style={{
              background: 'transparent',
              color: 'var(--ink-mute)',
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
