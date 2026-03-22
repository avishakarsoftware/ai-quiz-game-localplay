import { type AIProvider } from './PromptScreen';
import { useSwipeBack } from '../../utils/useSwipeBack';
import { useEntitlement } from '../../hooks/useEntitlement';
import QuotaBadge from '../QuotaBadge';
import SignInNudge from '../SignInNudge';

interface MLTPromptScreenProps {
    prompt: string;
    setPrompt: (v: string) => void;
    difficulty: string;
    setDifficulty: (v: string) => void;
    numRounds: number;
    setNumRounds: (v: number) => void;
    provider: string;
    setProvider: (v: string) => void;
    providers: AIProvider[];
    onGenerate: () => void;
    onBack: () => void;
}

const VIBES = [
    { value: 'party', label: 'Party', icon: '🎉' },
    { value: 'spicy', label: 'Spicy', icon: '🌶️' },
    { value: 'wholesome', label: 'Wholesome', icon: '💛' },
    { value: 'work', label: 'Work', icon: '💼' },
];

const PROVIDER_ICONS: Record<string, string> = {
    ollama: '🦙',
    gemini: '✨',
    claude: '🤖',
};

const THEME_IDEAS = [
    'camping trip with friends',
    'office party gone wrong',
    'zombie apocalypse survival',
    'deserted island',
    'road trip across the country',
    'high school reunion',
    'starting a band together',
    'winning the lottery',
    'time travel to the past',
    'living in a haunted house',
    'being on a reality TV show',
    'cooking competition',
    'superhero team',
    'planning a surprise party',
    'escape room challenge',
    'moving to a new country',
    'baby-sitting chaos',
    'going viral on social media',
    'opening a restaurant',
    'space mission to Mars',
    'holiday family dinner',
    'music festival weekend',
    'backpacking through Europe',
    'starting a business together',
    'alien invasion scenario',
    'medieval kingdom',
    'detective mystery night',
    'beach vacation',
    'gym and fitness challenge',
    'pet adoption day',
];

export default function MLTPromptScreen({
    prompt, setPrompt, difficulty, setDifficulty,
    numRounds, setNumRounds, provider, setProvider,
    providers, onGenerate, onBack,
}: MLTPromptScreenProps) {
    const { entitlement, loading: entitlementLoading } = useEntitlement();
    const swipeProgress = useSwipeBack(onBack);

    const shuffleTheme = () => {
        let next: string;
        do {
            next = THEME_IDEAS[Math.floor(Math.random() * THEME_IDEAS.length)];
        } while (next === prompt && THEME_IDEAS.length > 1);
        setPrompt(next);
    };

    return (
        <div
            className="min-h-dvh flex flex-col container-responsive safe-top safe-bottom animate-in"
            style={swipeProgress > 0 ? { transform: `translateX(${swipeProgress}px)`, opacity: 1 - swipeProgress / 400 } : undefined}
        >
            <div className="flex-1 flex flex-col justify-center py-8">
                <div className="text-center mb-8">
                    <div className="hero-icon mb-4">🎯</div>
                    <h1 className="hero-title">Most Likely To</h1>
                    <p className="text-[--text-tertiary] mt-2">Enter a theme for your statements</p>
                    <div className="mt-3" style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 6 }}>
                        <QuotaBadge entitlement={entitlement} loading={entitlementLoading} />
                        <SignInNudge isPremium={entitlement.premium} />
                    </div>
                </div>

                <div className="space-y-4">
                    <div className="prompt-input-wrapper" style={{ position: 'relative' }}>
                        <textarea
                            value={prompt}
                            onChange={(e) => setPrompt(e.target.value.slice(0, 140))}
                            placeholder="e.g., camping trip, office party, zombie apocalypse"
                            className="input-field input-large"
                            maxLength={140}
                        />
                        <button
                            type="button"
                            onClick={shuffleTheme}
                            className="shuffle-btn"
                            title="Suggest a random theme"
                        >
                            🎲
                        </button>
                        <div className="text-xs text-right mt-1" style={{ color: prompt.length > 120 ? 'var(--color-error, #ef4444)' : 'var(--text-tertiary)' }}>
                            {prompt.length}/140
                        </div>
                    </div>

                    {/* AI Provider selector */}
                    {import.meta.env.DEV && providers.length > 0 && (
                        <div>
                            <p className="section-header mb-2">AI Provider</p>
                            <div className="provider-selector">
                                {providers.map((p) => (
                                    <button
                                        key={p.id}
                                        onClick={() => p.available && setProvider(p.id)}
                                        className={`provider-option ${provider === p.id ? 'active' : ''} ${!p.available ? 'unavailable' : ''}`}
                                        disabled={!p.available}
                                    >
                                        <span className="text-lg">{PROVIDER_ICONS[p.id] || '🧠'}</span>
                                        <span className="provider-name">{p.name}</span>
                                        {!p.available && <span className="provider-badge">{p.id === 'ollama' ? 'Offline' : 'No key'}</span>}
                                    </button>
                                ))}
                            </div>
                        </div>
                    )}

                    {/* Vibe selector */}
                    <div>
                        <p className="section-header mb-2">Vibe</p>
                        <div className="difficulty-selector">
                            {VIBES.map((v) => (
                                <button
                                    key={v.value}
                                    onClick={() => setDifficulty(v.value)}
                                    className={`difficulty-option ${difficulty === v.value ? 'active' : ''}`}
                                >
                                    <span className="text-lg">{v.icon}</span>
                                    <span>{v.label}</span>
                                </button>
                            ))}
                        </div>
                    </div>

                    {/* Round count */}
                    <div className="settings-row" style={{ flexDirection: 'column', alignItems: 'stretch', gap: 8 }}>
                        <p className="font-medium">Rounds</p>
                        <div style={{ display: 'flex', gap: 8 }}>
                            {[5, 10, 15, 20].map(n => (
                                <button
                                    key={n}
                                    onClick={() => setNumRounds(n)}
                                    className={`btn ${numRounds === n ? 'btn-primary' : 'btn-secondary'}`}
                                    style={{ flex: 1, padding: '8px 0', fontSize: '1rem' }}
                                >
                                    {n}
                                </button>
                            ))}
                        </div>
                    </div>
                </div>
            </div>

            <div className="mt-auto pb-4 space-y-2">
                <button
                    onClick={onGenerate}
                    disabled={!prompt.trim()}
                    className="btn btn-primary btn-glow w-full"
                >
                    Generate Questions
                </button>
                <button onClick={onBack} className="btn btn-secondary w-full">
                    Back
                </button>
            </div>
        </div>
    );
}
