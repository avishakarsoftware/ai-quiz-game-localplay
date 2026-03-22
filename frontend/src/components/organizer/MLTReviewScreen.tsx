import { useState } from 'react';
import { type MLTGame, type MLTStatement } from '../../types';
import { useSwipeBack } from '../../utils/useSwipeBack';

interface MLTReviewScreenProps {
    game: MLTGame;
    timeLimit: number;
    setTimeLimit: (v: number) => void;
    showVotes: boolean;
    setShowVotes: (v: boolean) => void;
    onCreateRoom: () => void;
    onUpdateGame: (game: MLTGame) => void;
    onBack: () => void;
}

const TIME_PRESETS = [
    { value: 10, label: '10s' },
    { value: 15, label: '15s' },
    { value: 20, label: '20s' },
    { value: 30, label: '30s' },
];

export default function MLTReviewScreen({
    game, timeLimit, setTimeLimit, showVotes, setShowVotes,
    onCreateRoom, onUpdateGame, onBack,
}: MLTReviewScreenProps) {
    const swipeProgress = useSwipeBack(onBack);
    const [editingId, setEditingId] = useState<number | null>(null);
    const [editText, setEditText] = useState('');

    const startEdit = (s: MLTStatement) => {
        setEditingId(s.id);
        setEditText(s.text);
    };

    const cancelEdit = () => {
        setEditingId(null);
        setEditText('');
    };

    const saveEdit = () => {
        if (editingId === null) return;
        const updated: MLTGame = {
            ...game,
            statements: game.statements.map(s =>
                s.id === editingId ? { ...s, text: editText.trim() } : s
            ),
        };
        onUpdateGame(updated);
        cancelEdit();
    };

    const deleteStatement = (id: number) => {
        if (game.statements.length <= 3) return; // Minimum 3 statements
        const updated: MLTGame = {
            ...game,
            statements: game.statements.filter(s => s.id !== id),
        };
        onUpdateGame(updated);
    };

    return (
        <div
            className="min-h-dvh flex flex-col container-responsive safe-top safe-bottom animate-in"
            style={swipeProgress > 0 ? { transform: `translateX(${swipeProgress}px)`, opacity: 1 - swipeProgress / 400 } : undefined}
        >
            <div className="flex-1 py-6">
                <div className="text-center mb-6">
                    <h1 className="text-2xl font-bold">{game.game_title}</h1>
                    <p className="text-[--text-secondary] mt-1">
                        {game.statements.length} statements ready to go
                    </p>
                </div>

                {/* Statements list */}
                <div className="space-y-3 mb-6">
                    {game.statements.map((statement, i) => (
                        <div key={statement.id} className="review-question-card">
                            <div className="p-4">
                                {editingId === statement.id ? (
                                    <div className="space-y-3">
                                        <div className="flex items-center justify-between mb-1">
                                            <span className="review-q-number">{i + 1}</span>
                                        </div>
                                        <textarea
                                            value={editText}
                                            onChange={(e) => setEditText(e.target.value)}
                                            className="input-field text-sm"
                                            rows={2}
                                        />
                                        <div className="flex gap-2">
                                            <button onClick={cancelEdit} className="btn btn-secondary flex-1" style={{ height: 36, fontSize: 13 }}>Cancel</button>
                                            <button onClick={saveEdit} className="btn btn-primary flex-1" style={{ height: 36, fontSize: 13 }}>Save</button>
                                        </div>
                                    </div>
                                ) : (
                                    <>
                                        <div className="review-card-actions">
                                            <button
                                                onClick={() => startEdit(statement)}
                                                className="review-action-btn"
                                                title="Edit"
                                            >
                                                ✎
                                            </button>
                                            {game.statements.length > 3 && (
                                                <button
                                                    onClick={() => deleteStatement(statement.id)}
                                                    className="review-action-btn review-action-delete"
                                                    title="Delete"
                                                >
                                                    ✕
                                                </button>
                                            )}
                                        </div>
                                        <div className="flex items-center gap-2 mb-2">
                                            <span className="review-q-number">{i + 1}</span>
                                        </div>
                                        <p className="text-sm font-medium">{statement.text}</p>
                                    </>
                                )}
                            </div>
                        </div>
                    ))}
                </div>

                {/* Time per round */}
                <div className="settings-row" style={{ flexDirection: 'column', alignItems: 'stretch', gap: 8 }}>
                    <p className="font-medium">Time per Round</p>
                    <div style={{ display: 'flex', gap: 8 }}>
                        {TIME_PRESETS.map((t) => (
                            <button
                                key={t.value}
                                onClick={() => setTimeLimit(t.value)}
                                className={`btn ${timeLimit === t.value ? 'btn-primary' : 'btn-secondary'}`}
                                style={{ flex: 1, padding: '8px 0', fontSize: '1rem' }}
                            >
                                {t.label}
                            </button>
                        ))}
                    </div>
                </div>

                {/* Show votes toggle */}
                <div className="settings-row" style={{ justifyContent: 'space-between', alignItems: 'center' }}>
                    <div>
                        <p className="font-medium">Show Vote Breakdown</p>
                        <p className="text-xs text-[--text-tertiary]">Reveal who voted for whom after each round</p>
                    </div>
                    <button
                        onClick={() => setShowVotes(!showVotes)}
                        className={`btn ${showVotes ? 'btn-primary' : 'btn-secondary'}`}
                        style={{ minWidth: 60, padding: '6px 12px', fontSize: '0.875rem' }}
                    >
                        {showVotes ? 'ON' : 'OFF'}
                    </button>
                </div>
            </div>

            <div className="mt-auto pb-4 space-y-2">
                <button
                    onClick={onCreateRoom}
                    className="btn btn-primary btn-glow w-full"
                >
                    Create Room
                </button>
                <button onClick={onBack} className="btn btn-secondary w-full">
                    Back
                </button>
            </div>
        </div>
    );
}
