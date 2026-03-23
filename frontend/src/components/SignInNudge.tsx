import { useState } from 'react';
import { useAuth } from '../context/AuthContext';

interface SignInNudgeProps {
    isPremium: boolean;
}

/**
 * Dismissible nudge shown to users who aren't signed in.
 * Premium users: encourages sign-in to sync tokens across devices.
 * Free users: encourages sign-in to keep progress.
 * Clicking opens the settings drawer for sign-in.
 */
export default function SignInNudge({ isPremium }: SignInNudgeProps) {
    const { user } = useAuth();
    const [dismissed, setDismissed] = useState(() => {
        try { return sessionStorage.getItem('signin_nudge_dismissed') === '1'; } catch { return false; }
    });

    if (user || dismissed) return null;

    const dismiss = (e: React.MouseEvent) => {
        e.stopPropagation();
        setDismissed(true);
        try { sessionStorage.setItem('signin_nudge_dismissed', '1'); } catch { /* noop */ }
    };

    const openSettings = () => {
        window.dispatchEvent(new CustomEvent('open-settings'));
    };

    const message = isPremium
        ? 'Sign in to sync your sparks across devices'
        : 'Sign in to save your progress across devices';

    return (
        <div className="signin-nudge" onClick={openSettings} style={{ cursor: 'pointer' }}>
            <span>{message}</span>
            <button onClick={dismiss} className="signin-nudge-dismiss" title="Dismiss">&times;</button>
        </div>
    );
}
