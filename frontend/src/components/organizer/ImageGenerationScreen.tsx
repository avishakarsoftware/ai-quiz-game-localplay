import { type Quiz } from '../../types';

interface ImageGenerationScreenProps {
    quiz: Quiz;
    imageProgress: number;
}

export default function ImageGenerationScreen({ quiz, imageProgress }: ImageGenerationScreenProps) {
    const total = quiz.questions.length;
    const pct = (imageProgress / total) * 100;
    const radius = 52;
    const circumference = 2 * Math.PI * radius;
    const dashOffset = circumference * (1 - imageProgress / total);

    return (
        <div className="min-h-dvh flex flex-col items-center justify-center container-responsive animate-in">
            {/* Circular progress ring */}
            <div className="relative mb-6">
                <svg width="120" height="120" viewBox="0 0 120 120" className="image-gen-ring">
                    <circle cx="60" cy="60" r={radius} fill="none" stroke="var(--bg-tertiary)" strokeWidth="6" />
                    <circle
                        cx="60" cy="60" r={radius} fill="none"
                        stroke="url(#imgGrad)" strokeWidth="6"
                        strokeLinecap="round"
                        strokeDasharray={circumference}
                        strokeDashoffset={dashOffset}
                        transform="rotate(-90 60 60)"
                        style={{ transition: 'stroke-dashoffset 0.5s ease-out' }}
                    />
                    <defs>
                        <linearGradient id="imgGrad" x1="0%" y1="0%" x2="100%" y2="100%">
                            <stop offset="0%" stopColor="var(--accent-primary)" />
                            <stop offset="100%" stopColor="var(--accent-secondary)" />
                        </linearGradient>
                    </defs>
                </svg>
                <div className="absolute inset-0 flex items-center justify-center">
                    <span className="text-2xl">🎨</span>
                </div>
            </div>

            <p className="text-xl font-bold mb-1">Generating Images</p>
            <p className="text-[--text-tertiary]">{imageProgress} of {total} complete</p>

            {/* Progress bar fallback */}
            <div className="w-full max-w-xs mt-4">
                <div className="progress-bar">
                    <div
                        className="progress-bar-fill"
                        style={{ width: `${pct}%`, background: 'linear-gradient(90deg, var(--accent-primary), var(--accent-secondary))' }}
                    />
                </div>
            </div>
        </div>
    );
}
