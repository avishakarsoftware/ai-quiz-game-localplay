import { useState, useEffect, useRef } from 'react';

interface AnimatedNumberProps {
    value: number;
    duration?: number;
    className?: string;
}

export default function AnimatedNumber({ value, duration = 600, className = '' }: AnimatedNumberProps) {
    const [display, setDisplay] = useState(value);
    const prevRef = useRef(value);

    useEffect(() => {
        const start = prevRef.current;
        const diff = value - start;
        if (diff === 0) return;

        const startTime = performance.now();
        let frameId: number;
        const step = (now: number) => {
            const elapsed = now - startTime;
            const progress = Math.min(elapsed / duration, 1);
            const eased = 1 - Math.pow(1 - progress, 3);
            setDisplay(Math.round(start + diff * eased));
            if (progress < 1) {
                frameId = requestAnimationFrame(step);
            }
        };
        frameId = requestAnimationFrame(step);
        prevRef.current = value;

        return () => cancelAnimationFrame(frameId);
    }, [value, duration]);

    return <span className={className}>{display.toLocaleString()}</span>;
}
