import type { HousieCell, HousiePattern, HousieTicket, HousieWinner } from '../types';

export function HousieCalledBoard({ calledValues, latestValue }: { calledValues: Set<string>; latestValue?: string | number | null }) {
    return (
        <div className="grid grid-cols-10 gap-1">
            {Array.from({ length: 90 }, (_, idx) => idx + 1).map((num) => {
                const called = calledValues.has(String(num));
                const latest = String(latestValue ?? '') === String(num);
                return (
                    <div
                        key={num}
                        role="status"
                        aria-label={`${num}${latest ? ', latest call' : called ? ', called' : ', not called'}`}
                        className={[
                            'aspect-square rounded-md grid place-items-center text-sm font-bold border',
                            latest ? 'bg-[--accent-pink] text-black border-[--accent-pink]' : called ? 'bg-[--accent-cyan]/20 text-[--accent-cyan] border-[--accent-cyan]/60' : 'bg-white/5 text-[--text-tertiary] border-white/10',
                        ].join(' ')}
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
        <div className="rounded-xl border border-white/15 overflow-hidden bg-white/5">
            {ticket.rows.map((row, rowIndex) => (
                <div key={rowIndex} className="grid grid-cols-9">
                    {row.map((cell, colIndex) => {
                        if (!cell) {
                            return <div key={`${rowIndex}-${colIndex}`} className="aspect-square border border-white/10 bg-black/25" />;
                        }
                        const value = String(cell.value);
                        const called = calledValues.has(value);
                        const isMarked = marked.has(value);
                        const label = `Column ${colIndex + 1}, row ${rowIndex + 1}, number ${cell.display}${isMarked ? ', marked' : called ? ', called' : ''}`;
                        return (
                            <button
                                key={`${rowIndex}-${colIndex}`}
                                type="button"
                                onClick={() => onToggle?.(cell)}
                                aria-label={label}
                                className={[
                                    'aspect-square border border-white/10 text-lg font-black transition',
                                    called ? 'text-[--accent-cyan]' : 'text-[--text-primary]',
                                    isMarked ? 'bg-[--accent-pink] text-black' : 'bg-[--surface-card]',
                                    onToggle ? 'active:scale-95' : '',
                                ].join(' ')}
                            >
                                {cell.display}
                            </button>
                        );
                    })}
                </div>
            ))}
        </div>
    );
}

export function HousieWinners({ winners }: { winners: HousieWinner[] }) {
    if (!winners.length) {
        return <p className="text-[--text-tertiary] text-sm">No prizes claimed yet.</p>;
    }
    return (
        <div className="space-y-2">
            {winners.map((winner, index) => (
                <div key={`${winner.pattern_id}-${index}`} className="rounded-lg bg-white/8 border border-white/10 px-3 py-2 flex items-center justify-between">
                    <div>
                        <p className="font-bold">{winner.label}</p>
                        <p className="text-sm text-[--text-secondary]">{winner.nickname}</p>
                    </div>
                    <span className="text-xs text-[--text-tertiary]">{winner.called_count} calls</span>
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
        <div className="grid grid-cols-2 gap-2">
            {patterns.map((pattern) => (
                <button
                    key={pattern.id}
                    type="button"
                    disabled={claimed.has(pattern.id)}
                    onClick={() => onClaim(pattern.id)}
                    className="btn btn-secondary disabled:opacity-40"
                    title={pattern.description}
                >
                    {claimed.has(pattern.id) ? 'Claimed' : pattern.label}
                </button>
            ))}
        </div>
    );
}
