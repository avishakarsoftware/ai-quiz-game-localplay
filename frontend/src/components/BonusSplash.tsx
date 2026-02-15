import { useEffect, useState } from 'react';
import { soundManager } from '../utils/sound';

interface BonusSplashProps {
    onComplete: () => void;
    duration?: number;
}

export default function BonusSplash({ onComplete, duration = 1800 }: BonusSplashProps) {
    const [exiting, setExiting] = useState(false);

    useEffect(() => {
        soundManager.play('bonusRound');
        soundManager.vibrate([100, 50, 100, 50, 200]);

        const exitTimer = setTimeout(() => setExiting(true), duration - 400);
        const completeTimer = setTimeout(onComplete, duration);

        return () => {
            clearTimeout(exitTimer);
            clearTimeout(completeTimer);
        };
    }, [onComplete, duration]);

    return (
        <div className={`bonus-splash-overlay ${exiting ? 'exiting' : ''}`}>
            <div className="celebration-burst" style={{ position: 'absolute', top: '45%', left: '50%' }}>
                {Array.from({ length: 16 }).map((_, i) => (
                    <span key={i} className="burst-particle" style={{
                        '--angle': `${i * 22.5}deg`,
                        '--delay': `${i * 0.02}s`,
                        '--color': ['#FFD700', '#FFA500', '#FF6B00', '#FFE066'][i % 4],
                    } as React.CSSProperties} />
                ))}
            </div>
            <div className="bonus-multiplier">2X</div>
            <div className="bonus-title">DOUBLE POINTS</div>
            <div className="bonus-subtitle">This round is worth double!</div>
        </div>
    );
}
