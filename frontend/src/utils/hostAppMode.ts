export function isHostAppSurfaceLocation(pathname: string, search: string): boolean {
    if (pathname.startsWith('/revelry/')) return true;
    const params = new URLSearchParams(search);
    return (
        params.get('embed') === '1' ||
        params.has('launch_token') ||
        params.has('party_games_token') ||
        params.has('authoring_token')
    );
}
