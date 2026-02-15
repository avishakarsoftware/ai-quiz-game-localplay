import { useState, useEffect } from 'react';
import { type LeaderboardEntry, type TeamLeaderboardEntry } from '../../types';
import { soundManager } from '../../utils/sound';
import AnimatedNumber from '../AnimatedNumber';
import Fireworks from '../Fireworks';

interface PodiumScreenProps {
    leaderboard: LeaderboardEntry[];
    teamLeaderboard?: TeamLeaderboardEntry[];
    onPlayAgain: () => void;
}

export default function PodiumScreen({ leaderboard, teamLeaderboard, onPlayAgain }: PodiumScreenProps) {
    const [revealPhase, setRevealPhase] = useState(0);

    useEffect(() => {
        const timers = [
            setTimeout(() => setRevealPhase(1), 300),
            setTimeout(() => setRevealPhase(2), 1000),
            setTimeout(() => setRevealPhase(3), 1700),
            setTimeout(() => setRevealPhase(4), 2500),
        ];
        return () => timers.forEach(clearTimeout);
    }, []);

    useEffect(() => {
        if (revealPhase >= 1 && revealPhase <= 3) {
            soundManager.play('fireworkPop');
        }
    }, [revealPhase]);

    return (
        <div className="min-h-dvh flex flex-col items-center justify-center container-responsive safe-bottom animate-in"
             style={{ position: 'relative', overflow: 'hidden' }}>
            <Fireworks duration={15000} maxRockets={3} />

            <h2 className="text-3xl font-extrabold text-center tracking-tight mb-4" style={{ position: 'relative', zIndex: 11 }}>Final Results</h2>

            {revealPhase >= 4 && leaderboard[0] && (
                <div className="champion-label" style={{ position: 'relative', zIndex: 11 }}>
                    <span className="crown-bounce text-2xl">&#x1F451;</span>
                    <span className="gold-shimmer text-xl">{leaderboard[0].nickname} is the Champion!</span>
                </div>
            )}

            <div className="podium-container" style={{ position: 'relative', zIndex: 11 }}>
                {/* 2nd Place */}
                {leaderboard[1] && (
                    <div className={`podium-place podium-2 ${revealPhase >= 2 ? '' : 'podium-hidden'}`}>
                        <div className="w-12 h-12 rounded-full flex items-center justify-center mb-2" style={{ backgroundColor: '#C0C0C0' }}>
                            <span style={{ fontSize: '1.5rem', lineHeight: 1 }}>{leaderboard[1].avatar || leaderboard[1].nickname.slice(0, 2).toUpperCase()}</span>
                        </div>
                        <p className="podium-name">{leaderboard[1].nickname}</p>
                        <div className="podium-bar">2</div>
                        <p className="podium-score"><AnimatedNumber value={revealPhase >= 2 ? leaderboard[1].score : 0} /></p>
                    </div>
                )}
                {/* 1st Place */}
                {leaderboard[0] && (
                    <div className={`podium-place podium-1 ${revealPhase >= 3 ? '' : 'podium-hidden'} ${revealPhase >= 4 ? 'victory-glow' : ''}`}>
                        {revealPhase >= 4 && <span className="crown-bounce text-3xl" style={{ marginBottom: 4 }}>&#x1F451;</span>}
                        <div className="w-14 h-14 rounded-full flex items-center justify-center mb-2" style={{ backgroundColor: '#FFD700' }}>
                            <span style={{ fontSize: '1.75rem', lineHeight: 1 }}>{leaderboard[0].avatar || leaderboard[0].nickname.slice(0, 2).toUpperCase()}</span>
                        </div>
                        <p className="podium-name">{leaderboard[0].nickname}</p>
                        <div className="podium-bar">1</div>
                        <p className="podium-score"><AnimatedNumber value={revealPhase >= 3 ? leaderboard[0].score : 0} /></p>
                    </div>
                )}
                {/* 3rd Place */}
                {leaderboard[2] && (
                    <div className={`podium-place podium-3 ${revealPhase >= 1 ? '' : 'podium-hidden'}`}>
                        <div className="w-12 h-12 rounded-full flex items-center justify-center mb-2" style={{ backgroundColor: '#CD7F32' }}>
                            <span style={{ fontSize: '1.5rem', lineHeight: 1 }}>{leaderboard[2].avatar || leaderboard[2].nickname.slice(0, 2).toUpperCase()}</span>
                        </div>
                        <p className="podium-name">{leaderboard[2].nickname}</p>
                        <div className="podium-bar">3</div>
                        <p className="podium-score"><AnimatedNumber value={revealPhase >= 1 ? leaderboard[2].score : 0} /></p>
                    </div>
                )}
            </div>

            {/* Remaining leaderboard (4th+) */}
            {revealPhase >= 4 && leaderboard.length > 3 && (
                <div className="w-full mt-4 mb-4" style={{ position: 'relative', zIndex: 11 }}>
                    <div className="space-y-2">
                        {leaderboard.slice(3).map((entry, i) => (
                            <div key={entry.nickname} className="leaderboard-item stagger-in"
                                 style={{ animationDelay: `${i * 0.1}s` }}>
                                <div className="flex items-center gap-3">
                                    <span className="rank-badge rank-default">{i + 4}</span>
                                    <span className="font-medium">{entry.nickname}</span>
                                </div>
                                <AnimatedNumber value={entry.score} className="font-bold" />
                            </div>
                        ))}
                    </div>
                </div>
            )}

            {revealPhase >= 4 && teamLeaderboard && teamLeaderboard.length > 1 && (
                <div className="w-full mt-6 mb-4" style={{ position: 'relative', zIndex: 11 }}>
                    <h3 className="text-lg font-semibold text-center mb-4">Team Standings</h3>
                    <div className="podium-container" style={{ marginBottom: 8 }}>
                        {/* 2nd */}
                        {teamLeaderboard[1] && (
                            <div className="podium-place podium-2">
                                <p className="podium-name">{teamLeaderboard[1].team}</p>
                                {teamLeaderboard[1].members > 1 && (
                                    <p className="text-xs text-[--text-tertiary]">{teamLeaderboard[1].members} members</p>
                                )}
                                <div className="podium-bar">2</div>
                                <p className="podium-score"><AnimatedNumber value={teamLeaderboard[1].score} /></p>
                            </div>
                        )}
                        {/* 1st */}
                        {teamLeaderboard[0] && (
                            <div className="podium-place podium-1 victory-glow">
                                <p className="podium-name">{teamLeaderboard[0].team}</p>
                                {teamLeaderboard[0].members > 1 && (
                                    <p className="text-xs text-[--text-tertiary]">{teamLeaderboard[0].members} members</p>
                                )}
                                <div className="podium-bar">1</div>
                                <p className="podium-score"><AnimatedNumber value={teamLeaderboard[0].score} /></p>
                            </div>
                        )}
                        {/* 3rd */}
                        {teamLeaderboard[2] && (
                            <div className="podium-place podium-3">
                                <p className="podium-name">{teamLeaderboard[2].team}</p>
                                {teamLeaderboard[2].members > 1 && (
                                    <p className="text-xs text-[--text-tertiary]">{teamLeaderboard[2].members} members</p>
                                )}
                                <div className="podium-bar">3</div>
                                <p className="podium-score"><AnimatedNumber value={teamLeaderboard[2].score} /></p>
                            </div>
                        )}
                    </div>
                    {/* 4th+ teams */}
                    {teamLeaderboard.length > 3 && (
                        <div className="space-y-2 mt-2">
                            {teamLeaderboard.slice(3).map((team, i) => (
                                <div key={team.team} className="leaderboard-item stagger-in"
                                     style={{ animationDelay: `${i * 0.1}s` }}>
                                    <div className="flex items-center gap-3">
                                        <span className="rank-badge rank-default">{i + 4}</span>
                                        <div>
                                            <span className="font-medium">{team.team}</span>
                                            {team.members > 1 && (
                                                <span className="text-xs text-[--text-tertiary] ml-2">{team.members} members</span>
                                            )}
                                        </div>
                                    </div>
                                    <AnimatedNumber value={team.score} className="font-bold" />
                                </div>
                            ))}
                        </div>
                    )}
                </div>
            )}

            {revealPhase >= 4 && (
                <button onClick={onPlayAgain} className="btn btn-primary w-full mt-8 stagger-in"
                        style={{ position: 'relative', zIndex: 11 }}>
                    New Quiz
                </button>
            )}
        </div>
    );
}
