import { type BluffState, type PlayingCard } from '../types';

interface BluffTableProps {
    state: BluffState | null;
    viewerName?: string;
    selectedCardIds?: Set<string>;
    onToggleCard?: (cardId: string) => void;
    onPlay?: () => void;
    onPass?: () => void;
    onChallenge?: () => void;
    onContinue?: () => void;
    onEndGame?: () => void;
    controls?: 'player' | 'host' | 'spectator';
}

function cardSuitSymbol(suit?: string): string {
    if (suit === 'hearts') return '♥';
    if (suit === 'diamonds') return '♦';
    if (suit === 'clubs') return '♣';
    if (suit === 'spades') return '♠';
    return '';
}

function CardFace({ card, selected, onClick }: { card: PlayingCard; selected?: boolean; onClick?: () => void }) {
    const hidden = card.hidden || !card.rank;
    const red = card.color === 'red' || card.suit === 'hearts' || card.suit === 'diamonds';
    return (
        <button
            type="button"
            className={`bluff-card ${hidden ? 'bluff-card--back' : ''} ${selected ? 'bluff-card--selected' : ''}`}
            onClick={onClick}
            disabled={!onClick}
            aria-pressed={selected}
        >
            {hidden ? (
                <span className="bluff-card-backmark">R</span>
            ) : (
                <>
                    <span className={red ? 'bluff-red' : 'bluff-black'}>{card.rank}</span>
                    <span className={red ? 'bluff-red' : 'bluff-black'}>{cardSuitSymbol(card.suit)}</span>
                </>
            )}
        </button>
    );
}

function handCount(state: BluffState, name: string): number {
    return state.hands?.[name]?.count || 0;
}

export default function BluffTable({
    state,
    viewerName = '',
    selectedCardIds = new Set<string>(),
    onToggleCard,
    onPlay,
    onPass,
    onChallenge,
    onContinue,
    onEndGame,
    controls = 'spectator',
}: BluffTableProps) {
    if (!state) {
        return (
            <div className="bluff-shell container-responsive safe-top safe-bottom animate-in">
                <div className="screen-hero">
                    <div className="hero-icon mb-4">🂡</div>
                    <h1 className="hero-title">Bluff</h1>
                    <p className="hero-subtitle">Waiting for the table</p>
                </div>
            </div>
        );
    }

    const myTurn = controls === 'player' && viewerName && state.active_player_id === viewerName && state.phase === 'BLUFF_TURN';
    const canChallenge = controls === 'player'
        && state.phase === 'BLUFF_CHALLENGE'
        && viewerName
        && state.last_claim?.actor_id !== viewerName
        && state.players.includes(viewerName);
    const myHand = viewerName ? state.hands?.[viewerName]?.cards || [] : [];
    const winnerNames = new Set(state.winners.map((winner) => winner.player_id));
    const claim = state.last_claim;
    const selectedCount = selectedCardIds.size;
    const challengeWindow = state.phase === 'BLUFF_CHALLENGE';
    const turnLabel = myTurn
        ? 'Your turn'
        : challengeWindow
            ? 'Challenge window'
            : state.phase === 'BLUFF_TURN'
                ? `${state.active_player_id}'s turn`
                : state.phase === 'BLUFF_REVEAL'
                    ? 'Reveal'
                    : 'Final results';
    const turnDetail = myTurn
        ? `Play one or more ${state.required_rank}s, or pass.`
        : challengeWindow
            ? `${claim?.actor_id} played ${claim?.claimed_count || 0}. Call bluff or continue to pass control.`
            : state.phase === 'BLUFF_TURN'
                ? `Waiting for ${state.active_player_id} to act.`
                : state.phase === 'BLUFF_REVEAL'
                    ? 'Review the reveal, then continue.'
                    : 'Game complete.';

    return (
        <div className="bluff-shell container-responsive safe-top safe-bottom animate-in">
            <div className="bluff-hero">
                <div className="hero-icon">🂡</div>
                <div>
                    <p className="text-[--text-tertiary] text-sm font-bold uppercase tracking-wide">Card table</p>
                    <h1 className="hero-title">Bluff</h1>
                    <p className="hero-subtitle">
                        {state.phase === 'BLUFF_TURN'
                            ? `${state.active_player_id}'s turn · claim ${state.required_rank}s`
                            : state.phase === 'BLUFF_CHALLENGE'
                                ? `${claim?.actor_id} claims ${claim?.claimed_count} ${claim?.claimed_rank}${claim?.claimed_count === 1 ? '' : 's'}`
                                : state.phase === 'BLUFF_REVEAL'
                                    ? `${claim?.truthful ? 'Truthful claim' : 'Bluff caught'}`
                                    : 'Final results'}
                    </p>
                </div>
            </div>

            <div className={`turn-handoff-banner ${myTurn ? 'active' : challengeWindow ? 'warning' : ''}`}>
                <strong>{turnLabel}</strong>
                <span>{turnDetail}</span>
            </div>

            <div className="bluff-status-card">
                <div>
                    <span className="bluff-label">Pile</span>
                    <strong>{state.pile_count}</strong>
                </div>
                <div>
                    <span className="bluff-label">Required rank</span>
                    <strong>{state.required_rank || 'A'}</strong>
                </div>
                <div>
                    <span className="bluff-label">Turn</span>
                    <strong>{state.active_player_id || 'Done'}</strong>
                </div>
            </div>

            {state.phase === 'BLUFF_REVEAL' && (
                <div className="bluff-panel">
                    <h2>Reveal</h2>
                    <p className="text-[--text-secondary]">
                        {claim?.truthful
                            ? `${claim.challenger_id} challenged and takes the pile.`
                            : `${claim?.actor_id} was bluffing and takes the pile.`}
                    </p>
                    <div className="bluff-card-row">
                        {state.revealed_cards.map((card) => <CardFace key={card.id} card={card} />)}
                    </div>
                </div>
            )}

            <div className="bluff-panel">
                <h2>Players</h2>
                <div className="bluff-player-grid">
                    {state.players.map((name) => (
                        <div key={name} className={`bluff-player ${state.active_player_id === name ? 'active' : ''} ${winnerNames.has(name) ? 'winner' : ''}`}>
                            <span>{winnerNames.has(name) ? '🏁' : '🃏'}</span>
                            <strong>{name}</strong>
                            <small>{winnerNames.has(name) ? `Place ${state.winners.find((winner) => winner.player_id === name)?.place}` : `${handCount(state, name)} cards`}</small>
                        </div>
                    ))}
                </div>
            </div>

            {controls === 'player' && (
                <div className="bluff-panel">
                    <div className="bluff-hand-title">
                        <h2>Your hand</h2>
                        <span>{selectedCount} selected</span>
                    </div>
                    <div className="bluff-card-row bluff-hand">
                        {myHand.map((card) => (
                            <CardFace
                                key={card.id}
                                card={card}
                                selected={selectedCardIds.has(card.id)}
                                onClick={myTurn && onToggleCard ? () => onToggleCard(card.id) : undefined}
                            />
                        ))}
                    </div>
                </div>
            )}

            <div className="bluff-actions">
                {controls === 'player' && (
                    <>
                        {state.phase === 'BLUFF_TURN' && (
                            <>
                                <button className="btn btn-secondary" onClick={onPass} disabled={!myTurn}>Pass</button>
                                <button className="btn btn-primary btn-glow" onClick={onPlay} disabled={!myTurn || selectedCount === 0}>
                                    Play {selectedCount || ''}
                                </button>
                            </>
                        )}
                        {state.phase === 'BLUFF_CHALLENGE' && (
                            <button className="btn btn-primary btn-glow" onClick={onChallenge} disabled={!canChallenge}>Call Bluff</button>
                        )}
                        {(state.phase === 'BLUFF_CHALLENGE' || state.phase === 'BLUFF_REVEAL') && (
                            <button className="btn btn-secondary" onClick={onContinue}>Continue</button>
                        )}
                    </>
                )}
                {controls === 'host' && (
                    <>
                        {(state.phase === 'BLUFF_CHALLENGE' || state.phase === 'BLUFF_REVEAL') && (
                            <button className="btn btn-primary btn-glow" onClick={onContinue}>Continue</button>
                        )}
                        <button className="btn btn-secondary" onClick={onEndGame}>End Game</button>
                    </>
                )}
            </div>
        </div>
    );
}
