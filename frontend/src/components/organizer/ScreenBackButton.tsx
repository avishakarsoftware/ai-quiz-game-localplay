interface ScreenBackButtonProps {
    onBack: () => void;
    label?: string;
}

/**
 * Consistent top-left back control for every organizer setup/prompt/review/editor
 * screen. Flowed (not absolute) so it works inside any screen layout, left-aligned,
 * and on narrow screens it reserves the top zone so it clears the fixed menu
 * (top-left) and sparks badge (top-right).
 */
export default function ScreenBackButton({ onBack, label = 'Back' }: ScreenBackButtonProps) {
    return (
        <div className="screen-back-row">
            <button type="button" onClick={onBack} className="btn btn-secondary screen-back-button" aria-label={label}>
                <span aria-hidden="true">‹</span>{label}
            </button>
        </div>
    );
}
