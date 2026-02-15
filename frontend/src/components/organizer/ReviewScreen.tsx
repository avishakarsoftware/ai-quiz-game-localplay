import { useState } from 'react';
import { type Quiz, type Question, ANSWER_STYLES } from '../../types';

interface ReviewScreenProps {
    quiz: Quiz;
    timeLimit: number;
    setTimeLimit: (v: number) => void;
    sdAvailable: boolean;
    questionImages: Record<number, string>;
    onGenerateImages: () => void;
    onCreateRoom: () => void;
    onUpdateQuiz: (quiz: Quiz) => void;
    onExport: () => void;
    onImport: () => void;
    onBack: () => void;
}

export default function ReviewScreen({
    quiz, timeLimit, setTimeLimit, sdAvailable, questionImages,
    onGenerateImages, onCreateRoom, onUpdateQuiz, onExport, onImport, onBack,
}: ReviewScreenProps) {
    const [editingId, setEditingId] = useState<number | null>(null);
    const [editQuestion, setEditQuestion] = useState<Question | null>(null);

    const startEdit = (q: Question) => {
        setEditingId(q.id);
        setEditQuestion({ ...q, options: [...q.options] });
    };

    const cancelEdit = () => {
        setEditingId(null);
        setEditQuestion(null);
    };

    const saveEdit = () => {
        if (!editQuestion) return;
        const updated: Quiz = {
            ...quiz,
            questions: quiz.questions.map(q => q.id === editQuestion.id ? editQuestion : q),
        };
        onUpdateQuiz(updated);
        setEditingId(null);
        setEditQuestion(null);
    };

    const deleteQuestion = (id: number) => {
        if (quiz.questions.length <= 1) return;
        const updated: Quiz = {
            ...quiz,
            questions: quiz.questions.filter(q => q.id !== id),
        };
        onUpdateQuiz(updated);
    };

    return (
        <div className="min-h-dvh flex flex-col container-responsive safe-top safe-bottom animate-in">
            <div className="py-4">
                <h2 className="text-xl font-bold text-center">{quiz.quiz_title}</h2>
                <p className="text-center text-[--text-tertiary] text-sm">{quiz.questions.length} questions</p>
            </div>

            <div className="space-y-3 mb-4">
                <div className="settings-row">
                    <div>
                        <p className="font-medium">Time per question</p>
                        <p className="text-xs text-[--text-tertiary]">5-60 seconds</p>
                    </div>
                    <div className="flex items-center gap-2">
                        <input
                            type="number"
                            value={timeLimit}
                            onChange={(e) => setTimeLimit(Math.max(5, Math.min(60, parseInt(e.target.value) || 15)))}
                            className="settings-input"
                        />
                        <span className="text-[--text-tertiary]">s</span>
                    </div>
                </div>

                {sdAvailable && Object.keys(questionImages).length === 0 && (
                    <button onClick={onGenerateImages} className="btn btn-secondary w-full">
                        Generate Images
                    </button>
                )}

                {Object.keys(questionImages).length > 0 && (
                    <div className="status-pill status-success">
                        ✓ {Object.keys(questionImages).length} images ready
                    </div>
                )}
            </div>

            <div className="flex-1 overflow-y-auto no-scrollbar space-y-3 mb-4">
                {quiz.questions.map((q, i) => (
                    <div key={q.id} className="card">
                        <div className="p-4">
                            {editingId === q.id && editQuestion ? (
                                /* Edit mode */
                                <div className="space-y-3">
                                    <div className="flex items-start gap-3">
                                        <span className="rank-badge rank-default flex-shrink-0">{i + 1}</span>
                                        <input
                                            type="text"
                                            value={editQuestion.text}
                                            onChange={(e) => setEditQuestion({ ...editQuestion, text: e.target.value })}
                                            className="input-field text-sm"
                                        />
                                    </div>
                                    <div className="grid grid-cols-2 gap-2 ml-10">
                                        {editQuestion.options.map((opt, j) => {
                                            const style = ANSWER_STYLES[j];
                                            const isCorrect = j === editQuestion.answer_index;
                                            return (
                                                <div key={j} className="flex items-center gap-1">
                                                    <input
                                                        type="text"
                                                        value={opt}
                                                        onChange={(e) => {
                                                            const opts = [...editQuestion.options];
                                                            opts[j] = e.target.value;
                                                            setEditQuestion({ ...editQuestion, options: opts });
                                                        }}
                                                        className="input-field text-xs flex-1"
                                                        style={{ borderLeft: `3px solid ${style.bg}` }}
                                                    />
                                                    <button
                                                        onClick={() => setEditQuestion({ ...editQuestion, answer_index: j })}
                                                        className={`w-6 h-6 rounded-full flex items-center justify-center text-xs flex-shrink-0 ${isCorrect ? 'bg-[--accent-success] text-white' : 'bg-[--bg-tertiary] text-[--text-quaternary]'}`}
                                                        title={isCorrect ? 'Correct answer' : 'Set as correct'}
                                                    >
                                                        ✓
                                                    </button>
                                                </div>
                                            );
                                        })}
                                    </div>
                                    <div className="flex gap-2 ml-10">
                                        <button onClick={cancelEdit} className="btn btn-secondary flex-1" style={{ height: 36, fontSize: 13 }}>Cancel</button>
                                        <button onClick={saveEdit} className="btn btn-primary flex-1" style={{ height: 36, fontSize: 13 }}>Save</button>
                                    </div>
                                </div>
                            ) : (
                                /* View mode */
                                <>
                                    <div className="flex items-start gap-3 mb-3">
                                        <span className="rank-badge rank-default flex-shrink-0">{i + 1}</span>
                                        <p className="text-sm font-medium flex-1">{q.text}</p>
                                        <div className="flex gap-1 flex-shrink-0">
                                            <button
                                                onClick={() => startEdit(q)}
                                                className="w-7 h-7 rounded-lg bg-[--bg-tertiary] flex items-center justify-center text-xs text-[--text-tertiary]"
                                                title="Edit"
                                            >
                                                ✎
                                            </button>
                                            {quiz.questions.length > 1 && (
                                                <button
                                                    onClick={() => deleteQuestion(q.id)}
                                                    className="w-7 h-7 rounded-lg bg-[--bg-tertiary] flex items-center justify-center text-xs text-[--accent-danger]"
                                                    title="Delete"
                                                >
                                                    ✕
                                                </button>
                                            )}
                                        </div>
                                    </div>
                                    <div className={`grid gap-2 ml-10 ${q.options.length === 2 ? 'grid-cols-1' : 'grid-cols-2'}`}>
                                        {q.options.map((opt, j) => {
                                            const style = ANSWER_STYLES[j];
                                            const isCorrect = j === q.answer_index;
                                            return (
                                                <div
                                                    key={j}
                                                    className={`flex items-center gap-2 px-3 py-2 rounded-lg text-xs text-white font-medium ${isCorrect ? 'ring-2 ring-white ring-offset-2 ring-offset-[--bg-secondary]' : 'opacity-60'}`}
                                                    style={{ backgroundColor: style.bg }}
                                                >
                                                    <span className="text-base">{style.shape}</span>
                                                    <span className="truncate">{opt}</span>
                                                </div>
                                            );
                                        })}
                                    </div>
                                </>
                            )}
                        </div>
                    </div>
                ))}
            </div>

            <div className="flex gap-2 mb-3">
                <button onClick={onExport} className="btn btn-secondary flex-1" style={{ height: 40, fontSize: 14 }}>Export</button>
                <button onClick={onImport} className="btn btn-secondary flex-1" style={{ height: 40, fontSize: 14 }}>Import</button>
            </div>

            <div className="flex gap-3 pb-4">
                <button onClick={onBack} className="btn btn-secondary flex-1">Back</button>
                <button onClick={onCreateRoom} className="btn btn-primary flex-1">Create Room</button>
            </div>
        </div>
    );
}
