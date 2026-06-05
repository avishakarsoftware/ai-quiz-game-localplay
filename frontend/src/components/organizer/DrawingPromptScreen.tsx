import { type CSSProperties } from 'react';
import { type ReactNode } from 'react';
import { type AIProvider } from './PromptScreen';
import { SHOW_PROVIDER_SELECTOR } from '../../config';

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
    title?: string;
    icon?: string;
    subtitle?: string;
    placeholder?: string;
    countLabel?: string;
    countOptions?: number[];
    generateLabel?: string;
    secondaryActions?: Array<{ label: string; onClick: () => void }>;
    extraControls?: ReactNode;
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
    title = 'Drawing Game',
    icon = '🎨',
    subtitle = 'Generate drawable prompts for your group',
    placeholder = 'Theme, vibe, or topic',
    countLabel = 'Prompts',
    countOptions = [5, 8, 10, 15, 20],
    generateLabel = 'Generate Prompts',
    secondaryActions = [],
    extraControls,
}: DrawingPromptScreenProps) {
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
            <div className="flex-1 flex flex-col justify-center py-8" style={{ maxWidth: 560, width: '100%', margin: '0 auto' }}>
                <div className="text-center mb-7 prompt-header">
                    <button
                        type="button"
                        onClick={onBack}
                        className="btn btn-secondary prompt-header-back"
                    >
                        Back
                    </button>
                    <div className="hero-icon mb-4">{icon}</div>
                    <h1 className="hero-title">{title}</h1>
                    <p className="text-[--text-tertiary] mt-2">{subtitle}</p>
                </div>

                <div className="space-y-5" style={{ width: '100%' }}>
                    <textarea
                        value={prompt}
                        onChange={(event) => setPrompt(event.target.value)}
                        placeholder={placeholder}
                        maxLength={140}
                        className="input-field"
                        style={{ minHeight: 140, resize: 'vertical', width: '100%' }}
                    />

                    <div>
                        <p className="text-[--text-tertiary] text-sm font-semibold mb-2">Difficulty</p>
                        <div style={segmentGrid(3)}>
                            {['easy', 'medium', 'hard'].map((value) => (
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

                    {extraControls}

                    <div>
                        <p className="text-[--text-tertiary] text-sm font-semibold mb-2">{countLabel}</p>
                        <div style={segmentGrid(5)}>
                            {countOptions.map((value) => (
                                <button
                                    key={value}
                                    type="button"
                                    onClick={() => setNumPrompts(value)}
                                    className={`btn ${numPrompts === value ? 'btn-primary' : 'btn-secondary'}`}
                                    style={segmentButton(numPrompts === value)}
                                >
                                    {value}
                                </button>
                            ))}
                        </div>
                    </div>

                    {SHOW_PROVIDER_SELECTOR && providers.length > 0 && (
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
                        className="btn btn-primary btn-glow w-full prompt-primary-action"
                    >
                        {generateLabel}
                    </button>
                    {secondaryActions.map((action) => (
                        <button
                            key={action.label}
                            type="button"
                            onClick={action.onClick}
                            className="btn btn-secondary w-full"
                        >
                            {action.label}
                        </button>
                    ))}
                </div>
            </div>
        </div>
    );
}
