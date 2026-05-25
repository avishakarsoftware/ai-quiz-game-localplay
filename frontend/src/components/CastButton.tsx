import { useCallback, useMemo, useState } from 'react';

interface CastButtonProps {
  roomCode: string;
}

function buildTvUrl(roomCode: string): string {
  const isCapacitor =
    window.location.protocol === 'capacitor:' ||
    (window.location.hostname === 'localhost' && !window.location.port);
  const baseUrl = isCapacitor
    ? (import.meta.env.VITE_WEB_URL || 'https://games.revelryapp.me/quiz/')
    : `${window.location.origin}${import.meta.env.BASE_URL}`;
  return `${baseUrl.replace(/\/?$/, '/')}tv/${encodeURIComponent(roomCode)}`;
}

function displayUrl(url: string): string {
  try {
    const parsed = new URL(url);
    return `${parsed.host}${parsed.pathname}`;
  } catch {
    return url;
  }
}

export default function CastButton({ roomCode }: CastButtonProps) {
  const [showOptions, setShowOptions] = useState(false);
  const [copied, setCopied] = useState(false);
  const tvUrl = useMemo(() => buildTvUrl(roomCode), [roomCode]);

  const openWatchView = useCallback(() => {
    window.open(tvUrl, '_blank', 'noopener,noreferrer');
  }, [tvUrl]);

  const copyWatchLink = useCallback(async () => {
    try {
      await navigator.clipboard.writeText(tvUrl);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1800);
    } catch {
      setCopied(false);
    }
  }, [tvUrl]);

  return (
    <div>
      <button
        onClick={() => setShowOptions(prev => !prev)}
        className="btn btn-secondary w-full"
        style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8 }}
      >
        <svg viewBox="0 0 24 24" width="20" height="20" fill="currentColor" style={{ flexShrink: 0 }}>
          <path d="M21 3H3c-1.1 0-2 .9-2 2v3h2V5h18v14h-7v2h7c1.1 0 2-.9 2-2V5c0-1.1-.9-2-2-2zM1 18v3h3c0-1.66-1.34-3-3-3zm0-4v2c2.76 0 5 2.24 5 5h2c0-3.87-3.13-7-7-7zm0-4v2c4.97 0 9 4.03 9 9h2c0-6.08-4.93-11-11-11z"/>
        </svg>
        Display on TV
      </button>
      {showOptions && (
        <div
          className="mt-3"
          style={{
            padding: '14px 16px',
            borderRadius: 12,
            background: 'var(--bg-secondary)',
            border: '1px solid var(--border-color)',
          }}
        >
          <p className="text-[--text-secondary] text-sm mb-2">
            Open the watch view, then cast that tab or open the link on your TV.
          </p>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, marginBottom: 10 }}>
            <button className="btn btn-primary" onClick={openWatchView}>
              Open Watch View
            </button>
            <button className="btn btn-secondary" onClick={copyWatchLink}>
              {copied ? 'Copied' : 'Copy TV Link'}
            </button>
          </div>
          <p className="text-[--text-tertiary] text-xs mb-1">
            Browser Cast mirrors the current tab. If you cast this host screen, the TV sees host controls.
          </p>
          <p className="font-bold text-base" style={{ color: 'var(--accent-primary)', wordBreak: 'break-word' }}>
            {displayUrl(tvUrl)}
          </p>
        </div>
      )}
    </div>
  );
}
