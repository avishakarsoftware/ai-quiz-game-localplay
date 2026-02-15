import { type LeaderboardEntry, type TeamLeaderboardEntry } from '../../types';

interface PodiumScreenProps {
    leaderboard: LeaderboardEntry[];
    teamLeaderboard?: TeamLeaderboardEntry[];
}

export default function PodiumScreen({ leaderboard, teamLeaderboard }: PodiumScreenProps) {
    return (
        <div className="min-h-dvh flex flex-col items-center justify-center container-responsive safe-bottom animate-in">
            <h2 className="text-2xl font-bold mb-2">Final Results</h2>

            <div className="podium-container">
                {/* 2nd Place */}
                {leaderboard[1] && (
                    <div className="podium-place podium-2">
                        <p className="podium-name">{leaderboard[1].nickname}</p>
                        <div className="podium-bar">2</div>
                        <p className="podium-score">{leaderboard[1].score}</p>
                    </div>
                )}
                {/* 1st Place */}
                {leaderboard[0] && (
                    <div className="podium-place podium-1">
                        <p className="text-3xl mb-2">🏆</p>
                        <p className="podium-name">{leaderboard[0].nickname}</p>
                        <div className="podium-bar">1</div>
                        <p className="podium-score">{leaderboard[0].score}</p>
                    </div>
                )}
                {/* 3rd Place */}
                {leaderboard[2] && (
                    <div className="podium-place podium-3">
                        <p className="podium-name">{leaderboard[2].nickname}</p>
                        <div className="podium-bar">3</div>
                        <p className="podium-score">{leaderboard[2].score}</p>
                    </div>
                )}
            </div>

            {teamLeaderboard && teamLeaderboard.length > 0 && (
                <div className="w-full mt-6 mb-4">
                    <h3 className="text-lg font-semibold text-center mb-3">Team Standings</h3>
                    <div className="space-y-2">
                        {teamLeaderboard.map((team, i) => (
                            <div key={team.team} className="leaderboard-item">
                                <div className="flex items-center gap-3">
                                    <span className={`rank-badge ${i === 0 ? 'rank-1' : i === 1 ? 'rank-2' : i === 2 ? 'rank-3' : 'rank-default'}`}>
                                        {i + 1}
                                    </span>
                                    <div>
                                        <span className="font-medium">{team.team}</span>
                                        <span className="text-xs text-[--text-tertiary] ml-2">{team.members} members</span>
                                    </div>
                                </div>
                                <span className="font-bold">{team.score.toLocaleString()}</span>
                            </div>
                        ))}
                    </div>
                </div>
            )}

            <button onClick={() => window.location.reload()} className="btn btn-primary w-full mt-8">
                Play Again
            </button>
        </div>
    );
}
