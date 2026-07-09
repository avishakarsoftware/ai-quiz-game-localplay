import { useEffect, useMemo, useState } from 'react';
import { type SurveySaysState } from '../types';

interface SurveySaysGameProps {
    state: SurveySaysState | null;
    viewerName?: string;
    controls?: 'host' | 'player' | 'spectator';
    onSubmitGuess?: (guess: string) => void;
    onRevealAnswer?: (answerId: string) => void;
    onStrike?: () => void;
    onRevealAll?: () => void;
    onNextRound?: () => void;
    onEndGame?: () => void;
}

function teamName(state: SurveySaysState | null, teamId?: string | null): string {
    return state?.teams.find((team) => team.id === teamId)?.name || '';
}

function phaseCopy(state: SurveySaysState | null): string {
    if (!state) return 'Waiting for the room';
    if (state.phase === 'SURVEY_STEAL') return `${teamName(state, state.stealing_team_id)} can steal`;
    if (state.phase === 'SURVEY_REVEAL') return 'Round reveal';
    if (state.phase === 'PODIUM') return 'Final results';
    return `${teamName(state, state.active_team_id)} is guessing`;
}

export default function SurveySaysGame({
    state,
    viewerName = '',
    controls = 'spectator',
    onSubmitGuess,
    onRevealAnswer,
    onStrike,
    onRevealAll,
    onNextRound,
    onEndGame,
}: SurveySaysGameProps) {
    const [guess, setGuess] = useState('');
    const isHost = controls === 'host';
    const isPlayer = controls === 'player';
    const myTeam = useMemo(() => state?.teams.find((team) => team.player_ids.includes(viewerName)) || null, [state?.teams, viewerName]);
    const myLatestGuess = state?.guesses.find((item) => item.player_id === viewerName)?.guess || '';

    useEffect(() => {
        setGuess('');
    }, [state?.round_number, state?.phase]);

    if (!state) {
        return (
            <div className="common-ground-shell container-responsive safe-top safe-bottom animate-in">
                <div className="screen-hero">
                    <div className="hero-icon mb-4">📊</div>
                    <h1 className="hero-title">Survey Says</h1>
                    <p className="hero-subtitle">Waiting for the room</p>
                </div>
            </div>
        );
    }

    const canGuess = isPlayer && ['SURVEY_ANSWERING', 'SURVEY_STEAL'].includes(state.phase);
    const submitGuess = () => {
        const clean = guess.trim();
        if (!clean || !onSubmitGuess) return;
        onSubmitGuess(clean);
        setGuess('');
    };

    return (
        <div className="common-ground-shell container-responsive safe-top safe-bottom animate-in">
            <div className="common-ground-hero">
                <div className="hero-icon">📊</div>
                <div>
                    <p className="text-[--text-tertiary] text-sm font-bold uppercase tracking-wide">Team survey</p>
                    <h1 className="hero-title">{state.config?.game_title || 'Survey Says'}</h1>
                    <p className="hero-subtitle">Round {state.round_number} of {state.total_rounds}</p>
                </div>
            </div>

            <div className={`turn-handoff-banner ${state.phase === 'SURVEY_STEAL' ? 'warning' : state.phase === 'SURVEY_ANSWERING' ? 'active' : ''}`}>
                <strong>{phaseCopy(state)}</strong>
                <span>{state.question}</span>
            </div>

            <div className="common-ground-scoreboard">
                {state.standings.map((row) => (
                    <div key={row.team_id} className={row.team_id === myTeam?.id ? 'mine' : ''}>
                        <span>{row.rank}</span>
                        <strong>{row.team_name}</strong>
                        <small>{row.score}</small>
                    </div>
                ))}
            </div>

            <div className="common-ground-panel">
                <div className="flex items-center justify-between gap-4 mb-4">
                    <div>
                        <h2>Answer board</h2>
                        <p className="text-[--text-secondary]">Bank: {state.round_bank} · Strikes: {'✕'.repeat(state.strikes) || '0'}</p>
                    </div>
                    {isHost && state.phase !== 'PODIUM' && (
                        <button className="btn btn-secondary" type="button" onClick={onStrike} disabled={!['SURVEY_ANSWERING', 'SURVEY_STEAL'].includes(state.phase)}>
                            Strike
                        </button>
                    )}
                </div>

                <div className="grid gap-3">
                    {state.answers.map((answer) => (
                        <div
                            key={answer.id}
                            className="common-ground-submission"
                            style={{ display: 'grid', gridTemplateColumns: '44px 1fr auto', alignItems: 'center', textAlign: 'left' }}
                        >
                            <small>#{answer.rank}</small>
                            <strong>{answer.text || (answer.revealed ? 'Revealed' : 'Survey answer')}</strong>
                            <span>{answer.points}</span>
                            {isHost && !answer.revealed && (
                                <button className="btn btn-primary" type="button" onClick={() => onRevealAnswer?.(answer.id)} style={{ gridColumn: '1 / -1', marginTop: 8 }}>
                                    Reveal {answer.text}
                                </button>
                            )}
                        </div>
                    ))}
                </div>
            </div>

            {canGuess && (
                <div className="common-ground-panel">
                    <h2>{myTeam ? `${myTeam.name}'s guess` : 'Your guess'}</h2>
                    <div className="join-form" style={{ padding: 0 }}>
                        <input
                            value={guess}
                            onChange={(event) => setGuess(event.target.value.slice(0, 100))}
                            onKeyDown={(event) => event.key === 'Enter' && submitGuess()}
                            placeholder="Type a survey answer"
                            maxLength={100}
                        />
                        <button className="btn btn-primary btn-glow" type="button" onClick={submitGuess} disabled={guess.trim().length < 2}>
                            Submit Guess
                        </button>
                    </div>
                    {myLatestGuess && <p className="text-[--text-secondary] mt-3">Last guess: {myLatestGuess}</p>}
                </div>
            )}

            {isHost && (
                <div className="common-ground-panel">
                    <h2>Submitted guesses</h2>
                    {state.guesses.length ? (
                        <div className="common-ground-submissions">
                            {state.guesses
                                .slice()
                                .sort((a, b) => (b.at || 0) - (a.at || 0))
                                .map((item) => (
                                    <div key={`${item.player_id}-${item.at || item.guess}`} className="common-ground-submission">
                                        <small>{teamName(state, item.team_id)}</small>
                                        <strong>{item.guess}</strong>
                                        <span>{item.player_id}</span>
                                    </div>
                                ))}
                        </div>
                    ) : (
                        <p className="text-[--text-secondary]">No guesses submitted yet.</p>
                    )}
                </div>
            )}

            {isHost && (
                <div className="common-ground-actions">
                    {state.phase !== 'PODIUM' && <button className="btn btn-secondary" type="button" onClick={onRevealAll}>Reveal All</button>}
                    {state.phase === 'SURVEY_REVEAL' && (
                        <button className="btn btn-primary btn-glow" type="button" onClick={onNextRound}>
                            {state.round_number >= state.total_rounds ? 'Show Podium' : 'Next Round'}
                        </button>
                    )}
                    <button className="btn btn-secondary" type="button" onClick={onEndGame} data-testid="organizer-end-game">End Game</button>
                </div>
            )}
        </div>
    );
}
