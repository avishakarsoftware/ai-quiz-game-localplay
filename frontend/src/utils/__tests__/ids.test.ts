import { randomId } from '../ids';

describe('randomId', () => {
    it('uses crypto.randomUUID when available', () => {
        const originalCrypto = globalThis.crypto;
        Object.defineProperty(globalThis, 'crypto', {
            configurable: true,
            value: { randomUUID: vi.fn(() => 'uuid-from-crypto') },
        });
        expect(randomId()).toBe('uuid-from-crypto');
        Object.defineProperty(globalThis, 'crypto', { configurable: true, value: originalCrypto });
    });

    it('falls back to an RFC4122-shaped id without randomUUID', () => {
        const originalCrypto = globalThis.crypto;
        Object.defineProperty(globalThis, 'crypto', {
            configurable: true,
            value: {
                getRandomValues: vi.fn((bytes: Uint8Array) => {
                    bytes.fill(0xab);
                    return bytes;
                }),
            },
        });
        expect(randomId()).toMatch(/^[a-f0-9]{8}-[a-f0-9]{4}-4[a-f0-9]{3}-[89ab][a-f0-9]{3}-[a-f0-9]{12}$/);
        Object.defineProperty(globalThis, 'crypto', { configurable: true, value: originalCrypto });
    });
});
