import { useState, useEffect } from 'react';
import { useRemoteConfigContext } from '../context/RemoteConfigContext';

const DISMISSED_KEY = 'revelry_dismissed_announcements';

function getDismissedIds(): Set<string> {
  try {
    return new Set(JSON.parse(localStorage.getItem(DISMISSED_KEY) || '[]'));
  } catch {
    return new Set();
  }
}

function dismissAnnouncement(id: string) {
  const ids = getDismissedIds();
  ids.add(id);
  localStorage.setItem(DISMISSED_KEY, JSON.stringify([...ids]));
}

export default function AnnouncementBanner() {
  const { config } = useRemoteConfigContext();
  const [dismissed, setDismissed] = useState<Set<string>>(getDismissedIds);

  useEffect(() => {
    setDismissed(getDismissedIds());
  }, [config.announcements]);

  const visible = config.announcements.filter(a => !dismissed.has(a.id));
  if (visible.length === 0) return null;

  return (
    <div style={{ position: 'fixed', top: 0, left: 0, right: 0, zIndex: 100, padding: '0 1rem' }}>
      {visible.map(a => (
        <div
          key={a.id}
          style={{
            margin: '0.5rem auto', maxWidth: 600, padding: '0.75rem 1rem',
            borderRadius: 12, display: 'flex', alignItems: 'center', gap: '0.75rem',
            fontSize: '0.875rem',
            background: a.type === 'warning' ? 'rgba(255, 180, 50, 0.15)' : 'rgba(100, 140, 255, 0.15)',
            border: `1px solid ${a.type === 'warning' ? 'rgba(255, 180, 50, 0.3)' : 'rgba(100, 140, 255, 0.3)'}`,
          }}
        >
          <span style={{ flex: 1 }}>{a.text}</span>
          {a.dismissible && (
            <button
              onClick={() => {
                dismissAnnouncement(a.id);
                setDismissed(prev => new Set([...prev, a.id]));
              }}
              style={{
                background: 'none', border: 'none', color: 'var(--text-secondary)',
                cursor: 'pointer', fontSize: '1.25rem', padding: '0 0.25rem', lineHeight: 1,
              }}
            >
              ×
            </button>
          )}
        </div>
      ))}
    </div>
  );
}
