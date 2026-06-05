import { type WhoAmIGameContent } from '../../types';

interface WhoAmIReviewScreenProps {
    game: WhoAmIGameContent;
    onUpdateGame: (game: WhoAmIGameContent) => void;
    onCreateRoom: () => void;
    onBack: () => void;
}

export default function WhoAmIReviewScreen({ game, onUpdateGame, onCreateRoom, onBack }: WhoAmIReviewScreenProps) {
    const updateRound = (index: number, patch: Partial<WhoAmIGameContent['rounds'][number]>) => {
        onUpdateGame({ ...game, rounds: game.rounds.map((round, i) => i === index ? { ...round, ...patch } : round) });
    };
    const addRound = () => {
        const next = game.rounds.length + 1;
        onUpdateGame({
            ...game,
            rounds: [...game.rounds, { id: `round_${next}`, answer: '', aliases: [], category: 'Mystery', difficulty: 'medium', clues: ['', '', '', '', ''] }],
        });
    };
    const deleteRound = (index: number) => {
        if (game.rounds.length <= 3) return;
        onUpdateGame({ ...game, rounds: game.rounds.filter((_, i) => i !== index) });
    };
    const canCreate = game.rounds.length >= 3 && game.rounds.every((round) => round.answer.trim().length >= 2 && round.clues.filter((clue) => clue.trim().length >= 5).length >= 3);

    return (
        <div className="min-h-dvh flex flex-col container-responsive safe-top safe-bottom animate-in">
            <div className="flex-1 py-6">
                <div className="text-center mb-6">
                    <div className="hero-icon mb-3">❓</div>
                    <input
                        value={game.game_title}
                        onChange={(event) => onUpdateGame({ ...game, game_title: event.target.value })}
                        className="input-field text-center"
                        style={{ fontSize: 28, fontWeight: 900 }}
                    />
                    <p className="text-[--text-secondary] mt-2">{game.rounds.length} clue rounds ready</p>
                </div>
                <div className="space-y-3">
                    {game.rounds.map((round, index) => (
                        <div key={`${round.id}-${index}`} className="review-question-card">
                            <div className="p-4 space-y-3">
                                <div className="review-card-actions">
                                    {game.rounds.length > 3 && <button type="button" className="review-action-btn review-action-delete" onClick={() => deleteRound(index)}>✕</button>}
                                </div>
                                <span className="review-q-number">{index + 1}</span>
                                <input value={round.answer} onChange={(event) => updateRound(index, { answer: event.target.value })} placeholder="Answer" className="input-field" />
                                <input value={round.category || ''} onChange={(event) => updateRound(index, { category: event.target.value })} placeholder="Category" className="input-field" />
                                {(round.clues.length ? round.clues : ['', '', '']).map((clue, clueIndex) => (
                                    <input
                                        key={clueIndex}
                                        value={clue}
                                        onChange={(event) => {
                                            const clues = [...round.clues];
                                            clues[clueIndex] = event.target.value;
                                            updateRound(index, { clues });
                                        }}
                                        placeholder={`Clue ${clueIndex + 1}`}
                                        className="input-field"
                                    />
                                ))}
                            </div>
                        </div>
                    ))}
                </div>
                <button type="button" className="btn btn-secondary w-full mt-4" onClick={addRound}>Add Round</button>
            </div>
            <div className="mt-auto pb-4 space-y-2">
                <button type="button" onClick={() => onCreateRoom()} disabled={!canCreate} className="btn btn-primary btn-glow w-full">Create Room</button>
                <button type="button" onClick={onBack} className="btn btn-secondary w-full">Back</button>
            </div>
        </div>
    );
}
