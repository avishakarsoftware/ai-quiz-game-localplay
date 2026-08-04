import { useMemo, useState } from 'react';
import { type FindSomeoneCell, type FindSomeoneState } from '../types';

interface FindSomeoneGameProps {
    state: FindSomeoneState | null;
    viewerName?: string;
    controls?: 'host' | 'player' | 'spectator';
    onMarkCell?: (promptId: string, matchedPlayerId: string) => void;
    onConfirmMatch?: (requestId: string, accepted: boolean) => void;
    onClaimPattern?: (patternId: string) => void;
    onEndGame?: () => void;
}

function avatarFor(state: FindSomeoneState, nickname: string): string {
    return state.players.find((player) => player.nickname === nickname)?.avatar || '🙂';
}

function claimText(state: FindSomeoneState, patternId: string): string {
    const claim = state.accepted_claims.find((item) => item.pattern_id === patternId);
    return claim ? `${claim.pattern_label} claimed by ${claim.player_id}` : '';
}

function cellStatus(cell: FindSomeoneCell): string {
    if (cell.free) return 'Free';
    if (cell.confirmation_status === 'pending') return 'Waiting';
    if (cell.marked) return cell.matched_player_name || cell.matched_player_id || 'Matched';
    if (cell.confirmation_status === 'denied') return 'Try someone else';
    return 'Find someone';
}

export default function FindSomeoneGame({
    state,
    viewerName = '',
    controls = 'spectator',
    onMarkCell,
    onConfirmMatch,
    onClaimPattern,
    onEndGame,
}: FindSomeoneGameProps) {
    const [selectedCell, setSelectedCell] = useState<FindSomeoneCell | null>(null);
    const [matchedPlayer, setMatchedPlayer] = useState('');
    const [requestSent, setRequestSent] = useState(false);
    const isPlayer = controls === 'player';
    const isHost = controls === 'host';
    const title = state?.config?.game_title || 'Find Someone Who';
    const availablePlayers = useMemo(
        () => (state?.players || []).filter((player) => player.nickname !== viewerName),
        [state?.players, viewerName],
    );
    const cardSize = state?.my_card?.cells?.length || 5;

    if (!state) {
        return (
            <div className="common-ground-shell container-responsive safe-top safe-bottom animate-in">
                <div className="screen-hero">
                    <div className="hero-icon mb-4">🔎</div>
                    <h1 className="hero-title">Find Someone Who</h1>
                    <p className="hero-subtitle">Waiting for the room</p>
                </div>
            </div>
        );
    }

    const submitMark = () => {
        if (!selectedCell || !matchedPlayer || !onMarkCell) return;
        onMarkCell(selectedCell.prompt_id, matchedPlayer);
        setSelectedCell(null);
        setMatchedPlayer('');
        const honorMode = state?.config?.confirmation_mode === 'honor';
        if (!honorMode) {
            setRequestSent(true);
            setTimeout(() => setRequestSent(false), 2800);
        }
    };

    return (
        <div className="common-ground-shell container-responsive safe-top safe-bottom animate-in">
            <div className="common-ground-hero">
                <div className="hero-icon">🔎</div>
                <div>
                    <p className="text-[--text-tertiary] text-sm font-bold uppercase tracking-wide">Party icebreaker</p>
                    <h1 className="hero-title">{title}</h1>
                    <p className="hero-subtitle">{state.player_count} player{state.player_count === 1 ? '' : 's'} playing</p>
                </div>
            </div>

            <div className="turn-handoff-banner active">
                <strong>{state.phase === 'PODIUM' ? 'Final board' : 'Meet people and mark your grid'}</strong>
                <span>{state.config?.confirmation_mode === 'honor' ? 'Mark squares when someone matches.' : 'Ask someone, then they confirm it on their phone.'}</span>
            </div>

            {!!state.my_pending_confirmations?.length && (
                <section className="common-ground-panel">
                    <h2>Confirm for others</h2>
                    <div className="common-ground-submissions">
                        {state.my_pending_confirmations.map((request) => (
                            <div key={request.id} className="common-ground-submission">
                                <small>{request.requester_id} asked</small>
                                <strong>{request.display}</strong>
                                <div className="common-ground-actions">
                                    <button className="btn btn-primary" type="button" onClick={() => onConfirmMatch?.(request.id, true)}>Yes</button>
                                    <button className="btn btn-secondary" type="button" onClick={() => onConfirmMatch?.(request.id, false)}>No</button>
                                </div>
                            </div>
                        ))}
                    </div>
                </section>
            )}

            {requestSent && (
                <p className="text-[--accent-primary] font-bold text-center">Request sent — waiting for them to confirm ✓</p>
            )}

            {isPlayer && state.my_card && (
                <section className="common-ground-panel">
                    <h2>Your card</h2>
                    <div
                        className="grid gap-2"
                        style={{ gridTemplateColumns: `repeat(${cardSize}, minmax(0, 1fr))` }}
                    >
                        {state.my_card.cells.flat().map((cell) => (
                            <button
                                key={`${cell.row}-${cell.column}`}
                                type="button"
                                className={`min-h-[92px] rounded-lg border px-2 py-2 text-left transition ${
                                    cell.marked || cell.free
                                        ? 'border-[--accent] bg-[rgba(247,43,126,0.22)]'
                                        : cell.confirmation_status === 'pending'
                                            ? 'border-[--accent-warning] bg-[rgba(255,196,87,0.12)]'
                                            : cell.confirmation_status === 'denied'
                                                ? 'border-[rgba(255,90,90,0.5)] bg-[rgba(255,90,90,0.12)]'
                                                : 'border-[--border-primary] bg-[rgba(255,255,255,0.04)]'
                                }`}
                                onClick={() => !cell.free && !cell.marked && setSelectedCell(cell)}
                                disabled={cell.free || cell.marked || state.phase === 'PODIUM'}
                            >
                                <strong className="block text-sm leading-tight">{cell.display}</strong>
                                <small className="mt-2 block text-[--text-tertiary]">{cellStatus(cell)}</small>
                            </button>
                        ))}
                    </div>
                </section>
            )}

            {selectedCell && (
                <section className="common-ground-panel">
                    <h2>{selectedCell.display}</h2>
                    <select
                        className="input-field"
                        value={matchedPlayer}
                        onChange={(event) => setMatchedPlayer(event.target.value)}
                    >
                        <option value="">Who matches this?</option>
                        {availablePlayers.map((player) => (
                            <option key={player.nickname} value={player.nickname}>
                                {player.avatar} {player.nickname}
                            </option>
                        ))}
                    </select>
                    <div className="common-ground-actions">
                        <button className="btn btn-primary btn-glow" type="button" onClick={submitMark} disabled={!matchedPlayer}>
                            Ask to Confirm
                        </button>
                        <button className="btn btn-secondary" type="button" onClick={() => setSelectedCell(null)}>Cancel</button>
                    </div>
                </section>
            )}

            <section className="common-ground-panel">
                <h2>Claims</h2>
                <div className="common-ground-actions">
                    {(state.config?.claim_patterns || []).map((pattern) => {
                        const claimed = Boolean(claimText(state, pattern.id));
                        const mine = state.my_claimed_patterns?.includes(pattern.id);
                        return (
                            <button
                                key={pattern.id}
                                className={claimed ? 'btn btn-secondary' : 'btn btn-primary'}
                                type="button"
                                onClick={() => onClaimPattern?.(pattern.id)}
                                disabled={!isPlayer || claimed || mine || state.phase === 'PODIUM'}
                            >
                                {claimText(state, pattern.id) || `Claim ${pattern.label}`}
                            </button>
                        );
                    })}
                </div>
            </section>

            <div className="common-ground-scoreboard">
                {(state.leaderboard || []).map((row) => (
                    <div key={row.player_id}>
                        <span>{row.rank}</span>
                        <strong>{avatarFor(state, row.player_id)} {row.player_id}</strong>
                        <small>{row.claims} claim{row.claims === 1 ? '' : 's'} · {row.confirmed_cells} matches</small>
                    </div>
                ))}
            </div>

            {isHost && (
                <div className="common-ground-actions">
                    <button className="btn btn-primary btn-glow" type="button" onClick={onEndGame} data-testid="organizer-end-game">
                        End Game
                    </button>
                </div>
            )}
        </div>
    );
}
