import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { type Quiz } from '../../types';

vi.mock('../../components/organizer/CustomQuizEditor', () => ({
    default: ({ initialQuiz }: { initialQuiz: Quiz | null }) => (
        <div>
            <div>Mock editor</div>
            {initialQuiz?.questions.map((question) => (
                <div key={question.id}>
                    <span>{question.text}</span>
                    {question.image_url && <img src={question.image_url} alt={question.image_alt || question.text} />}
                </div>
            ))}
        </div>
    ),
}));

import RevelryAuthoringPage from '../RevelryAuthoringPage';

// Resolve mock for chooser-flow tests. `content` non-null = editing existing.
function stubResolve(content: unknown = null) {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input);
        if (url.includes('/integrations/revelry/content/authoring-token/resolve')) {
            return Response.json({
                launch_context: {
                    host_app: 'revelry',
                    external_container_type: 'party',
                    external_container_id: 'party-1',
                    external_container_title: 'Ava Party',
                    display: { container_label: 'Ava Party' },
                    return_url: 'https://revelry.example/return',
                },
                mode: 'create',
                localplay_content_id: null,
                content,
            });
        }
        if (url.includes('/sd/status')) return Response.json({ available: false });
        return new Response('not found', { status: 404 });
    });
    vi.stubGlobal('fetch', fetchMock);
}

describe('RevelryAuthoringPage', () => {
    beforeEach(() => {
        window.history.replaceState({}, '', '/revelry/author?authoring_token=token-123');
        vi.clearAllMocks();
    });

    it('shows the AI/custom chooser first for new content, with no detailed inputs', async () => {
        stubResolve(null);
        render(<RevelryAuthoringPage />);
        await screen.findByRole('heading', { name: 'Create a quiz' });
        expect(screen.getByRole('button', { name: /AI quiz/ })).toBeInTheDocument();
        expect(screen.getByRole('button', { name: /Custom quiz/ })).toBeInTheDocument();
        expect(screen.queryByText('Topic or theme')).toBeNull();
        expect(screen.queryByText('Mock editor')).toBeNull();
    });

    it('AI path reveals the topic form but not the editor until generated', async () => {
        stubResolve(null);
        render(<RevelryAuthoringPage />);
        fireEvent.click(await screen.findByRole('button', { name: /AI quiz/ }));
        expect(screen.getByText('Topic or theme')).toBeInTheDocument();
        expect(screen.queryByText('Mock editor')).toBeNull();
    });

    it('Custom path reveals the editor directly', async () => {
        stubResolve(null);
        render(<RevelryAuthoringPage />);
        fireEvent.click(await screen.findByRole('button', { name: /Custom quiz/ }));
        expect(screen.getByText('Mock editor')).toBeInTheDocument();
        expect(screen.queryByText('Topic or theme')).toBeNull();
    });

    it('editing existing saved content skips the chooser and opens the editor', async () => {
        stubResolve({ quiz: { quiz_title: 'Saved', questions: [{ id: 1, text: 'Saved question', options: ['A', 'B'], answer_index: 0, image_prompt: '' }] } });
        render(<RevelryAuthoringPage />);
        expect(await screen.findByText('Saved question')).toBeInTheDocument();
        expect(screen.queryByRole('heading', { name: 'Create a quiz' })).toBeNull();
    });

    it('hides image generation in Revelry authoring and still generates text quizzes', async () => {
        const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
            const url = String(input);
            if (url.includes('/integrations/revelry/content/authoring-token/resolve')) {
                return Response.json({
                    launch_context: {
                        host_app: 'revelry',
                        external_container_type: 'party',
                        external_container_id: 'party-1',
                        external_container_title: 'Ava Party',
                        display: { container_label: 'Ava Party' },
                    },
                    mode: 'create',
                    localplay_content_id: null,
                    content: null,
                });
            }
            if (url.includes('/sd/status')) {
                return Response.json({ available: true });
            }
            if (url.includes('/integrations/revelry/party-games/prompts/generate')) {
                return Response.json({
                    content_payload: {
                        quiz: {
                            quiz_title: 'Ava Party Quiz',
                            questions: [
                                {
                                    id: 1,
                                    text: 'What is on the cake?',
                                    options: ['Fox', 'Bear', 'Cat', 'Dog'],
                                    answer_index: 0,
                                    image_prompt: 'party cake with fox topper',
                                },
                            ],
                        },
                    },
                });
            }
            if (url.includes('/quiz/import')) {
                throw new Error('image import should not run in Revelry authoring');
            }
            if (url.includes('/quiz/generate-images')) {
                throw new Error('image generation should not run in Revelry authoring');
            }
            return new Response('not found', { status: 404 });
        });
        vi.stubGlobal('fetch', fetchMock);

        render(<RevelryAuthoringPage />);

        // Two-step: choose AI before the generate form appears.
        fireEvent.click(await screen.findByRole('button', { name: /AI quiz/ }));
        await screen.findByText('Create an AI quiz');
        expect(screen.queryByLabelText('Generate question images')).toBeNull();
        fireEvent.click(screen.getByRole('button', { name: 'Generate AI quiz' }));

        await waitFor(() => expect(screen.getByText('What is on the cake?')).toBeInTheDocument());
    });
});
