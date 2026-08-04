import { readFileSync, readdirSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';

/**
 * Tailwind utility classes in this app DO NOTHING. This test exists to keep that fact visible
 * and to stop the situation getting worse.
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
 * THAT IS WHY "just enable Tailwind" IS THE DANGEROUS OPTION. Adding the plugin would apply ~1450
 * dormant declarations at once across nearly every screen, changing layout unpredictably and
 * diffing every visual baseline. It needs a human reviewing screenshots, not an unattended flip.
 *
 * Two legitimate paths, both deliberate:
 *   A. Enable the plugin, then review and repair the fallout screen by screen.
 *   B. Remove `@import "tailwindcss"` and the dependency, and strip the dead classes over time.
 *
 * Until one is chosen, this test stops the dead-class count from growing — every new utility class
 * is one more thing to unpick later.
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
});
