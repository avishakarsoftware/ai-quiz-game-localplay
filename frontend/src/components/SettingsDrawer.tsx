import { useState, useEffect, useRef } from 'react';
import { soundManager } from '../utils/sound';
import { useAuth } from '../context/AuthContext';
import { track } from '../utils/analytics';

declare global {
    interface Window {
        google?: {
            accounts: {
                id: {
                    initialize: (config: Record<string, unknown>) => void;
                    renderButton: (element: HTMLElement, config: Record<string, unknown>) => void;
                    prompt: () => void;
                };
            };
        };
    }
}

const GOOGLE_CLIENT_ID = import.meta.env.VITE_GOOGLE_CLIENT_ID || '';

export default function SettingsDrawer() {
    const [open, setOpen] = useState(false);
    const [muted, setMuted] = useState(soundManager.muted);
    const [vibration, setVibration] = useState(soundManager.vibrationEnabled);
    const [signInLoading, setSignInLoading] = useState(false);
    const [signInError, setSignInError] = useState('');
    const drawerRef = useRef<HTMLDivElement>(null);
    const googleBtnRef = useRef<HTMLDivElement>(null);
    const { user, signIn, signOut } = useAuth();

    // Close on outside click
    useEffect(() => {
        if (!open) return;
        const handler = (e: MouseEvent) => {
            if (drawerRef.current && !drawerRef.current.contains(e.target as Node)) {
                setOpen(false);
            }
        };
        document.addEventListener('mousedown', handler);
        return () => document.removeEventListener('mousedown', handler);
    }, [open]);

    // Close on Escape
    useEffect(() => {
        if (!open) return;
        const handler = (e: KeyboardEvent) => {
            if (e.key === 'Escape') setOpen(false);
        };
        document.addEventListener('keydown', handler);
        return () => document.removeEventListener('keydown', handler);
    }, [open]);

    // Ref to always have latest signIn without re-triggering effects
    const signInRef = useRef(signIn);
    signInRef.current = signIn;

    // Initialize Google Sign-In SDK when drawer opens
    useEffect(() => {
        if (!open || !GOOGLE_CLIENT_ID || user) return;

        let scriptEl: HTMLScriptElement | null = null;

        function handleGoogleResponse(response: { credential: string }) {
            setSignInLoading(true);
            setSignInError('');
            signInRef.current('google', response.credential)
                .catch((err: unknown) => setSignInError(err instanceof Error ? err.message : 'Sign-in failed'))
                .finally(() => setSignInLoading(false));
        }

        function initGoogleBtn() {
            if (!window.google?.accounts || !googleBtnRef.current) return;
            window.google.accounts.id.initialize({
                client_id: GOOGLE_CLIENT_ID,
                callback: handleGoogleResponse,
                auto_select: false,
            });
            window.google.accounts.id.renderButton(googleBtnRef.current, {
                type: 'standard',
                theme: 'filled_black',
                size: 'large',
                width: 280,
                text: 'continue_with',
                shape: 'pill',
            });
        }

        // Load GSI script if not already loaded
        if (!window.google?.accounts) {
            scriptEl = document.createElement('script');
            scriptEl.src = 'https://accounts.google.com/gsi/client';
            scriptEl.async = true;
            scriptEl.onload = () => initGoogleBtn();
            document.head.appendChild(scriptEl);
        } else {
            initGoogleBtn();
        }

        return () => {
            // Clean up script tag if we added it and GSI hasn't loaded yet
            if (scriptEl && scriptEl.parentNode && !window.google?.accounts) {
                scriptEl.parentNode.removeChild(scriptEl);
            }
        };
    }, [open, user]);

    const toggleSound = () => {
        const newMuted = soundManager.toggleMute();
        setMuted(newMuted);
    };

    const toggleVibration = () => {
        const newVibration = soundManager.toggleVibration();
        setVibration(newVibration);
        if (newVibration) navigator.vibrate?.(50);
    };

    const handleSignOut = () => {
        signOut();
        track('signed_out', { source: 'settings' });
    };

    return (
        <>
            {/* Trigger button */}
            <button
                onClick={() => setOpen(!open)}
                className="settings-trigger"
                title="Settings"
            >
                {user ? (
                    <span style={{ fontSize: 16, lineHeight: 1 }}>
                        {user.email?.[0]?.toUpperCase() || user.provider[0].toUpperCase()}
                    </span>
                ) : (
                    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                        <path d="M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08a2 2 0 0 0-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74l-.15.09a2 2 0 0 0-.73 2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.39a2 2 0 0 0-.73-2.73l-.15-.08a2 2 0 0 1-1-1.74v-.5a2 2 0 0 1 1-1.74l.15-.09a2 2 0 0 0 .73-2.73l-.22-.38a2 2 0 0 0-2.73-.73l-.15.08a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2z" />
                        <circle cx="12" cy="12" r="3" />
                    </svg>
                )}
            </button>

            {/* Backdrop */}
            {open && <div className="settings-backdrop" onClick={() => setOpen(false)} />}

            {/* Drawer */}
            <div ref={drawerRef} className={`settings-drawer ${open ? 'settings-drawer-open' : ''}`}>
                <div className="settings-drawer-handle" />
                <h2 style={{ fontSize: 18, fontWeight: 700, marginBottom: 16, textAlign: 'center' }}>Settings</h2>

                {/* Account Section */}
                {user ? (
                    <div className="settings-drawer-row" style={{ flexDirection: 'column', alignItems: 'stretch', gap: 8 }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                            <div className="settings-avatar">
                                {user.email?.[0]?.toUpperCase() || user.provider[0].toUpperCase()}
                            </div>
                            <div style={{ flex: 1, minWidth: 0 }}>
                                <p style={{ fontWeight: 600, fontSize: 14 }}>Signed in</p>
                                <p style={{ fontSize: 12, color: 'var(--text-tertiary)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                                    {user.email || `${user.provider} account`}
                                </p>
                            </div>
                            <button onClick={handleSignOut} className="settings-sign-out-btn">
                                Sign Out
                            </button>
                        </div>
                    </div>
                ) : (
                    <div className="settings-drawer-row" style={{ flexDirection: 'column', alignItems: 'center', gap: 10 }}>
                        <p style={{ fontSize: 13, color: 'var(--text-secondary)', textAlign: 'center' }}>
                            Sign in to keep your Party Pass across devices
                        </p>
                        {signInLoading ? (
                            <p style={{ fontSize: 13, color: 'var(--text-tertiary)' }}>Signing in...</p>
                        ) : (
                            <>
                                {GOOGLE_CLIENT_ID && <div ref={googleBtnRef} style={{ minHeight: 44 }} />}
                                {!GOOGLE_CLIENT_ID && (
                                    <p style={{ fontSize: 12, color: 'var(--text-quaternary)' }}>Sign-in coming soon</p>
                                )}
                            </>
                        )}
                        {signInError && (
                            <p style={{ fontSize: 12, color: '#ff6b6b', wordBreak: 'break-word', maxWidth: '100%' }}>{signInError}</p>
                        )}
                    </div>
                )}

                <div className="settings-drawer-row">
                    <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                        <span style={{ fontSize: '1.25rem' }}>{muted ? '🔇' : '🔊'}</span>
                        <div>
                            <p style={{ fontWeight: 600, fontSize: 14 }}>Sound</p>
                            <p style={{ fontSize: 12, color: 'var(--text-tertiary)' }}>Game audio effects</p>
                        </div>
                    </div>
                    <button
                        onClick={toggleSound}
                        className={`settings-toggle ${!muted ? 'settings-toggle-on' : ''}`}
                    >
                        <span className="settings-toggle-knob" />
                    </button>
                </div>

                <div className="settings-drawer-row">
                    <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                        <span style={{ fontSize: '1.25rem' }}>{vibration ? '📳' : '📴'}</span>
                        <div>
                            <p style={{ fontWeight: 600, fontSize: 14 }}>Vibration</p>
                            <p style={{ fontSize: 12, color: 'var(--text-tertiary)' }}>Haptic feedback</p>
                        </div>
                    </div>
                    <button
                        onClick={toggleVibration}
                        className={`settings-toggle ${vibration ? 'settings-toggle-on' : ''}`}
                    >
                        <span className="settings-toggle-knob" />
                    </button>
                </div>

                <div style={{ textAlign: 'center', marginTop: 16, display: 'flex', flexDirection: 'column', gap: 4 }}>
                    <p style={{ fontSize: 11, color: 'var(--text-quaternary)' }}>Revelry Quiz v1.0</p>
                    <a href="privacy.html" target="_blank" rel="noopener noreferrer" style={{ fontSize: 11, color: 'var(--text-tertiary)', textDecoration: 'underline' }}>Privacy Policy</a>
                </div>
            </div>
        </>
    );
}
