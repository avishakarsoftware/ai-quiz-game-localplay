import { useEffect, useState } from 'react';
import CustomQuizEditor from '../components/organizer/CustomQuizEditor';
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
    mode: string;
    localplay_content_id?: string | null;
    content?: {
        quiz?: Quiz;
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
    const [generating, setGenerating] = useState(false);
    const [generationError, setGenerationError] = useState('');
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState('');

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

    function returnToRevelry(localplayContentId?: string) {
        const returnUrl = resolved?.launch_context.return_url;
        if (!returnUrl) return;
        const url = new URL(returnUrl, window.location.origin);
        if (localplayContentId) {
            url.searchParams.set('localplay_content_id', localplayContentId);
            url.searchParams.set('game_type', 'quiz');
            url.searchParams.set('status', 'ready');
        }
        returnToHostApp(url.toString(), { parentOrigin: resolved?.launch_context.parent_origin });
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

    async function generateAiQuiz() {
        const prompt = aiPrompt.trim() || resolved?.launch_context.external_container_title || 'this party';
        setGenerating(true);
        setGenerationError('');
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
            setGeneratedQuiz(quiz);
            setGeneratedVersion((value) => value + 1);
        } catch {
            setGenerationError('Could not generate an AI quiz. Try a different topic or create one manually.');
        } finally {
            setGenerating(false);
        }
    }

    if (loading) {
        return <main className="party-hub party-hub--center">Loading editor...</main>;
    }

    if (error || !resolved) {
        return <main className="party-hub party-hub--center">{error || 'Open this from Revelry again.'}</main>;
    }

    const containerScope = [
        resolved.launch_context.host_app || 'host_app',
        resolved.launch_context.external_container_type || 'container',
        resolved.launch_context.external_container_id || 'unknown',
    ].join(':');
    const contentScope = currentContentId || resolved.localplay_content_id || `new:${authoringToken.slice(0, 16)}`;
    const initialQuiz = generatedQuiz || resolved.content?.quiz || null;

    return (
        <>
            {!resolved.content?.quiz && (
                <section className="revelry-ai-authoring-panel container-responsive safe-top">
                    <div>
                        <p>{resolved.launch_context.display?.container_label || resolved.launch_context.external_container_title || 'Revelry Games'}</p>
                        <h1>Create an AI quiz</h1>
                        <span>Generate questions, edit anything, then save it to this party.</span>
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
                        <button className="btn btn-primary btn-glow" type="button" onClick={generateAiQuiz} disabled={generating}>
                            {generating ? 'Generating...' : generatedQuiz ? 'Regenerate quiz' : 'Generate AI quiz'}
                        </button>
                    </div>
                    {generationError && <p className="revelry-ai-authoring-error">{generationError}</p>}
                </section>
            )}
            <CustomQuizEditor
                key={`${contentScope}:${generatedVersion}`}
                initialQuiz={initialQuiz}
                packId={currentContentId || resolved.localplay_content_id || undefined}
                authToken={authoringToken}
                draftStorageKey={`localplay_revelry_quiz_draft_v2:${containerScope}:${contentScope}:${generatedVersion}`}
                contextLabel={resolved.launch_context.display?.container_label || resolved.launch_context.external_container_title || 'Revelry Games'}
                onBack={() => returnToRevelry()}
                onSave={saveQuiz}
                onReview={saveAndReturn}
            />
        </>
    );
}
