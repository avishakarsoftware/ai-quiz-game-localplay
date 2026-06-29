import { describe, expect, it } from 'vitest';
import { canResetFinishedRoomWithGame } from '../roomReuse';

describe('canResetFinishedRoomWithGame', () => {
    it('allows in-place reset for any game that has a content id', () => {
        expect(canResetFinishedRoomWithGame('quiz', 'quiz-123')).toBe(true);
        expect(canResetFinishedRoomWithGame('wmlt', 'mlt-123')).toBe(true);
        expect(canResetFinishedRoomWithGame('drawing', 'draw-123')).toBe(true);
    });

    it('allows in-place reset for default/config-driven games without a content id', () => {
        expect(canResetFinishedRoomWithGame('musical_chairs')).toBe(true);
        expect(canResetFinishedRoomWithGame('party_quests')).toBe(true);
        expect(canResetFinishedRoomWithGame('bluff')).toBe(true);
        expect(canResetFinishedRoomWithGame('poker')).toBe(true);
        expect(canResetFinishedRoomWithGame('photo_clue')).toBe(true);
    });

    it('allows in-place reset for generic-prompt party games without a content id', () => {
        expect(canResetFinishedRoomWithGame('caption_contest')).toBe(true);
        expect(canResetFinishedRoomWithGame('hot_takes')).toBe(true);
    });

    it('requires a fresh room for content games with no content id', () => {
        expect(canResetFinishedRoomWithGame('quiz')).toBe(false);
        expect(canResetFinishedRoomWithGame('wmlt')).toBe(false);
        expect(canResetFinishedRoomWithGame('drawing')).toBe(false);
        expect(canResetFinishedRoomWithGame('housie')).toBe(false);
        expect(canResetFinishedRoomWithGame('bingo')).toBe(false);
    });
});
