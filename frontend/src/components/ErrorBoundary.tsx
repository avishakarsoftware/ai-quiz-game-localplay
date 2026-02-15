import { Component, type ErrorInfo, type ReactNode } from 'react';

interface Props {
    children: ReactNode;
}

interface State {
    hasError: boolean;
    error: Error | null;
}

export default class ErrorBoundary extends Component<Props, State> {
    constructor(props: Props) {
        super(props);
        this.state = { hasError: false, error: null };
    }

    static getDerivedStateFromError(error: Error): State {
        return { hasError: true, error };
    }

    componentDidCatch(error: Error, errorInfo: ErrorInfo) {
        console.error('ErrorBoundary caught:', error, errorInfo);
    }

    render() {
        if (this.state.hasError) {
            return (
                <div className="app-container">
                    <div className="content-wrapper">
                        <div className="min-h-dvh flex flex-col items-center justify-center container-responsive">
                            <div className="text-5xl mb-4">⚠</div>
                            <h2 className="text-2xl font-bold mb-2">Something went wrong</h2>
                            <p className="text-[--text-tertiary] mb-6 text-center">
                                {this.state.error?.message || 'An unexpected error occurred'}
                            </p>
                            <button
                                onClick={() => window.location.reload()}
                                className="btn btn-primary"
                            >
                                Reload App
                            </button>
                        </div>
                    </div>
                </div>
            );
        }

        return this.props.children;
    }
}
