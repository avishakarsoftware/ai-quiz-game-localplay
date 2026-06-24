import type { LeaderboardEntry, PlayingCard, PokerState } from '../types';

interface PokerGameProps {
    state: PokerState | null;
    role: 'host' | 'player' | 'spectator';
    viewerName?: string;
    leaderboard?: LeaderboardEntry[];
    onStay?: () => void;
    onFold?: () => void;
    onReveal?: () => void;
    onNextHand?: () => void;
    onEndGame?: () => void;
}

function suitSymbol(suit?: string): string {
    if (suit === 'hearts') return '♥';
    if (suit === 'diamonds') return '♦';
    if (suit === 'clubs') return '♣';
    if (suit === 'spades') return '♠';
    return '';
}

function Card({ card }: { card: PlayingCard }) {
    const hidden = card.hidden || !card.rank;
    const red = card.suit === 'hearts' || card.suit === 'diamonds';
    return (
        <div className={`bluff-card ${hidden ? 'bluff-card--back' : ''}`}>
            {hidden ? (
                <span className="bluff-card-backmark">R</span>
            ) : (
                <>
                    <span className={red ? 'bluff-red' : 'bluff-black'}>{card.rank}</span>
                    <span className={red ? 'bluff-red' : 'bluff-black'}>{suitSymbol(card.suit)}</span>
                </>
            )}
        </div>
    );
}

function phaseText(phase?: string): string {
    if (phase === 'POKER_DECISION') return 'Choose stay or fold';
    if (phase === 'POKER_SHOWDOWN') return 'Showdown';
    if (phase === 'PODIUM') return 'Tournament complete';
    return 'Poker table';
}

export default function PokerGame({ state, role, viewerName = '', leaderboard = [], onStay, onFold, onReveal, onNextHand, onEndGame }: PokerGameProps) {
    if (!state) {
        return (
            <div className="bluff-shell container-responsive safe-top safe-bottom animate-in">
                <div className="screen-hero">
                    <div className="hero-icon mb-4">♠️</div>
                    <h1 className="hero-title">Party Poker</h1>
                    <p className="hero-subtitle">Waiting for the table</p>
                </div>
            </div>
        );
    }

    const title = state.config?.game_title || 'Party Poker';
    const myDecision = viewerName ? state.decisions?.[viewerName] : '';
    const canAct = role === 'player' && state.phase === 'POKER_DECISION' && myDecision === 'pending';
    const myCards = viewerName ? state.hole_cards?.[viewerName] || [] : [];
    const rows = state.players.map((name) => ({
        name,
        stack: state.stacks?.[name] || 0,
        status: state.statuses?.[name] || '',
        decision: state.decisions?.[name] || '',
        cards: state.hole_cards?.[name] || [],
    }));

    return (
        <div className="bluff-shell container-responsive safe-top safe-bottom animate-in">
            <div className="bluff-hero">
                <div className="hero-icon">♠️</div>
                <div>
                    <p className="text-[--text-tertiary] text-sm font-bold uppercase tracking-wide">No-money card table</p>
                    <h1 className="hero-title">{title}</h1>
                    <p className="hero-subtitle">Hand {state.hand_number} · Pot {state.pot} play chips · {phaseText(state.phase)}</p>
                </div>
            </div>

            <div className="turn-handoff-banner active">
                <strong>{phaseText(state.phase)}</strong>
                <span>Everyone starts equal. Play chips have no cash value.</span>
            </div>

            <div className="bluff-panel">
                <h2>Table Cards</h2>
                <div className="bluff-card-row">
                    {state.community_cards.map((card) => <Card key={card.id} card={card} />)}
                </div>
                {state.hand_result && (
                    <p className="mt-4 text-[--text-secondary]">
                        {state.hand_result.winner_id} wins {state.hand_result.pot} play chips
                        {state.hand_result.ranked?.[0]?.evaluation?.category ? ` with ${state.hand_result.ranked[0].evaluation.category.replace(/_/g, ' ')}` : ''}.
                    </p>
                )}
            </div>

            {role === 'player' && (
                <div className="bluff-panel">
                    <div className="bluff-hand-title">
                        <h2>Your hand</h2>
                        <span>{myDecision && myDecision !== 'pending' ? myDecision : 'decide now'}</span>
                    </div>
                    <div className="bluff-card-row bluff-hand">
                        {myCards.map((card) => <Card key={card.id} card={card} />)}
                    </div>
                </div>
            )}

            <div className="bluff-panel">
                <h2>Players</h2>
                <div className="bluff-player-grid">
                    {rows.map((row) => (
                        <div key={row.name} className={`bluff-player ${row.name === state.hand_result?.winner_id ? 'winner' : ''}`}>
                            <span>{row.status === 'eliminated' ? '×' : '♠'}</span>
                            <strong>{row.name}</strong>
                            <small>{row.stack} chips · {row.decision || row.status}</small>
                            {state.phase !== 'POKER_DECISION' && (
                                <div className="bluff-card-row" style={{ marginTop: 8 }}>
                                    {row.cards.map((card) => <Card key={card.id} card={card} />)}
                                </div>
                            )}
                        </div>
                    ))}
                </div>
            </div>

            <div className="bluff-actions">
                {role === 'player' && state.phase === 'POKER_DECISION' && (
                    <>
                        <button type="button" className="btn btn-secondary" onClick={onFold} disabled={!canAct}>Fold</button>
                        <button type="button" className="btn btn-primary btn-glow" onClick={onStay} disabled={!canAct}>Stay</button>
                    </>
                )}
                {role === 'host' && (
                    <>
                        <button type="button" className="btn btn-secondary" onClick={onReveal} disabled={state.phase !== 'POKER_DECISION'}>Reveal</button>
                        <button type="button" className="btn btn-primary btn-glow" onClick={onNextHand} disabled={state.phase !== 'POKER_SHOWDOWN'}>Next Hand</button>
                        <button type="button" className="btn btn-secondary" onClick={onEndGame}>End Game</button>
                    </>
                )}
            </div>

            {(state.phase === 'PODIUM' || leaderboard.length > 0) && (
                <div className="bluff-panel">
                    <h2>Standings</h2>
                    {(state.standings?.length ? state.standings : leaderboard.map((row, index) => ({ player_id: row.nickname, place: index + 1, stack: row.score }))).map((row) => (
                        <div key={row.player_id} className="flex justify-between rounded-lg bg-white/5 px-4 py-3 mb-2">
                            <span>#{row.place} {row.player_id}</span>
                            <strong>{row.stack || 0}</strong>
                        </div>
                    ))}
                </div>
            )}
        </div>
    );
}
