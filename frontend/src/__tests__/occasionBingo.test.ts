import { describe, it, expect } from 'vitest';
import { GAME_MODE_CONFIGS } from '../gameModes';

/**
 * Occasion Bingo decks (Wedding / Holiday / Road Trip). These are content-only games: they reuse
 * the existing `bingo` runtime, so the thing worth locking down is that they stay wired to that
 * runtime and never drift into needing socket work of their own.
 */
describe('occasion bingo variants', () => {
    const occasions = ['baby_bingo', 'wedding_bingo', 'holiday_bingo', 'road_trip_bingo'];

    it('all reuse the shared bingo runtime', () => {
        for (const id of occasions) {
            const mode = GAME_MODE_CONFIGS.find((m) => m.id === id);
            expect(mode, `${id} missing from GAME_MODE_CONFIGS`).toBeDefined();
            expect(mode!.runtimeType, `${id} must reuse the bingo runtime`).toBe('bingo');
        }
    });

    it('each has its own title, icon and description', () => {
        const modes = occasions.map((id) => GAME_MODE_CONFIGS.find((m) => m.id === id)!);
        expect(new Set(modes.map((m) => m.title)).size).toBe(occasions.length);
        expect(new Set(modes.map((m) => m.icon)).size).toBe(occasions.length);
        expect(new Set(modes.map((m) => m.description)).size).toBe(occasions.length);
    });

    it('no game id is duplicated in the catalog', () => {
        const ids = GAME_MODE_CONFIGS.map((m) => m.id);
        expect(new Set(ids).size).toBe(ids.length);
    });
});
