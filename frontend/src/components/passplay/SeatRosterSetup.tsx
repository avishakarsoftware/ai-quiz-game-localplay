import { useCallback, useMemo, useState } from 'react';

export interface Seat {
    id: string;
    name: string;
    emoji: string;
}

interface SeatRosterSetupProps {
    initialNames?: string[];
    minSeats: number;
    maxSeats: number;
    onStart: (names: string[], emojis: string[]) => void;
    /** Live-sync the roster so a host who reconnects mid-setup doesn't lose their typing. */
    onChange?: (names: string[], emojis: string[]) => void;
    startLabel?: string;
}

const EMOJI_POOL = ['🥭', '🐙', '🦊', '🐝', '🦕', '🌵', '🍄', '⚡', '🌙', '🐳', '🎈', '🔥'];

/**
 * Who's playing, typed by the host (SPEC-PASS-AND-PLAY §1).
 *
 * This exists because the normal join path is *structurally unavailable* to these players: joining
 * by QR code requires a device, and the whole point of pass-and-play is that they don't have one.
 * So the host types names, and a "seat" is a name with no socket, no session and no token.
 *
 * Names are NOT required to be unique — two guests really can both be Sam, and rejecting that
 * would be a worse experience than the ambiguity. Identity is the generated id, never the name.
 */
export default function SeatRosterSetup({
    initialNames = [],
    minSeats,
    maxSeats,
    onStart,
    onChange,
    startLabel = 'Start game',
}: SeatRosterSetupProps) {
    // Start with enough blank rows to reach the minimum, so the host sees what's required
    // rather than discovering it from a disabled button.
    const [names, setNames] = useState<string[]>(() => {
        const seeded = initialNames.slice(0, maxSeats);
        while (seeded.length < minSeats) seeded.push('');
        return seeded;
    });

    const emojis = useMemo(() => names.map((_, i) => EMOJI_POOL[i % EMOJI_POOL.length]), [names]);

    const filled = useMemo(() => names.map((n) => n.trim()).filter(Boolean), [names]);
    const canStart = filled.length >= minSeats;

    const publish = useCallback(
        (next: string[]) => {
            setNames(next);
            if (onChange) {
                const trimmed = next.map((n) => n.trim()).filter(Boolean);
                onChange(trimmed, trimmed.map((_, i) => EMOJI_POOL[i % EMOJI_POOL.length]));
            }
        },
        [onChange],
    );

    const setAt = useCallback(
        (index: number, value: string) => {
            const next = [...names];
            next[index] = value;
            publish(next);
        },
        [names, publish],
    );

    const addSeat = useCallback(() => {
        if (names.length >= maxSeats) return;
        publish([...names, '']);
    }, [names, maxSeats, publish]);

    const removeSeat = useCallback(
        (index: number) => {
            // Keep at least `minSeats` rows so the form can't be emptied into an unstartable state.
            if (names.length <= minSeats) {
                setAt(index, '');
                return;
            }
            publish(names.filter((_, i) => i !== index));
        },
        [names, minSeats, publish, setAt],
    );

    return (
        <div className="passplay-roster" data-testid="seat-roster">
            <h2 className="passplay-roster__title">Who's playing?</h2>
            <p className="passplay-roster__hint">
                One phone for everyone — nobody else needs to install anything.
            </p>

            <div className="passplay-roster__list">
                {names.map((name, i) => (
                    <div className="passplay-roster__row" key={i}>
                        <span className="passplay-roster__emoji" aria-hidden="true">{emojis[i]}</span>
                        <input
                            className="passplay-roster__input"
                            value={name}
                            onChange={(e) => setAt(i, e.target.value)}
                            placeholder={`Player ${i + 1}`}
                            aria-label={`Player ${i + 1} name`}
                            maxLength={24}
                            data-testid={`seat-input-${i}`}
                        />
                        <button
                            type="button"
                            className="passplay-roster__remove"
                            onClick={() => removeSeat(i)}
                            aria-label={`Remove player ${i + 1}`}
                            data-testid={`seat-remove-${i}`}
                        >
                            ✕
                        </button>
                    </div>
                ))}
            </div>

            <div className="passplay-roster__actions">
                <button
                    type="button"
                    className="btn btn-secondary"
                    onClick={addSeat}
                    disabled={names.length >= maxSeats}
                    data-testid="seat-add"
                >
                    Add player
                </button>
                <button
                    type="button"
                    className="btn btn-primary"
                    onClick={() => onStart(filled, filled.map((_, i) => EMOJI_POOL[i % EMOJI_POOL.length]))}
                    disabled={!canStart}
                    data-testid="seat-start"
                >
                    {startLabel}
                </button>
            </div>

            {!canStart && (
                <p className="passplay-roster__need" data-testid="seat-need-more">
                    Add at least {minSeats} players ({filled.length} so far).
                </p>
            )}
        </div>
    );
}
