import { useEffect, useRef, useState } from 'react';
import { type LeaderboardEntry } from '../../types';
import LeaderboardBarChart from '../LeaderboardBarChart';

const AUTO_ADVANCE_MS = 5000;

interface LeaderboardScreenProps {
    leaderboard: LeaderboardEntry[];
    questionNumber: number;
    totalQuestions: number;
    onNextQuestion: () => void;
    onEndQuiz?: () => void;
}

export default function LeaderboardScreen({ leaderboard, questionNumber, totalQuestions, onNextQuestion, onEndQuiz }: LeaderboardScreenProps) {
    const isFinal = totalQuestions > 0 && questionNumber >= totalQuestions;
    const [secondsLeft, setSecondsLeft] = useState(Math.round(AUTO_ADVANCE_MS / 1000));
    // Keep the latest callback in a ref so the auto-advance countdown is set up
    // exactly once on mount and is never reset by unrelated parent re-renders
    // (the old effect depended on `onNextQuestion`, a fresh closure each render).
    const advanceRef = useRef(onNextQuestion);
    useEffect(() => {
        advanceRef.current = onNextQuestion;
    }, [onNextQuestion]);

    useEffect(() => {
        const interval = setInterval(() => {
            setSecondsLeft((prev) => {
                if (prev <= 1) {
                    clearInterval(interval);
                    advanceRef.current();
                    return 0;
                }
                return prev - 1;
            });
        }, 1000);
        return () => clearInterval(interval);
    }, []);

    return (
        <div className="min-h-dvh flex flex-col container-responsive safe-top safe-bottom animate-in">
            {/* Auto-advance progress bar */}
            <div className="leaderboard-timer-bar">
                <div className="leaderboard-timer-fill" style={{ animationDuration: `${AUTO_ADVANCE_MS}ms` }} />
            </div>

            <div className="text-center py-6">
                <h1 className="hero-title mb-2">Leaderboard</h1>
                <p className="text-[--text-tertiary] text-base">After question {questionNumber} of {totalQuestions}</p>
            </div>

            <div className="flex-1 mb-6">
                <LeaderboardBarChart leaderboard={leaderboard} size="compact" />
            </div>

            <div className="pb-4 space-y-2">
                <button onClick={onNextQuestion} className="btn btn-primary btn-glow w-full">
                    {isFinal ? 'Show Results' : 'Next Question'}
                    {secondsLeft > 0 ? ` (${secondsLeft})` : ''}
                </button>
                {onEndQuiz && (
                    <button onClick={onEndQuiz} className="btn btn-secondary w-full">
                        End Game
                    </button>
                )}
            </div>
        </div>
    );
}
