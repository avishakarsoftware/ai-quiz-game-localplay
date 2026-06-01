import { type MusicalChairsConfig, type MusicalChairsGameplayMode, type MusicalChairsMusicMode, type MusicalChairsMusicStyle } from '../../types';

const STYLES: Array<{ id: MusicalChairsMusicStyle; label: string }> = [
    { id: 'upbeat', label: 'Upbeat' },
    { id: 'jazzy', label: 'Jazzy' },
    { id: 'suspenseful', label: 'Suspense' },
    { id: 'retro', label: 'Retro' },
    { id: 'tropical', label: 'Tropical' },
];

export const defaultMusicalChairsConfig: MusicalChairsConfig = {
    game_title: 'Musical Chairs',
    gameplay_mode: 'physical',
    music_mode: 'builtin',
    music_style: 'upbeat',
    min_music_seconds: 5,
    max_music_seconds: 20,
    grab_window_seconds: 5,
    eliminations_per_round: 1,
    auto_stop: true,
    intensity_ramp: true,
};

export default function MusicalChairsSetupScreen({
    config,
    setConfig,
    onCreateRoom,
    onBack,
}: {
    config: MusicalChairsConfig;
    setConfig: (value: MusicalChairsConfig) => void;
    onCreateRoom: () => void;
    onBack: () => void;
}) {
    const update = (patch: Partial<MusicalChairsConfig>) => setConfig({ ...config, ...patch });
    const setMode = (mode: MusicalChairsMusicMode) => update({ music_mode: mode, auto_stop: mode === 'builtin' ? config.auto_stop : false });

    return (
        <div className="min-h-dvh flex flex-col container-responsive safe-top safe-bottom animate-in">
            <div className="flex-1 flex flex-col justify-center py-8" style={{ maxWidth: 620, width: '100%', margin: '0 auto' }}>
                <div className="text-center mb-7 prompt-header">
                    <button type="button" onClick={onBack} className="btn btn-secondary prompt-header-back">Back</button>
                    <div className="hero-icon mb-4">🎵</div>
                    <h1 className="hero-title">Musical Chairs</h1>
                    <p className="text-[--text-tertiary] mt-2">Run it as a physical party game or a phone-tap race.</p>
                </div>

                <div className="space-y-5">
                    <label className="housie-field">
                        <span className="housie-section-label">Game title</span>
                        <input className="input-field" value={config.game_title} onChange={(event) => update({ game_title: event.target.value.slice(0, 120) })} />
                    </label>

                    <div className="settings-row" style={{ flexDirection: 'column', alignItems: 'stretch', gap: 10 }}>
                        <p className="font-medium">Game mode</p>
                        <div className="difficulty-grid">
                            {(['physical', 'digital'] as MusicalChairsGameplayMode[]).map((mode) => (
                                <button key={mode} type="button" onClick={() => update({ gameplay_mode: mode })} className={`btn ${config.gameplay_mode === mode ? 'btn-primary' : 'btn-secondary'}`}>
                                    {mode === 'physical' ? 'Physical chairs' : 'Phone tap'}
                                </button>
                            ))}
                        </div>
                        <p className="text-xs text-[--text-tertiary]">
                            {config.gameplay_mode === 'physical'
                                ? 'The app starts/stops randomly; players use real chairs and the host chooses who is out.'
                                : 'Players race to tap their phones when the music stops; the slowest tap is out.'}
                        </p>
                    </div>

                    <div className="settings-row" style={{ flexDirection: 'column', alignItems: 'stretch', gap: 10 }}>
                        <p className="font-medium">Music mode</p>
                        <div className="difficulty-grid">
                            {(['builtin', 'external'] as MusicalChairsMusicMode[]).map((mode) => (
                                <button key={mode} type="button" onClick={() => setMode(mode)} className={`btn ${config.music_mode === mode ? 'btn-primary' : 'btn-secondary'}`}>
                                    {mode === 'builtin' ? 'Built-in' : 'External'}
                                </button>
                            ))}
                        </div>
                    </div>

                    {config.music_mode === 'builtin' && (
                        <div className="settings-row" style={{ flexDirection: 'column', alignItems: 'stretch', gap: 10 }}>
                            <p className="font-medium">Style</p>
                            <div className="mc-style-grid">
                                {STYLES.map((style) => (
                                    <button key={style.id} type="button" onClick={() => update({ music_style: style.id })} className={`btn ${config.music_style === style.id ? 'btn-primary' : 'btn-secondary'}`}>
                                        {style.label}
                                    </button>
                                ))}
                            </div>
                        </div>
                    )}

                    <div className="settings-row" style={{ flexDirection: 'column', alignItems: 'stretch', gap: 10 }}>
                        <p className="font-medium">{config.gameplay_mode === 'physical' ? 'Music window' : 'Music and tap window'}</p>
                        <div className="mc-range-row">
                            <label>Min <input type="number" min={3} max={30} value={config.min_music_seconds} onChange={(event) => update({ min_music_seconds: Number(event.target.value) })} /></label>
                            <label>Max <input type="number" min={4} max={60} value={config.max_music_seconds} onChange={(event) => update({ max_music_seconds: Number(event.target.value) })} /></label>
                            {config.gameplay_mode === 'digital' && (
                                <label>Grab <input type="number" min={2} max={10} value={config.grab_window_seconds} onChange={(event) => update({ grab_window_seconds: Number(event.target.value) })} /></label>
                            )}
                        </div>
                    </div>

                    <div className="settings-row" style={{ justifyContent: 'space-between', alignItems: 'center' }}>
                        <div>
                            <p className="font-medium">Auto stop</p>
                            <p className="text-xs text-[--text-tertiary]">Server stops the music at a random time.</p>
                        </div>
                        <button type="button" onClick={() => update({ auto_stop: !config.auto_stop })} className={`velvet-toggle ${config.auto_stop ? 'velvet-toggle-on' : 'velvet-toggle-off'}`}>
                            {config.auto_stop ? 'ON' : 'OFF'}
                        </button>
                    </div>
                </div>
            </div>

            <div className="pb-4 prompt-footer-actions">
                <button type="button" onClick={onCreateRoom} className="btn btn-primary btn-glow w-full prompt-primary-action">Create Room</button>
            </div>
        </div>
    );
}
