export type HostAppSessionBinding = {
    hostAppSessionId?: string;
    hostAppContainerId?: string;
};

export function hostAppLaunchRequest(params: URLSearchParams) {
    return {
        token: params.get('launch_token') || '',
        sessionId: params.get('session_id') || '',
        containerId: params.get('party_id') || params.get('external_container_id') || '',
        managed: params.get('embed') === '1' || params.has('launch_token') || params.has('session_id'),
    };
}

// A room code alone must never select a previous party's runtime credential.
export function matchesHostAppSession(saved: HostAppSessionBinding | null, request: ReturnType<typeof hostAppLaunchRequest>): boolean {
    return Boolean(saved?.hostAppSessionId && request.sessionId
        && saved.hostAppSessionId === request.sessionId
        && (!request.containerId || saved.hostAppContainerId === request.containerId));
}

export function resolvedHostAppSession(data: Record<string, unknown>, request: ReturnType<typeof hostAppLaunchRequest>): HostAppSessionBinding {
    const context = (data.launch_context || {}) as Record<string, unknown>;
    const sessionId = String(data.session_id || '');
    const containerId = String(data.external_container_id || context.external_container_id || '');
    if (!sessionId || (request.sessionId && request.sessionId !== sessionId)
        || (request.containerId && request.containerId !== containerId)) {
        throw new Error('Launch session mismatch');
    }
    return { hostAppSessionId: sessionId, hostAppContainerId: containerId };
}

export function consumeHostAppLaunchToken(binding: HostAppSessionBinding): void {
    if (!binding.hostAppSessionId) return;
    const url = new URL(window.location.href);
    url.searchParams.delete('launch_token');
    url.searchParams.set('session_id', binding.hostAppSessionId);
    if (binding.hostAppContainerId) url.searchParams.set('party_id', binding.hostAppContainerId);
    window.history.replaceState(window.history.state, '', `${url.pathname}${url.search}${url.hash}`);
}
