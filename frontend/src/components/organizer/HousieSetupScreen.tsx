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
        <div className="min-h-dvh flex flex-col container-responsive safe-top safe-bottom animate-in">
            <div className="text-center mb-8">
                <div className="hero-icon mb-4">🎱</div>
                <h1 className="hero-title">Set Up Housie</h1>
                <p className="text-[--text-secondary] mt-2">Classic 90-ball tickets with prize claims.</p>
            </div>

            <div className="card space-y-6">
                <div>
                    <label className="label">Game title</label>
                    <input className="input text-xl" value={title} onChange={(event) => setTitle(event.target.value)} maxLength={120} />
                </div>

                <div className="rounded-xl border border-white/10 bg-white/5 p-4">
                    <div className="font-extrabold">Manual caller</div>
                    <p className="text-sm text-[--text-secondary]">The host calls numbers one by one. Auto-caller is planned after the first playable release.</p>
                </div>

                <div>
                    <label className="label">Prizes</label>
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                        {DEFAULT_PATTERNS.map((pattern) => (
                            <button
                                key={pattern.id}
                                type="button"
                                onClick={() => togglePattern(pattern.id)}
                                className={`text-left rounded-xl border p-4 transition ${selected.has(pattern.id) ? 'border-[--accent-pink] bg-[--accent-pink]/15' : 'border-white/10 bg-white/5'}`}
                            >
                                <div className="font-extrabold">{pattern.label}</div>
                                <div className="text-sm text-[--text-secondary]">{pattern.description}</div>
                            </button>
                        ))}
                    </div>
                </div>
            </div>

            <div className="mt-auto pt-6 grid grid-cols-[72px_1fr] gap-3">
                <button onClick={onBack} className="btn btn-secondary" aria-label="Back">‹</button>
                <button onClick={onCreateRoom} className="btn btn-primary btn-glow">Create Room</button>
            </div>
        </div>
    );
}
