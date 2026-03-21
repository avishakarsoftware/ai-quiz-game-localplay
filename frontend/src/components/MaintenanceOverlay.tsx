import { useRemoteConfigContext } from '../context/RemoteConfigContext';

export default function MaintenanceOverlay() {
  const { config } = useRemoteConfigContext();
  const { operations } = config;

  if (!operations.maintenance) return null;

  const untilText = operations.maintenance_until
    ? ` Back by ${new Date(operations.maintenance_until).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}.`
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
