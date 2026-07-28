import { useCallback, useEffect, useRef, useState } from 'react';

interface PrivacyGateProps {
    /** Who is meant to be looking. Named on the shield so the wrong person self-corrects. */
    seatName: string;
    seatEmoji?: string;
    /** Rendered ONLY after a deliberate reveal. Never rendered while shielded. */
    children: React.ReactNode;
    /** Called when the viewer confirms they're done and the phone should be passed on. */
    onDone: () => void;
    holdMs?: number;
    doneLabel?: string;
}

const DEFAULT_HOLD_MS = 450;

/**
 * The privacy boundary for pass-and-play (SPEC-PASS-AND-PLAY §1).
 *
 * One device serves every player in turn, so secrets can't be protected by scoping payloads —
 * there is a single viewer and the server has already sent everything. Privacy here is
 * *physical*, and this component is the whole mechanism:
 *
 * 1. A shield names who should be looking, so the wrong person stops before revealing.
 * 2. Revealing requires a deliberate press-and-HOLD, not a tap. A tap is what a phone being
 *    handed over receives by accident; a hold cannot happen in a pocket or mid-pass.
 * 3. The secret is un-rendered again the moment the viewer is done, so the next person receives
 *    a shielded screen rather than the previous player's role.
 *
 * `children` are not rendered at all while shielded — not hidden with CSS. A `display:none`
 * secret is still in the DOM, still in a screenshot-adjacent accessibility tree, and still one
 * devtools glance away.
 */
export default function PrivacyGate({
    seatName,
    seatEmoji = '',
    children,
    onDone,
    holdMs = DEFAULT_HOLD_MS,
    doneLabel = 'Got it — hide & pass',
}: PrivacyGateProps) {
    const [revealed, setRevealed] = useState(false);
    const [holding, setHolding] = useState(false);
    const timer = useRef<number | null>(null);

    const clearTimer = useCallback(() => {
        if (timer.current !== null) {
            window.clearTimeout(timer.current);
            timer.current = null;
        }
    }, []);

    // A hold interrupted by unmount must not fire later against a dead component.
    useEffect(() => clearTimer, [clearTimer]);

    // Re-shield whenever the seat changes. Without this, passing the phone to the next player
    // while the previous reveal is still mounted would show them the previous person's secret.
    useEffect(() => {
        setRevealed(false);
        setHolding(false);
        clearTimer();
    }, [seatName, clearTimer]);

    const startHold = useCallback(() => {
        if (revealed) return;
        setHolding(true);
        clearTimer();
        timer.current = window.setTimeout(() => {
            setRevealed(true);
            setHolding(false);
            timer.current = null;
        }, holdMs);
    }, [revealed, holdMs, clearTimer]);

    const cancelHold = useCallback(() => {
        setHolding(false);
        clearTimer();
    }, [clearTimer]);

    const finish = useCallback(() => {
        setRevealed(false);
        cancelHold();
        onDone();
    }, [cancelHold, onDone]);

    if (revealed) {
        return (
            <div className="passplay-gate passplay-gate--revealed" data-testid="privacy-gate-revealed">
                <div className="passplay-gate__content">{children}</div>
                <button
                    type="button"
                    className="btn btn-primary passplay-gate__done"
                    onClick={finish}
                    data-testid="privacy-gate-done"
                >
                    {doneLabel}
                </button>
            </div>
        );
    }

    return (
        <div className="passplay-gate passplay-gate--shielded" data-testid="privacy-gate-shield">
            <div className="passplay-gate__who">
                {seatEmoji && <span className="passplay-gate__emoji">{seatEmoji}</span>}
                <strong data-testid="privacy-gate-seat-name">{seatName}</strong>
            </div>
            <p className="passplay-gate__warning">Make sure nobody else can see the screen.</p>
            <button
                type="button"
                className={`btn btn-secondary passplay-gate__hold ${holding ? 'is-holding' : ''}`}
                onPointerDown={startHold}
                onPointerUp={cancelHold}
                onPointerLeave={cancelHold}
                onPointerCancel={cancelHold}
                data-testid="privacy-gate-hold"
                aria-label={`Hold to reveal ${seatName}'s secret`}
            >
                {holding ? 'Keep holding…' : 'Hold to reveal'}
            </button>
        </div>
    );
}
