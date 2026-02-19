import { useState, useEffect } from 'react';

const LOADING_MESSAGES = [
    'Crafting tricky questions...',
    'Adding a dash of difficulty...',
    'Mixing in some fun facts...',
    'Polishing the answer choices...',
    'Almost there...',
];

export default function LoadingScreen() {
    const [msgIndex, setMsgIndex] = useState(0);

    useEffect(() => {
        const interval = setInterval(() => {
            setMsgIndex((prev) => (prev + 1) % LOADING_MESSAGES.length);
        }, 2500);
        return () => clearInterval(interval);
    }, []);

    return (
        <div
            style={{
                height: '100dvh',
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'center',
                justifyContent: 'center',
            }}
            className="container-responsive animate-in"
        >
            <h1 className="hero-title mb-8">Generating Quiz</h1>

            {/* Animated concentric rings */}
            <div className="loading-rings mb-8">
                <div className="loading-ring ring-outer" />
                <div className="loading-ring ring-middle" />
                <div className="loading-ring ring-inner" />
                <img src="/icons/icon-192.png" alt="LocalPlay" className="loading-icon" style={{ width: 48, height: 48, borderRadius: 10 }} />
            </div>

            <p className="text-[--text-tertiary] loading-message-fade" key={msgIndex}>
                {LOADING_MESSAGES[msgIndex]}
            </p>
        </div>
    );
}
