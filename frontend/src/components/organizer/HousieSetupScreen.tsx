import type { HousiePattern } from '../../types';

const DEFAULT_PATTERNS: HousiePattern[] = [
    { id: 'quick_5', label: 'Quick 5', description: 'Any five called numbers' },
    { id: 'four_corners', label: 'Four Corners', description: 'Outermost filled corners' },
    { id: 'top_row', label: 'Top Row', description: 'All numbers in the top row' },
    { id: 'middle_row', label: 'Middle Row', description: 'All numbers in the middle row' },
    { id: 'bottom_row', label: 'Bottom Row', description: 'All numbers in the bottom row' },
    { id: 'full_house', label: 'Full House', description: 'Every number on the ticket' },
];

export default function HousieSetupScreen({
    title,
    setTitle,
    playMode,
    setPlayMode,
    selectedPatterns,
    setSelectedPatterns,
    callerMode,
    setCallerMode,
    autoIntervalSeconds,
    setAutoIntervalSeconds,
    autoPauseOnClaim,
    setAutoPauseOnClaim,
    onCreateRoom,
    onBack,
}: {
    title: string;
    setTitle: (value: string) => void;
    playMode: 'beginner' | 'pro';
    setPlayMode: (value: 'beginner' | 'pro') => void;
    selectedPatterns: string[];
    setSelectedPatterns: (value: string[]) => void;
    callerMode: 'manual' | 'auto';
    setCallerMode: (value: 'manual' | 'auto') => void;
    autoIntervalSeconds: number;
    setAutoIntervalSeconds: (value: number) => void;
    autoPauseOnClaim: boolean;
    setAutoPauseOnClaim: (value: boolean) => void;
    onCreateRoom: () => void;
    onBack: () => void;
}) {
    const selected = new Set(selectedPatterns);
    const togglePattern = (id: string) => {
        const next = new Set(selected);
        if (next.has(id)) next.delete(id);
        else next.add(id);
        if (next.size === 0) next.add('full_house');
        setSelectedPatterns(Array.from(next));
    };

    return (
        <div className="housie-setup min-h-dvh flex flex-col safe-top safe-bottom animate-in">
            <div className="housie-setup-hero prompt-header">
                <button type="button" onClick={onBack} className="btn btn-secondary prompt-header-back">Back</button>
                <div className="hero-icon mb-4">🎱</div>
                <h1 className="hero-title">Set Up Housie</h1>
                <p>Classic 90-ball tickets with prize claims.</p>
            </div>

            <div className="housie-setup-card">
                <div className="housie-field">
                    <label htmlFor="housie-title">Game title</label>
                    <input
                        id="housie-title"
                        className="input-field"
                        value={title}
                        onChange={(event) => setTitle(event.target.value)}
                        maxLength={120}
                    />
                </div>

                <div className="housie-field">
                    <div className="housie-section-label">Player mode</div>
                    <div className="housie-mode-grid">
                        <button type="button" className={`housie-prize-card ${playMode === 'beginner' ? 'selected' : ''}`} onClick={() => setPlayMode('beginner')}>
                            <span>Beginner</span>
                            <small>Shows called-number hints on player tickets.</small>
                        </button>
                        <button type="button" className={`housie-prize-card ${playMode === 'pro' ? 'selected' : ''}`} onClick={() => setPlayMode('pro')}>
                            <span>Pro</span>
                            <small>Classic play. Players mark manually with no ticket hints.</small>
                        </button>
                    </div>
                </div>

                <div className="housie-field">
                    <div className="housie-section-label">Caller</div>
                    <div className="housie-mode-grid">
                        <button type="button" className={`housie-prize-card ${callerMode === 'manual' ? 'selected' : ''}`} onClick={() => setCallerMode('manual')}>
                            <span>Manual</span>
                            <small>Host presses Call Next for every number.</small>
                        </button>
                        <button type="button" className={`housie-prize-card ${callerMode === 'auto' ? 'selected' : ''}`} onClick={() => setCallerMode('auto')}>
                            <span>Auto</span>
                            <small>Numbers call themselves on a timer.</small>
                        </button>
                    </div>
                </div>

                <div className="housie-info-panel">
                    <div>{callerMode === 'auto' ? 'Auto caller' : 'Manual caller'}</div>
                    <p>{callerMode === 'auto' ? `Calls a number every ${autoIntervalSeconds} seconds. You can pause or switch to manual during play.` : 'The host calls numbers one by one. The Call Next button stays above prizes during play.'}</p>
                    <label className="housie-inline-control">
                        <span>Timer</span>
                        <input
                            type="number"
                            min={3}
                            max={30}
                            value={autoIntervalSeconds}
                            onChange={(event) => setAutoIntervalSeconds(Math.max(3, Math.min(30, Number(event.target.value) || 8)))}
                            disabled={callerMode !== 'auto'}
                        />
                    </label>
                    <label className="housie-check-control">
                        <input
                            type="checkbox"
                            checked={autoPauseOnClaim}
                            onChange={(event) => setAutoPauseOnClaim(event.target.checked)}
                            disabled={callerMode !== 'auto'}
                        />
                        <span>Pause auto-caller on claims</span>
                    </label>
                </div>

                <div className="housie-field">
                    <div className="housie-section-label">Prizes</div>
                    <div className="housie-prize-grid">
                        {DEFAULT_PATTERNS.map((pattern) => (
                            <button
                                key={pattern.id}
                                type="button"
                                onClick={() => togglePattern(pattern.id)}
                                className={`housie-prize-card ${selected.has(pattern.id) ? 'selected' : ''}`}
                            >
                                <span>{pattern.label}</span>
                                <small>{pattern.description}</small>
                            </button>
                        ))}
                    </div>
                </div>
            </div>

            <div className="housie-setup-actions">
                <button onClick={onBack} className="btn btn-secondary" aria-label="Back">‹</button>
                <button onClick={() => onCreateRoom()} className="btn btn-primary btn-glow">Create Room</button>
            </div>
        </div>
    );
}
