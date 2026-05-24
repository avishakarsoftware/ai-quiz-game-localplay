import { useEffect, useRef, useState, type PointerEvent } from 'react';
import { type DrawOperation } from '../types';

interface DrawingCanvasProps {
    ops: DrawOperation[];
    drawable?: boolean;
    onDrawOp?: (op: DrawOperation) => void;
    height?: number;
}

const COLORS = ['#111111', '#ffffff', '#7dd3fc', '#a7f3d0', '#fde68a', '#f0abfc', '#fb7185'];

export default function DrawingCanvas({ ops, drawable = false, onDrawOp, height = 360 }: DrawingCanvasProps) {
    const canvasRef = useRef<HTMLCanvasElement | null>(null);
    const strokeRef = useRef<[number, number][]>([]);
    const [color, setColor] = useState(COLORS[0]);
    const [width, setWidth] = useState(5);

    useEffect(() => {
        const canvas = canvasRef.current;
        if (!canvas) return;
        const ctx = canvas.getContext('2d');
        if (!ctx) return;
        const rect = canvas.getBoundingClientRect();
        const scale = window.devicePixelRatio || 1;
        canvas.width = Math.max(1, Math.floor(rect.width * scale));
        canvas.height = Math.max(1, Math.floor(rect.height * scale));
        ctx.setTransform(scale, 0, 0, scale, 0, 0);
        ctx.clearRect(0, 0, rect.width, rect.height);
        ctx.lineCap = 'round';
        ctx.lineJoin = 'round';
        for (const op of ops) {
            if (op.kind !== 'stroke' || !op.points?.length) continue;
            ctx.strokeStyle = op.color || '#111111';
            ctx.lineWidth = op.width || 5;
            ctx.beginPath();
            op.points.forEach(([x, y], index) => {
                const px = x * rect.width;
                const py = y * rect.height;
                if (index === 0) ctx.moveTo(px, py);
                else ctx.lineTo(px, py);
            });
            ctx.stroke();
        }
    }, [ops]);

    const pointFromEvent = (event: PointerEvent<HTMLCanvasElement>): [number, number] => {
        const rect = event.currentTarget.getBoundingClientRect();
        const x = Math.min(1, Math.max(0, (event.clientX - rect.left) / rect.width));
        const y = Math.min(1, Math.max(0, (event.clientY - rect.top) / rect.height));
        return [Number(x.toFixed(3)), Number(y.toFixed(3))];
    };

    const startStroke = (event: PointerEvent<HTMLCanvasElement>) => {
        if (!drawable) return;
        event.currentTarget.setPointerCapture(event.pointerId);
        strokeRef.current = [pointFromEvent(event)];
    };

    const moveStroke = (event: PointerEvent<HTMLCanvasElement>) => {
        if (!drawable || strokeRef.current.length === 0) return;
        strokeRef.current.push(pointFromEvent(event));
        if (strokeRef.current.length >= 20) flushStroke();
    };

    const flushStroke = () => {
        if (strokeRef.current.length < 2) return;
        onDrawOp?.({ kind: 'stroke', points: strokeRef.current.slice(0, 80), color, width });
        strokeRef.current = strokeRef.current.slice(-1);
    };

    const endStroke = () => {
        if (!drawable) return;
        flushStroke();
        strokeRef.current = [];
    };

    return (
        <div>
            {drawable && (
                <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 10, flexWrap: 'wrap' }}>
                    {COLORS.map((swatch) => (
                        <button
                            key={swatch}
                            type="button"
                            aria-label={`Use color ${swatch}`}
                            onClick={() => setColor(swatch)}
                            style={{
                                width: 30,
                                height: 30,
                                borderRadius: 999,
                                border: swatch === color ? '3px solid var(--accent-primary)' : '1px solid rgba(255,255,255,.35)',
                                background: swatch,
                            }}
                        />
                    ))}
                    <input
                        aria-label="Brush width"
                        type="range"
                        min={2}
                        max={18}
                        value={width}
                        onChange={(event) => setWidth(Number(event.target.value))}
                    />
                    <button type="button" className="btn btn-secondary" onClick={() => onDrawOp?.({ kind: 'clear' })}>Clear</button>
                </div>
            )}
            <canvas
                ref={canvasRef}
                onPointerDown={startStroke}
                onPointerMove={moveStroke}
                onPointerUp={endStroke}
                onPointerCancel={endStroke}
                style={{
                    width: '100%',
                    height,
                    display: 'block',
                    background: 'rgba(255,255,255,.92)',
                    borderRadius: 18,
                    border: '1px solid rgba(255,255,255,.35)',
                    touchAction: 'none',
                    boxShadow: '0 18px 50px rgba(0,0,0,.22)',
                }}
            />
        </div>
    );
}
