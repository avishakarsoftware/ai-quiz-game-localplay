import type { HousieCell, HousiePattern, HousieTicket, HousieWinner } from '../types';

export function HousieCalledBoard({ calledValues, latestValue }: { calledValues: Set<string>; latestValue?: string | number | null }) {
    return (
        <div className="housie-called-board" role="grid" aria-label="Called Housie numbers">
            {Array.from({ length: 90 }, (_, idx) => idx + 1).map((num) => {
                const called = calledValues.has(String(num));
                const latest = String(latestValue ?? '') === String(num);
                return (
                    <div
                        key={num}
                        role="gridcell"
                        aria-label={`${num}${latest ? ', latest call' : called ? ', called' : ', not called'}`}
                        className={`housie-called-cell ${called ? 'called' : ''} ${latest ? 'latest' : ''}`}
                    >
                        {num}
                    </div>
                );
            })}
        </div>
    );
}

export function HousieTicketGrid({
    ticket,
    calledValues,
    marked,
    onToggle,
}: {
    ticket: HousieTicket;
    calledValues: Set<string>;
    marked: Set<string>;
    onToggle?: (cell: HousieCell) => void;
}) {
    return (
        <table className="housie-ticket-table" aria-label="Your Housie ticket">
            <tbody>
            {ticket.rows.map((row, rowIndex) => (
                <tr key={rowIndex}>
                    {row.map((cell, colIndex) => {
                        if (!cell) {
                            return <td key={`${rowIndex}-${colIndex}`} className="housie-ticket-cell empty" aria-label={`Column ${colIndex + 1}, row ${rowIndex + 1}, empty`} />;
                        }
                        const value = String(cell.value);
                        const called = calledValues.has(value);
                        const isMarked = marked.has(value);
                        const label = `Column ${colIndex + 1}, row ${rowIndex + 1}, number ${cell.display}${isMarked ? ', marked' : called ? ', called' : ''}`;
                        return (
                            <td key={`${rowIndex}-${colIndex}`} className={`housie-ticket-cell filled ${called ? 'called' : ''} ${isMarked ? 'marked' : ''}`}>
                                <button
                                    type="button"
                                    onClick={() => onToggle?.(cell)}
                                    aria-label={label}
                                    disabled={!onToggle}
                                >
                                    {cell.display}
                                </button>
                            </td>
                        );
                    })}
                </tr>
            ))}
            </tbody>
        </table>
    );
}

export function HousieWinners({ winners }: { winners: HousieWinner[] }) {
    if (!winners.length) {
        return <p className="housie-empty-copy">No prizes claimed yet.</p>;
    }
    return (
        <div className="housie-winner-list">
            {winners.map((winner, index) => (
                <div key={`${winner.pattern_id}-${index}`} className="housie-winner-row">
                    <div>
                        <p><strong>{winner.label}</strong></p>
                        <p className="housie-muted-copy">{winner.nickname}</p>
                    </div>
                    <span className="housie-muted-copy">{winner.called_count} calls</span>
                </div>
            ))}
        </div>
    );
}

export function HousieClaimButtons({
    patterns,
    winners,
    onClaim,
}: {
    patterns: HousiePattern[];
    winners: HousieWinner[];
    onClaim: (patternId: string) => void;
}) {
    const claimed = new Set(winners.map((winner) => winner.pattern_id));
    return (
        <div className="housie-claim-grid">
            {patterns.map((pattern) => (
                <button
                    key={pattern.id}
                    type="button"
                    disabled={claimed.has(pattern.id)}
                    onClick={() => onClaim(pattern.id)}
                    className="housie-claim-button"
                    title={pattern.description}
                >
                    {claimed.has(pattern.id) ? 'Claimed' : pattern.label}
                </button>
            ))}
        </div>
    );
}
