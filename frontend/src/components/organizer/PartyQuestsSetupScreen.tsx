import { useMemo, useState } from 'react';
import { SHOW_PROVIDER_SELECTOR } from '../../config';
import { type AIProvider } from './PromptScreen';
import ScreenBackButton from './ScreenBackButton';

export interface PartyQuestSetupConfig {
    game_title: string;
    theme: string;
    duration_minutes: number;
    quests_per_player: number;
    confirmation_mode: 'tap_confirm' | 'honor';
    allow_late_join: boolean;
    quests: Array<{ display: string; category?: string; points?: number }>;
}

interface PartyQuestsSetupScreenProps {
    initialConfig?: PartyQuestSetupConfig;
    provider: string;
    setProvider: (value: string) => void;
    providers: AIProvider[];
    onGenerateQuests: (request: {
        prompt: string;
        theme: string;
        numQuests: number;
        questsPerPlayer: number;
        durationMinutes: number;
        confirmationMode: PartyQuestSetupConfig['confirmation_mode'];
        provider: string;
    }) => Promise<PartyQuestSetupConfig | null>;
    onCreate: (config: PartyQuestSetupConfig) => void;
    onBack: () => void;
    submitLabel?: string;
    showBackButton?: boolean;
    submitting?: boolean;
}

const PACKS: Record<string, string[]> = {
    mingling: [
        'Talk to someone whose name starts with R.',
        'Find someone born in the same month as you.',
        'Meet someone who shares one of your hobbies.',
        'Find someone who has visited a city you want to visit.',
        'Ask someone for a song recommendation.',
        'Find someone wearing the same color as you.',
        'Talk to someone who has tried a new hobby this year.',
        'Meet someone who likes the same kind of movies as you.',
        'Find someone who has made a handmade gift.',
        'Talk to someone who has a funny travel story.',
    ],
    birthday: [
        'Find someone who has a favorite birthday dessert.',
        'Ask someone about their most memorable birthday.',
        'Find someone who knows the birthday person from school or work.',
        'Meet someone who can recommend a party song.',
        'Find someone who has given a handmade gift.',
        'Talk to someone who loves surprise parties.',
        'Find someone who has a photo with the birthday person.',
        'Meet someone who shares your favorite snack.',
        'Ask someone for a funny party memory.',
        'Find someone who can start a group toast.',
    ],
    wedding: [
        'Find someone who knows a good dance move.',
        'Ask someone how they know the couple.',
        'Find someone who traveled from another city.',
        'Meet someone who has wedding advice.',
        'Find someone who can recommend a romantic song.',
        'Talk to someone wearing your favorite color.',
        'Find someone who has been to a destination wedding.',
        'Ask someone for a favorite dessert recommendation.',
        'Meet someone who loves the same movie genre as you.',
        'Find someone who will join a group photo.',
    ],
    work_safe: [
        'Find someone from a different team.',
        'Ask someone what tool saves them the most time.',
        'Find someone who has a hidden creative hobby.',
        'Meet someone who joined in the last year.',
        'Ask someone for a lunch recommendation.',
        'Find someone who has worked in another city.',
        'Talk to someone who has presented to a large room.',
        'Find someone who enjoys solving puzzles.',
        'Ask someone what skill they want to learn next.',
        'Meet someone who knows a useful shortcut.',
    ],
    family: [
        'Find someone who can tell a funny family story.',
        'Ask someone about their favorite holiday food.',
        'Find someone who has a pet story.',
        'Meet someone who likes the same dessert as you.',
        'Ask someone to teach you one word from another language.',
        'Find someone who likes board games.',
        'Talk to someone who enjoys cooking.',
        'Find someone who has visited a beach recently.',
        'Meet someone who can recommend a family movie.',
        'Find someone who likes singing along to songs.',
    ],
};

const PACK_LABELS: Record<string, string> = {
    mingling: 'Mingling',
    birthday: 'Birthday',
    wedding: 'Wedding',
    work_safe: 'Work-safe',
    family: 'Family',
};

function buildConfig(theme = 'mingling'): PartyQuestSetupConfig {
    const quests = (PACKS[theme] || PACKS.mingling).map((display, index) => ({
        display,
        category: theme,
        points: index >= 8 ? 150 : 100,
    }));
    return {
        game_title: 'Party Quests',
        theme,
        duration_minutes: 90,
        quests_per_player: 8,
        confirmation_mode: 'tap_confirm',
        allow_late_join: true,
        quests,
    };
}

export const defaultPartyQuestsConfig = buildConfig;

export default function PartyQuestsSetupScreen({
    initialConfig,
    provider,
    setProvider,
    providers,
    onGenerateQuests,
    onCreate,
    onBack,
    submitLabel = 'Create Room',
    showBackButton = true,
    submitting = false,
}: PartyQuestsSetupScreenProps) {
    const [config, setConfig] = useState<PartyQuestSetupConfig>(initialConfig || buildConfig());
    const [questDrafts, setQuestDrafts] = useState(() => config.quests.map((item) => item.display));
    const [aiPrompt, setAiPrompt] = useState('friendly party mingling quests');
    const [generating, setGenerating] = useState(false);

    const parsedQuests = useMemo(() => questDrafts.map((line) => line.trim()).filter(Boolean), [questDrafts]);
    const questCountOptions = useMemo(() => {
        const maximum = Math.max(3, parsedQuests.length);
        return [...new Set([3, 5, 8, 10, 12, 15, 20, 25, maximum].filter((value) => value <= maximum))].sort((a, b) => a - b);
    }, [parsedQuests.length]);
    const canCreate = parsedQuests.length >= 3;

    const applyTheme = (theme: string) => {
        const next = buildConfig(theme);
        setConfig((current) => ({ ...current, theme, quests: next.quests }));
        setQuestDrafts(next.quests.map((item) => item.display));
    };

    const generateQuests = async () => {
        const prompt = aiPrompt.trim();
        if (!prompt || generating) return;
        setGenerating(true);
        try {
            const generated = await onGenerateQuests({
                prompt,
                theme: config.theme,
                numQuests: Math.max(10, parsedQuests.length || 10),
                questsPerPlayer: config.quests_per_player,
                durationMinutes: config.duration_minutes,
                confirmationMode: config.confirmation_mode,
                provider,
            });
            if (generated) {
                setConfig(generated);
                setQuestDrafts(generated.quests.map((item) => item.display));
            }
        } finally {
            setGenerating(false);
        }
    };

    const updateQuest = (index: number, value: string) => {
        setQuestDrafts((current) => current.map((quest, i) => (i === index ? value : quest)));
    };

    const addQuest = () => {
        setQuestDrafts((current) => [...current, '']);
    };

    const removeQuest = (index: number) => {
        setQuestDrafts((current) => current.filter((_, i) => i !== index));
    };

    const moveQuest = (index: number, direction: -1 | 1) => {
        setQuestDrafts((current) => {
            const nextIndex = index + direction;
            if (nextIndex < 0 || nextIndex >= current.length) return current;
            const next = [...current];
            [next[index], next[nextIndex]] = [next[nextIndex], next[index]];
            return next;
        });
    };

    const submit = () => {
        if (!canCreate) return;
        onCreate({
            ...config,
            quests_per_player: Math.min(config.quests_per_player, parsedQuests.length),
            quests: parsedQuests.map((display, index) => ({
                display,
                category: config.theme,
                points: index >= Math.max(0, parsedQuests.length - 2) ? 150 : 100,
            })),
        });
    };

    return (
        <div className="container-responsive safe-top safe-bottom animate-in">
            {showBackButton && <ScreenBackButton onBack={onBack} />}
            <div className="text-center mb-7 prompt-header">
                <div className="hero-icon mb-4">🗺️</div>
                <h1 className="hero-title">Party Quests</h1>
                <p className="hero-subtitle">Choose a quest pack guests can play throughout the party.</p>
            </div>

            <section className="common-ground-panel">
                <h2>Quest pack</h2>
                <div className="common-ground-actions mt-4">
                    {Object.entries(PACK_LABELS).map(([id, label]) => (
                        <button
                            type="button"
                            key={id}
                            className={`btn ${config.theme === id ? 'btn-primary' : 'btn-secondary'}`}
                            onClick={() => applyTheme(id)}
                        >
                            {label}
                        </button>
                    ))}
                </div>
            </section>

            <section className="common-ground-panel">
                <h2>AI quest block</h2>
                <p className="mt-2 text-[--text-secondary]">Describe the party, guest mix, or vibe. You can edit and reorder every generated quest before launch.</p>
                <div className="party-quest-ai-card mt-4">
                    <textarea
                        className="input-field party-quest-ai-input"
                        value={aiPrompt}
                        onChange={(event) => setAiPrompt(event.target.value.slice(0, 300))}
                        placeholder="Example: outdoor birthday, cousins and school friends, silly but family friendly"
                    />
                    {SHOW_PROVIDER_SELECTOR && providers.length > 0 && (
                        <select value={provider} onChange={(event) => setProvider(event.target.value)} className="input-field">
                            {providers.map((item) => (
                                <option key={item.id} value={item.id} disabled={!item.available}>
                                    {item.name}{item.available ? '' : ' (unavailable)'}
                                </option>
                            ))}
                        </select>
                    )}
                    <button type="button" className="btn btn-primary" onClick={generateQuests} disabled={generating || !aiPrompt.trim()}>
                        {generating ? 'Generating...' : 'Generate Quest Block'}
                    </button>
                </div>
            </section>

            <section className="common-ground-panel">
                <h2>Settings</h2>
                <div className="grid gap-4 md:grid-cols-2 mt-4">
                    <label className="space-y-2">
                        <span className="text-[--text-secondary] font-bold">Duration</span>
                        <select
                            className="input-field"
                            value={config.duration_minutes}
                            onChange={(event) => setConfig((current) => ({ ...current, duration_minutes: Number(event.target.value) }))}
                        >
                            {[30, 60, 90, 120, 180].map((value) => <option key={value} value={value}>{value} minutes</option>)}
                        </select>
                    </label>
                    <label className="space-y-2">
                        <span className="text-[--text-secondary] font-bold">Quests per player</span>
                        <select
                            className="input-field"
                            value={Math.min(config.quests_per_player, Math.max(3, parsedQuests.length))}
                            onChange={(event) => setConfig((current) => ({ ...current, quests_per_player: Number(event.target.value) }))}
                        >
                            {questCountOptions.map((value) => <option key={value} value={value}>{value}</option>)}
                        </select>
                    </label>
                    <label className="space-y-2">
                        <span className="text-[--text-secondary] font-bold">Confirmation</span>
                        <select
                            className="input-field"
                            value={config.confirmation_mode}
                            onChange={(event) => setConfig((current) => ({ ...current, confirmation_mode: event.target.value as PartyQuestSetupConfig['confirmation_mode'] }))}
                        >
                            <option value="tap_confirm">Other person taps confirm</option>
                            <option value="honor">Honor system</option>
                        </select>
                    </label>
                    <label className="flex items-center justify-between gap-4 rounded-lg border border-white/10 bg-white/5 px-4 py-3">
                        <span className="font-bold">Late joins</span>
                        <input
                            type="checkbox"
                            checked={config.allow_late_join}
                            onChange={(event) => setConfig((current) => ({ ...current, allow_late_join: event.target.checked }))}
                        />
                    </label>
                </div>
            </section>

            <section className="common-ground-panel">
                <h2>Quest list</h2>
                <p className="mt-2 text-[--text-secondary]">Starter quests are editable. Each player receives a random board from this list.</p>
                <div className="party-quest-card-grid mt-4">
                    {questDrafts.map((quest, index) => (
                        <div key={index} className="party-quest-edit-card">
                            <div className="party-quest-edit-card__number">{index + 1}</div>
                            <textarea
                                className="party-quest-edit-card__input"
                                aria-label={`Quest ${index + 1}`}
                                value={quest}
                                onChange={(event) => updateQuest(index, event.target.value.slice(0, 180))}
                                placeholder="Write a party quest"
                            />
                            <div className="party-quest-edit-card__actions">
                                <button type="button" className="btn btn-secondary" onClick={() => moveQuest(index, -1)} disabled={index === 0}>Up</button>
                                <button type="button" className="btn btn-secondary" onClick={() => moveQuest(index, 1)} disabled={index === questDrafts.length - 1}>Down</button>
                                <button type="button" className="btn btn-secondary" onClick={() => removeQuest(index)} disabled={questDrafts.length <= 3}>Remove</button>
                            </div>
                        </div>
                    ))}
                </div>
                <div className="party-quest-list-footer">
                    <p className="text-[--text-secondary]">{parsedQuests.length} quests available</p>
                    <button type="button" className="btn btn-secondary" onClick={addQuest}>Add quest</button>
                </div>
            </section>

            <button type="button" className="btn btn-primary w-full" disabled={!canCreate || submitting} onClick={submit}>
                {submitLabel}
            </button>
        </div>
    );
}
