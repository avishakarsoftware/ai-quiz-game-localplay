import { useEffect, useRef, useCallback, useState } from 'react';

const EDGE_ZONE = 30;       // px from left edge to start tracking
const THRESHOLD = 80;        // px swipe distance to trigger back
const MAX_Y_DRIFT = 60;      // px vertical drift before cancelling

export function useSwipeBack(onBack: () => void) {
    const startX = useRef(0);
    const startY = useRef(0);
    const tracking = useRef(false);
    const [swipeProgress, setSwipeProgress] = useState(0); // 0-1

    const handleTouchStart = useCallback((e: TouchEvent) => {
        const touch = e.touches[0];
        if (touch.clientX <= EDGE_ZONE) {
            tracking.current = true;
            startX.current = touch.clientX;
            startY.current = touch.clientY;
            setSwipeProgress(0);
        }
    }, []);

    const handleTouchMove = useCallback((e: TouchEvent) => {
        if (!tracking.current) return;
        const touch = e.touches[0];
        const dx = touch.clientX - startX.current;
        const dy = Math.abs(touch.clientY - startY.current);

        if (dy > MAX_Y_DRIFT || dx < 0) {
            tracking.current = false;
            setSwipeProgress(0);
            return;
        }

        setSwipeProgress(Math.min(dx / THRESHOLD, 1));
    }, []);

    const handleTouchEnd = useCallback(() => {
        if (tracking.current && swipeProgress >= 1) {
            onBack();
        }
        tracking.current = false;
        setSwipeProgress(0);
    }, [swipeProgress, onBack]);

    useEffect(() => {
        document.addEventListener('touchstart', handleTouchStart, { passive: true });
        document.addEventListener('touchmove', handleTouchMove, { passive: true });
        document.addEventListener('touchend', handleTouchEnd);
        return () => {
            document.removeEventListener('touchstart', handleTouchStart);
            document.removeEventListener('touchmove', handleTouchMove);
            document.removeEventListener('touchend', handleTouchEnd);
        };
    }, [handleTouchStart, handleTouchMove, handleTouchEnd]);

    return swipeProgress;
}
