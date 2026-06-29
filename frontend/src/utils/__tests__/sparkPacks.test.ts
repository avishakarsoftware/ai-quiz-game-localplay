import { describe, expect, it } from 'vitest';
import { SPARK_PACKS, DEFAULT_SPARK_SKU } from '../sparkPacks';

// Mirror of backend config.SPARK_PRODUCTS — must stay in lockstep for a future economy merge.
describe('SPARK_PACKS catalog', () => {
    it('has the three VibePix-aligned tiers with matching sparks/skus/rc-ids', () => {
        expect(SPARK_PACKS.map((p) => [p.sku, p.sparks, p.rcId])).toEqual([
            ['spark_pack_50', 50, 'rc_spark_pack_50'],
            ['spark_pack_200', 200, 'rc_spark_pack_200'],
            ['spark_pack_500', 500, 'rc_spark_pack_500'],
        ]);
    });

    it('default sku is the entry tier', () => {
        expect(DEFAULT_SPARK_SKU).toBe('spark_pack_50');
        expect(SPARK_PACKS.some((p) => p.sku === DEFAULT_SPARK_SKU)).toBe(true);
    });
});
