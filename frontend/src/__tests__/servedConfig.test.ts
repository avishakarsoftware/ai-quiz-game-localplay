import { describe, expect, it } from 'vitest';
import servedConfig from '../../public/config.json';

/**
 * `public/config.json` is fetched by the app AND served publicly by the backend at
 * `/config/public`. Anything left in it is therefore advertised to the world, whether or not any
 * code reads it.
 *
 * Real incident (found by the prod regression suite, 2026-08-04): the `pricing` block still
 * carried promo `launch_2026` — badge "LAUNCH DEAL — 2X SPARKS!", 110 sparks for $0.99 — with
 * `expires: 2026-04-30`. It had been expired for three months and was still being served on prod
 * and gamma. The pack it named (110/$0.99) cannot be bought at all; the real ladder is 50/200/500.
 * Retiring the promo earlier had removed the frontend *consumers* but left the *data* in place,
 * which is exactly the kind of half-migration a shape test catches and a unit test does not.
 */
describe('served remote config', () => {
    it('carries no pricing or promo block', () => {
        // Prices and pack sizes are backend/store-authoritative (SPARK_PRODUCTS, RevenueCat
        // store-localised pricing). Anything here is a second source of truth that will drift.
        expect(servedConfig).not.toHaveProperty('pricing');
        expect(JSON.stringify(servedConfig)).not.toMatch(/promo/i);
    });

    it('advertises no price or spark-pack amount anywhere', () => {
        const raw = JSON.stringify(servedConfig);
        expect(raw).not.toMatch(/\$\d/);              // no hardcoded currency
        expect(raw).not.toMatch(/\b110\b|\b55\b/);    // the retired single-pack amounts
    });

    it('has no date that has already passed', () => {
        // A served config with an expired date is advertising something untrue. Catch any future
        // promo/announcement window rotting, not just the one we removed.
        const dates = JSON.stringify(servedConfig).match(/\d{4}-\d{2}-\d{2}T[\d:.]+Z/g) || [];
        const stale = dates.filter((d) => new Date(d).getTime() < Date.now());
        expect(stale, `expired dates in served config: ${stale.join(', ')}`).toEqual([]);
    });

    it('still carries the blocks the app actually reads', () => {
        // Guard against over-deletion: removing the wrong key would silently reset flags.
        for (const key of ['feature_flags', 'economy', 'operations', 'version']) {
            expect(servedConfig).toHaveProperty(key);
        }
    });
});
