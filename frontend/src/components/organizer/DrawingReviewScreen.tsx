import { type DrawingGame } from '../../types';

interface DrawingReviewScreenProps {
    game: DrawingGame;
    timeLimit: number;
    setTimeLimit: (value: number) => void;
    autoAdvance: boolean;
    setAutoAdvance: (value: boolean) => void;
    onCreateRoom: () => void;
    onUpdateGame: (game: DrawingGame) => void;
    onBack: () => void;
}

export default function DrawingReviewScreen({ game, timeLimit, setTimeLimit, autoAdvance, setAutoAdvance, onCreateRoom, onUpdateGame, onBack }: DrawingReviewScreenProps) {
    const updatePrompt = (id: number, text: string) => {
        onUpdateGame({
            ...game,
            prompts: game.prompts.map((prompt) => prompt.id === id ? { ...prompt, text } : prompt),
        });
    };

    return (
        <div className="min-h-dvh flex flex-col container-responsive safe-top safe-bottom animate-in">
            <div className="py-6" style={{ maxWidth: 680, width: '100%', margin: '0 auto' }}>
                <button type="button" onClick={onBack} className="btn btn-secondary mb-5" style={{ minWidth: 92 }}>Back</button>
                <div className="text-center mb-6">
                    <div className="hero-icon mb-4">🎨</div>
                    <h1 className="hero-title">{game.game_title}</h1>
                    <p className="text-[--text-secondary] mt-2">{game.prompts.length} drawable prompts</p>
                </div>

                <div className="drawing-review-controls">
                    <p className="text-center font-semibold text-base mb-2">
                        <span style={{ fontSize: '1.5rem', verticalAlign: 'middle', marginRight: 6 }}>⏱</span>
                        Time per round
                    </p>
                    <div className="time-preset-selector">
                        {[15, 30, 45, 50, 60].map((value) => (
                            <button
                                key={value}
                                type="button"
                                onClick={() => setTimeLimit(value)}
                                className={`time-preset-option ${timeLimit === value ? 'active' : ''}`}
                            >
                                {value}s
                            </button>
                        ))}
                    </div>
                    <div className="drawing-advance-row">
                        <div>
                            <p className="font-semibold">Round advance</p>
                            <p className="text-[--text-tertiary] text-sm">
                                {autoAdvance ? 'Pause 5s, then start the next round' : 'Host starts each next round manually'}
                            </p>
                        </div>
                        <div className="segmented-pill" role="group" aria-label="Drawing round advance">
                            <button type="button" className={autoAdvance ? 'active' : ''} onClick={() => setAutoAdvance(true)}>Auto</button>
                            <button type="button" className={!autoAdvance ? 'active' : ''} onClick={() => setAutoAdvance(false)}>Manual</button>
                        </div>
                    </div>
                </div>

                <div className="space-y-3 mb-6">
                    {game.prompts.map((prompt, index) => (
                        <div key={prompt.id} className="card p-4">
                            <label className="text-[--text-tertiary] text-xs font-semibold mb-2 block">Prompt {index + 1}</label>
                            <input
                                value={prompt.text}
                                onChange={(event) => updatePrompt(prompt.id, event.target.value)}
                                className="input-field"
                                maxLength={80}
                            />
                            {prompt.aliases && prompt.aliases.length > 0 && (
                                <p className="text-[--text-tertiary] text-xs mt-2">Aliases: {prompt.aliases.join(', ')}</p>
                            )}
                        </div>
                    ))}
                </div>

                <div className="quiz-library-footer">
                    <button type="button" onClick={onBack} className="btn btn-secondary" aria-label="Back">‹</button>
                    <button type="button" onClick={() => onCreateRoom()} className="btn btn-primary btn-glow w-full">
                        Create Room
                    </button>
                </div>
            </div>
        </div>
    );
}
