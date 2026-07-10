import { useEffect, useState } from 'react';
import CustomQuizEditor from '../components/organizer/CustomQuizEditor';
import PartyQuestsSetupScreen, {
    defaultPartyQuestsConfig,
    partyQuestsConfigFromPayload,
    type PartyQuestSetupConfig,
} from '../components/organizer/PartyQuestsSetupScreen';
import { API_URL } from '../config';
import { type Quiz } from '../types';
import { returnToHostApp } from '../utils/hostAppReturn';

type AuthoringResolve = {
    launch_context: {
        host_app?: string;
        external_container_type?: string;
        external_container_id?: string;
        external_container_title?: string;
        return_url?: string;
        display?: {
            container_label?: string;
            return_label?: string;
        };
        parent_origin?: string;
    };
    game_type?: string;
    mode: string;
    localplay_content_id?: string | null;
    content?: {
        quiz?: Quiz;
        content_payload?: Record<string, unknown>;
    } | null;
};

export default function RevelryAuthoringPage() {
    const params = new URLSearchParams(window.location.search);
    const authoringToken = params.get('authoring_token') || '';
    const [resolved, setResolved] = useState<AuthoringResolve | null>(null);
    const [currentContentId, setCurrentContentId] = useState<string>('');
    const [generatedQuiz, setGeneratedQuiz] = useState<Quiz | null>(null);
    const [generatedVersion, setGeneratedVersion] = useState(0);
    const [aiPrompt, setAiPrompt] = useState('');
    const [aiDifficulty, setAiDifficulty] = useState('medium');
    const [aiQuestionCount, setAiQuestionCount] = useState(10);
    const [aiGenerateImages, setAiGenerateImages] = useState(false);
    const [imageGenerationAvailable, setImageGenerationAvailable] = useState(false);
    const [imageProgress, setImageProgress] = useState(0);
    const [generating, setGenerating] = useState(false);
    const [generationError, setGenerationError] = useState('');
    const [generationWarning, setGenerationWarning] = useState('');
    const [partyProvider, setPartyProvider] = useState('');
    const [partySaving, setPartySaving] = useState(false);
    const [partyError, setPartyError] = useState('');
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState('');
    // Two-step authoring: pick AI vs custom before showing detailed inputs.
    // Editing an existing saved quiz skips the chooser (handled in render).
    const [authoringMode, setAuthoringMode] = useState<'choose' | 'ai' | 'custom'>('choose');

    useEffect(() => {
        let cancelled = false;
        async function load() {
            if (!authoringToken) {
                setError('Open this from Revelry again.');
                setLoading(false);
                return;
            }
            try {
                const res = await fetch(`${API_URL}/integrations/revelry/content/authoring-token/resolve?authoring_token=${encodeURIComponent(authoringToken)}`);
                if (!res.ok) throw new Error('resolve_failed');
                const data = await res.json();
                if (!cancelled) {
                    setResolved(data);
                    setCurrentContentId(data.localplay_content_id || '');
                }
            } catch {
                if (!cancelled) setError('Open this from Revelry again.');
            } finally {
                if (!cancelled) setLoading(false);
            }
        }
        void load();
        return () => { cancelled = true; };
    }, [authoringToken]);

    useEffect(() => {
        let cancelled = false;
        async function loadImageStatus() {
            try {
                const res = await fetch(`${API_URL}/sd/status`);
                if (!res.ok) throw new Error('status_failed');
                const data = await res.json();
                if (!cancelled) setImageGenerationAvailable(Boolean(data?.available));
            } catch {
                if (!cancelled) setImageGenerationAvailable(false);
            }
        }
        void loadImageStatus();
        return () => { cancelled = true; };
    }, []);

    function returnToRevelry(localplayContentId?: string) {
        const returnUrl = resolved?.launch_context.return_url;
        if (!returnUrl) return;
        const url = new URL(returnUrl, window.location.origin);
        const gameType = resolved?.game_type || 'quiz';
        if (localplayContentId) {
            url.searchParams.set('localplay_content_id', localplayContentId);
            url.searchParams.set('game_type', gameType);
            url.searchParams.set('status', 'ready');
        }
        returnToHostApp(url.toString(), {
            parentOrigin: resolved?.launch_context.parent_origin,
            // Mirror the saved pointer in the postMessage payload so the host app can reconcile in place
            // without re-navigating (which was dropping the Revelry session and signing the host out).
            content: localplayContentId
                ? { localplay_content_id: localplayContentId, game_type: gameType, status: 'ready' }
                : undefined,
        });
    }

    async function saveQuiz(quiz: Quiz, packId?: string) {
        const res = await fetch(`${API_URL}/integrations/revelry/content`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                Authorization: `Bearer ${authoringToken}`,
            },
            body: JSON.stringify({
                game_type: 'quiz',
                title: quiz.quiz_title,
                content_id: packId || currentContentId || resolved?.localplay_content_id || undefined,
                content_payload: { quiz },
                status: 'ready',
            }),
        });
        if (!res.ok) throw new Error('save_failed');
        const data = await res.json();
        const contentId = data.localplay_content_id as string;
        setCurrentContentId(contentId);
        return contentId;
    }

    async function saveAndReturn(quiz: Quiz, packId?: string) {
        const contentId = await saveQuiz(quiz, packId);
        returnToRevelry(contentId);
        return contentId;
    }

    async function generatePartyQuests(request: {
        prompt: string;
        theme: string;
        numQuests: number;
        questsPerPlayer: number;
        durationMinutes: number;
        confirmationMode: PartyQuestSetupConfig['confirmation_mode'];
        provider: string;
    }): Promise<PartyQuestSetupConfig | null> {
        setPartyError('');
        try {
            const difficulty = request.theme === 'work_safe'
                ? 'work'
                : request.theme === 'family'
                    ? 'wholesome'
                    : 'party';
            const res = await fetch(`${API_URL}/integrations/revelry/party-games/prompts/generate`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    party_games_token: authoringToken,
                    game_type: 'party_quests',
                    prompt: request.prompt,
                    difficulty,
                    num_prompts: request.numQuests,
                    provider: request.provider,
                }),
            });
            if (!res.ok) throw new Error('generate_failed');
            const data = await res.json();
            const generated = partyQuestsConfigFromPayload(
                data.content_payload || {},
                resolved?.launch_context.external_container_title
                    ? `${resolved.launch_context.external_container_title} Quests`
                    : 'Party Quests',
            );
            return {
                ...generated,
                duration_minutes: request.durationMinutes,
                quests_per_player: Math.min(request.questsPerPlayer, generated.quests.length),
                confirmation_mode: request.confirmationMode,
            };
        } catch {
            setPartyError('Could not generate quests. Try a different party description or edit the starter pack.');
            return null;
        }
    }

    async function savePartyQuests(config: PartyQuestSetupConfig) {
        setPartySaving(true);
        setPartyError('');
        try {
            const res = await fetch(`${API_URL}/integrations/revelry/content`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    Authorization: `Bearer ${authoringToken}`,
                },
                body: JSON.stringify({
                    game_type: 'party_quests',
                    title: config.game_title,
                    content_id: currentContentId || resolved?.localplay_content_id || undefined,
                    content_payload: { game: config },
                    status: 'ready',
                }),
            });
            if (!res.ok) throw new Error('save_failed');
            const data = await res.json();
            const contentId = data.localplay_content_id as string;
            setCurrentContentId(contentId);
            returnToRevelry(contentId);
        } catch {
            setPartyError('Could not save Party Quests. Please try again.');
        } finally {
            setPartySaving(false);
        }
    }

    async function generateAiQuiz() {
        const prompt = aiPrompt.trim() || resolved?.launch_context.external_container_title || 'this party';
        setGenerating(true);
        setGenerationError('');
        setGenerationWarning('');
        setImageProgress(0);
        try {
            const partyGamesToken = authoringToken;
            const res = await fetch(`${API_URL}/integrations/revelry/party-games/prompts/generate`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    party_games_token: partyGamesToken,
                    game_type: 'quiz',
                    prompt,
                    difficulty: aiDifficulty,
                    num_prompts: aiQuestionCount,
                }),
            });
            if (!res.ok) throw new Error('generate_failed');
            const data = await res.json();
            const quiz = data.content_payload?.quiz as Quiz | undefined;
            if (!quiz?.questions?.length) throw new Error('empty_quiz');
            let nextQuiz = quiz;
            if (aiGenerateImages && canGenerateAiImages) {
                nextQuiz = await generateImagesForQuiz(quiz);
            }
            setGeneratedVersion((value) => value + 1);
            setGeneratedQuiz(nextQuiz);
        } catch {
            setGenerationError('Could not generate an AI quiz. Try a different topic or create one manually.');
        } finally {
            setGenerating(false);
        }
    }

    async function generateImagesForQuiz(quiz: Quiz): Promise<Quiz> {
        try {
            const importRes = await fetch(`${API_URL}/quiz/import`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    Authorization: `Bearer ${authoringToken}`,
                },
                body: JSON.stringify({ quiz }),
            });
            if (!importRes.ok) throw new Error('import_failed');
            const imported = await importRes.json();
            const quizId = imported.quiz_id as string;
            const questions = [...quiz.questions];
            const imageRes = await fetch(`${API_URL}/quiz/generate-images`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    Authorization: `Bearer ${authoringToken}`,
                },
                body: JSON.stringify({ quiz_id: quizId }),
            });
            if (!imageRes.ok) throw new Error('image_failed');
            const imageData = await imageRes.json();
            const assets = Array.isArray(imageData.assets) ? imageData.assets : [];
            const assetsByQuestion = new Map<number, { id: string; url: string; alt_text?: string }>();
            assets.forEach((asset: { question_id?: number; id: string; url: string; alt_text?: string }) => {
                if (asset.question_id && asset.url) assetsByQuestion.set(asset.question_id, asset);
            });
            questions.forEach((question, index) => {
                const asset = assetsByQuestion.get(question.id);
                if (!asset) return;
                questions[index] = {
                    ...question,
                    image_asset_id: asset.id,
                    image_url: asset.url,
                    image_alt: asset.alt_text || question.text,
                };
            });
            setImageProgress(questions.length);
            const failures = questions.length - assetsByQuestion.size;
            if (failures > 0) {
                setGenerationWarning(`${failures} image${failures === 1 ? '' : 's'} failed to generate. You can still save the quiz without those images.`);
            }
            return { ...quiz, questions };
        } catch {
            setGenerationWarning('Image generation could not start. The text quiz is ready to edit and save.');
            return quiz;
        }
    }

    if (loading) {
        return <main className="party-hub party-hub--center">Loading editor...</main>;
    }

    if (error || !resolved) {
        return <main className="party-hub party-hub--center">{error || 'Open this from Revelry again.'}</main>;
    }

    if (resolved.game_type === 'party_quests') {
        const fallback = defaultPartyQuestsConfig('mingling');
        const title = resolved.launch_context.external_container_title
            ? `${resolved.launch_context.external_container_title} Quests`
            : 'Party Quests';
        const initialConfig = resolved.content?.content_payload
            ? partyQuestsConfigFromPayload(resolved.content.content_payload, title)
            : { ...fallback, game_title: title };
        return (
            <>
                {partyError && <p className="revelry-ai-authoring-error container-responsive">{partyError}</p>}
                <PartyQuestsSetupScreen
                    initialConfig={initialConfig}
                    provider={partyProvider}
                    setProvider={setPartyProvider}
                    providers={[]}
                    onGenerateQuests={generatePartyQuests}
                    onCreate={(config) => { void savePartyQuests(config); }}
                    onBack={() => returnToRevelry()}
                    submitLabel={partySaving ? 'Saving...' : 'Save Party Quests'}
                    submitting={partySaving}
                />
            </>
        );
    }

    if (resolved.game_type && resolved.game_type !== 'quiz') {
        return (
            <main className="party-hub party-hub--center">
                This game setup is not available from this link. Return to Revelry Games and open it again.
            </main>
        );
    }

    const containerScope = [
        resolved.launch_context.host_app || 'host_app',
        resolved.launch_context.external_container_type || 'container',
        resolved.launch_context.external_container_id || 'unknown',
    ].join(':');
    const editorScope = resolved.localplay_content_id || `new:${authoringToken.slice(0, 16)}`;
    const draftScope = currentContentId || resolved.localplay_content_id || editorScope;
    const hostAppImageGenerationAllowed = Boolean(
        resolved.launch_context.host_app !== 'revelry'
        || false
    );
    const canGenerateAiImages = imageGenerationAvailable && hostAppImageGenerationAllowed;

    const editingExisting = Boolean(resolved.content?.quiz);
    const effectiveMode = editingExisting ? 'custom' : authoringMode;
    const containerLabel = resolved.launch_context.display?.container_label || resolved.launch_context.external_container_title || 'Revelry Games';
    const editorBack = editingExisting ? () => returnToRevelry() : () => setAuthoringMode('choose');
    const initialQuiz = effectiveMode === 'ai'
        ? generatedQuiz
        : resolved.content?.quiz || null;

    // Step 1 — choose AI vs custom (only for brand-new content).
    if (effectiveMode === 'choose') {
        return (
            <section className="revelry-ai-authoring-panel container-responsive safe-top">
                <button type="button" className="btn btn-secondary revelry-authoring-back" onClick={() => returnToRevelry()}>‹ Back</button>
                <div>
                    <p>{containerLabel}</p>
                    <h1>Create a quiz</h1>
                    <span>Choose how you want to build this quiz.</span>
                </div>
                <div className="revelry-authoring-choice-grid">
                    <button type="button" className="revelry-authoring-choice-card" onClick={() => setAuthoringMode('ai')}>
                        <span className="revelry-authoring-choice-emoji" aria-hidden="true">✨</span>
                        <strong>AI quiz</strong>
                        <span>Generate questions from a topic, then edit before saving.</span>
                    </button>
                    <button type="button" className="revelry-authoring-choice-card" onClick={() => setAuthoringMode('custom')}>
                        <span className="revelry-authoring-choice-emoji" aria-hidden="true">✍️</span>
                        <strong>Custom quiz</strong>
                        <span>Write your own questions.</span>
                    </button>
                </div>
            </section>
        );
    }

    return (
        <>
            {effectiveMode === 'ai' && (
                <section className="revelry-ai-authoring-panel container-responsive safe-top">
                    <button type="button" className="btn btn-secondary revelry-authoring-back" onClick={() => setAuthoringMode('choose')}>‹ Back</button>
                    <div>
                        <p>{containerLabel}</p>
                        <h1>Create an AI quiz</h1>
                        <span>Generate questions, edit anything, then save it to this party.</span>
                        <p className="revelry-ai-authoring-note">AI can make mistakes, and generated questions or images may not fit every age group. Please review before saving.</p>
                    </div>
                    <div className="revelry-ai-authoring-grid">
                        <label>
                            <span>Topic or theme</span>
                            <input
                                value={aiPrompt}
                                onChange={(event) => setAiPrompt(event.target.value)}
                                placeholder="Ava's birthday, Bollywood, cricket, inside jokes..."
                                maxLength={500}
                            />
                        </label>
                        <label>
                            <span>Difficulty</span>
                            <select value={aiDifficulty} onChange={(event) => setAiDifficulty(event.target.value)}>
                                <option value="easy">Easy</option>
                                <option value="medium">Medium</option>
                                <option value="hard">Hard</option>
                            </select>
                        </label>
                        <label>
                            <span>Questions</span>
                            <input
                                type="number"
                                min={3}
                                max={20}
                                value={aiQuestionCount}
                                onChange={(event) => setAiQuestionCount(Math.max(3, Math.min(20, Number(event.target.value) || 10)))}
                            />
                        </label>
                        {canGenerateAiImages && (
                            <label className="revelry-ai-image-toggle">
                                <span>Images</span>
                                <label className="revelry-ai-checkbox">
                                    <input
                                        type="checkbox"
                                        checked={aiGenerateImages}
                                        onChange={(event) => setAiGenerateImages(event.target.checked)}
                                        disabled={generating}
                                    />
                                    <span>Generate question images</span>
                                </label>
                            </label>
                        )}
                        <button className="btn btn-primary btn-glow" type="button" onClick={generateAiQuiz} disabled={generating}>
                            {generating ? (aiGenerateImages && canGenerateAiImages ? `Generating ${imageProgress ? `${imageProgress}/${aiQuestionCount}` : '...'}` : 'Generating...') : generatedQuiz ? 'Regenerate quiz' : 'Generate AI quiz'}
                        </button>
                    </div>
                    {generationError && <p className="revelry-ai-authoring-error">{generationError}</p>}
                    {generationWarning && <p className="revelry-ai-authoring-warning">{generationWarning}</p>}
                </section>
            )}
            {(effectiveMode === 'custom' || (effectiveMode === 'ai' && generatedQuiz)) && (
                <CustomQuizEditor
                    key={`${editorScope}:${generatedVersion}`}
                    initialQuiz={initialQuiz}
                    packId={currentContentId || resolved.localplay_content_id || undefined}
                    authToken={authoringToken}
                    draftStorageKey={`localplay_revelry_quiz_draft_v2:${containerScope}:${draftScope}:${generatedVersion}`}
                    contextLabel={containerLabel}
                    onBack={editorBack}
                    onSave={saveQuiz}
                    onReview={saveAndReturn}
                />
            )}
        </>
    );
}
