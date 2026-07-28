import { describe, it, expect } from 'vitest';
import { GAME_MODE_CONFIGS, QUIZ_VARIANT_IDS, GENERIC_PROMPT_GAME_IDS, getMinPlayers, BINGO_FAMILY_IDS } from '../gameModes';
import { LOCAL_GAME_RULES } from '../gameRules';

/**
 * Game-id collision guards.
 *
 * Real incident (2026-07-28): a standalone social-deduction game shipped with the id
 * `odd_one_out`, which was ALREADY a quiz variant ("find the item that breaks the pattern",
 * live since v3.1.3). TypeScript unions dedupe silently, so tsc never complained — and once the
 * backend catalog loaded, the quiz variant's rules modal showed the standalone game's rules
 * (min 3 for a solo-able quiz mode). The standalone game was renamed to `impostor`, then again to `odd_question` when
 * "Impostor" turned out to collide with the well-known teen pass-the-phone game of that name —
 * an id worth keeping free for a faithful build of it (SPEC-PASS-AND-PLAY). These tests
 * make the mistake structurally impossible to repeat.
 */

const SIMPLE_SOCIAL_IDS = ['would_you_rather', 'never_have_i_ever', 'word_association', 'acronym', 'odd_question'] as const;

describe('game id collision guards', () => {
    it('quiz-variant ids never collide with any other game family', () => {
        const others = new Set<string>([
            ...GENERIC_PROMPT_GAME_IDS,
            ...SIMPLE_SOCIAL_IDS,
            // Every non-quiz mode tile is a distinct game surface too.
            ...GAME_MODE_CONFIGS.filter((m) => m.runtimeType !== 'quiz').map((m) => m.id),
        ]);
        for (const variant of QUIZ_VARIANT_IDS) {
            expect(others.has(variant), `quiz variant '${variant}' collides with another game family`).toBe(false);
        }
    });

    it('every mode tile id appears exactly once', () => {
        const ids = GAME_MODE_CONFIGS.map((m) => m.id);
        expect(new Set(ids).size).toBe(ids.length);
    });

    it('every simple-social game has a picker tile with a matching runtime', () => {
        // The odd-question game was fully wired over the wire yet UNREACHABLE from the picker,
        // because nobody added a GAME_MODE_CONFIGS entry. A playable game must be pickable.
        for (const id of SIMPLE_SOCIAL_IDS) {
            const mode = GAME_MODE_CONFIGS.find((m) => m.id === id);
            expect(mode, `'${id}' has no picker tile`).toBeDefined();
            expect(mode!.runtimeType, `'${id}' tile must run its own runtime, not quiz`).toBe(id);
        }
    });

    it('odd_question advertises the enforced 3-player minimum, and the quiz variant stays solo-able', () => {
        expect(getMinPlayers('odd_question')).toBe(3);
        expect(getMinPlayers('odd_one_out')).toBe(1);    // quiz variant → quiz runtime
        expect(LOCAL_GAME_RULES.odd_question?.player_count?.min).toBe(3);
        expect(LOCAL_GAME_RULES.odd_one_out?.player_count?.min).toBe(1);
    });

    it('every occasion bingo has local rules so the modal works before the catalog loads', () => {
        for (const id of ['baby_bingo', 'wedding_bingo', 'holiday_bingo', 'road_trip_bingo'] as const) {
            expect(LOCAL_GAME_RULES[id], `'${id}' missing local rules`).toBeDefined();
        }
    });
});

// Real drift incident (2026-07-28, found by deploying to gamma): Wedding / Holiday / Road Trip
// Bingo shipped in the catalog, but three separate hardcoded lists in GameSelectScreen still said
// ['bingo', 'baby_bingo']. Consequences: the new decks fell out of the Bingo category filter, were
// offered an AI-generation flow they can't use (curated decks only), and stayed visible even with
// ENABLE_BINGO off. All three now derive from BINGO_FAMILY_IDS; these tests keep it that way.
describe('bingo family is derived, not hand-listed', () => {
    it('every tile on the bingo runtime is in BINGO_FAMILY_IDS', () => {
        const fromRuntime = GAME_MODE_CONFIGS.filter((m) => m.runtimeType === 'bingo').map((m) => m.id);
        expect([...BINGO_FAMILY_IDS].sort()).toEqual([...fromRuntime].sort());
        // Guard the specific decks that drifted, so a regression names itself.
        for (const id of ['bingo', 'baby_bingo', 'wedding_bingo', 'holiday_bingo', 'road_trip_bingo']) {
            expect(BINGO_FAMILY_IDS, `'${id}' missing from the bingo family`).toContain(id);
        }
    });

    it('no occasion bingo claims AI generation — they all use curated decks', () => {
        for (const id of BINGO_FAMILY_IDS) {
            const mode = GAME_MODE_CONFIGS.find((m) => m.id === id)!;
            // A curated-deck game must not advertise a prompt-driven AI flow.
            expect(mode.promptTitle, `'${id}' should not offer an AI prompt`).toBeUndefined();
        }
    });

    it('occasion bingos share the base game runtime rather than inventing one', () => {
        // If an occasion deck ever gets its own runtimeType, /room/create would reject it: the
        // backend validator allows game_type 'bingo', and the catalog maps every deck to it.
        for (const id of BINGO_FAMILY_IDS) {
            expect(GAME_MODE_CONFIGS.find((m) => m.id === id)!.runtimeType).toBe('bingo');
        }
    });
});
