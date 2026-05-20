import { type AIProvider } from './PromptScreen';

interface DrawingPromptScreenProps {
    prompt: string;
    setPrompt: (value: string) => void;
    difficulty: string;
    setDifficulty: (value: string) => void;
    numPrompts: number;
    setNumPrompts: (value: number) => void;
    provider: string;
    setProvider: (value: string) => void;
    providers: AIProvider[];
    onGenerate: () => void;
    onBack: () => void;
}

export default function DrawingPromptScreen({
    prompt,
    setPrompt,
    difficulty,
    setDifficulty,
    numPrompts,
    setNumPrompts,
    provider,
    setProvider,
    providers,
    onGenerate,
    onBack,
}: DrawingPromptScreenProps) {
    return (
        <div className="min-h-dvh flex flex-col container-responsive safe-top safe-bottom animate-in">
            <div className="flex-1 flex flex-col justify-center py-8">
                <button type="button" onClick={onBack} className="btn btn-secondary mb-6" style={{ alignSelf: 'flex-start' }}>Back</button>
                <div className="text-center mb-8">
                    <div className="hero-icon mb-4">🎨</div>
                    <h1 className="hero-title">Drawing Game</h1>
                    <p className="text-[--text-tertiary] mt-2">Generate drawable prompts for your group</p>
                </div>

                <div className="space-y-5">
                    <textarea
                        value={prompt}
                        onChange={(event) => setPrompt(event.target.value)}
                        placeholder="Theme, vibe, or topic"
                        maxLength={140}
                        className="input-field"
                        style={{ minHeight: 140, resize: 'vertical' }}
                    />

                    <div>
                        <p className="text-[--text-tertiary] text-sm font-semibold mb-2">Difficulty</p>
                        <div className="grid grid-cols-3 gap-2">
                            {['easy', 'medium', 'hard'].map((value) => (
                                <button
                                    key={value}
                                    type="button"
                                    onClick={() => setDifficulty(value)}
                                    className={`btn ${difficulty === value ? 'btn-primary' : 'btn-secondary'}`}
                                >
                                    {value[0].toUpperCase() + value.slice(1)}
                                </button>
                            ))}
                        </div>
                    </div>

                    <div>
                        <p className="text-[--text-tertiary] text-sm font-semibold mb-2">Prompts</p>
                        <div className="grid grid-cols-5 gap-2">
                            {[5, 8, 10, 15, 20].map((value) => (
                                <button
                                    key={value}
                                    type="button"
                                    onClick={() => setNumPrompts(value)}
                                    className={`btn ${numPrompts === value ? 'btn-primary' : 'btn-secondary'}`}
                                >
                                    {value}
                                </button>
                            ))}
                        </div>
                    </div>

                    {providers.length > 0 && (
                        <select value={provider} onChange={(event) => setProvider(event.target.value)} className="input-field">
                            {providers.map((item) => (
                                <option key={item.id} value={item.id} disabled={!item.available}>
                                    {item.name}{item.available ? '' : ' unavailable'}
                                </option>
                            ))}
                        </select>
                    )}

                    <button
                        type="button"
                        onClick={onGenerate}
                        disabled={!prompt.trim()}
                        className="btn btn-primary btn-glow w-full"
                    >
                        Generate Prompts
                    </button>
                </div>
            </div>
        </div>
    );
}
