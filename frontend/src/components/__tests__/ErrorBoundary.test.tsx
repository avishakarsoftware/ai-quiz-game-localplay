import { render, screen } from '@testing-library/react';
import ErrorBoundary from '../ErrorBoundary';

function ThrowingComponent({ message }: { message: string }): React.ReactNode {
    throw new Error(message);
}

function GoodComponent() {
    return <div>All good</div>;
}

describe('ErrorBoundary', () => {
    // Suppress React error boundary console.error noise in tests
    const originalError = console.error;
    beforeAll(() => {
        console.error = vi.fn();
    });
    afterAll(() => {
        console.error = originalError;
    });

    it('renders children when there is no error', () => {
        render(
            <ErrorBoundary>
                <GoodComponent />
            </ErrorBoundary>
        );
        expect(screen.getByText('All good')).toBeInTheDocument();
    });

    it('renders fallback UI when a child throws', () => {
        render(
            <ErrorBoundary>
                <ThrowingComponent message="Test crash" />
            </ErrorBoundary>
        );
        expect(screen.getByText('Something went wrong')).toBeInTheDocument();
    });

    it('displays the error message', () => {
        render(
            <ErrorBoundary>
                <ThrowingComponent message="Connection failed" />
            </ErrorBoundary>
        );
        expect(screen.getByText('Connection failed')).toBeInTheDocument();
    });

    it('shows a Reload App button', () => {
        render(
            <ErrorBoundary>
                <ThrowingComponent message="Oops" />
            </ErrorBoundary>
        );
        expect(screen.getByRole('button', { name: 'Reload App' })).toBeInTheDocument();
    });
});
