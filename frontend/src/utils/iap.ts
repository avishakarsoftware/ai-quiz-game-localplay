/**
 * RevenueCat native In-App Purchase wrapper (SPEC-IAP §6).
 *
 * The RevenueCat Capacitor plugin is loaded via dynamic import so the web build/tests never require
 * it. Every function is a graceful no-op on web or when the plugin / API key is missing, so the UI
 * can simply hide the native buy button when `isIAPConfigured()` is false.
 *
 * Fulfillment is server-side: after a successful native purchase, RevenueCat posts a webhook to
 * /webhook/revenuecat which credits sparks. The client confirms by polling the balance (see
 * SparkPurchaseModal), so these functions only drive the store transaction, not the credit.
 */
import { getPlatform } from './platform';
import { getDeviceId, getUserProfile } from './storage';
import { SPARK_PACKS, type SparkPack } from './sparkPacks';

type RCPackage = Record<string, unknown>;
interface RCPurchasesModule {
    Purchases: {
        configure(opts: { apiKey: string; appUserID?: string }): Promise<void>;
        logIn(opts: { appUserID: string }): Promise<unknown>;
        logOut(): Promise<unknown>;
        getOfferings(): Promise<unknown>;
        purchasePackage(opts: { aPackage: RCPackage }): Promise<unknown>;
        restorePurchases(): Promise<unknown>;
    };
}

let _module: RCPurchasesModule | null = null;
let _configured = false;

function rcApiKey(): string {
    const platform = getPlatform();
    if (platform === 'ios') return import.meta.env.VITE_REVENUECAT_IOS_KEY || '';
    if (platform === 'android') return import.meta.env.VITE_REVENUECAT_ANDROID_KEY || '';
    return '';
}

/** True when native + an API key is present, i.e. native purchasing can work. */
export function isIAPConfigured(): boolean {
    return getPlatform() !== 'web' && !!rcApiKey();
}

/** appUserID = signed-in user_id if available, else device_id — matches the backend wallet_id. */
function walletAppUserId(): string {
    return getUserProfile()?.id || getDeviceId();
}

async function loadModule(): Promise<RCPurchasesModule | null> {
    if (_module) return _module;
    try {
        // Indirect specifier + @vite-ignore: optional native dependency that may be absent in web
        // builds and not installed at all until the native plugin is added. Kept non-statically
        // analyzable so tsc/Vite don't require it to resolve.
        const spec = '@revenuecat/purchases-capacitor';
        _module = (await import(/* @vite-ignore */ spec)) as unknown as RCPurchasesModule;
        return _module;
    } catch {
        return null;
    }
}

/** Configure RevenueCat once at app start. No-op on web / when unconfigured / on failure. */
export async function initIAP(): Promise<void> {
    if (_configured || !isIAPConfigured()) return;
    const mod = await loadModule();
    if (!mod) return;
    try {
        await mod.Purchases.configure({ apiKey: rcApiKey(), appUserID: walletAppUserId() });
        _configured = true;
    } catch {
        /* leave unconfigured — UI gates on isIAPConfigured()/offerings */
    }
}

/** Tie RevenueCat transactions to the signed-in user wallet. Best-effort. */
export async function iapLogIn(userId: string): Promise<void> {
    if (!userId || !isIAPConfigured()) return;
    const mod = await loadModule();
    if (!mod) return;
    try { await mod.Purchases.logIn({ appUserID: userId }); } catch { /* best-effort */ }
}

/** Revert to the device-scoped wallet on sign-out. Best-effort. */
export async function iapLogOut(): Promise<void> {
    if (!isIAPConfigured()) return;
    const mod = await loadModule();
    if (!mod) return;
    try { await mod.Purchases.logOut(); } catch { /* best-effort */ }
}

// RevenueCat wraps getOfferings() in an extra { offerings: ... } envelope on Capacitor — unwrap it.
function unwrapOfferings(result: unknown): Record<string, unknown> {
    const r = result as Record<string, unknown>;
    return (r?.offerings as Record<string, unknown>) || r || {};
}

function allPackages(offerings: Record<string, unknown>): RCPackage[] {
    const packages: RCPackage[] = [];
    const current = offerings.current as Record<string, unknown> | undefined;
    const all = offerings.all as Record<string, Record<string, unknown>> | undefined;
    const collect = (off?: Record<string, unknown>) => {
        const pkgs = off?.availablePackages as RCPackage[] | undefined;
        if (Array.isArray(pkgs)) packages.push(...pkgs);
    };
    collect(current);
    if (all) Object.values(all).forEach(collect);
    return packages;
}

function productIdOf(pkg: RCPackage): string {
    const product = pkg.product as Record<string, unknown> | undefined;
    return (product?.identifier as string) || (pkg.identifier as string) || '';
}

/** Match a pack to a RevenueCat package by rc id → store id → suffix fallback (warn on suffix). */
function findPackage(packages: RCPackage[], pack: SparkPack): RCPackage | null {
    const wanted = [pack.rcId, `me.revelryapp.quiz.sparks_${pack.sparks}`];
    for (const w of wanted) {
        const exact = packages.find((p) => productIdOf(p) === w);
        if (exact) return exact;
    }
    const suffix = pack.sku.replace('spark_pack_', 'sparks_');
    const loose = packages.find((p) => productIdOf(p).endsWith(suffix) || productIdOf(p).endsWith(`sparks_${pack.sparks}`));
    if (loose) {
        console.warn(`[iap] matched ${pack.sku} by suffix fallback: ${productIdOf(loose)}`);
        return loose;
    }
    return null;
}

/** Localized store price strings keyed by sku, from RevenueCat offerings. Empty on web/failure. */
export async function getNativePrices(): Promise<Record<string, string>> {
    if (!isIAPConfigured()) return {};
    const mod = await loadModule();
    if (!mod) return {};
    try {
        const offerings = unwrapOfferings(await mod.Purchases.getOfferings());
        const packages = allPackages(offerings);
        const prices: Record<string, string> = {};
        for (const pack of SPARK_PACKS) {
            const pkg = findPackage(packages, pack);
            const product = pkg?.product as Record<string, unknown> | undefined;
            const label = (product?.priceString as string) || '';
            if (label) prices[pack.sku] = label;
        }
        return prices;
    } catch {
        return {};
    }
}

export interface NativePurchaseResult {
    status: 'completed' | 'cancelled' | 'error';
    message?: string;
}

/** Drive a native store purchase. Fulfillment (spark credit) happens server-side via webhook. */
export async function buySparksNative(sku: SparkPack['sku']): Promise<NativePurchaseResult> {
    if (!isIAPConfigured()) return { status: 'error', message: 'Purchases not available in this build' };
    const pack = SPARK_PACKS.find((p) => p.sku === sku);
    if (!pack) return { status: 'error', message: 'Unknown pack' };
    const mod = await loadModule();
    if (!mod) return { status: 'error', message: 'Purchases not available in this build' };
    try {
        const offerings = unwrapOfferings(await mod.Purchases.getOfferings());
        const pkg = findPackage(allPackages(offerings), pack);
        if (!pkg) return { status: 'error', message: 'This pack is not available right now' };
        await mod.Purchases.purchasePackage({ aPackage: pkg });
        return { status: 'completed' };
    } catch (e: unknown) {
        const err = e as { code?: number | string; message?: string; userCancelled?: boolean };
        if (err?.userCancelled || err?.code === 1 || String(err?.code) === 'PURCHASE_CANCELLED'
            || /cancel/i.test(err?.message || '')) {
            return { status: 'cancelled' };
        }
        return { status: 'error', message: err?.message || 'Purchase failed' };
    }
}

/** Restore native purchases. Note: consumed consumables are not re-credited (expected). */
export async function restoreNative(): Promise<boolean> {
    if (!isIAPConfigured()) return false;
    const mod = await loadModule();
    if (!mod) return false;
    try {
        await mod.Purchases.restorePurchases();
        return true;
    } catch {
        return false;
    }
}
