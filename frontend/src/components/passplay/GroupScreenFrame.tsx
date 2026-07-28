interface GroupScreenFrameProps {
    /** Shown large at the top — this is read from across a table, not held at reading distance. */
    title: string;
    subtitle?: string;
    children: React.ReactNode;
}

/**
 * The face-up frame for phases the WHOLE TABLE looks at (SPEC-PASS-AND-PLAY §1).
 *
 * A pass-and-play phone alternates between two completely different viewing contexts: a private
 * screen held close by one person, and a shared screen lying on a table with six people leaning
 * over it. Those need different type sizes and different information density, and mixing them is
 * how you get a vote list nobody can read from the far side of the table.
 *
 * This frame marks the shared context. Anything inside it is, by definition, public to the room —
 * so it must never contain a secret. That is the rule that lets the privacy gate mean something.
 */
export default function GroupScreenFrame({ title, subtitle, children }: GroupScreenFrameProps) {
    return (
        <div className="passplay-group" data-testid="group-screen">
            <header className="passplay-group__header">
                <h2 className="passplay-group__title">{title}</h2>
                {subtitle && <p className="passplay-group__subtitle">{subtitle}</p>}
            </header>
            <div className="passplay-group__body">{children}</div>
        </div>
    );
}
