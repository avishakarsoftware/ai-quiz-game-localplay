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
    selectedPatterns,
    setSelectedPatterns,
    onCreateRoom,
    onBack,
}: {
    title: string;
    setTitle: (value: string) => void;
    selectedPatterns: string[];
    setSelectedPatterns: (value: string[]) => void;
    callerMode: 'manual' | 'auto';
    setCallerMode: (value: 'manual' | 'auto') => void;
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
            <div className="housie-setup-hero">
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

                <div className="housie-info-panel">
                    <div>Manual caller</div>
                    <p>The host calls numbers one by one. Auto-caller is planned after the first playable release.</p>
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
                <button onClick={onCreateRoom} className="btn btn-primary btn-glow">Create Room</button>
            </div>
        </div>
    );
}
