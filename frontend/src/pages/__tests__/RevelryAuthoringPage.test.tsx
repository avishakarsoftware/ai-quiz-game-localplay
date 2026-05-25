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

describe('RevelryAuthoringPage', () => {
    beforeEach(() => {
        window.history.replaceState({}, '', '/revelry/author?authoring_token=token-123');
        vi.clearAllMocks();
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

        await screen.findByText('Create an AI quiz');
        expect(screen.queryByLabelText('Generate question images')).toBeNull();
        fireEvent.click(screen.getByRole('button', { name: 'Generate AI quiz' }));

        await waitFor(() => expect(screen.getByText('What is on the cake?')).toBeInTheDocument());
    });
});
