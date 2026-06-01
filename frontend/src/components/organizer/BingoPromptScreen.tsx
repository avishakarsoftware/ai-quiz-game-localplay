import { Wand2 } from 'lucide-react';
import SignInNudge from '../SignInNudge';
import { useTokenBalance } from '../../hooks/useTokenBalance';
import { type AIProvider } from './PromptScreen';
import { SHOW_PROVIDER_SELECTOR } from '../../config';

const ITEM_COUNTS = [24, 30, 40, 50];
const DIFFICULTIES = [
    { value: 'easy', label: 'Easy' },
    { value: 'medium', label: 'Medium' },
    { value: 'hard', label: 'Hard' },
];

export default function BingoPromptScreen({
    prompt,
    setPrompt,
    difficulty,
    setDifficulty,
    numItems,
    setNumItems,
    provider,
    setProvider,
    providers,
    onGenerate,
    onCreateCustom,
    onBack,
}: {
    prompt: string;
    setPrompt: (value: string) => void;
    difficulty: string;
    setDifficulty: (value: string) => void;
    numItems: number;
    setNumItems: (value: number) => void;
    provider: string;
    setProvider: (value: string) => void;
    providers: AIProvider[];
    onGenerate: () => void;
    onCreateCustom: () => void;
    onBack: () => void;
}) {
    const { tokenStatus } = useTokenBalance();

    return (
        <div className="min-h-dvh flex flex-col container-responsive safe-top safe-bottom animate-in">
            <div className="flex-1 flex flex-col justify-center py-8">
                <div className="text-center mb-8">
                    <div className="hero-icon mb-4">▦</div>
                    <h1 className="hero-title">Create Bingo</h1>
                    <p className="text-[--text-tertiary] mt-2">Give a theme and get an editable Bingo deck.</p>
                    <div className="mt-3" style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 6 }}>
                        <SignInNudge isPremium={tokenStatus.has_purchased} />
                    </div>
                </div>

                <div className="space-y-4">
                    <textarea
                        value={prompt}
                        onChange={(event) => setPrompt(event.target.value.slice(0, 140))}
                        placeholder="Baby shower, office holiday party, wedding reception..."
                        className="input-field input-large"
                        maxLength={140}
                    />

                    {SHOW_PROVIDER_SELECTOR && providers.length > 0 && (
                        <div>
                            <p className="section-header mb-2">AI Provider</p>
                            <div className="provider-selector">
                                {providers.map((option) => (
                                    <button
                                        key={option.id}
                                        onClick={() => option.available && setProvider(option.id)}
                                        className={`provider-option ${provider === option.id ? 'active' : ''} ${!option.available ? 'unavailable' : ''}`}
                                        disabled={!option.available}
                                    >
                                        <span className="provider-name">{option.name}</span>
                                    </button>
                                ))}
                            </div>
                        </div>
                    )}

                    <div>
                        <p className="section-header mb-2">Style</p>
                        <div className="difficulty-selector">
                            {DIFFICULTIES.map((option) => (
                                <button
                                    key={option.value}
                                    onClick={() => setDifficulty(option.value)}
                                    className={`difficulty-option ${difficulty === option.value ? 'active' : ''}`}
                                >
                                    <span>{option.label}</span>
                                </button>
                            ))}
                        </div>
                    </div>

                    <div className="settings-row" style={{ flexDirection: 'column', alignItems: 'stretch', gap: 8 }}>
                        <p className="font-medium">Deck items</p>
                        <div style={{ display: 'flex', gap: 8 }}>
                            {ITEM_COUNTS.map((count) => (
                                <button
                                    key={count}
                                    type="button"
                                    onClick={() => setNumItems(count)}
                                    className={`btn ${numItems === count ? 'btn-primary' : 'btn-secondary'}`}
                                    style={{ flex: 1, padding: '8px 0', fontSize: '1rem' }}
                                >
                                    {count}
                                </button>
                            ))}
                        </div>
                    </div>
                </div>
            </div>

            <div className="mt-auto pb-4 space-y-2 prompt-footer-actions">
                <button onClick={onGenerate} disabled={!prompt.trim()} className="btn btn-primary btn-glow w-full prompt-primary-action">
                    <Wand2 size={18} /> Generate Bingo
                </button>
                <button type="button" onClick={onCreateCustom} className="btn btn-secondary w-full">
                    Custom Deck
                </button>
                <button type="button" onClick={onBack} className="btn btn-secondary w-full">
                    Back
                </button>
            </div>
        </div>
    );
}
