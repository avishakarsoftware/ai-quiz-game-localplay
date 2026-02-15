import { useRef, useEffect } from 'react';

interface FireworksProps {
    duration?: number;
    maxRockets?: number;
}

interface Particle {
    x: number;
    y: number;
    vx: number;
    vy: number;
    color: string;
    alpha: number;
    size: number;
    type: 'rocket' | 'spark';
    trail: { x: number; y: number; alpha: number }[];
}

const COLORS = ['#FFD700', '#FF6B6B', '#00E5FF', '#FF4081', '#76FF03', '#FFFFFF', '#FFA500', '#E040FB'];
const GRAVITY = 0.04;
const SPARK_COUNT = 35;

export default function Fireworks({ duration = 12000, maxRockets = 3 }: FireworksProps) {
    const canvasRef = useRef<HTMLCanvasElement>(null);

    useEffect(() => {
        const canvas = canvasRef.current;
        if (!canvas) return;
        const ctx = canvas.getContext('2d')!;
        const particles: Particle[] = [];
        let animId = 0;
        let stopped = false;
        let spawning = true;
        let lastSpawn = 0;

        const resize = () => {
            const parent = canvas.parentElement;
            if (parent) {
                canvas.width = parent.clientWidth;
                canvas.height = parent.clientHeight;
            }
        };
        resize();
        window.addEventListener('resize', resize);

        const spawnRocket = () => {
            const rocketCount = particles.filter(p => p.type === 'rocket').length;
            if (rocketCount >= maxRockets) return;

            particles.push({
                x: canvas.width * (0.15 + Math.random() * 0.7),
                y: canvas.height,
                vx: (Math.random() - 0.5) * 2,
                vy: -(6 + Math.random() * 4),
                color: COLORS[Math.floor(Math.random() * COLORS.length)],
                alpha: 1,
                size: 3,
                type: 'rocket',
                trail: [],
            });
        };

        const explode = (rocket: Particle) => {
            const color = COLORS[Math.floor(Math.random() * COLORS.length)];
            const secondColor = COLORS[Math.floor(Math.random() * COLORS.length)];
            for (let i = 0; i < SPARK_COUNT; i++) {
                const angle = (Math.PI * 2 * i) / SPARK_COUNT + (Math.random() - 0.5) * 0.3;
                const speed = 1.5 + Math.random() * 3.5;
                particles.push({
                    x: rocket.x,
                    y: rocket.y,
                    vx: Math.cos(angle) * speed,
                    vy: Math.sin(angle) * speed,
                    color: i % 3 === 0 ? secondColor : color,
                    alpha: 1,
                    size: 2 + Math.random() * 2,
                    type: 'spark',
                    trail: [],
                });
            }
        };

        const animate = (time: number) => {
            if (stopped) return;
            ctx.clearRect(0, 0, canvas.width, canvas.height);

            // Spawn rockets
            if (spawning && time - lastSpawn > 400 + Math.random() * 600) {
                spawnRocket();
                lastSpawn = time;
            }

            // Update and draw
            for (let i = particles.length - 1; i >= 0; i--) {
                const p = particles[i];
                p.x += p.vx;
                p.y += p.vy;
                p.vy += GRAVITY;

                if (p.type === 'rocket') {
                    // Store trail
                    p.trail.push({ x: p.x, y: p.y, alpha: 0.6 });
                    if (p.trail.length > 8) p.trail.shift();

                    // Draw trail
                    for (const t of p.trail) {
                        ctx.globalAlpha = t.alpha * 0.3;
                        ctx.fillStyle = p.color;
                        ctx.beginPath();
                        ctx.arc(t.x, t.y, 1.5, 0, Math.PI * 2);
                        ctx.fill();
                        t.alpha *= 0.85;
                    }

                    // Explode when velocity turns downward or reaches target height
                    if (p.vy > -1 || p.y < canvas.height * (0.15 + Math.random() * 0.25)) {
                        explode(p);
                        particles.splice(i, 1);
                        continue;
                    }

                    // Draw rocket
                    ctx.globalAlpha = p.alpha;
                    ctx.fillStyle = '#FFFFFF';
                    ctx.beginPath();
                    ctx.arc(p.x, p.y, p.size, 0, Math.PI * 2);
                    ctx.fill();
                } else {
                    // Spark
                    p.alpha -= 0.012;
                    p.vx *= 0.98;
                    p.size *= 0.995;

                    if (p.alpha <= 0) {
                        particles.splice(i, 1);
                        continue;
                    }

                    ctx.globalAlpha = p.alpha;
                    ctx.fillStyle = p.color;
                    ctx.beginPath();
                    ctx.arc(p.x, p.y, p.size, 0, Math.PI * 2);
                    ctx.fill();

                    // Glow effect
                    ctx.globalAlpha = p.alpha * 0.3;
                    ctx.beginPath();
                    ctx.arc(p.x, p.y, p.size * 2.5, 0, Math.PI * 2);
                    ctx.fill();
                }
            }

            ctx.globalAlpha = 1;
            animId = requestAnimationFrame(animate);
        };

        animId = requestAnimationFrame(animate);

        // Stop spawning after duration
        const stopTimer = duration > 0 ? setTimeout(() => { spawning = false; }, duration) : null;

        return () => {
            stopped = true;
            cancelAnimationFrame(animId);
            if (stopTimer) clearTimeout(stopTimer);
            window.removeEventListener('resize', resize);
        };
    }, [duration, maxRockets]);

    return (
        <canvas
            ref={canvasRef}
            style={{
                position: 'absolute',
                inset: 0,
                pointerEvents: 'none',
                zIndex: 10,
            }}
        />
    );
}
