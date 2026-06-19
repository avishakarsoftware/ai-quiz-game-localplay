import { useMemo, useState } from 'react';
import { type PartyQuestItem, type PartyQuestsState } from '../types';

interface PartyQuestsGameProps {
    state: PartyQuestsState | null;
    viewerName?: string;
    controls?: 'host' | 'player' | 'spectator';
    onRequestConfirmation?: (questId: string, partnerPlayerId: string) => void;
    onConfirm?: (requestId: string, accepted: boolean) => void;
    onFinalCall?: () => void;
    onReveal?: () => void;
    onEndGame?: () => void;
}

function phaseLabel(phase?: string) {
    if (phase === 'QUESTS_FINAL_CALL') return 'Final call';
    if (phase === 'QUESTS_REVEAL') return 'Reveal';
    if (phase === 'PODIUM') return 'Results';
    return 'Active';
}

function partnerLabel(state: PartyQuestsState, id?: string) {
    if (!id) return '';
    return state.players.find((player) => player.nickname === id)?.nickname || id;
}

function QuestCard({
    item,
    state,
    viewerName,
    onRequestConfirmation,
}: {
    item: PartyQuestItem;
    state: PartyQuestsState;
    viewerName: string;
    onRequestConfirmation?: (questId: string, partnerPlayerId: string) => void;
}) {
    const [partner, setPartner] = useState('');
    const candidates = state.players.filter((player) => player.nickname !== viewerName);
    const isConfirmed = item.status === 'confirmed';
    const isPending = item.status === 'pending_confirmation';
    return (
        <article className={`rounded-xl border border-white/10 bg-white/[0.04] p-4 ${isConfirmed ? 'border-emerald-300/40 bg-emerald-400/10' : ''}`}>
            <div className="flex items-start justify-between gap-4">
                <div>
                    <p className="text-[--text-tertiary] text-sm font-bold uppercase tracking-wide">{item.points} pts</p>
                    <h3 className="text-2xl font-bold">{item.display}</h3>
                </div>
                <span className="rounded-lg bg-white/10 px-3 py-2 text-sm font-bold">
                    {isConfirmed ? 'Done' : isPending ? 'Pending' : 'Open'}
                </span>
            </div>
            {isConfirmed && (
                <p className="mt-3 text-[--text-secondary]">Confirmed by {partnerLabel(state, item.confirmed_by_player_id)}</p>
            )}
            {isPending && (
                <p className="mt-3 text-[--text-secondary]">Waiting for {partnerLabel(state, item.confirmed_by_player_id)} to confirm.</p>
            )}
            {!isConfirmed && !isPending && candidates.length > 0 && (
                <div className="mt-4 grid gap-3 md:grid-cols-[1fr_auto]">
                    <select className="input-field" value={partner} onChange={(event) => setPartner(event.target.value)}>
                        <option value="">Who did you meet?</option>
                        {candidates.map((player) => (
                            <option key={player.nickname} value={player.nickname}>
                                {player.avatar ? `${player.avatar} ` : ''}{player.nickname}
                            </option>
                        ))}
                    </select>
                    <button
                        type="button"
                        className="btn btn-primary"
                        disabled={!partner}
                        onClick={() => partner && onRequestConfirmation?.(item.quest_id, partner)}
                    >
                        Ask Confirm
                    </button>
                </div>
            )}
        </article>
    );
}

export default function PartyQuestsGame({
    state,
    viewerName = '',
    controls = 'spectator',
    onRequestConfirmation,
    onConfirm,
    onFinalCall,
    onReveal,
    onEndGame,
}: PartyQuestsGameProps) {
    const isHost = controls === 'host';
    const isPlayer = controls === 'player';
    const title = state?.config?.game_title || 'Party Quests';
    const sortedLeaderboard = useMemo(() => [...(state?.leaderboard || [])].sort((a, b) => a.rank - b.rank), [state]);

    if (!state) {
        return (
            <div className="container-responsive safe-top safe-bottom animate-in">
                <div className="screen-hero">
                    <div className="hero-icon mb-4">🗺️</div>
                    <h1 className="hero-title">Party Quests</h1>
                    <p className="hero-subtitle">Waiting for the room</p>
                </div>
            </div>
        );
    }

    const board = state.my_board || [];
    const completed = board.filter((item) => item.status === 'confirmed').length;
    const active = state.phase === 'QUESTS_ACTIVE' || state.phase === 'QUESTS_FINAL_CALL';

    return (
        <div className="container-responsive safe-top safe-bottom animate-in">
            <div className="common-ground-hero">
                <div className="hero-icon">🗺️</div>
                <div>
                    <p className="text-[--text-tertiary] text-sm font-bold uppercase tracking-wide">
                        {phaseLabel(state.phase)} · {state.player_count} players
                    </p>
                    <h1 className="hero-title">{title}</h1>
                    <p className="hero-subtitle">{state.completed_count} quests confirmed · {state.pending_count} pending</p>
                </div>
            </div>

            {isHost && (
                <section className="common-ground-panel">
                    <h2>Host controls</h2>
                    <div className="common-ground-actions mt-4">
                        <button type="button" className="btn btn-secondary" onClick={onFinalCall} disabled={state.phase !== 'QUESTS_ACTIVE'}>
                            Final Call
                        </button>
                        <button type="button" className="btn btn-secondary" onClick={onReveal} disabled={state.phase === 'PODIUM'}>
                            Reveal Scores
                        </button>
                        <button type="button" className="btn btn-primary" onClick={onEndGame}>
                            End Game
                        </button>
                    </div>
                </section>
            )}

            {isPlayer && active && (state.incoming_requests || []).length > 0 && (
                <section className="common-ground-panel border-pink-400/40">
                    <h2>Confirm for others</h2>
                    <div className="mt-4 space-y-3">
                        {(state.incoming_requests || []).map((request) => (
                            <div key={request.id} className="rounded-xl border border-white/10 bg-white/[0.04] p-4">
                                <p className="text-[--text-secondary]">{request.requester_id} says they completed:</p>
                                <h3 className="text-2xl font-bold">{request.display}</h3>
                                <div className="common-ground-actions mt-4">
                                    <button type="button" className="btn btn-primary" onClick={() => onConfirm?.(request.id, true)}>Confirm</button>
                                    <button type="button" className="btn btn-secondary" onClick={() => onConfirm?.(request.id, false)}>Not quite</button>
                                </div>
                            </div>
                        ))}
                    </div>
                </section>
            )}

            {isPlayer && (
                <section className="common-ground-panel">
                    <div className="flex flex-wrap items-center justify-between gap-4">
                        <div>
                            <p className="text-[--text-tertiary] text-sm font-bold uppercase tracking-wide">Your board</p>
                            <h2>{completed} of {board.length} complete</h2>
                        </div>
                        <div className="rounded-xl bg-white/10 px-4 py-3 text-2xl font-bold">{state.my_score || 0} pts</div>
                    </div>
                    <div className="mt-5 space-y-4">
                        {board.map((item) => (
                            <QuestCard
                                key={item.quest_id}
                                item={item}
                                state={state}
                                viewerName={viewerName}
                                onRequestConfirmation={onRequestConfirmation}
                            />
                        ))}
                    </div>
                </section>
            )}

            <section className="common-ground-panel">
                <h2>{state.phase === 'PODIUM' || state.phase === 'QUESTS_REVEAL' ? 'Results' : 'Live leaderboard'}</h2>
                {sortedLeaderboard.length === 0 ? (
                    <p className="mt-4 text-[--text-secondary]">Scores will appear as guests complete quests.</p>
                ) : (
                    <div className="common-ground-scoreboard mt-4">
                        {sortedLeaderboard.map((row) => (
                            <div key={row.player_id}>
                                <strong>{row.rank}. {row.avatar || ''} {row.nickname || row.player_id}</strong>
                                <small>{row.score} pts · {row.completed}/{row.total} quests · {row.unique_partners} people</small>
                            </div>
                        ))}
                    </div>
                )}
            </section>

            {(state.phase === 'QUESTS_REVEAL' || state.phase === 'PODIUM') && state.awards?.length > 0 && (
                <section className="common-ground-panel">
                    <h2>Awards</h2>
                    <div className="common-ground-scoreboard mt-4">
                        {state.awards.map((award) => (
                            <div key={award.id}>
                                <strong>{award.label}</strong>
                                <small>{award.player_id}</small>
                            </div>
                        ))}
                    </div>
                </section>
            )}
        </div>
    );
}
