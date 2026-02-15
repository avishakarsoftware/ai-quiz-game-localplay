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
    onBack: () => void;
}

export default function ReviewScreen({
    quiz, timeLimit, setTimeLimit,
    sdAvailable: _sdAvailable, questionImages: _questionImages, onGenerateImages: _onGenerateImages,
    onCreateRoom, onUpdateQuiz, onBack,
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
            {/* Header with back button */}
            <div className="review-header mb-4">
                <div className="review-header-accent" />
                <div className="flex items-center mb-1">
                    <button onClick={onBack} className="nav-back-btn" title="Back">
                        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                            <polyline points="15 18 9 12 15 6" />
                        </svg>
                    </button>
                    <h2 className="text-lg font-bold flex-1 text-center pr-9">{quiz.quiz_title}</h2>
                </div>
                <p className="text-center text-[--text-tertiary] text-sm">{quiz.questions.length} questions ready to go</p>
            </div>

            {/* Settings strip */}
            <div className="space-y-3 mb-4">
                <div className="settings-row">
                    <div className="flex items-center gap-2">
                        <span className="text-lg">⏱</span>
                        <div>
                            <p className="font-medium">Time per question</p>
                            <p className="text-xs text-[--text-tertiary]">5-60 seconds</p>
                        </div>
                    </div>
                    <div className="stepper">
                        <button
                            onClick={() => setTimeLimit(Math.max(5, timeLimit - 5))}
                            disabled={timeLimit <= 5}
                            className="stepper-btn"
                        >
                            −
                        </button>
                        <span className="stepper-value">{timeLimit}s</span>
                        <button
                            onClick={() => setTimeLimit(Math.min(60, timeLimit + 5))}
                            disabled={timeLimit >= 60}
                            className="stepper-btn"
                        >
                            +
                        </button>
                    </div>
                </div>

            </div>

            {/* Question list */}
            <div className="flex-1 overflow-y-auto no-scrollbar space-y-3 mb-4">
                {quiz.questions.map((q, i) => (
                    <div key={q.id} className="review-question-card">
                        <div className="p-4">
                            {editingId === q.id && editQuestion ? (
                                /* Edit mode */
                                <div className="space-y-3">
                                    <div className="flex items-center justify-between mb-1">
                                        <span className="review-q-number">{i + 1}</span>
                                    </div>
                                    <input
                                        type="text"
                                        value={editQuestion.text}
                                        onChange={(e) => setEditQuestion({ ...editQuestion, text: e.target.value })}
                                        className="input-field text-sm"
                                    />
                                    <div className="grid grid-cols-2 gap-2">
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
                                    <div className="flex gap-2">
                                        <button onClick={cancelEdit} className="btn btn-secondary flex-1" style={{ height: 36, fontSize: 13 }}>Cancel</button>
                                        <button onClick={saveEdit} className="btn btn-primary flex-1" style={{ height: 36, fontSize: 13 }}>Save</button>
                                    </div>
                                </div>
                            ) : (
                                /* View mode */
                                <>
                                    <div className="review-card-actions">
                                        <button
                                            onClick={() => startEdit(q)}
                                            className="review-action-btn"
                                            title="Edit"
                                        >
                                            ✎
                                        </button>
                                        {quiz.questions.length > 1 && (
                                            <button
                                                onClick={() => deleteQuestion(q.id)}
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
                                    <p className="text-sm font-medium mb-3">{q.text}</p>
                                    <div className={`grid gap-2 ${q.options.length === 2 ? 'grid-cols-1' : 'grid-cols-2'}`}>
                                        {q.options.map((opt, j) => {
                                            const style = ANSWER_STYLES[j];
                                            const isCorrect = j === q.answer_index;
                                            return (
                                                <div
                                                    key={j}
                                                    className={`review-option ${isCorrect ? 'review-option-correct' : ''}`}
                                                    style={{ backgroundColor: isCorrect ? style.bg : `${style.bg}33` }}
                                                >
                                                    <span className="text-base">{style.shape}</span>
                                                    <span className="truncate">{opt}</span>
                                                    {isCorrect && <span className="ml-auto text-xs opacity-80">✓</span>}
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

            <div className="pb-4">
                <button onClick={onCreateRoom} className="btn btn-primary btn-glow w-full">Create Room</button>
            </div>
        </div>
    );
}
