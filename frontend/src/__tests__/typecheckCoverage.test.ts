import { readFileSync, readdirSync, existsSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';

/**
 * Guards that every TypeScript file in the repo is actually typechecked by something.
 *
 * Written 2026-08-04 after finding that `frontend/e2e/` — 30 files, the entire Playwright layer —
 * had never been typechecked. `tsconfig.app.json` is `include: ["src"]`, and nothing else covered
 * e2e/, so `npm run build` was blind to it. That hid 7 real errors, the worst being an
 * `options.reloadOnly` branch in liveGameHarness.ts referring to a property its own options type
 * never declared: dead code that could not run, invisible for as long as it existed.
 *
 * Two ways the hole reopens, so two tests:
 *   1. someone adds a new top-level directory of .ts files and no tsconfig includes it;
 *   2. someone "checks types" with bare `tsc --noEmit`, which for THIS repo is a silent no-op —
 *      tsconfig.json has `files: []` and only project references, so it reports nothing at all.
 *      Verified by putting `const x: number = "str"` in src/ and watching `tsc --noEmit` exit 0.
 *      The real gate is `tsc -b`.
 */

/** tsconfigs here carry explanatory comments, so JSON.parse needs them stripped first. */
function readJsonc(path: string): Record<string, unknown> {
    const raw = readFileSync(path, 'utf8')
        .replace(/\/\*[\s\S]*?\*\//g, '')       // block comments
        .replace(/^\s*\/\/.*$/gm, '')           // line comments
        .replace(/,(\s*[}\]])/g, '$1');         // trailing commas left behind
    return JSON.parse(raw) as Record<string, unknown>;
}

function tsFilesUnder(dir: string): string[] {
    if (!existsSync(dir)) return [];
    return readdirSync(dir, { withFileTypes: true }).flatMap((e) => {
        const p = join(dir, e.name);
        if (e.isDirectory()) return e.name === 'node_modules' ? [] : tsFilesUnder(p);
        return /\.tsx?$/.test(e.name) ? [p] : [];
    });
}

describe('typecheck coverage', () => {
    it('every referenced project exists and the solution file references all three', () => {
        const solution = readJsonc('tsconfig.json');
        const refs = (solution.references as Array<{ path: string }>).map((r) => r.path);
        expect(refs.sort()).toEqual([
            './tsconfig.app.json',
            './tsconfig.node.json',
            './tsconfig.test.json',
        ]);
        for (const ref of refs) {
            expect(existsSync(ref), `${ref} is referenced but missing`).toBe(true);
        }
    });

    it('every .ts/.tsx file under src/ and e2e/ is covered by some project', () => {
        const solution = readJsonc('tsconfig.json');
        const refs = (solution.references as Array<{ path: string }>).map((r) => r.path);

        // Collect the include globs of every project, as a coarse prefix check. We are not
        // reimplementing tsc's glob semantics — we only need to know that SOMETHING claims each
        // directory, which is exactly what was false for e2e/.
        const covered: string[] = [];
        for (const ref of refs) {
            const cfg = readJsonc(ref);
            for (const pattern of (cfg.include as string[] | undefined) ?? []) {
                covered.push(pattern.replace(/\/?\*\*?.*$/, '').replace(/\/$/, ''));
            }
        }

        const files = [...tsFilesUnder('src'), ...tsFilesUnder('e2e')];
        expect(files.length, 'found no TS files — the walker is broken, not the config').toBeGreaterThan(50);

        const uncovered = files.filter(
            (f) => !covered.some((c) => c !== '' && (f === c || f.startsWith(`${c}/`))),
        );
        expect(
            uncovered,
            `These files are not covered by any tsconfig project, so type errors in them are `
            + `invisible to \`npm run build\`: ${uncovered.slice(0, 10).join(', ')}`
            + `${uncovered.length > 10 ? ` (+${uncovered.length - 10} more)` : ''}. `
            + 'Add the directory to tsconfig.test.json (test code) or tsconfig.app.json (app code).',
        ).toEqual([]);
    });

    it('the build gate is `tsc -b`, never bare `tsc --noEmit`', () => {
        const scripts = (readJsonc('package.json').scripts ?? {}) as Record<string, string>;
        expect(scripts.build, 'the build script must run `tsc -b`').toContain('tsc -b');

        // Bare `tsc --noEmit` / `tsc` with no -b or -p checks nothing here and reads as if it does.
        const bogus = Object.entries(scripts).filter(([, cmd]) =>
            /(^|&&|;|\|)\s*(npx\s+)?tsc(\s+--noEmit)?\s*($|&&|;|\|)/.test(cmd));
        expect(
            bogus.map(([k]) => k),
            `These scripts run tsc without -b or -p, which for this repo checks NOTHING (tsconfig.json `
            + `has files: [] and only references). Use \`tsc -b\`: ${bogus.map(([k, v]) => `${k}="${v}"`).join(', ')}`,
        ).toEqual([]);
    });
});
