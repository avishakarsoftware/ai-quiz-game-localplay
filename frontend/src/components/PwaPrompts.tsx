import { useEffect, useMemo, useState } from 'react';
import { Bell, Download, RefreshCw, X } from 'lucide-react';

interface BeforeInstallPromptEvent extends Event {
    readonly platforms: string[];
    readonly userChoice: Promise<{ outcome: 'accepted' | 'dismissed'; platform: string }>;
    prompt: () => Promise<void>;
}

type PromptKind = 'refresh' | 'install' | 'notifications';

const INSTALL_DISMISSED_KEY = 'localplay_pwa_install_dismissed';
const NOTIFICATIONS_DISMISSED_KEY = 'localplay_notifications_prompt_dismissed';

function isStandaloneDisplay(): boolean {
    return window.matchMedia?.('(display-mode: standalone)').matches
        || (navigator as Navigator & { standalone?: boolean }).standalone === true;
}

function storageGet(key: string): string | null {
    try {
        return window.localStorage.getItem(key);
    } catch {
        return null;
    }
}

function storageSet(key: string, value: string) {
    try {
        window.localStorage.setItem(key, value);
    } catch {
        // Ignore private-mode or blocked-storage failures.
    }
}

function PromptCard({
    kind,
    title,
    body,
    actionLabel,
    onAction,
    onDismiss,
}: {
    kind: PromptKind;
    title: string;
    body: string;
    actionLabel: string;
    onAction: () => void | Promise<void>;
    onDismiss?: () => void;
}) {
    const Icon = kind === 'refresh' ? RefreshCw : kind === 'install' ? Download : Bell;
    return (
        <div className="pwa-prompt-card" role="status" aria-live={kind === 'refresh' ? 'assertive' : 'polite'}>
            <div className="pwa-prompt-icon" aria-hidden="true">
                <Icon size={18} strokeWidth={2.4} />
            </div>
            <div className="pwa-prompt-copy">
                <div className="pwa-prompt-title">{title}</div>
                <div className="pwa-prompt-body">{body}</div>
            </div>
            <button className="pwa-prompt-action" type="button" onClick={onAction}>
                {actionLabel}
            </button>
            {onDismiss && (
                <button className="pwa-prompt-dismiss" type="button" onClick={onDismiss} aria-label="Dismiss">
                    <X size={18} />
                </button>
            )}
        </div>
    );
}

export default function PwaPrompts({ isHostAppSurface = false }: { isHostAppSurface?: boolean }) {
    const [installEvent, setInstallEvent] = useState<BeforeInstallPromptEvent | null>(null);
    const [installVisible, setInstallVisible] = useState(false);
    const [notificationVisible, setNotificationVisible] = useState(false);
    const [waitingWorker, setWaitingWorker] = useState<ServiceWorker | null>(null);

    const promptsAllowed = useMemo(() => !isHostAppSurface && !isStandaloneDisplay(), [isHostAppSurface]);
    const notificationSupported = typeof window !== 'undefined' && 'Notification' in window;

    useEffect(() => {
        const onUpdate = (event: Event) => {
            const customEvent = event as CustomEvent<{ worker?: ServiceWorker }>;
            setWaitingWorker(customEvent.detail?.worker || null);
        };
        window.addEventListener('localplay-sw-update', onUpdate);
        return () => window.removeEventListener('localplay-sw-update', onUpdate);
    }, []);

    useEffect(() => {
        if (isHostAppSurface) return undefined;

        const onBeforeInstallPrompt = (event: Event) => {
            event.preventDefault();
            if (storageGet(INSTALL_DISMISSED_KEY) === '1' || isStandaloneDisplay()) return;
            setInstallEvent(event as BeforeInstallPromptEvent);
            setInstallVisible(true);
        };

        window.addEventListener('beforeinstallprompt', onBeforeInstallPrompt);
        return () => window.removeEventListener('beforeinstallprompt', onBeforeInstallPrompt);
    }, [isHostAppSurface]);

    useEffect(() => {
        if (!promptsAllowed || !notificationSupported) return undefined;
        if (Notification.permission !== 'default') return undefined;
        if (storageGet(NOTIFICATIONS_DISMISSED_KEY) === '1') return undefined;

        const timer = window.setTimeout(() => setNotificationVisible(true), 7000);
        return () => window.clearTimeout(timer);
    }, [notificationSupported, promptsAllowed]);

    useEffect(() => {
        if (!waitingWorker) return undefined;

        let refreshing = false;
        const onControllerChange = () => {
            if (refreshing) return;
            refreshing = true;
            window.location.reload();
        };
        navigator.serviceWorker?.addEventListener('controllerchange', onControllerChange);
        return () => navigator.serviceWorker?.removeEventListener('controllerchange', onControllerChange);
    }, [waitingWorker]);

    const installApp = async () => {
        if (!installEvent) return;
        await installEvent.prompt();
        setInstallVisible(false);
        setInstallEvent(null);
        const choice = await installEvent.userChoice.catch(() => ({ outcome: 'dismissed' as const, platform: '' }));
        if (choice.outcome !== 'accepted') storageSet(INSTALL_DISMISSED_KEY, '1');
    };

    const enableNotifications = async () => {
        if (!notificationSupported) return;
        await Notification.requestPermission().catch(() => 'denied');
        setNotificationVisible(false);
        storageSet(NOTIFICATIONS_DISMISSED_KEY, '1');
    };

    const refreshNow = () => {
        if (waitingWorker) {
            waitingWorker.postMessage({ type: 'SKIP_WAITING' });
        } else {
            window.location.reload();
        }
    };

    const dismissInstall = () => {
        storageSet(INSTALL_DISMISSED_KEY, '1');
        setInstallVisible(false);
    };

    const dismissNotifications = () => {
        storageSet(NOTIFICATIONS_DISMISSED_KEY, '1');
        setNotificationVisible(false);
    };

    if (!waitingWorker && !installVisible && !notificationVisible) return null;

    return (
        <div className="pwa-prompt-stack">
            {waitingWorker && (
                <PromptCard
                    kind="refresh"
                    title="New version ready"
                    body="Refresh when you are between rounds to get the latest fixes."
                    actionLabel="Refresh"
                    onAction={refreshNow}
                />
            )}
            {installVisible && installEvent && (
                <PromptCard
                    kind="install"
                    title="Install Revelry Games"
                    body="Keep the party games one tap away on this device."
                    actionLabel="Install"
                    onAction={installApp}
                    onDismiss={dismissInstall}
                />
            )}
            {notificationVisible && (
                <PromptCard
                    kind="notifications"
                    title="Game alerts"
                    body="Get notified when a game starts or results are ready."
                    actionLabel="Enable"
                    onAction={enableNotifications}
                    onDismiss={dismissNotifications}
                />
            )}
        </div>
    );
}
