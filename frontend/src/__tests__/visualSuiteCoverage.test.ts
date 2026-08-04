import { readFileSync, readdirSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';

/**
 * Every Playwright spec that takes a screenshot must be run by scripts/visual-regression.sh.
 *
 * Written 2026-08-04. The visual runner executed only `visual-regression.spec.ts`, but two other
 * specs also call `toHaveScreenshot` — bingo-authoring (2 baselines) and drawing-game (2 baselines).
 * Those 4 were therefore never exercised by `npm run test:e2e:visual`, and both specs turned out to
 * be FAILING on master against baselines last refreshed 2026-05-31. The failure was invisible
 * because the thing people run ("the visual suite") genuinely passed.
 *
 * A baseline nobody runs is worse than no baseline: it looks like coverage and provides none.
 */

const RUNNER = '../scripts/visual-regression.sh';

function specsUnder(dir: string): string[] {
    return readdirSync(dir, { withFileTypes: true }).flatMap((e) => {
        const p = join(dir, e.name);
        if (e.isDirectory()) return e.name.endsWith('-snapshots') ? [] : specsUnder(p);
        return e.name.endsWith('.ts') ? [p] : [];
    });
}

describe('visual suite coverage', () => {
    it('every spec taking a screenshot is listed in the visual runner', () => {
        const runner = readFileSync(RUNNER, 'utf8');
        const shooters = specsUnder('e2e').filter((f) => {
            if (!f.endsWith('.spec.ts')) return false;
            return readFileSync(f, 'utf8').includes('toHaveScreenshot');
        });

        expect(shooters.length, 'no screenshot specs found — the walker is broken').toBeGreaterThan(0);

        const missing = shooters.filter((f) => !runner.includes(f));
        expect(
            missing,
            `These specs take screenshots but are not run by scripts/visual-regression.sh, so their `
            + `baselines will rot without anyone noticing: ${missing.join(', ')}. `
            + 'Add them to the VISUAL_SPECS array in that script.',
        ).toEqual([]);
    });

    it('every baseline directory belongs to a spec the runner executes', () => {
        const runner = readFileSync(RUNNER, 'utf8');
        const orphaned = readdirSync('e2e', { withFileTypes: true })
            .filter((e) => e.isDirectory() && e.name.endsWith('-snapshots'))
            .map((e) => e.name.replace('-snapshots', ''))
            .filter((spec) => !runner.includes(`e2e/${spec}`));
        expect(
            orphaned,
            `These baseline directories have no spec in the visual runner: `
            + `${orphaned.map((s) => `e2e/${s}-snapshots`).join(', ')}. `
            + 'Either run the spec in visual-regression.sh or delete the stale baselines.',
        ).toEqual([]);
    });
});
