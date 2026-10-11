import { describe, expect, it } from 'vitest';
import { hostAppLaunchRequest, matchesHostAppSession, resolvedHostAppSession } from '../hostAppSession';

describe('managed gameplay recovery binding', () => {
    it('requires an exact session and any requested party instead of falling back to a previous room', () => {
        const saved = { hostAppSessionId: 'session-1', hostAppContainerId: 'party-1' };
        expect(matchesHostAppSession(saved, hostAppLaunchRequest(new URLSearchParams('session_id=session-1&party_id=party-1')))).toBe(true);
        for (const query of ['session_id=session-2', 'session_id=session-1&party_id=party-2', 'embed=1']) {
            expect(matchesHostAppSession(saved, hostAppLaunchRequest(new URLSearchParams(query)))).toBe(false);
        }
        expect(matchesHostAppSession({}, hostAppLaunchRequest(new URLSearchParams('session_id=session-1')))).toBe(false);
    });

    it('rejects a resolver response for a different session or party', () => {
        const request = hostAppLaunchRequest(new URLSearchParams('session_id=session-1&party_id=party-1'));
        expect(resolvedHostAppSession({ session_id: 'session-1', external_container_id: 'party-1' }, request)).toEqual({ hostAppSessionId: 'session-1', hostAppContainerId: 'party-1' });
        expect(() => resolvedHostAppSession({ session_id: 'session-2', external_container_id: 'party-1' }, request)).toThrow('Launch session mismatch');
        expect(() => resolvedHostAppSession({ session_id: 'session-1', external_container_id: 'party-2' }, request)).toThrow('Launch session mismatch');
    });
});
