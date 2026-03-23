import { useState, useEffect, useRef } from 'react';
import { soundManager } from '../utils/sound';
import { useAuth } from '../context/AuthContext';
import { track } from '../utils/analytics';
import { useTokenBalance } from '../hooks/useTokenBalance';
import TokenBadge from './TokenBadge';

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
        AppleID?: {
            auth: {
                init: (config: Record<string, unknown>) => void;
                signIn: () => Promise<{ authorization: { id_token: string } }>;
            };
        };
    }
}

const GOOGLE_CLIENT_ID = import.meta.env.VITE_GOOGLE_CLIENT_ID || '';
const APPLE_CLIENT_ID = import.meta.env.VITE_APPLE_CLIENT_ID || '';
const APPLE_REDIRECT_URI = import.meta.env.VITE_APPLE_REDIRECT_URI || '';

function isNativePlatform(): boolean {
    const cap = (window as Record<string, unknown>).Capacitor as Record<string, unknown> | undefined;
    return typeof cap?.isNativePlatform === 'function' && (cap.isNativePlatform as () => boolean)();
}

export default function SettingsDrawer() {
    const [open, setOpen] = useState(false);
    const [muted, setMuted] = useState(soundManager.muted);
    const [vibration, setVibration] = useState(soundManager.vibrationEnabled);
    const [signInLoading, setSignInLoading] = useState(false);
    const [signInError, setSignInError] = useState('');
    const drawerRef = useRef<HTMLDivElement>(null);
    const googleBtnRef = useRef<HTMLDivElement>(null);
    const { user, signIn, signOut } = useAuth();
    const { tokenStatus, loading: tokenLoading } = useTokenBalance();

    // Listen for external open requests (e.g. from SignInNudge)
    useEffect(() => {
        const handler = () => setOpen(true);
        window.addEventListener('open-settings', handler);
        return () => window.removeEventListener('open-settings', handler);
    }, []);

    // Clear errors when drawer reopens
    useEffect(() => {
        if (open) setSignInError('');
    }, [open]);

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

    // Initialize Google Sign-In SDK when drawer opens (web only)
    useEffect(() => {
        if (!open || !GOOGLE_CLIENT_ID || user || isNativePlatform()) return;

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
            if (scriptEl && scriptEl.parentNode && !window.google?.accounts) {
                scriptEl.parentNode.removeChild(scriptEl);
            }
        };
    }, [open, user]);

    // Initialize Apple Sign-In SDK when drawer opens (web only)
    useEffect(() => {
        if (!open || !APPLE_CLIENT_ID || user || isNativePlatform()) return;

        let scriptEl: HTMLScriptElement | null = null;

        function initApple() {
            if (!window.AppleID) return;
            window.AppleID.auth.init({
                clientId: APPLE_CLIENT_ID,
                scope: 'email',
                redirectURI: APPLE_REDIRECT_URI || window.location.origin,
                usePopup: true,
            });
        }

        if (!window.AppleID) {
            scriptEl = document.createElement('script');
            scriptEl.src = 'https://appleid.cdn-apple.com/appleauth/static/jsapi/appleid/1/en_US/appleid.auth.js';
            scriptEl.async = true;
            scriptEl.onload = () => initApple();
            document.head.appendChild(scriptEl);
        } else {
            initApple();
        }

        return () => {
            if (scriptEl && scriptEl.parentNode && !window.AppleID) {
                scriptEl.parentNode.removeChild(scriptEl);
            }
        };
    }, [open, user]);

    // Handle Apple Sign-In button click (web)
    const handleAppleSignIn = async () => {
        if (!window.AppleID) return;
        setSignInLoading(true);
        setSignInError('');
        try {
            const response = await window.AppleID.auth.signIn();
            const idToken = response?.authorization?.id_token;
            if (!idToken) throw new Error('No ID token from Apple');
            await signIn('apple', idToken);
        } catch (err: unknown) {
            // User cancelled is not an error
            const errObj = err as Record<string, unknown> | null;
            const msg = err instanceof Error ? err.message
                : typeof errObj?.error === 'string' ? errObj.error
                : typeof err === 'string' ? err : '';
            if (!msg.includes('popup_closed') && !msg.includes('user_cancelled') && !msg.includes('user_cancelled_authorize')) {
                setSignInError(msg || 'Apple sign-in failed');
            }
        } finally {
            setSignInLoading(false);
        }
    };

    // Native sign-in via Capacitor social login plugin
    const handleNativeSignIn = async (provider: 'google' | 'apple') => {
        setSignInLoading(true);
        setSignInError('');
        try {
            // Dynamic import — only loaded on native
            const { SocialLogin } = await import('@capgo/capacitor-social-login');
            const result = await SocialLogin.login({
                provider,
                options: provider === 'google'
                    ? { scopes: ['email'] }
                    : { scopes: ['email'] },
            });
            const idToken = result.result?.idToken;
            if (!idToken) throw new Error('No ID token received');
            await signIn(provider, idToken);
        } catch (err: unknown) {
            const msg = err instanceof Error ? err.message : String(err);
            if (!msg.includes('cancelled') && !msg.includes('popup_closed')) {
                setSignInError(msg || 'Sign-in failed');
            }
        } finally {
            setSignInLoading(false);
        }
    };

    // Restore purchases (native only)
    const handleRestorePurchases = async () => {
        setSignInLoading(true);
        setSignInError('');
        try {
            const { apiFetch } = await import('../utils/api');
            const res = await apiFetch('/purchases/restore', { method: 'POST' });
            if (!res.ok) {
                const data = await res.json().catch(() => ({ detail: 'Restore failed' }));
                setSignInError(data.detail || 'No purchases found to restore');
            } else {
                const data = await res.json().catch(() => ({ restored: false }));
                if (data.restored) {
                    track('purchases_restored', { source: 'settings', tokens_added: data.tokens_added });
                    window.dispatchEvent(new CustomEvent('refresh-sparks'));
                } else {
                    setSignInError(data.reason === 'expired'
                        ? 'Your purchase has expired'
                        : 'No active purchases found');
                }
            }
        } catch {
            setSignInError('Failed to restore purchases');
        } finally {
            setSignInLoading(false);
        }
    };

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
            {/* Spark badge — fixed top-right */}
            <div className="settings-spark-badge">
                <TokenBadge tokenStatus={tokenStatus} loading={tokenLoading} />
            </div>

            {/* Hamburger menu trigger — top-left */}
            <button
                onClick={() => setOpen(!open)}
                className="settings-trigger"
                title="Menu"
            >
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
                    <line x1="3" y1="6" x2="21" y2="6" />
                    <line x1="3" y1="12" x2="21" y2="12" />
                    <line x1="3" y1="18" x2="21" y2="18" />
                </svg>
            </button>

            {/* Backdrop */}
            {open && <div className="settings-backdrop" onClick={() => setOpen(false)} />}

            {/* Drawer */}
            <div ref={drawerRef} className={`settings-drawer ${open ? 'settings-drawer-open' : ''}`}>
                <div className="settings-drawer-handle" />
                <h2 style={{ fontSize: 18, fontWeight: 700, marginBottom: 16, textAlign: 'center' }}>Menu</h2>

                {/* Home button */}
                <div
                    className="settings-drawer-row"
                    style={{ cursor: 'pointer' }}
                    onClick={() => {
                        setOpen(false);
                        window.dispatchEvent(new CustomEvent('navigate-home'));
                    }}
                >
                    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                        <path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" />
                        <polyline points="9 22 9 12 15 12 15 22" />
                    </svg>
                    <span style={{ fontWeight: 600, fontSize: 14 }}>Home</span>
                </div>

                {/* Account Section */}
                {user ? (
                    <div className="settings-drawer-row" style={{ flexDirection: 'column', alignItems: 'stretch', gap: 8 }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                            <div className="settings-avatar">
                                {user.email?.[0]?.toUpperCase() || user.provider?.[0]?.toUpperCase() || '?'}
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
                            Sign in to sync your sparks across devices
                        </p>
                        {signInLoading ? (
                            <p style={{ fontSize: 13, color: 'var(--text-tertiary)' }}>Signing in...</p>
                        ) : isNativePlatform() ? (
                            /* Native: Capacitor-based sign-in buttons */
                            <div style={{ display: 'flex', flexDirection: 'column', gap: 8, width: '100%' }}>
                                <button
                                    onClick={() => handleNativeSignIn('google')}
                                    className="settings-social-btn settings-social-google"
                                >
                                    <svg width="18" height="18" viewBox="0 0 24 24"><path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92a5.06 5.06 0 0 1-2.2 3.32v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.1z" fill="#4285F4"/><path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" fill="#34A853"/><path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" fill="#FBBC05"/><path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" fill="#EA4335"/></svg>
                                    Continue with Google
                                </button>
                                <button
                                    onClick={() => handleNativeSignIn('apple')}
                                    className="settings-social-btn settings-social-apple"
                                >
                                    <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor"><path d="M17.05 20.28c-.98.95-2.05.88-3.08.4-1.09-.5-2.08-.48-3.24 0-1.44.62-2.2.44-3.06-.4C2.79 15.25 3.51 7.59 9.05 7.31c1.35.07 2.29.74 3.08.8 1.18-.24 2.31-.93 3.57-.84 1.51.12 2.65.72 3.4 1.8-3.12 1.87-2.38 5.98.48 7.13-.57 1.5-1.31 2.99-2.54 4.09zM12.03 7.25c-.15-2.23 1.66-4.07 3.74-4.25.29 2.58-2.34 4.5-3.74 4.25z"/></svg>
                                    Continue with Apple
                                </button>
                            </div>
                        ) : (
                            /* Web: Google GSI button + Apple button */
                            <div style={{ display: 'flex', flexDirection: 'column', gap: 8, width: '100%', alignItems: 'center' }}>
                                {GOOGLE_CLIENT_ID && <div ref={googleBtnRef} style={{ minHeight: 44 }} />}
                                {APPLE_CLIENT_ID && (
                                    <button
                                        onClick={handleAppleSignIn}
                                        className="settings-social-btn settings-social-apple"
                                    >
                                        <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor"><path d="M17.05 20.28c-.98.95-2.05.88-3.08.4-1.09-.5-2.08-.48-3.24 0-1.44.62-2.2.44-3.06-.4C2.79 15.25 3.51 7.59 9.05 7.31c1.35.07 2.29.74 3.08.8 1.18-.24 2.31-.93 3.57-.84 1.51.12 2.65.72 3.4 1.8-3.12 1.87-2.38 5.98.48 7.13-.57 1.5-1.31 2.99-2.54 4.09zM12.03 7.25c-.15-2.23 1.66-4.07 3.74-4.25.29 2.58-2.34 4.5-3.74 4.25z"/></svg>
                                        Continue with Apple
                                    </button>
                                )}
                                {!GOOGLE_CLIENT_ID && !APPLE_CLIENT_ID && (
                                    <p style={{ fontSize: 12, color: 'var(--text-quaternary)' }}>Sign-in coming soon</p>
                                )}
                            </div>
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

                {/* Restore Purchases — native only */}
                {isNativePlatform() && (
                    <div className="settings-drawer-row" style={{ justifyContent: 'center' }}>
                        <button
                            onClick={handleRestorePurchases}
                            disabled={signInLoading}
                            className="settings-restore-btn"
                        >
                            Restore Purchases
                        </button>
                    </div>
                )}

                <div style={{ textAlign: 'center', marginTop: 16, display: 'flex', flexDirection: 'column', gap: 4 }}>
                    <p style={{ fontSize: 11, color: 'var(--text-quaternary)' }}>Revelry Quiz v1.0</p>
                    <a href="privacy.html" target="_blank" rel="noopener noreferrer" style={{ fontSize: 11, color: 'var(--text-tertiary)', textDecoration: 'underline' }}>Privacy Policy</a>
                </div>
            </div>
        </>
    );
}
