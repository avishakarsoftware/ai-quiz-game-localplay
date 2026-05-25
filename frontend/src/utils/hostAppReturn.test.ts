import { describe, expect, it } from 'vitest';
import { getHostAppReturnTargetOrigin, shouldNavigateWithinCurrentFrame } from './hostAppReturn';

describe('hostAppReturn', () => {
    it('navigates same-origin LocalPlay returns inside the iframe', () => {
        expect(shouldNavigateWithinCurrentFrame('/revelry/games?party_games_token=abc')).toBe(true);
        expect(shouldNavigateWithinCurrentFrame(`${window.location.origin}/revelry/games?party_games_token=abc`)).toBe(true);
        expect(shouldNavigateWithinCurrentFrame('https://api-gamma.revelryapp.me/party/party-1')).toBe(false);
    });

    it('uses the Revelry parent origin for cross-origin postMessage targets', () => {
        expect(
            getHostAppReturnTargetOrigin(
                'https://gamesapi-gamma.revelryapp.me/revelry/games?party_games_token=abc',
                'https://api-gamma.revelryapp.me/party/party-1',
            ),
        ).toBe('https://api-gamma.revelryapp.me');
    });
});
