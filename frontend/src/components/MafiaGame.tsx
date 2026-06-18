import { useMemo } from 'react';
import { type MafiaRole, type MafiaState } from '../types';

interface MafiaGameProps {
    state: MafiaState | null;
    viewerName?: string;
    controls?: 'host' | 'player' | 'spectator';
    onNightAction?: (target: string) => void;
    onNightRead?: (target: string) => void;
    onVote?: (target: string) => void;
    onSkipTimer?: () => void;
    onExtendTimer?: () => void;
    onEndGame?: () => void;
}

const ROLE_LABELS: Record<MafiaRole, string> = {
    villager: 'Villager',
    detective: 'Detective',
    doctor: 'Doctor',
    mafia: 'Mafia',
};

function roleLabel(role?: string | null) {
    return role && role in ROLE_LABELS ? ROLE_LABELS[role as MafiaRole] : 'Hidden';
}

function phaseLabel(phase?: string) {
    switch (phase) {
        case 'MAFIA_ROLE_REVEAL': return 'Role Reveal';
        case 'MAFIA_NIGHT': return 'Night';
        case 'MAFIA_DAY_DISCUSSION': return 'Day Discussion';
        case 'MAFIA_DAY_VOTE': return 'Day Vote';
        case 'MAFIA_VOTE_RESULT': return 'Vote Result';
        case 'PODIUM': return 'Game Over';
        default: return 'Mafia';
    }
}

function roleDescription(role?: string) {
    if (role === 'mafia') return 'Work with the Mafia at night and avoid being voted out.';
    if (role === 'detective') return 'Investigate one player each night to learn their team.';
    if (role === 'doctor') return 'Protect one player each night from the Mafia attack.';
    return 'Find the Mafia during the day and vote them out.';
}

export default function MafiaGame({
    state,
    viewerName = '',
    controls = 'spectator',
    onNightAction,
    onNightRead,
    onVote,
    onSkipTimer,
    onExtendTimer,
    onEndGame,
}: MafiaGameProps) {
    const isHost = controls === 'host';
    const isPlayer = controls === 'player';
    const title = state?.config?.game_title || 'Mafia';
    const selectedNightTarget = state?.my_action?.submitted_target || '';
    const selectedNightReadTarget = state?.my_action?.night_read?.submitted_target || '';
    const selectedVote = state?.my_vote || '';
    const sortedPlayers = useMemo(() => {
        if (!state) return [];
        return [...state.players].sort((a, b) => Number(b.alive) - Number(a.alive) || a.nickname.localeCompare(b.nickname));
    }, [state]);

    if (!state) {
        return (
            <div className="container-responsive safe-top safe-bottom animate-in">
                <div className="screen-hero">
                    <div className="hero-icon mb-4">🕵️</div>
                    <h1 className="hero-title">Mafia</h1>
                    <p className="hero-subtitle">Waiting for the room</p>
                </div>
            </div>
        );
    }

    const gameOver = state.phase === 'PODIUM';
    const publicMessage = state.phase === 'MAFIA_NIGHT'
        ? 'Night has fallen. Check your phone and keep your role secret.'
        : state.phase === 'MAFIA_ROLE_REVEAL'
            ? 'Roles have been assigned. Check your phone.'
            : state.phase === 'MAFIA_DAY_VOTE'
                ? 'Time to vote. Choose a suspect or skip.'
                : state.last_night?.narration || 'Discuss with the group and watch for suspicious stories.';

    return (
        <div className="container-responsive safe-top safe-bottom animate-in">
            <div className="common-ground-hero">
                <div className="hero-icon">🕵️</div>
                <div>
                    <p className="text-[--text-tertiary] text-sm font-bold uppercase tracking-wide">
                        Round {state.round} · {phaseLabel(state.phase)}
                    </p>
                    <h1 className="hero-title">{title}</h1>
                    <p className="hero-subtitle">{state.alive_count} alive · {state.eliminated_count} eliminated</p>
                </div>
            </div>

            <section className="common-ground-panel">
                <p className="text-[--text-tertiary] text-sm font-bold uppercase tracking-wide">Town square</p>
                <h2>{gameOver ? `${state.winner === 'mafia' ? 'Mafia' : 'Town'} wins` : publicMessage}</h2>
                {state.phase === 'MAFIA_DAY_VOTE' && (
                    <p className="text-[--text-secondary]">
                        {state.vote_progress?.submitted || 0} of {state.vote_progress?.eligible || 0} votes submitted
                    </p>
                )}
                {state.last_vote && (state.phase === 'MAFIA_VOTE_RESULT' || gameOver) && (
                    <div className="mt-4 space-y-2">
                        <p className="text-[--text-secondary]">
                            {state.last_vote.tied
                                ? 'The vote was tied. No one was eliminated.'
                                : state.last_vote.eliminated
                                    ? `${state.last_vote.eliminated} was eliminated as ${roleLabel(state.last_vote.eliminated_role)}.`
                                    : 'No one was eliminated.'}
                        </p>
                        <div className="common-ground-scoreboard">
                            {Object.entries(state.last_vote.tally || {}).map(([target, count]) => (
                                <div key={target}>
                                    <strong>{target}</strong>
                                    <small>{count} vote{count === 1 ? '' : 's'}</small>
                                </div>
                            ))}
                        </div>
                    </div>
                )}
                {state.last_night?.night_read_highlights && state.last_night.night_read_highlights.length > 0 && state.phase === 'MAFIA_DAY_DISCUSSION' && (
                    <div className="mt-4 common-ground-scoreboard">
                        {state.last_night.night_read_highlights.map((item) => (
                            <div key={item.prompt_id}>
                                <strong>{item.label}</strong>
                                <small>{item.player_id}{item.tied ? ' (tied)' : ''} · {item.count}/{item.total}</small>
                            </div>
                        ))}
                    </div>
                )}
            </section>

            {isPlayer && (
                <section className={`common-ground-panel ${state.ghost ? 'opacity-80' : ''}`}>
                    <p className="text-[--text-tertiary] text-sm font-bold uppercase tracking-wide">
                        {state.ghost ? "You're a ghost" : 'Your role'}
                    </p>
                    <h2>{roleLabel(state.my_role)}</h2>
                    <p className="text-[--text-secondary]">{roleDescription(state.my_role)}</p>
                    {state.my_action?.kind === 'mafia_kill' && Boolean(state.my_action.mafia_teammates?.length) && (
                        <p className="text-[--text-secondary] mt-2">Your Mafia teammate{state.my_action.mafia_teammates!.length === 1 ? '' : 's'}: {state.my_action.mafia_teammates!.join(', ')}</p>
                    )}
                    {state.my_investigations && state.my_investigations.length > 0 && (
                        <div className="mt-4 common-ground-scoreboard">
                            {state.my_investigations.map((item) => (
                                <div key={`${item.round}-${item.target}`}>
                                    <strong>{item.target}</strong>
                                    <small>Night {item.round}: {item.result}</small>
                                </div>
                            ))}
                        </div>
                    )}
                </section>
            )}

            {isPlayer && state.phase === 'MAFIA_NIGHT' && state.my_action && state.my_action.kind !== 'none' && !state.ghost && (
                <section className="common-ground-panel">
                    <h2>{state.my_action.kind === 'mafia_kill' ? 'Choose a target' : state.my_action.kind === 'investigate' ? 'Investigate a player' : 'Protect a player'}</h2>
                    <div className="common-ground-actions">
                        {state.my_action.eligible_targets.map((target) => (
                            <button
                                type="button"
                                key={target}
                                className={`btn ${selectedNightTarget === target ? 'btn-primary' : 'btn-secondary'}`}
                                onClick={() => onNightAction?.(target)}
                            >
                                {target}
                            </button>
                        ))}
                    </div>
                </section>
            )}

            {isPlayer && state.phase === 'MAFIA_NIGHT' && state.my_action?.night_read && !state.ghost && (
                <section className="common-ground-panel">
                    <p className="text-[--text-tertiary] text-sm font-bold uppercase tracking-wide">
                        Night read
                    </p>
                    <h2>{state.my_action.night_read.question}</h2>
                    <p className="text-[--text-secondary]">
                        These answers are shown only as anonymous group patterns before discussion.
                    </p>
                    <div className="common-ground-actions mt-4">
                        {state.my_action.night_read.eligible_targets.map((target) => (
                            <button
                                type="button"
                                key={target}
                                className={`btn ${selectedNightReadTarget === target ? 'btn-primary' : 'btn-secondary'}`}
                                onClick={() => onNightRead?.(target)}
                            >
                                {target}
                            </button>
                        ))}
                    </div>
                </section>
            )}

            {isPlayer && state.phase === 'MAFIA_DAY_VOTE' && !state.ghost && (
                <section className="common-ground-panel">
                    <h2>Who do you suspect?</h2>
                    <div className="common-ground-actions">
                        {state.players.filter((player) => player.alive && player.nickname !== viewerName).map((player) => (
                            <button
                                type="button"
                                key={player.nickname}
                                className={`btn ${selectedVote === player.nickname ? 'btn-primary' : 'btn-secondary'}`}
                                onClick={() => onVote?.(player.nickname)}
                            >
                                {player.avatar} {player.nickname}
                            </button>
                        ))}
                        <button
                            type="button"
                            className={`btn ${selectedVote === 'skip' ? 'btn-primary' : 'btn-secondary'}`}
                            onClick={() => onVote?.('skip')}
                        >
                            Skip
                        </button>
                    </div>
                </section>
            )}

            <div className="common-ground-scoreboard">
                {sortedPlayers.map((player) => {
                    const revealOwn = isPlayer && player.nickname === viewerName && state.my_role;
                    return (
                        <div key={player.nickname} className={player.nickname === viewerName ? 'mine' : ''}>
                            <strong>{player.avatar} {player.nickname}</strong>
                            <small>
                                {player.alive ? 'Alive' : 'Eliminated'}
                                {' · '}
                                {gameOver || player.role || revealOwn ? roleLabel(player.role || (revealOwn ? state.my_role : null)) : 'Role hidden'}
                            </small>
                        </div>
                    );
                })}
            </div>

            {isHost && (
                <div className="common-ground-actions">
                    <button type="button" className="btn btn-primary btn-glow" onClick={onSkipTimer}>Skip Timer</button>
                    <button type="button" className="btn btn-secondary" onClick={onExtendTimer} disabled={state.phase !== 'MAFIA_DAY_DISCUSSION'}>Extend Discussion</button>
                    <button type="button" className="btn btn-secondary" onClick={onEndGame}>End Game</button>
                </div>
            )}
        </div>
    );
}
