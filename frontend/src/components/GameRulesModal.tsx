import { X } from 'lucide-react';
import { type GameRules } from '../gameRules';

interface GameRulesModalProps {
    rules: GameRules | null;
    onClose: () => void;
}

export default function GameRulesModal({ rules, onClose }: GameRulesModalProps) {
    if (!rules) return null;
    const playerCount = rules.player_count;
    const playerCountText = [
        playerCount?.min ? `${playerCount.min}+ players` : '',
        playerCount?.recommended ? `Best: ${playerCount.recommended}` : '',
    ].filter(Boolean).join(' · ');

    return (
        <div className="rules-modal-backdrop" role="dialog" aria-modal="true" aria-labelledby="game-rules-title" onClick={onClose}>
            <section className="rules-modal" onClick={(event) => event.stopPropagation()}>
                <div className="rules-modal__header">
                    <div>
                        <p className="rules-modal__eyebrow">Rules</p>
                        <h2 id="game-rules-title">{rules.title}</h2>
                        <p>{rules.summary}</p>
                        {playerCountText && <small>{playerCountText}</small>}
                    </div>
                    <button type="button" className="rules-modal__close" onClick={onClose} aria-label="Close rules">
                        <X size={22} aria-hidden="true" />
                    </button>
                </div>

                <div className="rules-modal__content">
                    {rules.sections.map((section) => (
                        <section key={section.id} className="rules-modal__section">
                            <h3>{section.title}</h3>
                            <ul>
                                {section.items.map((item) => <li key={item}>{item}</li>)}
                            </ul>
                        </section>
                    ))}

                    {rules.physical_setup && rules.physical_setup.length > 0 && (
                        <section className="rules-modal__section">
                            <h3>Physical setup</h3>
                            <ul>
                                {rules.physical_setup.map((item) => <li key={item}>{item}</li>)}
                            </ul>
                        </section>
                    )}

                    {rules.host_notes && rules.host_notes.length > 0 && (
                        <section className="rules-modal__section">
                            <h3>Host notes</h3>
                            <ul>
                                {rules.host_notes.map((item) => <li key={item}>{item}</li>)}
                            </ul>
                        </section>
                    )}
                </div>

                <button type="button" className="btn btn-primary rules-modal__done" onClick={onClose}>
                    Got it
                </button>
            </section>
        </div>
    );
}
