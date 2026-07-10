import { getHostAppReturnTargetOrigin, postReturnToHostApp, REVELRY_RETURN_MESSAGE } from '../hostAppReturn';

describe('hostAppReturn', () => {
    const originalParent = window.parent;

    afterEach(() => {
        Object.defineProperty(window, 'parent', {
            value: originalParent,
            configurable: true,
        });
        vi.restoreAllMocks();
    });

    it('derives target origin from Revelry return_url instead of LocalPlay origin', () => {
        expect(getHostAppReturnTargetOrigin('https://api-gamma.revelryapp.me/party/party-1?tab=games')).toBe('https://api-gamma.revelryapp.me');
    });

    it('prefers explicit parent_origin when provided', () => {
        expect(getHostAppReturnTargetOrigin(
            'https://api-gamma.revelryapp.me/party/party-1?tab=games',
            'https://app.revelryapp.me',
        )).toBe('https://app.revelryapp.me');
    });

    it('posts close message to the parent Revelry origin in iframe mode', () => {
        const postMessage = vi.fn();
        Object.defineProperty(window, 'parent', {
            value: { postMessage },
            configurable: true,
        });

        const didPost = postReturnToHostApp('https://api-gamma.revelryapp.me/party/party-1?tab=games');

        expect(didPost).toBe(true);
        expect(postMessage).toHaveBeenCalledWith({
            type: REVELRY_RETURN_MESSAGE,
            return_url: 'https://api-gamma.revelryapp.me/party/party-1?tab=games',
        }, 'https://api-gamma.revelryapp.me');
    });

    it('mirrors the saved content pointer in the message so the host can reconcile without re-navigating', () => {
        const postMessage = vi.fn();
        Object.defineProperty(window, 'parent', {
            value: { postMessage },
            configurable: true,
        });

        const didPost = postReturnToHostApp(
            'https://api-gamma.revelryapp.me/party/party-1?tab=games&localplay_content_id=lp_abc&game_type=party_quests&status=ready',
            { content: { localplay_content_id: 'lp_abc', game_type: 'party_quests', status: 'ready' } },
        );

        expect(didPost).toBe(true);
        expect(postMessage).toHaveBeenCalledWith({
            type: REVELRY_RETURN_MESSAGE,
            return_url: 'https://api-gamma.revelryapp.me/party/party-1?tab=games&localplay_content_id=lp_abc&game_type=party_quests&status=ready',
            content: { localplay_content_id: 'lp_abc', game_type: 'party_quests', status: 'ready' },
        }, 'https://api-gamma.revelryapp.me');
    });
});
