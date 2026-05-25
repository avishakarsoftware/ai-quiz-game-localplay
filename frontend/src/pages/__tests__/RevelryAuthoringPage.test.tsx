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

    it('can generate an AI quiz with question images for review', async () => {
        const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
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
                expect(init?.headers).toMatchObject({ Authorization: 'Bearer token-123' });
                return Response.json({ quiz_id: 'quiz-1', quiz: {} });
            }
            if (url.includes('/quiz/generate-images')) {
                expect(init?.headers).toMatchObject({ Authorization: 'Bearer token-123' });
                return Response.json({
                    status: 'success',
                    question_id: 1,
                    asset: {
                        id: 'media-1',
                        url: '/media/media-1',
                        alt_text: 'Generated cake image',
                    },
                });
            }
            return new Response('not found', { status: 404 });
        });
        vi.stubGlobal('fetch', fetchMock);

        render(<RevelryAuthoringPage />);

        await screen.findByText('Create an AI quiz');
        fireEvent.click(screen.getByLabelText('Generate question images'));
        fireEvent.click(screen.getByRole('button', { name: 'Generate AI quiz' }));

        await waitFor(() => expect(screen.getByAltText('Generated cake image')).toBeInTheDocument());
        expect(screen.getByText('What is on the cake?')).toBeInTheDocument();
        expect(screen.getByAltText('Generated cake image')).toHaveAttribute('src', '/media/media-1');
    });
});
