interface PromptScreenProps {
    prompt: string;
    setPrompt: (v: string) => void;
    difficulty: string;
    setDifficulty: (v: string) => void;
    numQuestions: number;
    setNumQuestions: (v: number) => void;
    onGenerate: () => void;
    sdAvailable: boolean;
}

const DIFFICULTIES = [
    { value: 'easy', label: 'Easy' },
    { value: 'medium', label: 'Medium' },
    { value: 'hard', label: 'Hard' },
];

export default function PromptScreen({
    prompt, setPrompt, difficulty, setDifficulty,
    numQuestions, setNumQuestions, onGenerate, sdAvailable,
}: PromptScreenProps) {
    return (
        <div className="min-h-dvh flex flex-col container-responsive safe-top safe-bottom animate-in">
            <div className="flex-1 flex flex-col justify-center py-8">
                <h1 className="text-3xl font-bold text-center mb-2">Create Quiz</h1>
                <p className="text-center text-[--text-tertiary] mb-8">Describe what you want to quiz about</p>

                <div className="space-y-4">
                    <textarea
                        value={prompt}
                        onChange={(e) => setPrompt(e.target.value)}
                        placeholder="e.g., 10 questions about the solar system..."
                        className="input-field input-large"
                    />

                    <div>
                        <p className="text-xs text-[--text-tertiary] mb-2">Difficulty</p>
                        <div className="segmented-control">
                            {DIFFICULTIES.map((d) => (
                                <button
                                    key={d.value}
                                    onClick={() => setDifficulty(d.value)}
                                    className={`segmented-option ${difficulty === d.value ? 'active' : ''}`}
                                >
                                    {d.label}
                                </button>
                            ))}
                        </div>
                    </div>

                    <div className="settings-row">
                        <div>
                            <p className="font-medium">Questions</p>
                            <p className="text-xs text-[--text-tertiary]">3-20 questions</p>
                        </div>
                        <div className="flex items-center gap-2">
                            <input
                                type="number"
                                value={numQuestions}
                                onChange={(e) => setNumQuestions(Math.max(3, Math.min(20, parseInt(e.target.value) || 10)))}
                                className="settings-input"
                            />
                        </div>
                    </div>

                    {sdAvailable ? (
                        <div className="status-pill status-success">
                            <span>●</span> Image generation ready
                        </div>
                    ) : (
                        <div className="status-pill status-warning">
                            <span>●</span> Images unavailable
                        </div>
                    )}
                </div>
            </div>

            <div className="mt-auto pb-4">
                <button
                    onClick={onGenerate}
                    disabled={!prompt.trim()}
                    className="btn btn-primary w-full"
                >
                    Generate Quiz
                </button>
            </div>
        </div>
    );
}
