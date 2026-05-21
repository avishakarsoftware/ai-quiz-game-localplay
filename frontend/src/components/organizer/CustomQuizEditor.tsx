import { useEffect, useMemo, useState } from 'react';
import { type Question, type Quiz, ANSWER_STYLES } from '../../types';
import { useSwipeBack } from '../../utils/useSwipeBack';
import { mediaUrl } from '../../utils/media';
import GameImage from '../media/GameImage';

type QuestionType = 'multiple_choice' | 'true_false';

interface DraftQuestion {
    id: string;
    type: QuestionType;
    text: string;
    options: string[];
    answerIndex: number;
    imageUrl: string;
    imageAlt: string;
}

interface CustomQuizEditorProps {
    onBack: () => void;
    onReview: (quiz: Quiz) => void;
}

interface DraftData {
    title: string;
    questions: DraftQuestion[];
    selectedId: string;
}

const STORAGE_KEY = 'localplay_custom_quiz_draft_v1';

function createQuestion(): DraftQuestion {
    return {
        id: `q_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`,
        type: 'multiple_choice',
        text: '',
        options: ['', '', '', ''],
        answerIndex: 0,
        imageUrl: '',
        imageAlt: '',
    };
}

function normalizeOptions(question: DraftQuestion): string[] {
    return question.type === 'true_false'
        ? ['True', 'False']
        : question.options.slice(0, 4);
}

function isAllowedImageReference(value: string): boolean {
    const path = value.trim();
    if (!path) return true;
    return (
        path.startsWith('/media/') ||
        path.startsWith('/quiz/') ||
        /^https:\/\/media\.revelryapp\.me\/apps\/localplay\//i.test(path)
    );
}

function isQuestionValid(question: DraftQuestion): boolean {
    const options = normalizeOptions(question).map((opt) => opt.trim());
    const filled = options.filter(Boolean);
    return (
        question.text.trim().length > 0 &&
        filled.length >= 2 &&
        filled.length === options.length &&
        question.answerIndex >= 0 &&
        question.answerIndex < options.length &&
        isAllowedImageReference(question.imageUrl)
    );
}

function toQuiz(title: string, questions: DraftQuestion[]): Quiz {
    const validQuestions = questions.filter(isQuestionValid);
    return {
        quiz_title: title.trim(),
        questions: validQuestions.map((question, index): Question => ({
            id: index + 1,
            text: question.text.trim(),
            options: normalizeOptions(question).map((opt) => opt.trim()),
            answer_index: question.answerIndex,
            image_prompt: '',
            ...(question.imageUrl.trim() ? {
                image_url: question.imageUrl.trim(),
                image_alt: question.imageAlt.trim() || question.text.trim(),
            } : {}),
        })),
    };
}

function normalizeDraftQuestion(question: Partial<DraftQuestion>): DraftQuestion {
    const fallback = createQuestion();
    const type = question.type === 'true_false' ? 'true_false' : 'multiple_choice';
    return {
        id: question.id || fallback.id,
        type,
        text: question.text || '',
        options: type === 'true_false'
            ? ['True', 'False']
            : [...(Array.isArray(question.options) ? question.options.slice(0, 4) : []), '', '', '', ''].slice(0, 4),
        answerIndex: typeof question.answerIndex === 'number' ? question.answerIndex : 0,
        imageUrl: question.imageUrl || '',
        imageAlt: question.imageAlt || '',
    };
}

function loadDraft(): DraftData {
    const fallbackQuestion = createQuestion();
    const fallback = {
        title: 'Custom Quiz',
        questions: [fallbackQuestion],
        selectedId: fallbackQuestion.id,
    };

    try {
        const saved = localStorage.getItem(STORAGE_KEY);
        if (!saved) return fallback;
        const parsed = JSON.parse(saved) as Partial<DraftData>;
        if (!Array.isArray(parsed.questions) || parsed.questions.length === 0) return fallback;
        const questions = parsed.questions.map(normalizeDraftQuestion);
        return {
            title: parsed.title || fallback.title,
            questions,
            selectedId: parsed.selectedId || questions[0].id,
        };
    } catch {
        localStorage.removeItem(STORAGE_KEY);
        return fallback;
    }
}

export default function CustomQuizEditor({ onBack, onReview }: CustomQuizEditorProps) {
    const swipeProgress = useSwipeBack(onBack);
    const [initialDraft] = useState(loadDraft);
    const [title, setTitle] = useState(initialDraft.title);
    const [questions, setQuestions] = useState<DraftQuestion[]>(initialDraft.questions);
    const [selectedId, setSelectedId] = useState<string>(initialDraft.selectedId);

    useEffect(() => {
        localStorage.setItem(STORAGE_KEY, JSON.stringify({ title, questions, selectedId }));
    }, [title, questions, selectedId]);

    const selectedQuestion = questions.find((question) => question.id === selectedId) || questions[0];
    const validCount = questions.filter(isQuestionValid).length;
    const canReview = title.trim().length > 0 && validCount > 0;

    const updateQuestion = (id: string, patch: Partial<DraftQuestion>) => {
        setQuestions((current) => current.map((question) => {
            if (question.id !== id) return question;
            const next = { ...question, ...patch };
            if (patch.type === 'true_false') {
                next.options = ['True', 'False'];
                next.answerIndex = Math.min(next.answerIndex, 1);
            }
            if (patch.type === 'multiple_choice' && next.options.length < 4) {
                next.options = [...next.options, ...Array(4 - next.options.length).fill('')];
            }
            return next;
        }));
    };

    const addQuestion = () => {
        const question = createQuestion();
        setQuestions((current) => [...current, question]);
        setSelectedId(question.id);
    };

    const duplicateQuestion = (id: string) => {
        const source = questions.find((question) => question.id === id);
        if (!source) return;
        const duplicate = {
            ...source,
            id: `q_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`,
            text: source.text ? `${source.text} copy` : '',
        };
        const index = questions.findIndex((question) => question.id === id);
        setQuestions((current) => [
            ...current.slice(0, index + 1),
            duplicate,
            ...current.slice(index + 1),
        ]);
        setSelectedId(duplicate.id);
    };

    const deleteQuestion = (id: string) => {
        if (questions.length <= 1) return;
        const next = questions.filter((question) => question.id !== id);
        setQuestions(next);
        if (selectedId === id) setSelectedId(next[Math.max(0, questions.findIndex((question) => question.id === id) - 1)]?.id || next[0].id);
    };

    const moveQuestion = (id: string, direction: -1 | 1) => {
        const index = questions.findIndex((question) => question.id === id);
        const target = index + direction;
        if (index < 0 || target < 0 || target >= questions.length) return;
        const next = [...questions];
        [next[index], next[target]] = [next[target], next[index]];
        setQuestions(next);
    };

    const handleReview = () => {
        if (!canReview) return;
        onReview(toQuiz(title, questions));
    };

    const selectedIndex = useMemo(
        () => Math.max(0, questions.findIndex((question) => question.id === selectedQuestion?.id)),
        [questions, selectedQuestion?.id],
    );

    return (
        <div className="min-h-dvh flex flex-col container-responsive safe-top safe-bottom animate-in">
            {swipeProgress > 0 && (
                <div className="swipe-back-indicator" style={{ opacity: swipeProgress, transform: `translateX(${swipeProgress * 24 - 24}px)` }}>
                    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                        <polyline points="15 18 9 12 15 6" />
                    </svg>
                </div>
            )}

            <div className="text-center py-5">
                <div className="hero-icon mb-3">✍️</div>
                <h1 className="hero-title">Create Your Own</h1>
                <p className="text-[--text-tertiary] mt-2">{validCount} of {questions.length} questions ready</p>
            </div>

            <div className="space-y-4 flex-1 overflow-y-auto no-scrollbar pb-4">
                <div className="review-question-card">
                    <div className="p-4 space-y-3">
                        <p className="section-header">Quiz Title</p>
                        <input
                            value={title}
                            onChange={(event) => setTitle(event.target.value.slice(0, 80))}
                            className="input-field"
                            maxLength={80}
                            aria-label="Quiz title"
                        />
                    </div>
                </div>

                <div className="review-question-card">
                    <div className="p-3">
                        <div className="flex items-center justify-between mb-3">
                            <p className="section-header">Questions</p>
                            <button onClick={addQuestion} className="btn btn-secondary" style={{ height: 34, padding: '0 12px', fontSize: 13 }}>
                                Add
                            </button>
                        </div>
                        <div className="flex gap-2 overflow-x-auto no-scrollbar">
                            {questions.map((question, index) => {
                                const valid = isQuestionValid(question);
                                return (
                                    <button
                                        key={question.id}
                                        onClick={() => setSelectedId(question.id)}
                                        className={`time-preset-option ${selectedQuestion?.id === question.id ? 'active' : ''}`}
                                        style={{ minWidth: 48, borderColor: valid ? undefined : 'rgba(255, 107, 107, 0.55)' }}
                                        aria-label={`Question ${index + 1}`}
                                    >
                                        {index + 1}
                                    </button>
                                );
                            })}
                        </div>
                    </div>
                </div>

                {selectedQuestion && (
                    <div className="review-question-card">
                        <div className="p-4 space-y-4">
                            <div className="flex items-center justify-between gap-2">
                                <span className="review-q-number">{selectedIndex + 1}</span>
                                <div className="flex gap-2">
                                    <button onClick={() => moveQuestion(selectedQuestion.id, -1)} disabled={selectedIndex === 0} className="review-action-btn" title="Move earlier">↑</button>
                                    <button onClick={() => moveQuestion(selectedQuestion.id, 1)} disabled={selectedIndex === questions.length - 1} className="review-action-btn" title="Move later">↓</button>
                                    <button onClick={() => duplicateQuestion(selectedQuestion.id)} className="review-action-btn" title="Duplicate">⧉</button>
                                    {questions.length > 1 && (
                                        <button onClick={() => deleteQuestion(selectedQuestion.id)} className="review-action-btn review-action-delete" title="Delete">✕</button>
                                    )}
                                </div>
                            </div>

                            <div>
                                <p className="section-header mb-2">Question</p>
                                <textarea
                                    value={selectedQuestion.text}
                                    onChange={(event) => updateQuestion(selectedQuestion.id, { text: event.target.value.slice(0, 500) })}
                                    className="input-field"
                                    style={{ minHeight: 96, resize: 'vertical' }}
                                    maxLength={500}
                                    aria-label="Question text"
                                />
                            </div>

                            <div>
                                <p className="section-header mb-2">Type</p>
                                <div className="segmented-control">
                                    <button
                                        onClick={() => updateQuestion(selectedQuestion.id, { type: 'multiple_choice' })}
                                        className={`segmented-option ${selectedQuestion.type === 'multiple_choice' ? 'active' : ''}`}
                                    >
                                        Multiple Choice
                                    </button>
                                    <button
                                        onClick={() => updateQuestion(selectedQuestion.id, { type: 'true_false' })}
                                        className={`segmented-option ${selectedQuestion.type === 'true_false' ? 'active' : ''}`}
                                    >
                                        True / False
                                    </button>
                                </div>
                            </div>

                            <div>
                                <p className="section-header mb-2">Answers</p>
                                <div className="space-y-2">
                                    {normalizeOptions(selectedQuestion).map((option, optionIndex) => {
                                        const style = ANSWER_STYLES[optionIndex];
                                        const isCorrect = selectedQuestion.answerIndex === optionIndex;
                                        return (
                                            <div key={optionIndex} className="flex items-center gap-2">
                                                <span className="answer-label" style={{ marginRight: 0 }}>{String.fromCharCode(65 + optionIndex)}</span>
                                                <input
                                                    value={option}
                                                    onChange={(event) => {
                                                        const nextOptions = normalizeOptions(selectedQuestion);
                                                        nextOptions[optionIndex] = event.target.value.slice(0, 200);
                                                        updateQuestion(selectedQuestion.id, { options: nextOptions });
                                                    }}
                                                    disabled={selectedQuestion.type === 'true_false'}
                                                    className="input-field text-sm flex-1"
                                                    maxLength={200}
                                                    style={{ borderLeft: `3px solid ${style.bg}` }}
                                                    aria-label={`Answer ${String.fromCharCode(65 + optionIndex)}`}
                                                />
                                                <button
                                                    onClick={() => updateQuestion(selectedQuestion.id, { answerIndex: optionIndex })}
                                                    className={`w-8 h-8 rounded-full flex items-center justify-center text-sm flex-shrink-0 ${isCorrect ? 'bg-[--accent-success] text-white' : 'bg-[--bg-tertiary] text-[--text-quaternary]'}`}
                                                    title={isCorrect ? 'Correct answer' : 'Set as correct'}
                                                >
                                                    ✓
                                                </button>
                                            </div>
                                        );
                                    })}
                                </div>
                            </div>

                            <div>
                                <p className="section-header mb-2">Question Image</p>
                                {selectedQuestion.imageUrl.trim() && isAllowedImageReference(selectedQuestion.imageUrl) && (
                                    <div className="mb-3">
                                        <GameImage
                                            src={mediaUrl(selectedQuestion.imageUrl.trim())}
                                            alt={selectedQuestion.imageAlt.trim() || selectedQuestion.text || 'Question image'}
                                            mode="thumbnail"
                                        />
                                    </div>
                                )}
                                <input
                                    value={selectedQuestion.imageUrl}
                                    onChange={(event) => updateQuestion(selectedQuestion.id, { imageUrl: event.target.value.slice(0, 1000) })}
                                    className="input-field text-sm mb-2"
                                    maxLength={1000}
                                    placeholder="IONOS media URL or /media asset path"
                                    aria-label="Question image URL"
                                />
                                {selectedQuestion.imageUrl.trim() && !isAllowedImageReference(selectedQuestion.imageUrl) && (
                                    <p className="text-xs text-[--accent-danger] mb-2">Use a LocalPlay media URL from IONOS or /media.</p>
                                )}
                                <input
                                    value={selectedQuestion.imageAlt}
                                    onChange={(event) => updateQuestion(selectedQuestion.id, { imageAlt: event.target.value.slice(0, 300) })}
                                    className="input-field text-sm"
                                    maxLength={300}
                                    placeholder="Image alt text"
                                    aria-label="Question image alt text"
                                />
                            </div>
                        </div>
                    </div>
                )}
            </div>

            <div className="pb-4" style={{ display: 'flex', gap: 8 }}>
                <button onClick={onBack} className="btn btn-secondary" style={{ flexShrink: 0, paddingLeft: 16, paddingRight: 16 }}>
                    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                        <polyline points="15 18 9 12 15 6" />
                    </svg>
                </button>
                <button onClick={handleReview} disabled={!canReview} className="btn btn-primary btn-glow" style={{ flex: 1 }}>
                    Review & Start
                </button>
            </div>
        </div>
    );
}
