import type { HousieCell, HousiePattern, HousieTicket, HousieWinner } from '../types';

export function HousieCalledBoard({ calledValues, latestValue }: { calledValues: Set<string>; latestValue?: string | number | null }) {
    const rows = Array.from({ length: 9 }, (_, rowIndex) =>
        Array.from({ length: 10 }, (_, colIndex) => rowIndex * 10 + colIndex + 1),
    );

    return (
        <table className="housie-called-table" aria-label="Called Housie numbers">
            <tbody>
                {rows.map((row, rowIndex) => (
                    <tr key={rowIndex}>
                        {row.map((num) => {
                            const called = calledValues.has(String(num));
                            const latest = String(latestValue ?? '') === String(num);
                            return (
                                <td
                                    key={num}
                                    aria-label={`${num}${latest ? ', latest call' : called ? ', called' : ', not called'}`}
                                    className={`housie-called-cell ${called ? 'called' : ''} ${latest ? 'latest' : ''}`}
                                >
                                    {num}
                                </td>
                            );
                        })}
                    </tr>
                ))}
            </tbody>
        </table>
    );
}

export function HousieTicketGrid({
    ticket,
    calledValues,
    marked,
    playMode = 'beginner',
    winningValues,
    onToggle,
}: {
    ticket: HousieTicket;
    calledValues: Set<string>;
    marked: Set<string>;
    playMode?: 'beginner' | 'pro';
    winningValues?: Set<string>;
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
                        const called = playMode === 'beginner' && calledValues.has(value);
                        const isMarked = marked.has(value);
                        const isWinning = winningValues?.has(value) ?? false;
                        const label = `Column ${colIndex + 1}, row ${rowIndex + 1}, number ${cell.display}${isMarked ? ', marked' : called ? ', called' : ''}${isWinning ? ', winning cell' : ''}`;
                        return (
                            <td key={`${rowIndex}-${colIndex}`} className={`housie-ticket-cell filled ${called ? 'called' : ''} ${isMarked ? 'marked' : ''} ${isWinning ? 'winning' : ''}`}>
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
