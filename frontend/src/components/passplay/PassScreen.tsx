interface PassScreenProps {
    /** Who should receive the phone next. */
    seatName: string;
    seatEmoji?: string;
    /** Optional line above the name, e.g. "Round 2 of 3". */
    context?: string;
    /** Confirms the phone has physically changed hands. */
    onReady: () => void;
    readyLabel?: string;
}

/**
 * The handover screen (SPEC-PASS-AND-PLAY §1).
 *
 * Deliberately holds NOTHING but a name. It is the screen most likely to be visible to the whole
 * room — held up, angled, passed across a table — so anything sensitive rendered here defeats the
 * privacy gate that follows it. If you are tempted to add the round's secret, a score table, or
 * "you are the impostor" here, that is the bug this component exists to prevent.
 *
 * The confirm button matters too: it means the app advances when the phone has *actually* changed
 * hands, rather than on a timer that keeps running while someone is still looking for their glasses.
 */
export default function PassScreen({
    seatName,
    seatEmoji = '',
    context = '',
    onReady,
    readyLabel = "I'm ready",
}: PassScreenProps) {
    return (
        <div className="passplay-pass" data-testid="pass-screen">
            {context && <p className="passplay-pass__context">{context}</p>}
            <p className="passplay-pass__label">Pass the phone to</p>
            <div className="passplay-pass__name" data-testid="pass-screen-seat">
                {seatEmoji && <span className="passplay-pass__emoji">{seatEmoji}</span>}
                <strong>{seatName}</strong>
            </div>
            <button
                type="button"
                className="btn btn-primary passplay-pass__ready"
                onClick={onReady}
                data-testid="pass-screen-ready"
            >
                {readyLabel}
            </button>
        </div>
    );
}
