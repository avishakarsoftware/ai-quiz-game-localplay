import { AVATAR_EMOJIS, ANSWER_STYLES } from '../types';

describe('AVATAR_EMOJIS', () => {
    it('contains 56 emojis', () => {
        expect(AVATAR_EMOJIS).toHaveLength(56);
    });

    it('contains no duplicates', () => {
        const unique = new Set(AVATAR_EMOJIS);
        expect(unique.size).toBe(AVATAR_EMOJIS.length);
    });

    it('every entry is a non-empty string', () => {
        AVATAR_EMOJIS.forEach((emoji) => {
            expect(typeof emoji).toBe('string');
            expect(emoji.length).toBeGreaterThan(0);
        });
    });
});

describe('ANSWER_STYLES', () => {
    it('has 4 entries', () => {
        expect(ANSWER_STYLES).toHaveLength(4);
    });

    it('each entry has bg, shape, and className', () => {
        ANSWER_STYLES.forEach((style) => {
            expect(style).toHaveProperty('bg');
            expect(style).toHaveProperty('shape');
            expect(style).toHaveProperty('className');
            expect(typeof style.bg).toBe('string');
            expect(typeof style.shape).toBe('string');
            expect(typeof style.className).toBe('string');
        });
    });

    it('bg values are hex colors', () => {
        ANSWER_STYLES.forEach((style) => {
            expect(style.bg).toMatch(/^#[0-9A-Fa-f]{6}$/);
        });
    });

    it('classNames are unique', () => {
        const names = ANSWER_STYLES.map((s) => s.className);
        expect(new Set(names).size).toBe(names.length);
    });
});
