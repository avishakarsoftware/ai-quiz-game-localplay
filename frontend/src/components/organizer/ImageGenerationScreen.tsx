import { type Quiz } from '../../types';

interface ImageGenerationScreenProps {
    quiz: Quiz;
    imageProgress: number;
}

export default function ImageGenerationScreen({ quiz, imageProgress }: ImageGenerationScreenProps) {
    return (
        <div className="min-h-dvh flex flex-col items-center justify-center container-responsive animate-in">
            <p className="text-lg font-semibold mb-4">Generating Images</p>
            <div className="w-full max-w-xs">
                <div className="progress-bar mb-2">
                    <div className="progress-bar-fill" style={{ width: `${(imageProgress / quiz.questions.length) * 100}%` }} />
                </div>
                <p className="text-center text-[--text-tertiary]">{imageProgress} / {quiz.questions.length}</p>
            </div>
        </div>
    );
}
