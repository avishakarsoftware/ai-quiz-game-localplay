/**
 * Mobile app-store links, for surfaces that need to hand a user off to the phone app
 * (SPEC-TV-APP §4b — games the TV can never host, e.g. anything needing a camera).
 *
 * These are deliberately configurable and deliberately allowed to be ABSENT. As of 2026-07-28 the
 * Android app is live on Google Play (v3.1.3, 177 countries) but **iOS has never been submitted** —
 * v3.1.3 (9) sits in App Store Connect undistributed. Rendering an App Store QR for an app nobody
 * can download is worse than rendering nothing: the user scans, gets "app not available", and
 * concludes the product is broken.
 *
 * So: `hasIosApp()` gates the iOS affordance, and it stays false until VITE_IOS_APP_URL is set.
 * Set it at build time once the app is actually live.
 */

export const ANDROID_APP_URL =
    (import.meta.env.VITE_ANDROID_APP_URL as string | undefined)
    || 'https://play.google.com/store/apps/details?id=me.revelryapp.quiz';

/** Empty until the iOS app is actually downloadable — see the note above. */
export const IOS_APP_URL = (import.meta.env.VITE_IOS_APP_URL as string | undefined) || '';

export function hasIosApp(): boolean {
    return IOS_APP_URL.trim().length > 0;
}

export function hasAndroidApp(): boolean {
    return ANDROID_APP_URL.trim().length > 0;
}

/** True when there is at least one real store link to offer. */
export function hasAnyAppStoreLink(): boolean {
    return hasIosApp() || hasAndroidApp();
}
