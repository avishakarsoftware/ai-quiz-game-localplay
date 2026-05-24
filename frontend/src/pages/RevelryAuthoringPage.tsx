import { useEffect, useState } from 'react';
import CustomQuizEditor from '../components/organizer/CustomQuizEditor';
import { API_URL } from '../config';
import { type Quiz } from '../types';

type AuthoringResolve = {
    launch_context: {
        external_container_title?: string;
        return_url?: string;
        display?: {
            container_label?: string;
            return_label?: string;
        };
    };
    mode: string;
    localplay_content_id?: string | null;
    content?: {
        quiz?: Quiz;
    } | null;
};

function returnToHostApp(returnUrl: string) {
    const url = new URL(returnUrl, window.location.origin);
    if (window.parent && window.parent !== window) {
        window.parent.postMessage({
            type: 'LOCALPLAY_REQUEST_CLOSE',
            return_url: url.toString(),
        }, url.origin);
        return;
    }
    window.location.href = url.toString();
}

export default function RevelryAuthoringPage() {
    const params = new URLSearchParams(window.location.search);
    const authoringToken = params.get('authoring_token') || '';
    const [resolved, setResolved] = useState<AuthoringResolve | null>(null);
    const [currentContentId, setCurrentContentId] = useState<string>('');
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
        returnToHostApp(url.toString());
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

    if (loading) {
        return <main className="party-hub party-hub--center">Loading editor...</main>;
    }

    if (error || !resolved) {
        return <main className="party-hub party-hub--center">{error || 'Open this from Revelry again.'}</main>;
    }

    return (
        <CustomQuizEditor
            initialQuiz={resolved.content?.quiz || null}
            packId={currentContentId || resolved.localplay_content_id || undefined}
            authToken={authoringToken}
            contextLabel={resolved.launch_context.display?.container_label || resolved.launch_context.external_container_title || 'Revelry Games'}
            onBack={() => returnToRevelry()}
            onSave={saveQuiz}
            onReview={saveAndReturn}
        />
    );
}
