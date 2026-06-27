import { describe, expect, it } from 'vitest';
import { getMinPlayers } from '../gameModes';

// These must stay in sync with backend/config.py MIN_*_PLAYERS. The backend is
// authoritative; this guard catches drift in the lobby's Start-button gating.
describe('getMinPlayers', () => {
    it('matches backend minimums for representative games', () => {
        expect(getMinPlayers('quiz')).toBe(1);
        expect(getMinPlayers('mafia')).toBe(6);
        expect(getMinPlayers('common_ground')).toBe(4);
        expect(getMinPlayers('bluff')).toBe(3);
        expect(getMinPlayers('musical_chairs')).toBe(3);
        expect(getMinPlayers('would_you_rather')).toBe(2);
    });

    it('defaults generic-prompt party games to 2', () => {
        expect(getMinPlayers('caption_contest')).toBe(2);
        expect(getMinPlayers('hot_takes')).toBe(2);
    });
});
