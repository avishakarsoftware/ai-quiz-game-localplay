import { type Question, ANSWER_STYLES } from '../../types';

interface GameQuestionScreenProps {
    question: Question;
    questionNumber: number;
    totalQuestions: number;
    timeRemaining: number;
    timeLimit: number;
    imageUrl?: string;
    answeredCount?: number;
    playerCount?: number;
    isBonus?: boolean;
    onNextQuestion?: () => void;
    onEndQuiz?: () => void;
}

export default function GameQuestionScreen({
    question, questionNumber, totalQuestions, timeRemaining, timeLimit, imageUrl,
    answeredCount, playerCount, isBonus, onNextQuestion, onEndQuiz,
}: GameQuestionScreenProps) {
    const timerPct = (timeRemaining / timeLimit) * 100;
    const timerColor = timeRemaining <= 5 ? 'var(--accent-danger)'
        : timeRemaining <= 10 ? 'var(--accent-warning)'
        : 'var(--accent-primary)';

    return (
        <div className="min-h-dvh flex flex-col container-responsive safe-top safe-bottom animate-in">
            {/* Timer bar + question counter */}
            <div className="py-4 stagger-in" style={{ animationDelay: '0s' }}>
                <div className="flex items-center justify-between mb-2">
                    <div className="flex items-center gap-2">
                        <span className="text-[--text-tertiary] text-lg font-bold">Q{questionNumber}/{totalQuestions}</span>
                        {isBonus && <span className="bonus-badge">2X BONUS</span>}
                    </div>
                    <span className={`font-extrabold tabular-nums text-2xl ${timeRemaining <= 5 ? 'timer-number-pulse' : ''}`}
                        style={{ color: timerColor }}>
                        {timeRemaining}s
                    </span>
                </div>
                <div className="question-timer-bar">
                    <div
                        className="question-timer-fill"
                        style={{
                            width: `${timerPct}%`,
                            background: timerColor,
                        }}
                    />
                </div>
            </div>

            {answeredCount !== undefined && playerCount !== undefined && playerCount > 0 && (
                <div className="flex items-center justify-center gap-3 mb-4 stagger-in" style={{ animationDelay: '0.05s' }}>
                    <span className="text-sm text-[--text-tertiary]">
                        {answeredCount} of {playerCount} answered
                    </span>
                    <div className="w-24 h-1.5 bg-[--bg-tertiary] rounded-full overflow-hidden">
                        <div
                            className="h-full bg-[--accent-success] rounded-full transition-all duration-300"
                            style={{ width: `${(answeredCount / playerCount) * 100}%` }}
                        />
                    </div>
                </div>
            )}

            <div className={`question-card mb-6 question-enter ${imageUrl ? 'has-image' : ''}`}
                style={imageUrl ? { backgroundImage: `url(${imageUrl})` } : undefined}>
                <p className="question-text">{question.text}</p>
            </div>

            <div className={question.options.length === 2 ? 'answer-grid-tf' : 'answer-grid'}>
                {question.options.map((opt, i) => (
                    <div key={i} className={`answer-btn answer-stagger ${ANSWER_STYLES[i].className}`}
                        style={{ animationDelay: `${0.2 + i * 0.08}s` }}>
                        <span className="text-4xl opacity-50 mr-3">{ANSWER_STYLES[i].shape}</span>
                        <span>{opt}</span>
                    </div>
                ))}
            </div>

            {(onNextQuestion || onEndQuiz) && (
                <div className="mt-auto pb-6 space-y-3" style={{ paddingTop: 32 }}>
                    {onNextQuestion && (
                        <button onClick={onNextQuestion} className="btn btn-game-next w-full" style={{ height: 56, fontSize: 18 }}>
                            Next Question &rarr;
                        </button>
                    )}
                    {onEndQuiz && (
                        <button onClick={onEndQuiz} className="btn btn-game-end w-full" style={{ height: 56, fontSize: 18 }}>
                            End Quiz
                        </button>
                    )}
                </div>
            )}
        </div>
    );
}
