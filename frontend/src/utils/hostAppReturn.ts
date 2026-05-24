export const REVELRY_RETURN_MESSAGE = 'revelry.localplay.return_to_parent';

type ReturnOptions = {
    parentOrigin?: string;
};

export function isEmbeddedFrame(): boolean {
    return typeof window !== 'undefined' && Boolean(window.parent && window.parent !== window);
}

export function getHostAppReturnTargetOrigin(returnUrl: string, parentOrigin?: string): string {
    const fallback = new URL(returnUrl, window.location.origin);
    if (!parentOrigin) return fallback.origin;
    try {
        return new URL(parentOrigin, window.location.origin).origin;
    } catch {
        return fallback.origin;
    }
}

export function postReturnToHostApp(returnUrl: string, options: ReturnOptions = {}): boolean {
    if (!isEmbeddedFrame() || !returnUrl) return false;
    const url = new URL(returnUrl, window.location.origin);
    const targetOrigin = getHostAppReturnTargetOrigin(url.toString(), options.parentOrigin);
    window.parent.postMessage({
        type: REVELRY_RETURN_MESSAGE,
        return_url: url.toString(),
    }, targetOrigin);
    return true;
}

export function returnToHostApp(returnUrl: string, options: ReturnOptions = {}): boolean {
    if (!returnUrl) return false;
    const url = new URL(returnUrl, window.location.origin);
    if (postReturnToHostApp(url.toString(), options)) return true;
    window.location.assign(url.toString());
    return true;
}
