import { publicWebUrl } from '../webUrl';

afterEach(() => {
    delete (window as unknown as Record<string, unknown>).Capacitor;
    vi.unstubAllEnvs();
});

it('uses the public native web URL and normalizes a missing trailing slash', () => {
    (window as unknown as Record<string, unknown>).Capacitor = { isNativePlatform: () => true, getPlatform: () => 'android' };
    vi.stubEnv('VITE_WEB_URL', 'https://gamesapi-gamma.revelryapp.me');
    expect(publicWebUrl('join/ROOM42')).toBe('https://gamesapi-gamma.revelryapp.me/join/ROOM42');
    expect(publicWebUrl('?tv=1&game=housie')).toBe('https://gamesapi-gamma.revelryapp.me/?tv=1&game=housie');
});

it('keeps the deployed browser base path for guest and TV links', () => {
    vi.stubEnv('BASE_URL', '/games/');
    expect(publicWebUrl('/tv/ROOM42')).toBe(`${window.location.origin}/games/tv/ROOM42`);
});
