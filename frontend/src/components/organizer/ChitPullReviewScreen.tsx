import { type ChitPullCategory, type ChitPullGameContent } from '../../types';
import ScreenBackButton from './ScreenBackButton';

interface ChitPullReviewScreenProps {
    game: ChitPullGameContent;
    onUpdateGame: (game: ChitPullGameContent) => void;
    onCreateRoom: () => void;
    onBack: () => void;
}

const CATEGORIES: ChitPullCategory[] = ['question', 'action', 'funny_face', 'mini_challenge', 'group'];

export default function ChitPullReviewScreen({ game, onUpdateGame, onCreateRoom, onBack }: ChitPullReviewScreenProps) {
    const updateChit = (index: number, patch: Partial<ChitPullGameContent['chits'][number]>) => {
        onUpdateGame({ ...game, chits: game.chits.map((chit, i) => i === index ? { ...chit, ...patch } : chit) });
    };
    const addChit = () => {
        const next = game.chits.length + 1;
        onUpdateGame({ ...game, chits: [...game.chits, { id: `chit_${next}`, text: '', category: 'question', safe_level: game.safe_level || 'family' }] });
    };
    const deleteChit = (index: number) => {
        if (game.chits.length <= 5) return;
        onUpdateGame({ ...game, chits: game.chits.filter((_, i) => i !== index), rounds: Math.min(game.rounds, game.chits.length - 1) });
    };
    const canCreate = game.chits.filter((chit) => chit.text.trim().length >= 3).length >= 5;

    return (
        <div className="min-h-dvh flex flex-col container-responsive safe-top safe-bottom animate-in">
            <ScreenBackButton onBack={onBack} />
            <div className="flex-1 py-6">
                <div className="text-center mb-6">
                    <div className="hero-icon mb-3">🎟️</div>
                    <input
                        value={game.game_title}
                        onChange={(event) => onUpdateGame({ ...game, game_title: event.target.value })}
                        className="input-field text-center"
                        style={{ fontSize: 28, fontWeight: 900 }}
                    />
                    <p className="text-[--text-secondary] mt-2">{game.chits.length} chits · {game.rounds} rounds</p>
                </div>
                <div className="common-ground-panel mb-4">
                    <h2>Rounds</h2>
                    <div className="time-preset-selector">
                        {[10, 20, 30, 50].map((value) => (
                            <button
                                key={value}
                                type="button"
                                className={`time-preset-option ${game.rounds === value ? 'active' : ''}`}
                                onClick={() => onUpdateGame({ ...game, rounds: Math.min(value, game.chits.length) })}
                            >
                                {value}
                            </button>
                        ))}
                    </div>
                </div>
                <div className="space-y-3">
                    {game.chits.map((chit, index) => (
                        <div key={`${chit.id}-${index}`} className="review-question-card">
                            <div className="p-4 space-y-3">
                                <div className="review-card-actions">
                                    {game.chits.length > 5 && <button type="button" className="review-action-btn review-action-delete" onClick={() => deleteChit(index)}>✕</button>}
                                </div>
                                <span className="review-q-number">{index + 1}</span>
                                <textarea
                                    value={chit.text}
                                    onChange={(event) => updateChit(index, { text: event.target.value })}
                                    placeholder="Chit text"
                                    className="input-field"
                                    rows={2}
                                />
                                <select value={chit.category} onChange={(event) => updateChit(index, { category: event.target.value as ChitPullCategory })} className="input-field">
                                    {CATEGORIES.map((category) => <option key={category} value={category}>{category.replace(/_/g, ' ')}</option>)}
                                </select>
                            </div>
                        </div>
                    ))}
                </div>
                <button type="button" className="btn btn-secondary w-full mt-4" onClick={addChit}>Add Chit</button>
            </div>
            <div className="mt-auto pb-4 space-y-2">
                <button type="button" onClick={() => onCreateRoom()} disabled={!canCreate} className="btn btn-primary btn-glow w-full">Create Room</button>
            </div>
        </div>
    );
}
