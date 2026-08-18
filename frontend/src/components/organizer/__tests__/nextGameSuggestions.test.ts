import { describe, expect, it } from 'vitest';

import {
    NEXT_GAME_SUGGESTION_COUNT,
    suggestNextGames,
} from '../nextGameSuggestions';
import { BINGO_FAMILY_IDS, GAME_MODE_CONFIGS, getMinPlayers, runtimeGameType } from '../../../gameModes';
import type { GameType } from '../../../types';

/**
 * Ranking rules for the podium's "next game" strip (REVIEW-2026-08 P4). Pure function, so these are
 * cheap — and the rules encode product judgement worth pinning: a suggestion the group cannot start
 * is worse than no suggestion, and repeating the same kind of game is how a party stops feeling varied.
 */
describe('suggestNextGames', () => {
    it('never suggests the game just played', () => {
        for (const played of ['quiz', 'wmlt', 'two_truths'] as GameType[]) {
            const ids = suggestNextGames(played, 6).map((s) => s.id);
            expect(ids).not.toContain(played);
        }
    });

    it('returns at most the configured count', () => {
        expect(suggestNextGames('quiz', 6).length).toBeLessThanOrEqual(NEXT_GAME_SUGGESTION_COUNT);
    });

    it('only suggests games the current group is big enough for', () => {
        for (const playerCount of [2, 3, 5, 10]) {
            for (const suggestion of suggestNextGames('quiz', playerCount)) {
                expect(getMinPlayers(suggestion.id)).toBeLessThanOrEqual(playerCount);
            }
        }
    });

    it('a two-player group is never offered a game needing more', () => {
        const suggestions = suggestNextGames('quiz', 2);
        for (const s of suggestions) {
            expect(getMinPlayers(s.id)).toBeLessThanOrEqual(2);
        }
    });

    it('prefers a different kind of game than the one just played', () => {
        const played: GameType = 'quiz';
        const previousRuntime = runtimeGameType(played);
        const suggestions = suggestNextGames(played, 8);
        expect(suggestions.length).toBeGreaterThan(0);
        // The top pick must be a change of pace, not more of the same.
        expect(runtimeGameType(suggestions[0].id)).not.toBe(previousRuntime);
    });

    it('never suggests pass-and-play, which needs a seat roster rather than one tap', () => {
        const passAndPlayIds = GAME_MODE_CONFIGS.filter((c) => c.passAndPlay).map((c) => c.id);
        const ids = suggestNextGames('quiz', 8).map((s) => s.id);
        for (const id of passAndPlayIds) expect(ids).not.toContain(id);
    });

    it('gives every suggestion a human reason', () => {
        for (const s of suggestNextGames('quiz', 6)) {
            expect(s.reason.length).toBeGreaterThan(3);
            expect(s.title.length).toBeGreaterThan(0);
            expect(s.icon.length).toBeGreaterThan(0);
        }
    });

    it('is deterministic for the same inputs', () => {
        const a = suggestNextGames('wmlt', 5).map((s) => s.id);
        const b = suggestNextGames('wmlt', 5).map((s) => s.id);
        expect(a).toEqual(b);
    });

    it('returns nothing rather than something unstartable when the group is too small', () => {
        // A one-player "group": almost nothing is startable, and the strip must simply not appear.
        for (const s of suggestNextGames('quiz', 1)) {
            expect(getMinPlayers(s.id)).toBeLessThanOrEqual(1);
        }
    });

    it('never stacks the same family — the Housie/Bingo/Baby-Bingo regression', () => {
        // The first implementation suggested all three bingo-family games at once after a quiz:
        // each was a legitimate "different kind than quiz", so nothing stopped them stacking, and
        // the host was offered three near-identical options.
        const ids = suggestNextGames('quiz', 8).map((s) => s.id);
        const bingoFamilyCount = ids.filter((id) => BINGO_FAMILY_IDS.includes(id)).length;
        expect(bingoFamilyCount).toBeLessThanOrEqual(1);
    });

    it('never offers Housie and Bingo together — the same game to a player', () => {
        // runtimeType alone is the wrong grain: housie and bingo are separate runtimes but one
        // experience, and the visual diff caught them being suggested side by side.
        const ids = suggestNextGames('quiz', 8).map((s) => String(s.id));
        const numberCalling = ids.filter((id) => id === 'housie' || BINGO_FAMILY_IDS.includes(id as never));
        expect(numberCalling.length).toBeLessThanOrEqual(1);
    });

    it('offers three distinct kinds of game, not three flavours of one', () => {
        const suggestions = suggestNextGames('quiz', 8);
        const families = suggestions.map((s) =>
            BINGO_FAMILY_IDS.includes(s.id) ? 'bingo-family' : runtimeGameType(s.id));
        expect(new Set(families).size).toBe(families.length);
    });

    it('respects an explicit available list (catalog gating)', () => {
        const onlyTwo = GAME_MODE_CONFIGS.filter((c) => ['wmlt', 'two_truths'].includes(c.id));
        const ids = suggestNextGames('quiz', 8, onlyTwo).map((s) => s.id);
        expect(new Set(ids)).toEqual(new Set(['wmlt', 'two_truths']));
    });

    it('tolerates an unknown game id instead of throwing', () => {
        expect(() => suggestNextGames('not_a_game' as GameType, 6)).not.toThrow();
        expect(suggestNextGames('not_a_game' as GameType, 6).length).toBeGreaterThan(0);
    });
});
