import GameImage from './media/GameImage';
import { mediaUrl } from '../utils/media';
import type { HousieCell, HousiePattern, HousieTicket, HousieWinner } from '../types';

type BingoDisplayItem = {
    value?: number | string;
    display: string;
    kind?: string;
    image_url?: string;
    alt_text?: string;
};

function cellKey(cell: HousieCell): string {
    return String(cell.id || cell.item_id || cell.value);
}

export function BingoCardGrid({
    ticket,
    calledValues,
    marked,
    winningValues,
    onToggle,
}: {
    ticket: HousieTicket;
    calledValues: Set<string>;
    marked: Set<string>;
    winningValues?: Set<string>;
    onToggle?: (cell: HousieCell) => void;
}) {
    return (
        <div className="bingo-card-grid" aria-label="Your Bingo card">
            {ticket.rows.flatMap((row, rowIndex) =>
                row.map((cell, colIndex) => {
                    if (!cell) return <div key={`${rowIndex}-${colIndex}`} className="bingo-card-cell empty" />;
                    const key = cellKey(cell);
                    const called = calledValues.has(String(cell.value)) || calledValues.has(String(cell.id || ''));
                    const isMarked = cell.kind === 'free' || marked.has(key);
                    const isWinning = winningValues?.has(String(cell.value)) ?? false;
                    const label = `${cell.display}${isMarked ? ', marked' : called ? ', called' : ''}${isWinning ? ', winning cell' : ''}`;
                    return (
                        <button
                            key={`${rowIndex}-${colIndex}`}
                            type="button"
                            onClick={() => cell.kind !== 'free' && onToggle?.(cell)}
                            disabled={!onToggle || cell.kind === 'free'}
                            aria-label={label}
                            className={`bingo-card-cell ${cell.kind} ${called ? 'called' : ''} ${isMarked ? 'marked' : ''} ${isWinning ? 'winning' : ''}`}
                        >
                            {cell.kind === 'image' && cell.image_url ? (
                                <>
                                    <GameImage src={mediaUrl(cell.image_url)} alt={cell.alt_text || cell.display} mode="thumbnail" />
                                    <span>{cell.display}</span>
                                </>
                            ) : cell.kind === 'emoji' ? (
                                <span className="bingo-card-emoji">{cell.display}</span>
                            ) : (
                                <span>{cell.display}</span>
                            )}
                        </button>
                    );
                }),
            )}
        </div>
    );
}

export function BingoCallOverlay({ item }: { item: BingoDisplayItem }) {
    return (
        <div className="bingo-call-overlay">
            <div className="bingo-call-card">
                <p>Called</p>
                {item.kind === 'image' && item.image_url && (
                    <GameImage src={mediaUrl(item.image_url)} alt={item.alt_text || item.display} mode="thumbnail" />
                )}
                <strong>{item.display}</strong>
            </div>
        </div>
    );
}

export function BingoCalledList({ items }: { items: BingoDisplayItem[] }) {
    if (!items.length) return <p className="housie-empty-copy">No calls yet.</p>;
    return (
        <div className="bingo-called-list">
            {items.slice().reverse().slice(0, 24).map((item, index) => (
                <div key={`${item.value}-${index}`} className="bingo-called-chip">
                    {item.kind === 'image' && item.image_url && <GameImage src={mediaUrl(item.image_url)} alt={item.alt_text || item.display} mode="thumbnail" />}
                    <span className={item.kind === 'emoji' ? 'bingo-called-emoji' : ''}>{item.display}</span>
                </div>
            ))}
        </div>
    );
}

export function BingoClaimButtons({
    patterns,
    winners,
    onClaim,
}: {
    patterns: HousiePattern[];
    winners: HousieWinner[];
    onClaim: (patternId: string) => void;
}) {
    return (
        <div className="housie-claim-grid">
            {patterns.map((pattern) => {
                const patternWinners = winners.filter((winner) => winner.pattern_id === pattern.id);
                const claimedBy = patternWinners.map((winner) => winner.nickname).join(', ');
                const isTerminal = Boolean(pattern.terminal || pattern.id === 'full_house' || pattern.id === 'blackout');
                const isClaimed = patternWinners.length > 0;
                return (
                    <button
                        key={pattern.id}
                        type="button"
                        disabled={isClaimed && !isTerminal}
                        onClick={() => onClaim(pattern.id)}
                        className="housie-claim-button"
                        title={pattern.description}
                    >
                        {isClaimed ? `${pattern.label} claimed by ${claimedBy}` : pattern.label}
                    </button>
                );
            })}
        </div>
    );
}
