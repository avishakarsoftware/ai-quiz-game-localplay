import { fireEvent, render, screen } from '@testing-library/react';
import { act } from 'react';
import PwaPrompts from '../PwaPrompts';

function dispatchBeforeInstallPrompt(overrides: Partial<Event> = {}) {
    const event = new Event('beforeinstallprompt', { cancelable: true }) as Event & {
        prompt: ReturnType<typeof vi.fn>;
        userChoice: Promise<{ outcome: 'accepted' | 'dismissed'; platform: string }>;
    };
    event.prompt = vi.fn().mockResolvedValue(undefined);
    event.userChoice = Promise.resolve({ outcome: 'accepted', platform: 'web' });
    Object.assign(event, overrides);
    window.dispatchEvent(event);
    return event;
}

describe('PwaPrompts', () => {
    let store: Record<string, string>;

    beforeEach(() => {
        store = {};
        Object.defineProperty(window, 'localStorage', {
            value: {
                getItem: vi.fn((key: string) => store[key] ?? null),
                setItem: vi.fn((key: string, value: string) => { store[key] = value; }),
                removeItem: vi.fn((key: string) => { delete store[key]; }),
                clear: vi.fn(() => { store = {}; }),
            },
            writable: true,
        });
        vi.useFakeTimers();
    });

    afterEach(() => {
        vi.useRealTimers();
        vi.restoreAllMocks();
    });

    it('shows and runs the standalone install prompt', async () => {
        render(<PwaPrompts />);

        let event!: ReturnType<typeof dispatchBeforeInstallPrompt>;
        await act(async () => {
            event = dispatchBeforeInstallPrompt();
        });

        expect(screen.getByText('Install Revelry Games')).toBeInTheDocument();
        await act(async () => {
            fireEvent.click(screen.getByRole('button', { name: 'Install' }));
        });

        expect(event.prompt).toHaveBeenCalled();
    });

    it('does not show install prompt inside host-app surfaces', () => {
        render(<PwaPrompts isHostAppSurface />);

        act(() => {
            dispatchBeforeInstallPrompt();
        });

        expect(screen.queryByText('Install Revelry Games')).not.toBeInTheDocument();
    });

    it('shows refresh prompt for a waiting service worker and activates it', () => {
        const worker = { postMessage: vi.fn() } as unknown as ServiceWorker;
        render(<PwaPrompts />);

        act(() => {
            window.dispatchEvent(new CustomEvent('localplay-sw-update', { detail: { worker } }));
        });

        expect(screen.getByText('New version ready')).toBeInTheDocument();
        fireEvent.click(screen.getByRole('button', { name: 'Refresh' }));
        expect(worker.postMessage).toHaveBeenCalledWith({ type: 'SKIP_WAITING' });
    });

    it('offers notification opt-in without requesting permission until clicked', async () => {
        const requestPermission = vi.fn().mockResolvedValue('granted');
        vi.stubGlobal('Notification', {
            permission: 'default',
            requestPermission,
        });

        render(<PwaPrompts />);
        act(() => {
            vi.advanceTimersByTime(7000);
        });

        expect(screen.getByText('Game alerts')).toBeInTheDocument();
        expect(requestPermission).not.toHaveBeenCalled();

        await act(async () => {
            fireEvent.click(screen.getByRole('button', { name: 'Enable' }));
        });
        expect(requestPermission).toHaveBeenCalled();
        expect(window.localStorage.getItem('localplay_notifications_prompt_dismissed')).toBe('1');
    });
});
