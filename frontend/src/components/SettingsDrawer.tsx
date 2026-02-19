import { useState, useEffect, useRef } from 'react';
import { soundManager } from '../utils/sound';

export default function SettingsDrawer() {
    const [open, setOpen] = useState(false);
    const [muted, setMuted] = useState(soundManager.muted);
    const [vibration, setVibration] = useState(soundManager.vibrationEnabled);
    const drawerRef = useRef<HTMLDivElement>(null);

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

    const toggleSound = () => {
        const newMuted = soundManager.toggleMute();
        setMuted(newMuted);
    };

    const toggleVibration = () => {
        const newVibration = soundManager.toggleVibration();
        setVibration(newVibration);
        if (newVibration) navigator.vibrate?.(50); // quick feedback
    };

    return (
        <>
            {/* Trigger button */}
            <button
                onClick={() => setOpen(!open)}
                className="settings-trigger"
                title="Settings"
            >
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08a2 2 0 0 0-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74l-.15.09a2 2 0 0 0-.73 2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.39a2 2 0 0 0-.73-2.73l-.15-.08a2 2 0 0 1-1-1.74v-.5a2 2 0 0 1 1-1.74l.15-.09a2 2 0 0 0 .73-2.73l-.22-.38a2 2 0 0 0-2.73-.73l-.15.08a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2z" />
                    <circle cx="12" cy="12" r="3" />
                </svg>
            </button>

            {/* Backdrop */}
            {open && <div className="settings-backdrop" onClick={() => setOpen(false)} />}

            {/* Drawer */}
            <div ref={drawerRef} className={`settings-drawer ${open ? 'settings-drawer-open' : ''}`}>
                <div className="settings-drawer-handle" />
                <h2 style={{ fontSize: 18, fontWeight: 700, marginBottom: 16, textAlign: 'center' }}>Settings</h2>

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

                <p style={{ textAlign: 'center', fontSize: 11, color: 'var(--text-quaternary)', marginTop: 16 }}>
                    LocalPlay v1.0
                </p>
            </div>
        </>
    );
}
