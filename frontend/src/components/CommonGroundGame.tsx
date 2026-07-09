import { useEffect, useMemo, useState } from 'react';
import { type CommonGroundState } from '../types';

interface CommonGroundGameProps {
    state: CommonGroundState | null;
    viewerName?: string;
    controls?: 'host' | 'player' | 'spectator';
    onSubmitFact?: (text: string) => void;
    onVote?: (submissionId: string) => void;
    onStartReveal?: () => void;
    onStartVoting?: () => void;
    onScoreRound?: () => void;
    onNextRound?: () => void;
    onEndGame?: () => void;
}

function titleCase(value?: string): string {
    return String(value || 'most_surprising')
        .replace(/_/g, ' ')
        .replace(/\b\w/g, (match) => match.toUpperCase());
}

function teamForPlayer(state: CommonGroundState | null, nickname?: string) {
    if (!state || !nickname) return null;
    return state.teams.find((team) => team.player_ids.includes(nickname)) || null;
}

function avatarFor(state: CommonGroundState, nickname: string): string {
    return state.players.find((player) => player.nickname === nickname)?.avatar || '🙂';
}

export default function CommonGroundGame({
    state,
    viewerName = '',
    controls = 'spectator',
    onSubmitFact,
    onVote,
    onStartReveal,
    onStartVoting,
    onScoreRound,
    onNextRound,
    onEndGame,
}: CommonGroundGameProps) {
    const [fact, setFact] = useState('');

    useEffect(() => {
        setFact(state?.my_submission?.text || '');
    }, [state?.my_submission?.text, state?.round_number]);

    const isPlayer = controls === 'player';
    const isHost = controls === 'host';
    const myTeam = teamForPlayer(state, viewerName);
    const title = state?.config?.game_title || 'Common Ground';
    const voteLabel = titleCase(state?.config?.vote_category);
    const visibleSubmissions = state?.submissions || [];
    const submittedTeams = useMemo(() => new Set(visibleSubmissions.filter((item) => item.has_submission).map((item) => item.team_id)), [visibleSubmissions]);
    const validFact = fact.trim().length >= 6 && fact.trim().split(/\s+/).length >= 2;

    if (!state) {
        return (
            <div className="common-ground-shell container-responsive safe-top safe-bottom animate-in">
                <div className="screen-hero">
                    <div className="hero-icon mb-4">🤝</div>
                    <h1 className="hero-title">Common Ground</h1>
                    <p className="hero-subtitle">Waiting for the room</p>
                </div>
            </div>
        );
    }

    const submit = () => {
        if (!onSubmitFact || !validFact) return;
        onSubmitFact(fact.trim());
    };

    return (
        <div className="common-ground-shell container-responsive safe-top safe-bottom animate-in">
            <div className="common-ground-hero">
                <div className="hero-icon">🤝</div>
                <div>
                    <p className="text-[--text-tertiary] text-sm font-bold uppercase tracking-wide">Team icebreaker</p>
                    <h1 className="hero-title">{title}</h1>
                    <p className="hero-subtitle">Round {state.round_number} of {state.total_rounds}</p>
                </div>
            </div>

            <div className={`turn-handoff-banner ${state.phase === 'COMMON_DISCUSSION' ? 'active' : state.phase === 'COMMON_VOTING' ? 'warning' : ''}`}>
                <strong>
                    {state.phase === 'COMMON_DISCUSSION'
                        ? 'Discuss with your team'
                        : state.phase === 'COMMON_REVEAL'
                            ? 'Reveal'
                            : state.phase === 'COMMON_VOTING'
                                ? `Vote: ${voteLabel}`
                                : state.phase === 'COMMON_ROUND_RESULT'
                                    ? 'Round results'
                                    : 'Final results'}
                </strong>
                <span>{state.prompt?.text || 'Find something everyone on your team has in common.'}</span>
            </div>

            <div className="common-ground-teams">
                {state.teams.map((team) => (
                    <section key={team.id} className={`common-ground-team ${team.id === myTeam?.id ? 'mine' : ''} ${submittedTeams.has(team.id) ? 'ready' : ''}`}>
                        <div>
                            <strong>{team.name}</strong>
                            <small>{submittedTeams.has(team.id) ? 'Submitted' : 'Talking'}</small>
                        </div>
                        <div className="common-ground-members">
                            {team.player_ids.map((name) => (
                                <span key={name}>{avatarFor(state, name)} {name}</span>
                            ))}
                        </div>
                    </section>
                ))}
            </div>

            {state.phase === 'COMMON_DISCUSSION' && (
                <div className="common-ground-panel">
                    {isPlayer ? (
                        <>
                            <h2>{myTeam ? `${myTeam.name}'s shared fact` : 'Your shared fact'}</h2>
                            <textarea
                                value={fact}
                                onChange={(event) => setFact(event.target.value.slice(0, 220))}
                                placeholder="We all..."
                                maxLength={220}
                            />
                            <div className="common-ground-panel-footer">
                                <small>{fact.length}/220</small>
                                <button className="btn btn-primary btn-glow" onClick={submit} disabled={!validFact}>
                                    {state.my_submission ? 'Update Answer' : 'Submit Answer'}
                                </button>
                            </div>
                        </>
                    ) : (
                        <>
                            <h2>Team progress</h2>
                            <p className="text-[--text-secondary]">{submittedTeams.size} of {state.teams.length} teams have submitted.</p>
                        </>
                    )}
                </div>
            )}

            {(state.phase === 'COMMON_REVEAL' || state.phase === 'COMMON_VOTING' || state.phase === 'COMMON_ROUND_RESULT' || state.phase === 'PODIUM') && (
                <div className="common-ground-submissions">
                    {visibleSubmissions.map((submission) => {
                        const canVote = isPlayer && state.phase === 'COMMON_VOTING' && submission.has_submission && submission.team_id !== myTeam?.id && !state.my_vote && onVote;
                        const selected = state.my_vote === submission.id;
                        return (
                            <button
                                key={submission.team_id}
                                type="button"
                                className={`common-ground-submission ${selected ? 'selected' : ''}`}
                                onClick={() => canVote && onVote(submission.id)}
                                disabled={!canVote}
                            >
                                <small>{submission.team_name}</small>
                                <strong>{submission.has_submission ? submission.text : 'No answer submitted'}</strong>
                                {(state.phase === 'COMMON_ROUND_RESULT' || state.phase === 'PODIUM') && (
                                    <span>{submission.vote_count} vote{submission.vote_count === 1 ? '' : 's'}</span>
                                )}
                            </button>
                        );
                    })}
                </div>
            )}

            <div className="common-ground-scoreboard">
                {state.teams
                    .map((team) => ({ ...team, score: state.scores[team.id] || 0 }))
                    .sort((a, b) => b.score - a.score)
                    .map((team, index) => (
                        <div key={team.id}>
                            <span>{index + 1}</span>
                            <strong>{team.name}</strong>
                            <small>{team.score}</small>
                        </div>
                    ))}
            </div>

            {isHost && (
                <div className="common-ground-actions">
                    {state.phase === 'COMMON_DISCUSSION' && <button className="btn btn-primary btn-glow" onClick={onStartReveal} disabled={submittedTeams.size === 0}>Reveal Answers</button>}
                    {state.phase === 'COMMON_REVEAL' && (
                        state.config?.voting_enabled === false
                            ? <button className="btn btn-primary btn-glow" onClick={onScoreRound}>Score Round</button>
                            : <button className="btn btn-primary btn-glow" onClick={onStartVoting}>Start Voting</button>
                    )}
                    {state.phase === 'COMMON_VOTING' && <button className="btn btn-primary btn-glow" onClick={onScoreRound}>Score Round</button>}
                    {state.phase === 'COMMON_ROUND_RESULT' && <button className="btn btn-primary btn-glow" onClick={onNextRound}>{state.round_number >= state.total_rounds ? 'Show Podium' : 'Next Round'}</button>}
                    <button className="btn btn-secondary" onClick={onEndGame} data-testid="organizer-end-game">End Game</button>
                </div>
            )}
        </div>
    );
}
