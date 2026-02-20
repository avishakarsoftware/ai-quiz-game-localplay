// Provide a proper localStorage mock since jsdom's may be incomplete
const store: Record<string, string> = {};
const mockLocalStorage = {
    getItem: vi.fn((key: string) => store[key] ?? null),
    setItem: vi.fn((key: string, value: string) => { store[key] = value; }),
    removeItem: vi.fn((key: string) => { delete store[key]; }),
    clear: vi.fn(() => { for (const k in store) delete store[k]; }),
    get length() { return Object.keys(store).length; },
    key: vi.fn((i: number) => Object.keys(store)[i] ?? null),
};

vi.stubGlobal('localStorage', mockLocalStorage);

describe('SoundManager', () => {
    beforeEach(() => {
        for (const k in store) delete store[k];
        vi.resetModules();
        vi.mocked(navigator.vibrate).mockClear();
    });

    async function freshSoundManager() {
        const mod = await import('../sound');
        return mod.soundManager;
    }

    it('defaults to not muted', async () => {
        const sm = await freshSoundManager();
        expect(sm.muted).toBe(false);
    });

    it('defaults to vibration enabled', async () => {
        const sm = await freshSoundManager();
        expect(sm.vibrationEnabled).toBe(true);
    });

    it('reads muted state from localStorage', async () => {
        store['localplay_muted'] = 'true';
        const sm = await freshSoundManager();
        expect(sm.muted).toBe(true);
    });

    it('reads vibration disabled from localStorage', async () => {
        store['localplay_vibration'] = 'false';
        const sm = await freshSoundManager();
        expect(sm.vibrationEnabled).toBe(false);
    });

    it('toggleMute flips muted state', async () => {
        const sm = await freshSoundManager();
        expect(sm.muted).toBe(false);
        const result = sm.toggleMute();
        expect(result).toBe(true);
        expect(sm.muted).toBe(true);
    });

    it('toggleMute persists to localStorage', async () => {
        const sm = await freshSoundManager();
        sm.toggleMute();
        expect(store['localplay_muted']).toBe('true');
        sm.toggleMute();
        expect(store['localplay_muted']).toBe('false');
    });

    it('toggleVibration flips vibration state', async () => {
        const sm = await freshSoundManager();
        expect(sm.vibrationEnabled).toBe(true);
        const result = sm.toggleVibration();
        expect(result).toBe(false);
        expect(sm.vibrationEnabled).toBe(false);
    });

    it('toggleVibration persists to localStorage', async () => {
        const sm = await freshSoundManager();
        sm.toggleVibration();
        expect(store['localplay_vibration']).toBe('false');
        sm.toggleVibration();
        expect(store['localplay_vibration']).toBe('true');
    });

    it('play does nothing when muted', async () => {
        const sm = await freshSoundManager();
        sm.toggleMute();
        expect(() => sm.play('correct')).not.toThrow();
    });

    it('vibrate does nothing when vibration disabled', async () => {
        const sm = await freshSoundManager();
        sm.toggleVibration();
        sm.vibrate(100);
        expect(navigator.vibrate).not.toHaveBeenCalled();
    });

    it('vibrate calls navigator.vibrate when enabled', async () => {
        const sm = await freshSoundManager();
        sm.vibrate([100, 50, 100]);
        expect(navigator.vibrate).toHaveBeenCalledWith([100, 50, 100]);
    });
});
