import { readFileSync, readdirSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';

/**
 * Tailwind utility classes in this app DO NOTHING, with one deliberate exception (see part 3).
 * This test keeps that fact visible and stops the situation getting worse.
 *
 * Discovered 2026-08-04 by the visual-regression work. The setup looks complete but isn't:
 *   - `tailwindcss@^4` IS a devDependency.
 *   - `src/index.css` line 1 IS `@import "tailwindcss";`
 *   - but Tailwind v4 needs EITHER `@tailwindcss/vite` in vite.config.ts OR `@tailwindcss/postcss`,
 *     and NEITHER is installed. So no utilities are ever generated.
 * Verified against the shipped bundle: `.justify-between`, `.flex-col`, `.min-h-dvh`, `.items-center`
 * all appear ZERO times in `dist/assets/*.css`.
 *
 * Measured blast radius: ~1450 utility occurrences across ~49 files, 77 distinct utilities
 * (`flex` x193, `text-center` x76, `mb-4` x66, ...). The app's real styling is the hand-written CSS
 * in index.css, which was tuned to look right WITHOUT these classes.
 *
 * THAT IS WHY "just enable Tailwind" IS THE DANGEROUS OPTION. It was tried and reverted: adding the
 * plugin applied ~1450 dormant declarations at once and diffed 8 of 10 visual baselines, including
 * type sizes on nearly every screen. Layout regressions, not an improvement.
 *
 * WHAT WAS DONE INSTEAD (option C, 2026-08-04): only the *colour* classes were revived, by
 * hand-writing 14 escaped rules in index.css. Those 204 occurrences were the ones whose deadness
 * was a real visual bug — every `text-[--text-tertiary]` rendered at full-strength body colour, so
 * captions, hints and helper text had no hierarchy. Reviving them changed 0.03% of pixels and no
 * layout at all. The remaining ~1450 layout/spacing utilities are still inert and still dead code.
 *
 * So the rule for new code is unchanged: DO NOT add Tailwind utility classes. Style with the
 * hand-written CSS in index.css. The colour shims exist to fix existing damage, not to invite more.
 */

const UTILITY = /\b(flex|flex-col|flex-1|grid|items-\w+|justify-\w+|gap-\d+|p[xytblr]?-\d+|m[xytblr]?-\d+|w-\w+|h-\w+|min-h-\w+|text-\w+|font-\w+|rounded\w*|border\w*|opacity-\d+|absolute|relative|fixed|hidden|block|inline-\w+)\b/g;

/** Baseline measured 2026-08-04. Only ever ratchet this DOWN. */
const BASELINE_OCCURRENCES = 1452;
const TOLERANCE = 40;   // small headroom so unrelated refactors aren't blocked

function walk(dir: string): string[] {
    return readdirSync(dir, { withFileTypes: true }).flatMap((e) => {
        const p = join(dir, e.name);
        if (e.isDirectory()) return e.name === '__tests__' ? [] : walk(p);
        return p.endsWith('.tsx') ? [p] : [];
    });
}

function countUtilities(): number {
    let total = 0;
    for (const file of walk('src')) {
        const classNames = readFileSync(file, 'utf8').match(/className="([^"]*)"/g) || [];
        total += (classNames.join(' ').match(UTILITY) || []).length;
    }
    return total;
}

describe('Tailwind utilities are inert (known, documented)', () => {
    it('no Tailwind plugin is configured, so utilities are not compiled', () => {
        // If this fails, somebody enabled Tailwind. That is fine and welcome — but it changes
        // layout across ~49 files, so review the visual baselines before accepting, then delete
        // this test rather than adjusting it.
        const pkg = readFileSync('package.json', 'utf8');
        const vite = readFileSync('vite.config.ts', 'utf8');
        const enabled = pkg.includes('@tailwindcss/vite')
            || pkg.includes('@tailwindcss/postcss')
            || vite.includes('tailwindcss(');
        expect(
            enabled,
            'Tailwind now appears enabled — verify every visual baseline, then remove this test.',
        ).toBe(false);
    });

    it('the count of dead utility classes is not growing', () => {
        const count = countUtilities();
        expect(
            count,
            `Dead Tailwind utility classes rose to ${count} (baseline ${BASELINE_OCCURRENCES}). `
            + 'These do nothing at runtime. Style with the hand-written CSS in index.css instead, '
            + 'or take one of the two remediation paths in this file\'s header comment.',
        ).toBeLessThanOrEqual(BASELINE_OCCURRENCES + TOLERANCE);
    });

    // Part 3: the arbitrary-value COLOUR classes are the ones deliberately revived by hand-written
    // shims. Two ways for that to rot silently, both of which really happened while doing it:
    //   - a component uses `text-[--foo]` with no matching shim  -> renders as inherited colour
    //   - a shim points at a var that was never declared         -> renders as inherited colour
    // Both look like "the class is applied" in devtools and produce no error anywhere. Hence a test.
    const ARBITRARY_COLOUR = /(?:text|bg|border)-\[--[a-z0-9-]+\]/g;

    function usedColourClasses(): Map<string, string[]> {
        const used = new Map<string, string[]>();
        for (const file of walk('src')) {
            for (const cls of readFileSync(file, 'utf8').match(ARBITRARY_COLOUR) || []) {
                used.set(cls, [...(used.get(cls) || []), file]);
            }
        }
        return used;
    }

    it('every arbitrary-value colour class has a shim rule and a declared variable', () => {
        const css = readFileSync('src/index.css', 'utf8');
        // Shims are written escaped, e.g. `.text-\[--text-tertiary\] { ... }`
        const shimmed = new Set(
            [...css.matchAll(/\.((?:text|bg|border)-)\\\[(--[a-z0-9-]+)\\\]/g)]
                .map((m) => `${m[1]}[${m[2]}]`),
        );
        const declared = new Set([...css.matchAll(/^\s*(--[a-z0-9-]+)\s*:/gm)].map((m) => m[1]));
        const used = usedColourClasses();

        const unshimmed = [...used.keys()].filter((c) => !shimmed.has(c));
        expect(
            unshimmed,
            `These colour classes are used but have no shim rule in index.css, so they render as the `
            + `inherited colour with no error: ${unshimmed.map((c) => `${c} (${used.get(c)![0]})`).join(', ')}. `
            + 'Add a matching `.text-\\[--var\\] { color: var(--var); }` rule, or use a real CSS class.',
        ).toEqual([]);

        // Check the variable named by the CLASS...
        const undeclared = [...used.keys()].filter(
            (c) => !declared.has(c.match(/\[(--[a-z0-9-]+)\]/)![1]),
        );
        expect(
            undeclared,
            `These colour classes reference CSS variables that are never declared: `
            + `${undeclared.map((c) => `${c} (${used.get(c)![0]})`).join(', ')}. `
            + 'Fix the call site to name a real variable — shimming a typo just hides it.',
        ).toEqual([]);

        // ...AND the variable the shim's rule body actually resolves. These can disagree: a shim
        // named `.text-\[--text-tertiary\]` whose body says `var(--text-tertiarry)` renders as the
        // inherited colour while looking correct at the call site. Caught by mutation-testing this
        // very test, which passed the first time round with exactly that bug injected.
        const brokenTargets = [
            ...css.matchAll(/\.(?:text|bg|border)-\\\[(--[a-z0-9-]+)\\\]\s*\{([^}]*)\}/g),
        ].flatMap(([, name, body]) => {
            const target = body.match(/var\((--[a-z0-9-]+)\)/)?.[1];
            if (!target) return [`${name} (shim body has no var() at all)`];
            return declared.has(target) ? [] : [`${name} -> var(${target}) is undeclared`];
        });
        expect(
            brokenTargets,
            `These shim rules in index.css resolve to nothing: ${brokenTargets.join(', ')}. `
            + 'The class applies but paints the inherited colour, silently.',
        ).toEqual([]);
    });

    it('has no shim rules for classes nobody uses', () => {
        const css = readFileSync('src/index.css', 'utf8');
        const shimmed = [...css.matchAll(/\.((?:text|bg|border)-)\\\[(--[a-z0-9-]+)\\\]/g)]
            .map((m) => `${m[1]}[${m[2]}]`);
        const used = usedColourClasses();
        const dead = shimmed.filter((c) => !used.has(c));
        expect(
            dead,
            `index.css has shim rules for colour classes no component uses: ${dead.join(', ')}. `
            + 'Delete them — the shims are a repair for existing usage, not a utility framework.',
        ).toEqual([]);
    });
});
