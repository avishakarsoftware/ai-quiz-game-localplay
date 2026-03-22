import { useRemoteConfigContext } from '../context/RemoteConfigContext';

const APP_VERSION = '3.0.0';

function isVersionBelow(current: string, minimum: string): boolean {
  const c = current.split('.').map(Number);
  const m = minimum.split('.').map(Number);
  for (let i = 0; i < 3; i++) {
    if ((c[i] || 0) < (m[i] || 0)) return true;
    if ((c[i] || 0) > (m[i] || 0)) return false;
  }
  return false;
}

export default function MaintenanceOverlay() {
  const { config } = useRemoteConfigContext();
  const { operations } = config;

  // Kill switch — complete app disable
  if (operations.kill_switch) {
    return (
      <div style={{
        position: 'fixed', inset: 0, zIndex: 9999,
        display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
        background: 'var(--bg-primary)', padding: '2rem', textAlign: 'center',
      }}>
        <div style={{ fontSize: '3rem', marginBottom: '1rem' }}>🚫</div>
        <h1 style={{ fontSize: '1.5rem', fontWeight: 700, marginBottom: '0.5rem' }}>
          App Unavailable
        </h1>
        <p style={{ color: 'var(--text-secondary)', maxWidth: 400 }}>
          {operations.kill_switch_message || 'This app is temporarily unavailable. Please try again later.'}
        </p>
      </div>
    );
  }

  // Force update — app version too old
  if (operations.min_supported_version && isVersionBelow(APP_VERSION, operations.min_supported_version)) {
    return (
      <div style={{
        position: 'fixed', inset: 0, zIndex: 9999,
        display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
        background: 'var(--bg-primary)', padding: '2rem', textAlign: 'center',
      }}>
        <div style={{ fontSize: '3rem', marginBottom: '1rem' }}>📲</div>
        <h1 style={{ fontSize: '1.5rem', fontWeight: 700, marginBottom: '0.5rem' }}>
          Update Required
        </h1>
        <p style={{ color: 'var(--text-secondary)', maxWidth: 400 }}>
          Please update to the latest version to continue using Revelry.
        </p>
      </div>
    );
  }

  // Maintenance mode
  if (!operations.maintenance) return null;

  const untilText = operations.maintenance_until
    ? ` Back by ${new Date(operations.maintenance_until).toLocaleString([], { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })}.`
    : '';

  return (
    <div style={{
      position: 'fixed', inset: 0, zIndex: 9999,
      display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
      background: 'var(--bg-primary)', padding: '2rem', textAlign: 'center',
    }}>
      <div style={{ fontSize: '3rem', marginBottom: '1rem' }}>🔧</div>
      <h1 style={{ fontSize: '1.5rem', fontWeight: 700, marginBottom: '0.5rem' }}>
        Under Maintenance
      </h1>
      <p style={{ color: 'var(--text-secondary)', maxWidth: 400 }}>
        {operations.maintenance_message || 'We\'re making things better. Back soon!'}
        {untilText}
      </p>
    </div>
  );
}
