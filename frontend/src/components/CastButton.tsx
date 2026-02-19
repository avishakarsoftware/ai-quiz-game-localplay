import { useState, useEffect, useCallback } from 'react';
import '../cast.d.ts';
import { CAST_APP_ID, CAST_NAMESPACE } from '../cast-constants';

interface CastButtonProps {
  roomCode: string;
  joinUrl: string;
  displayUrl?: string;
}

export default function CastButton({ roomCode, displayUrl }: CastButtonProps) {
  const [castSdkReady, setCastSdkReady] = useState(false);
  const [casting, setCasting] = useState(false);
  const [showFallback, setShowFallback] = useState(false);

  const hostname = displayUrl?.split(':')[0] || window.location.hostname;
  const tvUrl = `${window.location.protocol}//${hostname}:${window.location.port}/spectator`;

  useEffect(() => {
    if (!CAST_APP_ID) return;
    const initCast = (isAvailable: boolean) => {
      if (!isAvailable) return;
      try {
        const context = cast.framework.CastContext.getInstance();
        context.setOptions({
          receiverApplicationId: CAST_APP_ID,
          autoJoinPolicy: chrome.cast.AutoJoinPolicy.ORIGIN_SCOPED,
        });

        context.addEventListener(
          cast.framework.CastContextEventType.CAST_STATE_CHANGED,
          (event: cast.framework.CastStateEvent) => {
            setCasting(event.castState === cast.framework.CastState.CONNECTED);
          }
        );

        setCastSdkReady(true);
        setCasting(context.getCastState() === cast.framework.CastState.CONNECTED);
      } catch (err) {
        console.error('Cast SDK init error:', err);
      }
    };

    if (typeof cast !== 'undefined' && cast.framework) {
      initCast(true);
    } else {
      window.__onGCastApiAvailable = initCast;
    }
  }, []);

  // Send room code when casting starts or room code changes
  useEffect(() => {
    if (!casting || !roomCode) return;
    const session = cast.framework.CastContext.getInstance().getCurrentSession();
    if (session) {
      session.sendMessage(CAST_NAMESPACE, JSON.stringify({ type: 'JOIN_ROOM', roomCode }))
        .catch(err => console.error('Cast sendMessage error:', err));
    }
  }, [casting, roomCode]);

  const handleCast = useCallback(async () => {
    if (castSdkReady) {
      try {
        await cast.framework.CastContext.getInstance().requestSession();
      } catch (err) {
        console.error('Cast request failed:', err);
      }
    } else {
      setShowFallback(prev => !prev);
    }
  }, [castSdkReady]);

  return (
    <div>
      <button
        onClick={handleCast}
        className={`btn ${casting ? 'btn-primary' : 'btn-secondary'} w-full`}
        style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8 }}
      >
        <svg viewBox="0 0 24 24" width="20" height="20" fill="currentColor" style={{ flexShrink: 0 }}>
          <path d="M1 18v3h3c0-1.66-1.34-3-3-3zm0-4v2c2.76 0 5 2.24 5 5h2c0-3.87-3.13-7-7-7zm0-4v2c4.97 0 9 4.03 9 9h2c0-6.08-4.93-11-11-11zm20-7H3c-1.1 0-2 .9-2 2v3h2V5h18v14h-7v2h7c1.1 0 2-.9 2-2V5c0-1.1-.9-2-2-2z"/>
        </svg>
        {casting ? 'Casting to TV' : 'Cast to TV'}
      </button>
      {showFallback && !castSdkReady && (
        <div className="text-center mt-3" style={{ padding: '12px 16px', borderRadius: 12, background: 'var(--bg-secondary)' }}>
          <p className="text-[--text-secondary] text-sm mb-1">Casting not available on this browser</p>
          <p className="text-[--text-tertiary] text-xs mb-2">Open this URL on your TV:</p>
          <p className="font-bold text-lg" style={{ color: 'var(--accent-primary)', letterSpacing: '0.02em' }}>{tvUrl}</p>
        </div>
      )}
    </div>
  );
}
