import { useMemo } from 'react';
import { type ChitPullState } from '../types';

interface ChitPullGameProps {
    state: ChitPullState | null;
    viewerName?: string;
    controls?: 'host' | 'player' | 'spectator';
    onNext?: () => void;
    onComplete?: (bonus?: boolean) => void;
    onSkip?: () => void;
    onRedrawPlayer?: () => void;
    onRedrawChit?: () => void;
    onEndGame?: () => void;
}

function categoryLabel(value?: string) {
    return String(value || 'question').replace(/_/g, ' ');
}

export default function ChitPullGame({
    state,
    viewerName = '',
    controls = 'spectator',
    onNext,
    onComplete,
    onSkip,
    onRedrawPlayer,
    onRedrawChit,
    onEndGame,
}: ChitPullGameProps) {
    const isHost = controls === 'host';
    const isPlayer = controls === 'player';
    const selected = state?.selected_player_id || '';
    const amSelected = isPlayer && selected === viewerName;
    const title = state?.config?.game_title || 'Random Chit';
    const scoreboard = useMemo(() => {
        if (!state) return [];
        return [...state.players]
            .map((player) => ({
                ...player,
                score: state.scores[player.nickname] || 0,
                turns: state.player_turn_counts[player.nickname] || 0,
            }))
            .sort((a, b) => b.score - a.score || b.turns - a.turns || a.nickname.localeCompare(b.nickname));
    }, [state]);

    if (!state) {
        return (
            <div className="chit-pull-shell container-responsive safe-top safe-bottom animate-in">
                <div className="screen-hero">
                    <div className="hero-icon mb-4">🎟️</div>
                    <h1 className="hero-title">Random Chit</h1>
                    <p className="hero-subtitle">Waiting for the room</p>
                </div>
            </div>
        );
    }

    const active = state.phase === 'CHIT_ACTIVE';
    const result = state.turn_results[state.turn_results.length - 1];

    return (
        <div className="chit-pull-shell container-responsive safe-top safe-bottom animate-in">
            <div className="common-ground-hero">
                <div className="hero-icon">🎟️</div>
                <div>
                    <p className="text-[--text-tertiary] text-sm font-bold uppercase tracking-wide">Round {Math.min(state.round_number, state.total_rounds)} of {state.total_rounds}</p>
                    <h1 className="hero-title">{title}</h1>
                    <p className="hero-subtitle">Skip is allowed. Keep it fun.</p>
                </div>
            </div>

            <div className={`turn-handoff-banner ${active ? 'active' : 'warning'}`}>
                <strong>{active ? `${selected} is up` : result ? `${result.player_id} ${result.outcome}` : 'Ready for a pull'}</strong>
                <span>{active ? categoryLabel(state.current_chit?.category) : 'Host controls the next chit.'}</span>
            </div>

            <section className={`common-ground-panel chit-pull-card ${amSelected ? 'mine' : ''}`}>
                {active && state.current_chit ? (
                    <>
                        <p className="text-[--text-tertiary] text-sm font-bold uppercase tracking-wide">{categoryLabel(state.current_chit.category)}</p>
                        <h2>{state.current_chit.text}</h2>
                        {amSelected && <p className="text-[--accent-primary] font-bold">You're up!</p>}
                    </>
                ) : result ? (
                    <>
                        <p className="text-[--text-tertiary] text-sm font-bold uppercase tracking-wide">Last result</p>
                        <h2>{result.chit_text}</h2>
                        <p className="text-[--text-secondary]">{result.player_id} · {result.outcome}{result.points_awarded ? ` · +${result.points_awarded}` : ''}</p>
                    </>
                ) : (
                    <>
                        <h2>Ready for the first chit</h2>
                        <p className="text-[--text-secondary]">The host will pull a random player and prompt.</p>
                    </>
                )}
            </section>

            <div className="common-ground-scoreboard chit-pull-scoreboard">
                {scoreboard.map((player, index) => (
                    <div key={player.nickname} className={player.nickname === viewerName ? 'mine' : ''}>
                        <span>{index + 1}</span>
                        <strong>{player.avatar} {player.nickname}</strong>
                        <small className="chit-pull-score-meta">
                            {player.score} pts · {player.turns} turn{player.turns === 1 ? '' : 's'}
                        </small>
                    </div>
                ))}
            </div>

            {isHost && (
                <div className="common-ground-actions">
                    {!active && <button type="button" className="btn btn-primary btn-glow" onClick={onNext}>Pull Chit</button>}
                    {active && <button type="button" className="btn btn-primary btn-glow" onClick={() => onComplete?.(false)}>Completed</button>}
                    {active && <button type="button" className="btn btn-secondary" onClick={() => onComplete?.(true)}>Bonus Done</button>}
                    {active && <button type="button" className="btn btn-secondary" onClick={onSkip}>Skip</button>}
                    {active && <button type="button" className="btn btn-secondary" onClick={onRedrawPlayer}>New Player</button>}
                    {active && <button type="button" className="btn btn-secondary" onClick={onRedrawChit}>New Chit</button>}
                    <button type="button" className="btn btn-secondary" onClick={onEndGame}>End Game</button>
                </div>
            )}
        </div>
    );
}
