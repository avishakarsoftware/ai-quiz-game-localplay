/**
 * Spark pack catalog — mirrors backend config.SPARK_PRODUCTS (SPEC-IAP §4).
 *
 * Single source of truth for the client. Spark amounts and SKUs match the backend exactly so a
 * future VibePix economy merge stays a backend join. Web shows the static `priceLabel`; native
 * overrides it with the localized store price from RevenueCat offerings.
 */
export interface SparkPack {
    sku: 'spark_pack_50' | 'spark_pack_200' | 'spark_pack_500';
    sparks: number;
    priceLabel: string;   // fallback/web price; native replaces with store-localized price
    rcId: string;         // RevenueCat product id
    badge?: string;       // optional UI badge (e.g. "Best value")
}

export const SPARK_PACKS: SparkPack[] = [
    { sku: 'spark_pack_50', sparks: 50, priceLabel: '$1.99', rcId: 'rc_spark_pack_50' },
    { sku: 'spark_pack_200', sparks: 200, priceLabel: '$4.99', rcId: 'rc_spark_pack_200', badge: 'Popular' },
    { sku: 'spark_pack_500', sparks: 500, priceLabel: '$9.99', rcId: 'rc_spark_pack_500', badge: 'Best value' },
];

export const DEFAULT_SPARK_SKU: SparkPack['sku'] = 'spark_pack_50';

/**
 * Per-action spark costs — mirror backend `config.COST_ROOM` / `config.COST_GENERATE`.
 * Used in the purchase modal so pack sizes are meaningful ("what does a spark buy?").
 * If the backend economy changes these, update here too.
 */
export const SPARK_COST_ROOM = 10;
export const SPARK_COST_GENERATE = 1;
