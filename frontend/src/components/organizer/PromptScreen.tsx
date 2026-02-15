import { useState, useEffect } from 'react';

export interface AIProvider {
    id: string;
    name: string;
    description: string;
    available: boolean;
}

interface PromptScreenProps {
    prompt: string;
    setPrompt: (v: string) => void;
    difficulty: string;
    setDifficulty: (v: string) => void;
    numQuestions: number;
    setNumQuestions: (v: number) => void;
    provider: string;
    setProvider: (v: string) => void;
    providers: AIProvider[];
    onGenerate: () => void;
    sdAvailable: boolean;
}

const DIFFICULTIES = [
    { value: 'easy', label: 'Easy', icon: '🟢' },
    { value: 'medium', label: 'Medium', icon: '🟡' },
    { value: 'hard', label: 'Hard', icon: '🔴' },
];

const PROVIDER_ICONS: Record<string, string> = {
    ollama: '🦙',
    gemini: '✨',
    claude: '🤖',
};

const TOPIC_IDEAS = [
    'The solar system and space exploration',
    'World capitals and geography',
    '90s pop culture and music',
    'Famous inventions that changed the world',
    'Ancient Egyptian history and mythology',
    'Marvel and DC superheroes',
    'World Cup football trivia',
    'Famous scientists and their discoveries',
    'Disney and Pixar movies',
    'Ocean creatures and marine biology',
    'Video game history and iconic characters',
    'Olympic Games records and moments',
    'Classic rock bands of the 70s and 80s',
    'Mythical creatures from around the world',
    'Famous landmarks and wonders',
    'The human body and health facts',
    'Dogs breeds and fun animal facts',
    'Harry Potter wizarding world',
    'Food and cuisine around the world',
    'Technology milestones of the 21st century',
];

export default function PromptScreen({
    prompt, setPrompt, difficulty, setDifficulty,
    numQuestions, setNumQuestions, provider, setProvider,
    providers, onGenerate, sdAvailable: _sdAvailable,
}: PromptScreenProps) {
    const [initialTopic] = useState(() =>
        TOPIC_IDEAS[Math.floor(Math.random() * TOPIC_IDEAS.length)]
    );

    useEffect(() => {
        if (!prompt) setPrompt(initialTopic);
    }, []); // eslint-disable-line react-hooks/exhaustive-deps

    return (
        <div className="min-h-dvh flex flex-col container-responsive safe-top safe-bottom animate-in">
            <div className="flex-1 flex flex-col justify-center py-8">
                {/* Hero header */}
                <div className="text-center mb-8">
                    <div className="hero-icon mb-4">⚡</div>
                    <h1 className="hero-title">Create Quiz</h1>
                    <p className="text-[--text-tertiary] mt-2">What should your players be quizzed on?</p>
                </div>

                <div className="space-y-4">
                    {/* Prompt textarea with glass border */}
                    <div className="prompt-input-wrapper">
                        <textarea
                            value={prompt}
                            onChange={(e) => setPrompt(e.target.value)}
                            placeholder="Describe your quiz topic..."
                            className="input-field input-large"
                        />
                    </div>

                    {/* AI Provider selector */}
                    {providers.length > 0 && (
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

                    {/* Difficulty selector */}
                    <div>
                        <p className="section-header mb-2">Difficulty</p>
                        <div className="difficulty-selector">
                            {DIFFICULTIES.map((d) => (
                                <button
                                    key={d.value}
                                    onClick={() => setDifficulty(d.value)}
                                    className={`difficulty-option ${difficulty === d.value ? 'active' : ''}`}
                                >
                                    <span className="text-lg">{d.icon}</span>
                                    <span>{d.label}</span>
                                </button>
                            ))}
                        </div>
                    </div>

                    {/* Question count stepper */}
                    <div className="settings-row">
                        <div>
                            <p className="font-medium">Questions</p>
                            <p className="text-xs text-[--text-tertiary]">3-20 questions</p>
                        </div>
                        <div className="stepper">
                            <button
                                onClick={() => setNumQuestions(Math.max(3, numQuestions - 1))}
                                disabled={numQuestions <= 3}
                                className="stepper-btn"
                            >
                                −
                            </button>
                            <span className="stepper-value">{numQuestions}</span>
                            <button
                                onClick={() => setNumQuestions(Math.min(20, numQuestions + 1))}
                                disabled={numQuestions >= 20}
                                className="stepper-btn"
                            >
                                +
                            </button>
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
                    Generate Quiz
                </button>

            </div>
        </div>
    );
}
