import { render, screen, fireEvent } from '@testing-library/react';
import CustomQuizEditor from '../organizer/CustomQuizEditor';

const store: Record<string, string> = {};
const mockLocalStorage = {
    getItem: vi.fn((key: string) => store[key] ?? null),
    setItem: vi.fn((key: string, value: string) => { store[key] = value; }),
    removeItem: vi.fn((key: string) => { delete store[key]; }),
    clear: vi.fn(() => { for (const key in store) delete store[key]; }),
};

vi.stubGlobal('localStorage', mockLocalStorage);

describe('CustomQuizEditor', () => {
    beforeEach(() => {
        mockLocalStorage.clear();
        vi.clearAllMocks();
    });

    it('builds a runtime-compatible quiz for review', () => {
        const onReview = vi.fn();
        render(<CustomQuizEditor onBack={() => {}} onReview={onReview} />);

        fireEvent.change(screen.getByLabelText('Quiz title'), {
            target: { value: 'Birthday Trivia' },
        });
        fireEvent.change(screen.getByLabelText('Question text'), {
            target: { value: 'Where did we first meet?' },
        });
        fireEvent.change(screen.getByLabelText('Answer A'), {
            target: { value: 'Mumbai' },
        });
        fireEvent.change(screen.getByLabelText('Answer B'), {
            target: { value: 'Seattle' },
        });
        fireEvent.change(screen.getByLabelText('Answer C'), {
            target: { value: 'Austin' },
        });
        fireEvent.change(screen.getByLabelText('Answer D'), {
            target: { value: 'London' },
        });
        fireEvent.click(screen.getAllByTitle('Set as correct')[0]);
        fireEvent.click(screen.getByRole('button', { name: 'Review & Start' }));

        expect(onReview).toHaveBeenCalledWith({
            quiz_title: 'Birthday Trivia',
            questions: [
                {
                    id: 1,
                    text: 'Where did we first meet?',
                    options: ['Mumbai', 'Seattle', 'Austin', 'London'],
                    answer_index: 1,
                    image_prompt: '',
                },
            ],
        });
    });

    it('supports true false questions', () => {
        const onReview = vi.fn();
        render(<CustomQuizEditor onBack={() => {}} onReview={onReview} />);

        fireEvent.change(screen.getByLabelText('Question text'), {
            target: { value: 'The party starts at seven.' },
        });
        fireEvent.click(screen.getByRole('button', { name: 'True / False' }));
        fireEvent.click(screen.getByRole('button', { name: 'Review & Start' }));

        expect(onReview.mock.calls[0][0].questions[0]).toMatchObject({
            options: ['True', 'False'],
            answer_index: 0,
        });
    });

    it('preserves saved question image references without exposing storage paths', () => {
        const onReview = vi.fn();
        render(<CustomQuizEditor
            onBack={() => {}}
            onReview={onReview}
            initialQuiz={{
                quiz_title: 'Picture Round',
                questions: [
                    {
                        id: 1,
                        text: 'Who is pictured here?',
                        options: ['A', 'B', 'C', 'D'],
                        answer_index: 0,
                        image_prompt: '',
                        image_url: 'https://media.revelryapp.me/apps/localplay/gamma/uploads/test.webp',
                        image_alt: 'A person holding a trophy',
                    },
                ],
            }}
        />);

        expect(screen.queryByLabelText('Question image URL')).toBeNull();
        fireEvent.change(screen.getByLabelText('Question image alt text'), {
            target: { value: 'A person holding a trophy' },
        });
        fireEvent.click(screen.getByRole('button', { name: 'Review & Start' }));

        expect(onReview.mock.calls[0][0].questions[0]).toMatchObject({
            image_url: 'https://media.revelryapp.me/apps/localplay/gamma/uploads/test.webp',
            image_alt: 'A person holding a trophy',
        });
    });

    it('removes a saved question image from the review payload', () => {
        const onReview = vi.fn();
        render(<CustomQuizEditor
            onBack={() => {}}
            onReview={onReview}
            initialQuiz={{
                quiz_title: 'Picture Round',
                questions: [
                    {
                        id: 1,
                        text: 'Who is pictured here?',
                        options: ['A', 'B', 'C', 'D'],
                        answer_index: 0,
                        image_prompt: '',
                        image_url: 'https://media.revelryapp.me/apps/localplay/gamma/uploads/test.webp',
                        image_alt: 'A person holding a trophy',
                    },
                ],
            }}
        />);

        fireEvent.click(screen.getByRole('button', { name: 'Remove Image' }));
        fireEvent.click(screen.getByRole('button', { name: 'Review & Start' }));

        expect(onReview.mock.calls[0][0].questions[0]).not.toHaveProperty('image_url');
        expect(onReview.mock.calls[0][0].questions[0]).not.toHaveProperty('image_alt');
    });

    it('does not read old unscoped v1 drafts that may contain host-app content', () => {
        mockLocalStorage.setItem('localplay_custom_quiz_draft_v1', JSON.stringify({
            title: 'Christmas Quiz',
            questions: [
                {
                    id: 'q_party',
                    type: 'multiple_choice',
                    text: 'When was the first Christmas celebrated?',
                    options: ['1965', '2001', '1001', '501'],
                    answerIndex: 0,
                    imageUrl: 'https://media.revelryapp.me/apps/localplay/gamma/uploads/christmas.webp',
                    imageAlt: 'Christmas party image',
                },
            ],
            selectedId: 'q_party',
        }));

        render(<CustomQuizEditor onBack={() => {}} onReview={() => {}} />);

        expect(screen.getByDisplayValue('Custom Quiz')).toBeInTheDocument();
        expect(screen.queryByDisplayValue('Christmas Quiz')).not.toBeInTheDocument();
        expect(screen.queryByDisplayValue('When was the first Christmas celebrated?')).not.toBeInTheDocument();
    });

    it('keeps host-app drafts scoped away from standalone drafts', () => {
        render(<CustomQuizEditor
            onBack={() => {}}
            onReview={() => {}}
            initialQuiz={{
                quiz_title: 'Party Scoped Quiz',
                questions: [
                    {
                        id: 1,
                        text: 'Party-only question',
                        options: ['A', 'B', 'C', 'D'],
                        answer_index: 0,
                        image_prompt: '',
                    },
                ],
            }}
            draftStorageKey="localplay_revelry_quiz_draft_v2:party-1"
        />);

        expect(mockLocalStorage.setItem).toHaveBeenCalledWith(
            'localplay_revelry_quiz_draft_v2:party-1',
            expect.stringContaining('Party Scoped Quiz'),
        );
        expect(store.localplay_custom_quiz_draft_v2).toBeUndefined();
    });
});
