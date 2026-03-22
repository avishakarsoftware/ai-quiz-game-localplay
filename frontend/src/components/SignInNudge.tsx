import { useState } from 'react';
import { useAuth } from '../context/AuthContext';

interface SignInNudgeProps {
    isPremium: boolean;
}

/**
 * Dismissible nudge shown to premium users who aren't signed in.
 * Encourages them to sign in to keep their Party Pass across devices.
 */
export default function SignInNudge({ isPremium }: SignInNudgeProps) {
    const { user } = useAuth();
    const [dismissed, setDismissed] = useState(() => {
        try { return sessionStorage.getItem('signin_nudge_dismissed') === '1'; } catch { return false; }
    });

    if (!isPremium || user || dismissed) return null;

    const dismiss = () => {
        setDismissed(true);
        try { sessionStorage.setItem('signin_nudge_dismissed', '1'); } catch { /* noop */ }
    };

    return (
        <div className="signin-nudge">
            <span>Sign in to keep your Party Pass across devices</span>
            <button onClick={dismiss} className="signin-nudge-dismiss" title="Dismiss">&times;</button>
        </div>
    );
}
