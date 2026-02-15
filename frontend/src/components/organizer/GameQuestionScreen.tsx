import { type Question, ANSWER_STYLES } from '../../types';

interface GameQuestionScreenProps {
    question: Question;
    questionNumber: number;
    totalQuestions: number;
    timeRemaining: number;
    timeLimit: number;
    imageUrl?: string;
}

export default function GameQuestionScreen({
    question, questionNumber, totalQuestions, timeRemaining, timeLimit, imageUrl,
}: GameQuestionScreenProps) {
    const timerProgress = (timeRemaining / timeLimit) * 100;

    return (
        <div className="min-h-dvh flex flex-col container-responsive safe-top safe-bottom animate-in">
            <div className="flex items-center justify-between py-4">
                <span className="text-[--text-tertiary]">Q{questionNumber}/{totalQuestions}</span>
                <span className={`timer-display ${timeRemaining <= 5 ? 'danger' : timeRemaining <= 10 ? 'warning' : ''}`}>
                    {timeRemaining}
                </span>
            </div>

            <div className="progress-bar mb-6">
                <div className={`progress-bar-fill ${timeRemaining <= 5 ? 'danger' : timeRemaining <= 10 ? 'warning' : ''}`}
                    style={{ width: `${timerProgress}%` }} />
            </div>

            <div className={`question-card mb-6 ${imageUrl ? 'has-image' : ''}`}
                style={imageUrl ? { backgroundImage: `url(${imageUrl})` } : undefined}>
                <p className="question-text">{question.text}</p>
            </div>

            <div className={question.options.length === 2 ? 'answer-grid-tf' : 'answer-grid'}>
                {question.options.map((opt, i) => (
                    <div key={i} className={`answer-btn ${ANSWER_STYLES[i].className}`}>
                        <span className="text-2xl opacity-50 mr-2">{ANSWER_STYLES[i].shape}</span>
                        <span>{opt}</span>
                    </div>
                ))}
            </div>
        </div>
    );
}
