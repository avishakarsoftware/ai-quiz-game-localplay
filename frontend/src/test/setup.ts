import '@testing-library/jest-dom';

// Mock matchMedia (used by various components)
Object.defineProperty(window, 'matchMedia', {
    writable: true,
    value: vi.fn().mockImplementation((query: string) => ({
        matches: false,
        media: query,
        onchange: null,
        addListener: vi.fn(),
        removeListener: vi.fn(),
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
        dispatchEvent: vi.fn(),
    })),
});

// Mock navigator.vibrate
Object.defineProperty(navigator, 'vibrate', {
    writable: true,
    value: vi.fn(),
});

// Stub AudioContext
const mockAudioContext = {
    createOscillator: vi.fn(() => ({
        type: 'sine',
        frequency: { value: 0 },
        connect: vi.fn().mockReturnThis(),
        start: vi.fn(),
        stop: vi.fn(),
    })),
    createGain: vi.fn(() => ({
        gain: { value: 0, setValueAtTime: vi.fn(), exponentialRampToValueAtTime: vi.fn() },
        connect: vi.fn().mockReturnThis(),
    })),
    destination: {},
    currentTime: 0,
    state: 'running',
    resume: vi.fn(),
};

vi.stubGlobal('AudioContext', vi.fn(() => mockAudioContext));

// Mock ResizeObserver (used by recharts ResponsiveContainer)
vi.stubGlobal('ResizeObserver', vi.fn().mockImplementation(() => ({
    observe: vi.fn(),
    unobserve: vi.fn(),
    disconnect: vi.fn(),
})));

// Working localStorage / sessionStorage.
//
// Node 22+ ships an experimental built-in `localStorage` that SHADOWS jsdom's implementation here,
// and it is a hollow stub: `typeof localStorage.setItem === 'undefined'` (the runtime also warns
// "`--localstorage-file` was provided without a valid path"). Anything under test that persists
// state therefore silently did nothing, and `localStorage.clear()` in a test throws. That is why
// AnnouncementBanner.test.tsx defines its own mock — this makes it unnecessary for new tests.
function createStorage(): Storage {
    let store: Record<string, string> = {};
    return {
        get length() { return Object.keys(store).length; },
        key: (index: number) => Object.keys(store)[index] ?? null,
        getItem: (key: string) => (key in store ? store[key] : null),
        setItem: (key: string, value: string) => { store[key] = String(value); },
        removeItem: (key: string) => { delete store[key]; },
        clear: () => { store = {}; },
    } as Storage;
}

for (const name of ['localStorage', 'sessionStorage'] as const) {
    Object.defineProperty(window, name, { value: createStorage(), writable: true, configurable: true });
    // `localStorage` is also referenced bare (not via window) in app code and tests.
    Object.defineProperty(globalThis, name, { value: window[name], writable: true, configurable: true });
}
