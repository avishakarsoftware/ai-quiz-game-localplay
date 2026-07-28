import { getMinPlayers } from '../gameModes';
import { rulesForGame } from '../gameRules';
import { type GameType } from '../types';

const gamesWithNonDefaultMinimums: GameType[] = [
    'housie',
    'bingo',
    'baby_bingo',
    'musical_chairs',
    'bluff',
    'two_truths',
    'story_chain',
    'common_ground',
    'who_am_i',
    'chit_pull',
    'mafia',
    'odd_one_out',
];

describe('local fallback rules', () => {
    it('mirror the lobby minimum-player gates', () => {
        for (const gameType of gamesWithNonDefaultMinimums) {
            expect(rulesForGame(gameType)?.player_count?.min).toBe(getMinPlayers(gameType));
        }
    });
});
