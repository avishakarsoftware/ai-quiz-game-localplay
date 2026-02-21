import { useState, useEffect, useCallback, useRef } from 'react';
import '../cast.d.ts';
import { CAST_APP_ID, CAST_NAMESPACE } from '../cast-constants';

const CAST_SENDER_SDK_URL = 'https://www.gstatic.com/cv/js/sender/v1/cast_sender.js?loadCastFramework=1';

interface CastButtonProps {
  roomCode: string;
  joinUrl: string;
}

export default function CastButton({ roomCode }: CastButtonProps) {
  const [castSdkReady, setCastSdkReady] = useState(false);
  const [casting, setCasting] = useState(false);
  const [showFallback, setShowFallback] = useState(false);
  const sdkLoaded = useRef(false);

  // In Capacitor, window.location.origin is capacitor://localhost — use the web URL
  const isCapacitor = window.location.protocol === 'capacitor:' || (window.location.hostname === 'localhost' && !window.location.port);
  const tvUrl = isCapacitor
    ? `${import.meta.env.VITE_WEB_URL || 'https://games.revelryapp.me/quiz/'}spectator`
    : `${window.location.origin}${import.meta.env.BASE_URL}spectator`;

  // Dynamically load Cast Sender SDK (not in index.html to avoid conflict with receiver on spectator page)
  useEffect(() => {
    if (sdkLoaded.current) return;
    sdkLoaded.current = true;

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

    // Set callback before loading script
    window.__onGCastApiAvailable = initCast;

    const script = document.createElement('script');
    script.src = CAST_SENDER_SDK_URL;
    script.onerror = () => {}; // Silently fail if SDK can't load
    document.head.appendChild(script);
  }, []);

  // Send room code when casting starts or room code changes
  useEffect(() => {
    if (!casting || !roomCode) return;
    try {
      const session = cast.framework.CastContext.getInstance().getCurrentSession();
      if (session) {
        session.sendMessage(CAST_NAMESPACE, JSON.stringify({ type: 'JOIN_ROOM', roomCode }))
          .catch(err => console.error('Cast sendMessage error:', err));
      }
    } catch (err) {
      console.error('Cast session access error:', err);
    }
  }, [casting, roomCode]);

  const handleCast = useCallback(async () => {
    if (castSdkReady) {
      try {
        const context = cast.framework.CastContext.getInstance();
        await context.requestSession();
      } catch (err: unknown) {
        // 'cancel' means user closed the device picker — not a real error
        const isCancel = err && typeof err === 'object' && 'code' in err && (err as { code: string }).code === 'cancel';
        if (!isCancel) {
          console.error('Cast request failed:', err);
        }
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
