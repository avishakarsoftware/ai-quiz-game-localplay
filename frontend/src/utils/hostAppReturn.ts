export const REVELRY_RETURN_MESSAGE = 'revelry.localplay.return_to_parent';

// Structured pointer to what LocalPlay just saved, mirrored into the return message so the host app can
// reconcile its state in place (no URL parsing, no navigation). Same values are also on return_url's query
// string for backward compatibility.
export type HostAppReturnContent = {
    localplay_content_id?: string;
    game_type?: string;
    status?: string;
};

type ReturnOptions = {
    parentOrigin?: string;
    content?: HostAppReturnContent;
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

export function shouldNavigateWithinCurrentFrame(returnUrl: string): boolean {
    if (!returnUrl) return false;
    try {
        return new URL(returnUrl, window.location.origin).origin === window.location.origin;
    } catch {
        return false;
    }
}

export function postReturnToHostApp(returnUrl: string, options: ReturnOptions = {}): boolean {
    if (!isEmbeddedFrame() || !returnUrl) return false;
    const url = new URL(returnUrl, window.location.origin);
    const targetOrigin = getHostAppReturnTargetOrigin(url.toString(), options.parentOrigin);
    const message: { type: string; return_url: string; content?: HostAppReturnContent } = {
        type: REVELRY_RETURN_MESSAGE,
        return_url: url.toString(),
    };
    if (options.content) message.content = options.content;
    window.parent.postMessage(message, targetOrigin);
    return true;
}

export function returnToHostApp(returnUrl: string, options: ReturnOptions = {}): boolean {
    if (!returnUrl) return false;
    const url = new URL(returnUrl, window.location.origin);
    if (shouldNavigateWithinCurrentFrame(url.toString())) {
        window.location.assign(url.toString());
        return true;
    }
    if (postReturnToHostApp(url.toString(), options)) return true;
    window.location.assign(url.toString());
    return true;
}
