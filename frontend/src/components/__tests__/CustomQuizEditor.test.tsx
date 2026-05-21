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

    it('preserves question image references', () => {
        const onReview = vi.fn();
        render(<CustomQuizEditor onBack={() => {}} onReview={onReview} />);

        fireEvent.change(screen.getByLabelText('Question text'), {
            target: { value: 'Who is pictured here?' },
        });
        fireEvent.change(screen.getByLabelText('Answer A'), { target: { value: 'A' } });
        fireEvent.change(screen.getByLabelText('Answer B'), { target: { value: 'B' } });
        fireEvent.change(screen.getByLabelText('Answer C'), { target: { value: 'C' } });
        fireEvent.change(screen.getByLabelText('Answer D'), { target: { value: 'D' } });
        fireEvent.change(screen.getByLabelText('Question image URL'), {
            target: { value: 'https://media.revelryapp.me/apps/localplay/gamma/uploads/test.webp' },
        });
        fireEvent.change(screen.getByLabelText('Question image alt text'), {
            target: { value: 'A person holding a trophy' },
        });
        fireEvent.click(screen.getByRole('button', { name: 'Review & Start' }));

        expect(onReview.mock.calls[0][0].questions[0]).toMatchObject({
            image_url: 'https://media.revelryapp.me/apps/localplay/gamma/uploads/test.webp',
            image_alt: 'A person holding a trophy',
        });
    });
});
