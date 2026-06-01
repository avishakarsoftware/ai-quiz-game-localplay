import { useState } from 'react';
import { type Quiz, type Question, ANSWER_STYLES } from '../../types';
import { useSwipeBack } from '../../utils/useSwipeBack';
import { mediaUrl } from '../../utils/media';
import GameImage from '../media/GameImage';

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

const TIME_PRESETS = [
    { value: 10, label: '10s' },
    { value: 15, label: '15s' },
    { value: 20, label: '20s' },
    { value: 30, label: '30s' },
    { value: 45, label: '45s' },
    { value: 60, label: '60s' },
];

export default function ReviewScreen({
    quiz, timeLimit, setTimeLimit,
    sdAvailable, questionImages, onGenerateImages,
    onCreateRoom, onUpdateQuiz, onBack,
}: ReviewScreenProps) {
    const swipeProgress = useSwipeBack(onBack);
    const [selectedIndex, setSelectedIndex] = useState(0);
    const [editingId, setEditingId] = useState<number | null>(null);
    const [editQuestion, setEditQuestion] = useState<Question | null>(null);
    const [showAnswers, setShowAnswers] = useState(false);
    const [touchStartX, setTouchStartX] = useState<number | null>(null);

    const boundedIndex = Math.min(selectedIndex, Math.max(quiz.questions.length - 1, 0));
    const selectedQuestion = quiz.questions[boundedIndex];
    const selectedImageUrl = selectedQuestion?.image_url
        ? mediaUrl(selectedQuestion.image_url)
        : (selectedQuestion ? questionImages[selectedQuestion.id] : '');

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
        const deletedIndex = quiz.questions.findIndex(q => q.id === id);
        const updated: Quiz = {
            ...quiz,
            questions: quiz.questions.filter(q => q.id !== id),
        };
        onUpdateQuiz(updated);
        setSelectedIndex(Math.max(0, Math.min(deletedIndex, updated.questions.length - 1)));
        if (editingId === id) cancelEdit();
    };

    const goToQuestion = (index: number) => {
        setSelectedIndex(Math.max(0, Math.min(index, quiz.questions.length - 1)));
        cancelEdit();
    };

    const goRelative = (delta: -1 | 1) => {
        goToQuestion(boundedIndex + delta);
    };

    const handleTouchEnd = (x: number) => {
        if (touchStartX === null) return;
        const delta = x - touchStartX;
        setTouchStartX(null);
        if (Math.abs(delta) < 48) return;
        if (delta < 0 && boundedIndex < quiz.questions.length - 1) goRelative(1);
        if (delta > 0 && boundedIndex > 0) goRelative(-1);
    };

    return (
        <div className="min-h-dvh flex flex-col container-responsive safe-top safe-bottom animate-in">
            {/* Swipe-back indicator */}
            {swipeProgress > 0 && (
                <div className="swipe-back-indicator" style={{ opacity: swipeProgress, transform: `translateX(${swipeProgress * 24 - 24}px)` }}>
                    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                        <polyline points="15 18 9 12 15 6" />
                    </svg>
                </div>
            )}
            <div className="review-header mb-4">
                <div className="review-header-accent" />
                <h1 className="hero-title" style={{ textAlign: 'center', marginBottom: 8 }}>{quiz.quiz_title}</h1>
                <div className="flex items-center justify-center gap-3 flex-wrap">
                    <p className="text-[--text-tertiary] text-base">{quiz.questions.length} questions ready to go</p>
                    {sdAvailable && (
                        <button
                            onClick={onGenerateImages}
                            className="btn btn-secondary"
                            style={{ padding: '4px 12px', fontSize: 13, minWidth: 0 }}
                        >
                            Generate Images
                        </button>
                    )}
                </div>
            </div>

            <div className="mb-4">
                <p className="text-center font-semibold text-base mb-2"><span style={{ fontSize: '1.5rem', verticalAlign: 'middle', marginRight: 6 }}>⏱</span>Time per question</p>
                <div className="time-preset-selector">
                    {TIME_PRESETS.map((t) => (
                        <button
                            key={t.value}
                            onClick={() => setTimeLimit(t.value)}
                            className={`time-preset-option ${timeLimit === t.value ? 'active' : ''}`}
                        >
                            {t.label}
                        </button>
                    ))}
                </div>
            </div>

            <div className="review-question-nav" aria-label="Question list">
                {quiz.questions.map((q, i) => (
                    <button
                        key={q.id}
                        type="button"
                        onClick={() => goToQuestion(i)}
                        className={`review-question-nav-btn ${i === boundedIndex ? 'active' : ''} ${q.image_url || questionImages[q.id] ? 'has-image' : ''}`}
                        aria-label={`Question ${i + 1}`}
                        aria-current={i === boundedIndex ? 'true' : undefined}
                    >
                        {i + 1}
                    </button>
                ))}
            </div>

            {selectedQuestion && (
                <div className="review-selected-wrap flex-1 overflow-y-auto no-scrollbar mb-4">
                    <div className="review-selected-controls">
                        <button onClick={() => goRelative(-1)} disabled={boundedIndex === 0} className="btn btn-secondary">Previous</button>
                        <span>Question {boundedIndex + 1} of {quiz.questions.length}</span>
                        <button onClick={() => goRelative(1)} disabled={boundedIndex === quiz.questions.length - 1} className="btn btn-secondary">Next</button>
                    </div>

                    <div
                        className="review-question-card review-selected-card"
                        onTouchStart={(event) => setTouchStartX(event.changedTouches[0]?.clientX ?? null)}
                        onTouchEnd={(event) => handleTouchEnd(event.changedTouches[0]?.clientX ?? 0)}
                    >
                        <div className="p-4">
                            {editingId === selectedQuestion.id && editQuestion ? (
                                <div className="space-y-3">
                                    <div className="flex items-center justify-between mb-1">
                                        <span className="review-q-number">{boundedIndex + 1}</span>
                                    </div>
                                    <input
                                        type="text"
                                        value={editQuestion.text}
                                        onChange={(e) => setEditQuestion({ ...editQuestion, text: e.target.value.slice(0, 2000) })}
                                        className="input-field text-sm"
                                        maxLength={2000}
                                    />
                                    {editQuestion.image_url && (
                                        <div className="space-y-2">
                                            <GameImage
                                                src={mediaUrl(editQuestion.image_url)}
                                                alt={editQuestion.image_alt || editQuestion.text}
                                                mode="thumbnail"
                                            />
                                            <input
                                                type="text"
                                                value={editQuestion.image_alt || ''}
                                                onChange={(e) => setEditQuestion({ ...editQuestion, image_alt: e.target.value.slice(0, 300) || undefined })}
                                                className="input-field text-xs"
                                                maxLength={300}
                                                placeholder="Image alt text"
                                                aria-label="Question image alt text"
                                            />
                                            <button
                                                type="button"
                                                onClick={() => setEditQuestion({ ...editQuestion, image_url: undefined, image_asset_id: undefined, image_alt: undefined })}
                                                className="btn btn-secondary"
                                                style={{ height: 36, fontSize: 13 }}
                                            >
                                                Remove Image
                                            </button>
                                        </div>
                                    )}
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
                                                            opts[j] = e.target.value.slice(0, 500);
                                                            setEditQuestion({ ...editQuestion, options: opts });
                                                        }}
                                                        className="input-field text-xs flex-1"
                                                        maxLength={500}
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
                                <>
                                    <div className="review-card-actions">
                                        <button onClick={() => startEdit(selectedQuestion)} className="review-action-btn" title="Edit">✎</button>
                                        {quiz.questions.length > 1 && (
                                            <button onClick={() => deleteQuestion(selectedQuestion.id)} className="review-action-btn review-action-delete" title="Delete">✕</button>
                                        )}
                                    </div>
                                    <div className="flex items-center gap-2 mb-3">
                                        <span className="review-q-number">{boundedIndex + 1}</span>
                                        <span className="text-xs font-bold text-[--text-tertiary]">Player preview</span>
                                    </div>
                                    <div className={`question-card review-player-preview ${selectedImageUrl ? 'has-image' : ''}`}>
                                        {selectedImageUrl && (
                                            <GameImage
                                                src={selectedImageUrl}
                                                alt={selectedQuestion.image_alt || selectedQuestion.text}
                                                mode="question"
                                            />
                                        )}
                                        <h2>{selectedQuestion.text}</h2>
                                        <div className="review-answer-grid">
                                            {selectedQuestion.options.map((opt, j) => {
                                                const isCorrect = showAnswers && j === selectedQuestion.answer_index;
                                                const style = ANSWER_STYLES[j];
                                                return (
                                                    <div
                                                        key={j}
                                                        className={`answer-option review-option ${style.className} ${isCorrect ? 'review-option-correct' : ''} ${showAnswers && !isCorrect ? 'review-option-muted' : ''}`}
                                                    >
                                                        <span className="answer-label">{String.fromCharCode(65 + j)}</span>
                                                        <span className="review-option-text">{opt}</span>
                                                        {isCorrect && <span className="review-correct-badge">Correct</span>}
                                                    </div>
                                                );
                                            })}
                                        </div>
                                    </div>
                                </>
                            )}
                        </div>
                    </div>
                </div>
            )}

            <div className="review-footer-actions pb-4">
                <button onClick={onBack} className="btn btn-secondary" style={{ flexShrink: 0, paddingLeft: 16, paddingRight: 16 }}>
                    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                        <polyline points="15 18 9 12 15 6" />
                    </svg>
                </button>
                <button
                    onClick={() => setShowAnswers(!showAnswers)}
                    className="btn btn-secondary review-answer-toggle"
                    title={showAnswers ? 'Hide answers (safe for screen mirroring)' : 'Show correct answers'}
                >
                    {showAnswers ? 'Hide Answers' : 'Show Answers'}
                </button>
                <button onClick={() => onCreateRoom()} className="btn btn-primary btn-glow" style={{ flex: 1 }}>Create Room</button>
            </div>
        </div>
    );
}
