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
        <div style={{ height: '100dvh', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <div className="flex flex-col items-center text-center animate-in">
                {/* Animated concentric rings */}
                <div className="loading-rings mb-8">
                    <div className="loading-ring ring-outer" />
                    <div className="loading-ring ring-middle" />
                    <div className="loading-ring ring-inner" />
                    <span className="loading-icon">🧠</span>
                </div>

                <p className="text-xl font-bold mb-2">Generating Quiz</p>
                <p className="text-[--text-tertiary] loading-message-fade" key={msgIndex}>
                    {LOADING_MESSAGES[msgIndex]}
                </p>
            </div>
        </div>
    );
}
