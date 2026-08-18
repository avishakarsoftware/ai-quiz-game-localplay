import { describe, expect, it, vi } from 'vitest';
import { act, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

// Fireworks paints on a <canvas>, and jsdom provides no 2D context — without this the podium
// throws "Cannot read properties of null (reading 'clearRect')" before anything renders.
vi.mock('../../Fireworks', () => ({ default: () => null }));
vi.mock('../../../utils/sound', () => ({ soundManager: { play: vi.fn(), stop: vi.fn() } }));

import PodiumScreen from '../PodiumScreen';
import type { NextGameSuggestion } from '../nextGameSuggestions';

/**
 * The podium's "next game" strip (REVIEW-2026-08 P4). The strip reveals with the rest of the podium
 * actions (revealPhase 4), so these tests advance timers before asserting.
 */

const LEADERBOARD = [
    { nickname: 'Ada', score: 30, avatar: '🦊' },
    { nickname: 'Grace', score: 20, avatar: '🐼' },
];

const SUGGESTIONS: NextGameSuggestion[] = [
    { id: 'wmlt', title: "Who's Most Likely", icon: '🎭', reason: 'Different vibe · starts instantly' },
    { id: 'two_truths', title: 'Two Truths and a Lie', icon: '🤥', reason: 'Starts instantly' },
];

async function renderPodium(props: Partial<React.ComponentProps<typeof PodiumScreen>> = {}) {
    vi.useFakeTimers();
    const result = render(
        <PodiumScreen leaderboard={LEADERBOARD} onPlayAgain={() => {}} {...props} />,
    );
    // Walk past the staged reveal so the actions (and the strip) are mounted.
    await act(async () => { vi.advanceTimersByTime(6000); });
    vi.useRealTimers();
    return result;
}

describe('PodiumScreen next-game strip', () => {
    it('offers the suggested games once the podium has revealed', async () => {
        await renderPodium({ nextGameSuggestions: SUGGESTIONS, onPickNextGame: () => {} });
        expect(screen.getByTestId('next-game-strip')).toBeInTheDocument();
        expect(screen.getByTestId('next-game-wmlt')).toHaveTextContent("Who's Most Likely");
        expect(screen.getByTestId('next-game-two_truths')).toBeInTheDocument();
        expect(screen.getByText(/keep the party going/i)).toBeInTheDocument();
    });

    it('shows each suggestion’s reason, so the pick reads as considered', async () => {
        await renderPodium({ nextGameSuggestions: SUGGESTIONS, onPickNextGame: () => {} });
        expect(screen.getByText('Different vibe · starts instantly')).toBeInTheDocument();
    });

    it('passes the chosen id up', async () => {
        const onPick = vi.fn();
        await renderPodium({ nextGameSuggestions: SUGGESTIONS, onPickNextGame: onPick });
        await userEvent.click(screen.getByTestId('next-game-wmlt'));
        expect(onPick).toHaveBeenCalledWith('wmlt');
    });

    it('hides the strip when there are no suggestions', async () => {
        await renderPodium({ nextGameSuggestions: [], onPickNextGame: () => {} });
        expect(screen.queryByTestId('next-game-strip')).toBeNull();
    });

    it('hides the strip when no handler is supplied (host-app mode)', async () => {
        await renderPodium({ nextGameSuggestions: SUGGESTIONS });
        expect(screen.queryByTestId('next-game-strip')).toBeNull();
    });

    it('keeps Play Again and the full picker as the primary paths', async () => {
        await renderPodium({
            nextGameSuggestions: SUGGESTIONS,
            onPickNextGame: () => {},
            onChooseAnotherGame: () => {},
        });
        expect(screen.getByRole('button', { name: /play again/i })).toBeInTheDocument();
        expect(screen.getByRole('button', { name: /choose another game/i })).toBeInTheDocument();
    });
});
