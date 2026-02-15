import { useEffect, useRef } from 'react';
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

export default function LeaderboardScreen({ leaderboard, questionNumber, totalQuestions, onNextQuestion, onEndQuiz: _onEndQuiz }: LeaderboardScreenProps) {
    const timerRef = useRef<ReturnType<typeof setTimeout>>(undefined);

    useEffect(() => {
        timerRef.current = setTimeout(onNextQuestion, AUTO_ADVANCE_MS);
        return () => clearTimeout(timerRef.current);
    }, [onNextQuestion]);

    return (
        <div className="min-h-dvh flex flex-col container-responsive safe-top safe-bottom animate-in">
            {/* Auto-advance progress bar */}
            <div className="leaderboard-timer-bar">
                <div className="leaderboard-timer-fill" style={{ animationDuration: `${AUTO_ADVANCE_MS}ms` }} />
            </div>

            <div className="text-center py-6">
                <h2 className="text-xl font-bold">Leaderboard</h2>
                <p className="text-[--text-tertiary] text-sm">After question {questionNumber} of {totalQuestions}</p>
            </div>

            <div className="flex-1 mb-6">
                <LeaderboardBarChart leaderboard={leaderboard} size="compact" />
            </div>

            <div className="pb-4 flex justify-center">
                <p className="text-sm text-[--text-tertiary]">Auto-advancing to next question…</p>
            </div>
        </div>
    );
}
