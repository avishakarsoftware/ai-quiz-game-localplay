import { signInWithBackend, fetchUserProfile } from '../auth';

// Mock the api module
vi.mock('../api', () => ({
    apiUrl: (path: string) => `http://test${path}`,
    apiHeaders: () => ({ 'Content-Type': 'application/json' }),
}));

// Mock the storage module
const mockSetSessionToken = vi.fn();
const mockSetUserProfile = vi.fn();
const mockGetDeviceId = vi.fn(() => 'test-device-id');
vi.mock('../storage', () => ({
    setSessionToken: (...args: unknown[]) => mockSetSessionToken(...args),
    setUserProfile: (...args: unknown[]) => mockSetUserProfile(...args),
    getDeviceId: () => mockGetDeviceId(),
    signOut: vi.fn(),
}));

describe('signInWithBackend', () => {
    beforeEach(() => {
        vi.restoreAllMocks();
        mockSetSessionToken.mockClear();
        mockSetUserProfile.mockClear();
    });

    it('returns user and session_token on success', async () => {
        const mockResponse = {
            user: { id: '1', provider: 'google', email: 'test@test.com' },
            session_token: 'tok_123',
        };
        globalThis.fetch = vi.fn().mockResolvedValue({
            ok: true,
            json: () => Promise.resolve(mockResponse),
        });

        const result = await signInWithBackend('google', 'id_token_123');
        expect(result.user.email).toBe('test@test.com');
        expect(result.session_token).toBe('tok_123');
        expect(mockSetSessionToken).toHaveBeenCalledWith('tok_123');
        expect(mockSetUserProfile).toHaveBeenCalledWith(mockResponse.user);
    });

    it('throws on non-ok response', async () => {
        globalThis.fetch = vi.fn().mockResolvedValue({
            ok: false,
            json: () => Promise.resolve({ detail: 'Invalid token' }),
        });

        await expect(signInWithBackend('google', 'bad_token')).rejects.toThrow('Invalid token');
    });

    it('throws on malformed JSON response', async () => {
        globalThis.fetch = vi.fn().mockResolvedValue({
            ok: true,
            json: () => Promise.reject(new Error('Unexpected end of JSON')),
        });

        await expect(signInWithBackend('google', 'token')).rejects.toThrow('Invalid server response');
    });

    it('throws on incomplete response (missing session_token)', async () => {
        globalThis.fetch = vi.fn().mockResolvedValue({
            ok: true,
            json: () => Promise.resolve({ user: { id: '1' } }),
        });

        await expect(signInWithBackend('google', 'token')).rejects.toThrow('Incomplete sign-in response');
    });

    it('throws on incomplete response (missing user)', async () => {
        globalThis.fetch = vi.fn().mockResolvedValue({
            ok: true,
            json: () => Promise.resolve({ session_token: 'tok' }),
        });

        await expect(signInWithBackend('google', 'token')).rejects.toThrow('Incomplete sign-in response');
    });
});

describe('fetchUserProfile', () => {
    beforeEach(() => {
        vi.restoreAllMocks();
    });

    it('returns profile on success', async () => {
        const mockProfile = {
            user: { id: '1', provider: 'google', email: 'test@test.com' },
            entitlement: {},
        };
        globalThis.fetch = vi.fn().mockResolvedValue({
            ok: true,
            json: () => Promise.resolve(mockProfile),
        });

        const result = await fetchUserProfile();
        expect(result?.user.email).toBe('test@test.com');
    });

    it('returns null on non-ok response', async () => {
        globalThis.fetch = vi.fn().mockResolvedValue({
            ok: false,
        });

        const result = await fetchUserProfile();
        expect(result).toBeNull();
    });

    it('returns null on network error', async () => {
        globalThis.fetch = vi.fn().mockRejectedValue(new Error('Network error'));

        const result = await fetchUserProfile();
        expect(result).toBeNull();
    });

    it('returns null on abort (timeout)', async () => {
        globalThis.fetch = vi.fn().mockRejectedValue(new DOMException('Aborted', 'AbortError'));

        const result = await fetchUserProfile();
        expect(result).toBeNull();
    });
});
