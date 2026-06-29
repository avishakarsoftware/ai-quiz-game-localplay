import { afterEach, describe, expect, it } from 'vitest';
import { getPlatform, isNativePlatform } from '../platform';

function setCapacitor(value: unknown) {
    (window as unknown as Record<string, unknown>).Capacitor = value;
}

describe('getPlatform', () => {
    afterEach(() => {
        delete (window as unknown as Record<string, unknown>).Capacitor;
    });

    it('returns web when Capacitor is absent', () => {
        expect(getPlatform()).toBe('web');
        expect(isNativePlatform()).toBe(false);
    });

    it('returns web when Capacitor exists but is not native (mobile browser)', () => {
        setCapacitor({ isNativePlatform: () => false, getPlatform: () => 'web' });
        expect(getPlatform()).toBe('web');
        expect(isNativePlatform()).toBe(false);
    });

    it('returns ios on a native iOS app', () => {
        setCapacitor({ isNativePlatform: () => true, getPlatform: () => 'ios' });
        expect(getPlatform()).toBe('ios');
        expect(isNativePlatform()).toBe(true);
    });

    it('returns android on a native Android app', () => {
        setCapacitor({ isNativePlatform: () => true, getPlatform: () => 'android' });
        expect(getPlatform()).toBe('android');
        expect(isNativePlatform()).toBe(true);
    });
});
