import { type Question, type GameType, ANSWER_STYLES } from '../../types';
import GameImage from '../media/GameImage';
import { hasEmoji, isEmojiForwardGame } from '../../utils/emoji';

interface GameQuestionScreenProps {
    question?: Question;
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
    onContinue?: () => void;
    revealAnswerIndex?: number | null;
    gameType?: GameType;
    statementText?: string;
}

export default function GameQuestionScreen({
    question, questionNumber, totalQuestions, timeRemaining, timeLimit, imageUrl,
    answeredCount, playerCount, isBonus, onNextQuestion, onEndQuiz, onContinue, revealAnswerIndex,
    gameType, statementText,
}: GameQuestionScreenProps) {
    const revealing = revealAnswerIndex !== undefined && revealAnswerIndex !== null;
    const timerPct = timeLimit > 0 ? (timeRemaining / timeLimit) * 100 : 0;
    const timerColor = timeRemaining <= 5 ? 'var(--accent-danger)'
        : timeRemaining <= 10 ? 'var(--accent-warning)'
        : 'var(--accent-primary)';

    const isWMLT = gameType === 'wmlt';
    const isDrawing = gameType === 'drawing';
    const isEmojiGame = isEmojiForwardGame(gameType);
    const progressLabel = isWMLT ? 'voted' : isDrawing ? 'guessed' : 'answered';
    const roundLabel = isWMLT || isDrawing ? 'Round' : 'Q';

    return (
        <div className="min-h-dvh flex flex-col container-responsive safe-top safe-bottom animate-in">
            {/* Timer bar + question counter */}
            <div className="py-4 stagger-in" style={{ animationDelay: '0s' }}>
                <div className="flex items-center justify-between mb-2">
                    <span className="text-[--text-tertiary] text-lg font-bold">{roundLabel}{questionNumber}/{totalQuestions}</span>
                    <div className="flex items-center gap-2">
                        {isBonus && <span className="bonus-badge">2X BONUS</span>}
                        {revealing ? (
                            <span className="font-extrabold text-2xl" style={{ color: 'var(--accent-success)' }}>✓ Answer</span>
                        ) : (
                            <span className={`font-extrabold tabular-nums text-2xl ${timeRemaining <= 5 ? 'timer-number-pulse' : ''}`}
                                style={{ color: timerColor }}>
                                {timeRemaining}s
                            </span>
                        )}
                    </div>
                </div>
                {!revealing && (
                    <div className="question-timer-bar">
                        <div
                            className="question-timer-fill"
                            style={{
                                width: `${timerPct}%`,
                                background: timerColor,
                            }}
                        />
                    </div>
                )}
            </div>

            {!revealing && answeredCount !== undefined && playerCount !== undefined && playerCount > 0 && (
                <div className="flex items-center justify-center gap-3 mb-4 stagger-in" style={{ animationDelay: '0.05s' }}>
                    <span className="text-sm text-[--text-tertiary]">
                        {answeredCount} of {playerCount} {progressLabel}
                    </span>
                    <div className="w-24 h-1.5 bg-[--bg-tertiary] rounded-full overflow-hidden">
                        <div
                            className="h-full bg-[--accent-success] rounded-full transition-all duration-300"
                            style={{ width: `${(answeredCount / playerCount) * 100}%` }}
                        />
                    </div>
                </div>
            )}

            {isWMLT || isDrawing ? (
                /* WMLT: show statement */
                <div className="question-card mb-6 question-enter">
                    <p className="question-text" style={{ whiteSpace: isDrawing ? 'pre-line' : undefined }}>
                        {statementText || 'Loading...'}
                    </p>
                </div>
            ) : question ? (
                /* Quiz: show question + answer options */
                <>
                    <div className={`question-card mb-6 question-enter ${imageUrl ? 'has-image' : ''}`}>
                        {imageUrl && <GameImage src={imageUrl} alt={question.text} mode="question" />}
                        <p className={`question-text ${isEmojiGame || hasEmoji(question.text) ? 'emoji-question-text' : ''}`}>{question.text}</p>
                    </div>

                    <div className={question.options.length === 2 ? 'answer-grid-tf' : 'answer-grid'}>
                        {question.options.map((opt, i) => {
                            const isAnswer = revealing && revealAnswerIndex === i;
                            return (
                                <div key={i} className={`answer-btn answer-stagger ${ANSWER_STYLES[i].className}`}
                                    style={{
                                        animationDelay: `${0.2 + i * 0.08}s`,
                                        ...(revealing ? { opacity: isAnswer ? 1 : 0.35, outline: isAnswer ? '4px solid var(--accent-success)' : undefined, outlineOffset: isAnswer ? 2 : undefined } : {}),
                                    }}>
                                    <span className="answer-label">{String.fromCharCode(65 + i)}</span>
                                    <span className={hasEmoji(opt) ? 'emoji-answer-text' : ''}>{opt}{isAnswer ? ' ✓' : ''}</span>
                                </div>
                            );
                        })}
                    </div>
                </>
            ) : null}

            {revealing ? (
                <div className="mt-auto pb-6 space-y-3" style={{ paddingTop: 32 }}>
                    {onContinue && (
                        <button onClick={onContinue} className="btn btn-game-next w-full" style={{ height: 56, fontSize: 18 }}>
                            Show Scores &rarr;
                        </button>
                    )}
                    {onEndQuiz && (
                        <button onClick={onEndQuiz} className="btn btn-game-end w-full" style={{ height: 56, fontSize: 18 }}>
                            End Game
                        </button>
                    )}
                </div>
            ) : (onNextQuestion || onEndQuiz) && (
                <div className="mt-auto pb-6 space-y-3" style={{ paddingTop: 32 }}>
                    {onNextQuestion && (
                        <button onClick={onNextQuestion} className="btn btn-game-next w-full" style={{ height: 56, fontSize: 18 }}>
                            {isWMLT || isDrawing ? 'Next Round' : 'Next Question'} &rarr;
                        </button>
                    )}
                    {onEndQuiz && (
                        <button onClick={onEndQuiz} className="btn btn-game-end w-full" style={{ height: 56, fontSize: 18 }}>
                            End Game
                        </button>
                    )}
                </div>
            )}
        </div>
    );
}
