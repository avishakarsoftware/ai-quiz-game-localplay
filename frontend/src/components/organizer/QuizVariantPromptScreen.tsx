import { type CSSProperties } from 'react';
import { type GameModeConfig } from '../../gameModes';
import { type AIProvider } from './PromptScreen';

interface QuizVariantPromptScreenProps {
    config: GameModeConfig;
    prompt: string;
    setPrompt: (value: string) => void;
    difficulty: string;
    setDifficulty: (value: string) => void;
    numQuestions: number;
    setNumQuestions: (value: number) => void;
    provider: string;
    setProvider: (value: string) => void;
    providers: AIProvider[];
    onGenerate: () => void;
    onBack: () => void;
}

const DIFFICULTIES = ['easy', 'medium', 'hard'];
const COUNTS = [5, 10, 15, 20, 25];

export default function QuizVariantPromptScreen({
    config,
    prompt,
    setPrompt,
    difficulty,
    setDifficulty,
    numQuestions,
    setNumQuestions,
    provider,
    setProvider,
    providers,
    onGenerate,
    onBack,
}: QuizVariantPromptScreenProps) {
    const segmentGrid = (columns: number): CSSProperties => ({
        display: 'grid',
        gridTemplateColumns: `repeat(${columns}, minmax(0, 1fr))`,
        gap: 10,
        width: '100%',
    });

    const segmentButton = (active: boolean): CSSProperties => ({
        minHeight: 56,
        padding: '0 12px',
        borderRadius: 14,
        fontSize: 18,
        fontWeight: 800,
        whiteSpace: 'nowrap',
        boxShadow: active ? '0 12px 28px rgba(255, 45, 125, 0.28)' : undefined,
    });

    return (
        <div className="min-h-dvh flex flex-col container-responsive safe-top safe-bottom animate-in">
            <div className="flex-1 flex flex-col justify-center py-8 quiz-variant-shell">
                <button
                    type="button"
                    onClick={onBack}
                    className="btn btn-secondary mb-6 drawing-prompt-back"
                    style={{ alignSelf: 'flex-start', minWidth: 92 }}
                >
                    Back
                </button>

                <div className="text-center mb-7">
                    <div className="hero-icon mb-4">{config.icon}</div>
                    <h1 className="hero-title">{config.promptTitle || config.title}</h1>
                    <p className="text-[--text-tertiary] mt-2">{config.promptSubtitle || config.description}</p>
                </div>

                <div className="space-y-5" style={{ width: '100%' }}>
                    <textarea
                        value={prompt}
                        onChange={(event) => setPrompt(event.target.value.slice(0, 140))}
                        placeholder={config.promptPlaceholder || 'Theme, category, or topic'}
                        maxLength={140}
                        className="input-field"
                        style={{ minHeight: 140, resize: 'vertical', width: '100%' }}
                    />

                    <div>
                        <p className="text-[--text-tertiary] text-sm font-semibold mb-2">Difficulty</p>
                        <div style={segmentGrid(3)}>
                            {DIFFICULTIES.map((value) => (
                                <button
                                    key={value}
                                    type="button"
                                    onClick={() => setDifficulty(value)}
                                    className={`btn ${difficulty === value ? 'btn-primary' : 'btn-secondary'}`}
                                    style={segmentButton(difficulty === value)}
                                >
                                    {value[0].toUpperCase() + value.slice(1)}
                                </button>
                            ))}
                        </div>
                    </div>

                    <div>
                        <p className="text-[--text-tertiary] text-sm font-semibold mb-2">Rounds</p>
                        <div style={segmentGrid(5)}>
                            {COUNTS.map((value) => (
                                <button
                                    key={value}
                                    type="button"
                                    onClick={() => setNumQuestions(value)}
                                    className={`btn ${numQuestions === value ? 'btn-primary' : 'btn-secondary'}`}
                                    style={segmentButton(numQuestions === value)}
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
                        {config.generateLabel || 'Generate Game'}
                    </button>
                </div>
            </div>
        </div>
    );
}
