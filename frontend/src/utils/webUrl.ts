import { isNativePlatform } from './platform';

/** Guest-facing links must open the public site, including from a native WebView. */
export function publicWebUrl(path: string): string {
    const native = isNativePlatform() || window.location.protocol === 'capacitor:';
    const base = native
        ? import.meta.env.VITE_WEB_URL || 'https://games.revelryapp.me/'
        : `${window.location.origin}${import.meta.env.BASE_URL}`;
    return `${base.replace(/\/?$/, '/')}${path.replace(/^\//, '')}`;
}
