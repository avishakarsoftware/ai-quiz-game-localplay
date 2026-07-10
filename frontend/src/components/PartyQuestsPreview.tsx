import { useMemo, useState } from 'react';
import { type PartyQuestSetupConfig } from './organizer/PartyQuestsSetupScreen';

interface PartyQuestsPreviewProps {
    config: PartyQuestSetupConfig;
    onBack: () => void;
    onEdit: () => void;
    onStart?: () => void;
}

type PreviewTab = 'host' | 'player' | 'tv';

const SAMPLE_PLAYERS = ['Aarav', 'Maya', 'Jordan', 'Sam'];

export default function PartyQuestsPreview({ config, onBack, onEdit, onStart }: PartyQuestsPreviewProps) {
    const [tab, setTab] = useState<PreviewTab>('player');
    const sampleQuests = useMemo(
        () => config.quests.slice(0, Math.min(config.quests_per_player, 5)),
        [config.quests, config.quests_per_player],
    );

    return (
        <div className="container-responsive safe-top safe-bottom animate-in">
            <div className="lobby-top-actions">
                <button type="button" className="btn btn-secondary lobby-back-button" onClick={onBack}>Back to games</button>
                <button type="button" className="btn btn-secondary lobby-back-button" onClick={onEdit}>Edit setup</button>
            </div>
            <div className="text-center mb-7 prompt-header">
                <div className="hero-icon mb-4">🗺️</div>
                <p className="text-[--text-tertiary] text-sm font-bold uppercase tracking-wide">Preview · Sample data</p>
                <h1 className="hero-title">{config.game_title}</h1>
                <p className="hero-subtitle">See the host, player, and TV experience before guests join.</p>
            </div>

            <div className="game-category-tabs mb-6" aria-label="Party Quests preview view">
                {(['host', 'player', 'tv'] as PreviewTab[]).map((item) => (
                    <button
                        key={item}
                        type="button"
                        className={`game-category-tab ${tab === item ? 'active' : ''}`}
                        onClick={() => setTab(item)}
                    >
                        {item === 'tv' ? 'TV' : item[0].toUpperCase() + item.slice(1)}
                    </button>
                ))}
            </div>

            {tab === 'host' && (
                <section className="common-ground-panel">
                    <p className="text-[--text-tertiary] text-sm font-bold uppercase tracking-wide">Active · {SAMPLE_PLAYERS.length} sample players</p>
                    <h2>Host controls</h2>
                    <p className="mt-2 text-[--text-secondary]">{config.duration_minutes} minutes · {config.quests_per_player} quests per player · {config.confirmation_mode === 'honor' ? 'Honor system' : 'Guest confirmation'}</p>
                    <div className="common-ground-actions mt-4">
                        <button type="button" className="btn btn-secondary" disabled>Final call</button>
                        <button type="button" className="btn btn-primary" disabled>End and reveal</button>
                    </div>
                    <div className="common-ground-scoreboard mt-5">
                        {SAMPLE_PLAYERS.map((name, index) => (
                            <div key={name}><strong>{index + 1}. {name}</strong><small>{Math.max(0, 350 - index * 75)} sample pts</small></div>
                        ))}
                    </div>
                </section>
            )}

            {tab === 'player' && (
                <section className="common-ground-panel">
                    <div className="flex flex-wrap items-center justify-between gap-4">
                        <div><p className="text-[--text-tertiary] text-sm font-bold uppercase tracking-wide">Maya's sample board</p><h2>1 of {sampleQuests.length} complete</h2></div>
                        <div className="rounded-lg bg-white/10 px-4 py-3 text-2xl font-bold">100 pts</div>
                    </div>
                    <div className="mt-5 space-y-4">
                        {sampleQuests.map((quest, index) => (
                            <article key={`${quest.display}-${index}`} className={`rounded-lg border p-4 ${index === 0 ? 'border-emerald-300/40 bg-emerald-400/10' : 'border-white/10 bg-white/[0.04]'}`}>
                                <p className="text-[--text-tertiary] text-sm font-bold uppercase tracking-wide">{quest.points || 100} pts · {index === 0 ? 'Done' : 'Open'}</p>
                                <h3 className="text-2xl font-bold">{quest.display}</h3>
                                {index === 0 && <p className="mt-2 text-[--text-secondary]">Confirmed by Aarav</p>}
                            </article>
                        ))}
                    </div>
                </section>
            )}

            {tab === 'tv' && (
                <section className="common-ground-panel text-center">
                    <p className="text-[--text-tertiary] text-sm font-bold uppercase tracking-wide">Party screen · Private quests stay on phones</p>
                    <h2>{config.game_title}</h2>
                    <p className="mt-2 text-[--text-secondary]">8 sample quests confirmed · 2 pending</p>
                    <div className="common-ground-scoreboard mt-5 text-left">
                        {SAMPLE_PLAYERS.map((name, index) => (
                            <div key={name}><strong>{index + 1}. {name}</strong><small>{Math.max(0, 350 - index * 75)} sample pts</small></div>
                        ))}
                    </div>
                </section>
            )}

            <p className="text-center text-[--text-tertiary] mt-5">Preview uses sample guests. Nothing is scored or sent to Revelry.</p>
            {onStart && <button type="button" className="btn btn-primary w-full mt-5" onClick={onStart}>Start this setup</button>}
        </div>
    );
}
