import { useState } from 'react';
import { type MLTGame, type MLTStatement } from '../../types';
import { useSwipeBack } from '../../utils/useSwipeBack';

interface MLTReviewScreenProps {
    game: MLTGame;
    timeLimit: number;
    setTimeLimit: (v: number) => void;
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
    game, timeLimit, setTimeLimit,
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
                        {game.statements.length} statements — tap to edit
                    </p>
                </div>

                {/* Statements list */}
                <div className="space-y-3 mb-6">
                    {game.statements.map((statement, i) => (
                        <div key={statement.id} className="review-card">
                            {editingId === statement.id ? (
                                <div className="p-4 space-y-3">
                                    <textarea
                                        value={editText}
                                        onChange={(e) => setEditText(e.target.value)}
                                        className="input-field"
                                        rows={2}
                                    />
                                    <div className="flex gap-2">
                                        <button onClick={saveEdit} className="btn btn-primary" style={{ flex: 1 }}>
                                            Save
                                        </button>
                                        <button onClick={cancelEdit} className="btn btn-secondary" style={{ flex: 1 }}>
                                            Cancel
                                        </button>
                                    </div>
                                </div>
                            ) : (
                                <div
                                    className="p-4 flex items-start gap-3 cursor-pointer"
                                    onClick={() => startEdit(statement)}
                                >
                                    <span className="text-[--text-tertiary] font-mono text-sm mt-0.5">
                                        {i + 1}
                                    </span>
                                    <p className="flex-1 text-[--text-primary]">{statement.text}</p>
                                    {game.statements.length > 3 && (
                                        <button
                                            onClick={(e) => { e.stopPropagation(); deleteStatement(statement.id); }}
                                            className="text-[--text-tertiary] hover:text-[--color-error] text-lg"
                                            title="Delete statement"
                                        >
                                            ×
                                        </button>
                                    )}
                                </div>
                            )}
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
