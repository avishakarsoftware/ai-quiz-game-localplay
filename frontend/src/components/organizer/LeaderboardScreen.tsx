import { type LeaderboardEntry } from '../../types';

interface LeaderboardScreenProps {
    leaderboard: LeaderboardEntry[];
    questionNumber: number;
    totalQuestions: number;
    onNextQuestion: () => void;
}

export default function LeaderboardScreen({ leaderboard, questionNumber, totalQuestions, onNextQuestion }: LeaderboardScreenProps) {
    return (
        <div className="min-h-dvh flex flex-col container-responsive safe-top safe-bottom animate-in">
            <div className="text-center py-6">
                <h2 className="text-xl font-bold">Leaderboard</h2>
                <p className="text-[--text-tertiary] text-sm">After question {questionNumber}</p>
            </div>

            <div className="flex-1 space-y-2 mb-6">
                {leaderboard.map((player, i) => (
                    <div key={player.nickname} className="leaderboard-item">
                        <div className="flex items-center gap-3">
                            <span className={`rank-badge ${i === 0 ? 'rank-1' : i === 1 ? 'rank-2' : i === 2 ? 'rank-3' : 'rank-default'}`}>
                                {i + 1}
                            </span>
                            <span className="font-medium">{player.nickname}</span>
                            {player.rank_change !== undefined && player.rank_change !== 0 && (
                                <span className={`text-xs ${player.rank_change > 0 ? 'text-[--accent-success]' : 'text-[--accent-danger]'}`}>
                                    {player.rank_change > 0 ? `↑${player.rank_change}` : `↓${Math.abs(player.rank_change)}`}
                                </span>
                            )}
                        </div>
                        <span className="font-bold">{player.score.toLocaleString()}</span>
                    </div>
                ))}
            </div>

            <button onClick={onNextQuestion} className="btn btn-primary w-full">
                {questionNumber >= totalQuestions ? 'Show Results' : 'Next Question'}
            </button>
        </div>
    );
}
