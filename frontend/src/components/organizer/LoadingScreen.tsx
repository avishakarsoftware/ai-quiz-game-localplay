import { useState, useEffect } from 'react';

const LOADING_MESSAGES = [
    'Crafting tricky questions...',
    'Adding a dash of difficulty...',
    'Mixing in some fun facts...',
    'Polishing the answer choices...',
    'Almost there...',
];

const PREPARING_MESSAGES = [
    'Loading your saved questions...',
    'Preparing answer choices...',
    'Checking images...',
    'Almost ready...',
];

interface LoadingScreenProps {
    title?: string;
    messages?: string[];
}

export default function LoadingScreen({ title = 'Generating Quiz', messages = LOADING_MESSAGES }: LoadingScreenProps) {
    const [msgIndex, setMsgIndex] = useState(0);

    useEffect(() => {
        const interval = setInterval(() => {
            setMsgIndex((prev) => (prev + 1) % messages.length);
        }, 2500);
        return () => clearInterval(interval);
    }, [messages.length]);

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
            <h1 className="hero-title mb-8">{title}</h1>

            {/* Animated concentric rings */}
            <div className="loading-rings mb-8">
                <div className="loading-ring ring-outer" />
                <div className="loading-ring ring-middle" />
                <div className="loading-ring ring-inner" />
                <img src={`${import.meta.env.BASE_URL}icons/icon-192.png`} alt="Revelry Games" className="loading-icon" style={{ width: 48, height: 48, borderRadius: 10 }} />
            </div>

            <p className="text-[--text-tertiary] loading-message-fade" key={msgIndex}>
                {messages[msgIndex] || messages[0]}
            </p>
        </div>
    );
}

export { PREPARING_MESSAGES };
