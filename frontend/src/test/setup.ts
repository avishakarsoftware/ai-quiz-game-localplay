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
