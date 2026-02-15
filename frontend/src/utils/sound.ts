type SoundName = 'playerJoin' | 'correct' | 'wrong' | 'timerTick' | 'gameStart' | 'podium' | 'lobbyAmbient' | 'streakBonus' | 'fanfare' | 'fireworkPop' | 'bonusRound';

const MUTE_KEY = 'localplay_muted';
const VIBRATE_KEY = 'localplay_vibration';

class SoundManager {
    private ctx: AudioContext | null = null;
    private _muted: boolean;
    private _vibrationEnabled: boolean;
    private ambientOsc: OscillatorNode | null = null;
    private ambientGain: GainNode | null = null;

    constructor() {
        this._muted = localStorage.getItem(MUTE_KEY) === 'true';
        this._vibrationEnabled = localStorage.getItem(VIBRATE_KEY) !== 'false'; // on by default
    }

    get muted() { return this._muted; }
    get vibrationEnabled() { return this._vibrationEnabled; }

    toggleMute(): boolean {
        this._muted = !this._muted;
        localStorage.setItem(MUTE_KEY, String(this._muted));
        if (this._muted) this.stopAmbient();
        return this._muted;
    }

    toggleVibration(): boolean {
        this._vibrationEnabled = !this._vibrationEnabled;
        localStorage.setItem(VIBRATE_KEY, String(this._vibrationEnabled));
        return this._vibrationEnabled;
    }

    private getCtx(): AudioContext {
        if (!this.ctx) this.ctx = new AudioContext();
        if (this.ctx.state === 'suspended') this.ctx.resume();
        return this.ctx;
    }

    private tone(freq: number, duration: number, type: OscillatorType = 'sine', volume = 0.3, startTime = 0) {
        const ctx = this.getCtx();
        const osc = ctx.createOscillator();
        const gain = ctx.createGain();
        osc.type = type;
        osc.frequency.value = freq;
        gain.gain.setValueAtTime(volume, ctx.currentTime + startTime);
        gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + startTime + duration);
        osc.connect(gain).connect(ctx.destination);
        osc.start(ctx.currentTime + startTime);
        osc.stop(ctx.currentTime + startTime + duration);
    }

    play(sound: SoundName) {
        if (this._muted) return;
        try {
            switch (sound) {
                case 'playerJoin':
                    this.tone(880, 0.15, 'sine', 0.2);
                    this.tone(1320, 0.12, 'sine', 0.1, 0.05);
                    break;
                case 'correct':
                    this.tone(523, 0.12, 'sine', 0.25);
                    this.tone(659, 0.2, 'sine', 0.25, 0.1);
                    break;
                case 'wrong':
                    this.tone(330, 0.12, 'sine', 0.25);
                    this.tone(262, 0.2, 'sine', 0.25, 0.1);
                    break;
                case 'timerTick':
                    this.tone(600, 0.05, 'square', 0.1);
                    break;
                case 'gameStart':
                    this.tone(523, 0.12, 'sine', 0.2);
                    this.tone(659, 0.12, 'sine', 0.2, 0.1);
                    this.tone(784, 0.2, 'sine', 0.2, 0.2);
                    break;
                case 'podium':
                    this.tone(523, 0.5, 'sine', 0.15);
                    this.tone(659, 0.5, 'sine', 0.15);
                    this.tone(784, 0.5, 'sine', 0.15);
                    this.tone(1047, 0.4, 'sine', 0.1, 0.15);
                    break;
                case 'streakBonus':
                    // Quick ascending sparkle
                    this.tone(784, 0.08, 'sine', 0.15);
                    this.tone(988, 0.08, 'sine', 0.15, 0.06);
                    this.tone(1175, 0.12, 'sine', 0.12, 0.12);
                    break;
                case 'fanfare': {
                    // Triumphant ascending brass-like fanfare
                    this.tone(523, 0.3, 'square', 0.12);
                    this.tone(659, 0.3, 'square', 0.12, 0.25);
                    this.tone(784, 0.3, 'square', 0.12, 0.5);
                    this.tone(1047, 0.6, 'square', 0.15, 0.75);
                    // Harmony layer
                    this.tone(440, 0.25, 'sine', 0.08);
                    this.tone(523, 0.25, 'sine', 0.08, 0.25);
                    this.tone(659, 0.25, 'sine', 0.08, 0.5);
                    this.tone(880, 0.5, 'sine', 0.1, 0.75);
                    // Final triumphant chord
                    this.tone(1047, 0.8, 'sine', 0.08, 1.2);
                    this.tone(1319, 0.8, 'sine', 0.06, 1.2);
                    this.tone(1568, 0.8, 'sine', 0.05, 1.2);
                    break;
                }
                case 'fireworkPop': {
                    // Percussive burst with sparkle tail
                    this.tone(200, 0.05, 'sawtooth', 0.15);
                    this.tone(800 + Math.random() * 400, 0.08, 'sine', 0.1, 0.03);
                    this.tone(2000 + Math.random() * 1000, 0.12, 'sine', 0.06, 0.05);
                    break;
                }
                case 'bonusRound': {
                    // Dramatic ascending power-up sound
                    this.tone(330, 0.15, 'square', 0.15);
                    this.tone(440, 0.15, 'square', 0.15, 0.1);
                    this.tone(554, 0.15, 'square', 0.15, 0.2);
                    this.tone(660, 0.15, 'square', 0.18, 0.3);
                    this.tone(880, 0.4, 'sawtooth', 0.12, 0.4);
                    // Sparkle top
                    this.tone(1760, 0.15, 'sine', 0.08, 0.6);
                    this.tone(2200, 0.2, 'sine', 0.06, 0.65);
                    break;
                }
                case 'lobbyAmbient':
                    this.startAmbient();
                    break;
            }
        } catch {
            // AudioContext may fail in some environments
        }
    }

    private startAmbient() {
        if (this.ambientOsc) return;
        try {
            const ctx = this.getCtx();
            this.ambientOsc = ctx.createOscillator();
            this.ambientGain = ctx.createGain();
            this.ambientOsc.type = 'sine';
            this.ambientOsc.frequency.value = 220;
            this.ambientGain.gain.value = 0.03; // Very subtle
            this.ambientOsc.connect(this.ambientGain).connect(ctx.destination);
            this.ambientOsc.start();
        } catch {
            // Ignore
        }
    }

    stopAmbient() {
        try {
            this.ambientOsc?.stop();
        } catch {
            // Already stopped
        }
        this.ambientOsc = null;
        this.ambientGain = null;
    }

    vibrate(pattern: number | number[]) {
        if (!this._vibrationEnabled) return;
        navigator.vibrate?.(pattern);
    }
}

export const soundManager = new SoundManager();
