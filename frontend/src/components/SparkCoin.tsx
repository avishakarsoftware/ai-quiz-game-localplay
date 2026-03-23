import { useId } from 'react';

interface SparkCoinProps {
    size?: number;
}

export default function SparkCoin({ size = 20 }: SparkCoinProps) {
    const gradId = useId();
    return (
        <svg
            width={size}
            height={size}
            viewBox="0 0 32 32"
            fill="none"
            xmlns="http://www.w3.org/2000/svg"
            style={{ display: 'inline-block', verticalAlign: 'middle', overflow: 'visible' }}
        >
            {/* Coin body */}
            <circle cx="16" cy="17" r="12" fill="#B8860B" />
            <circle cx="16" cy="16" r="12" fill={`url(#${gradId})`} />
            <circle cx="16" cy="16" r="9.5" stroke="#B8860B" strokeWidth="0.75" fill="none" opacity="0.5" />

            {/* S emblem */}
            <text
                x="16" y="21"
                textAnchor="middle"
                fontFamily="system-ui, sans-serif"
                fontWeight="800"
                fontSize="14"
                fill="#B8860B"
                opacity="0.6"
            >
                S
            </text>

            {/* 4-point star sparkles */}
            {/* Top-right sparkle (large) */}
            <g transform="translate(29, 2)">
                <path d="M0,-4.5 L0.9,0 L0,4.5 L-0.9,0 Z" fill="#FFF8DC" />
                <path d="M-4.5,0 L0,-0.9 L4.5,0 L0,0.9 Z" fill="#FFF8DC" />
                <animate attributeName="opacity" values="0;1;0" dur="2s" begin="0s" repeatCount="indefinite" />
                <animateTransform attributeName="transform" type="scale" values="0.5;1.2;0.5" dur="2s" begin="0s" repeatCount="indefinite" additive="sum" />
            </g>

            {/* Top-left sparkle */}
            <g transform="translate(3, 4)">
                <path d="M0,-3.2 L0.7,0 L0,3.2 L-0.7,0 Z" fill="#FFD700" />
                <path d="M-3.2,0 L0,-0.7 L3.2,0 L0,0.7 Z" fill="#FFD700" />
                <animate attributeName="opacity" values="0;0.8;0" dur="2.4s" begin="0.8s" repeatCount="indefinite" />
                <animateTransform attributeName="transform" type="scale" values="0.4;1.1;0.4" dur="2.4s" begin="0.8s" repeatCount="indefinite" additive="sum" />
            </g>

            {/* Bottom-left sparkle */}
            <g transform="translate(5, 28)">
                <path d="M0,-2.8 L0.6,0 L0,2.8 L-0.6,0 Z" fill="#FFF8DC" />
                <path d="M-2.8,0 L0,-0.6 L2.8,0 L0,0.6 Z" fill="#FFF8DC" />
                <animate attributeName="opacity" values="0;0.7;0" dur="1.8s" begin="1.3s" repeatCount="indefinite" />
                <animateTransform attributeName="transform" type="scale" values="0.4;1;0.4" dur="1.8s" begin="1.3s" repeatCount="indefinite" additive="sum" />
            </g>

            {/* Right sparkle */}
            <g transform="translate(31, 11)">
                <path d="M0,-3.5 L0.7,0 L0,3.5 L-0.7,0 Z" fill="#FFD700" />
                <path d="M-3.5,0 L0,-0.7 L3.5,0 L0,0.7 Z" fill="#FFD700" />
                <animate attributeName="opacity" values="0;0.9;0" dur="2.2s" begin="0.4s" repeatCount="indefinite" />
                <animateTransform attributeName="transform" type="scale" values="0.4;1.15;0.4" dur="2.2s" begin="0.4s" repeatCount="indefinite" additive="sum" />
            </g>

            {/* Bottom-right sparkle */}
            <g transform="translate(27, 26)">
                <path d="M0,-2.2 L0.5,0 L0,2.2 L-0.5,0 Z" fill="#FFE066" />
                <path d="M-2.2,0 L0,-0.5 L2.2,0 L0,0.5 Z" fill="#FFE066" />
                <animate attributeName="opacity" values="0;0.6;0" dur="2.6s" begin="1.8s" repeatCount="indefinite" />
                <animateTransform attributeName="transform" type="scale" values="0.3;1;0.3" dur="2.6s" begin="1.8s" repeatCount="indefinite" additive="sum" />
            </g>

            <defs>
                <radialGradient id={gradId} cx="0.4" cy="0.35" r="0.65">
                    <stop offset="0%" stopColor="#FFE066" />
                    <stop offset="50%" stopColor="#FFD700" />
                    <stop offset="100%" stopColor="#DAA520" />
                </radialGradient>
            </defs>
        </svg>
    );
}
