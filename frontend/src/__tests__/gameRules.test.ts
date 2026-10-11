import { getMinPlayers } from '../gameModes';
import { LOCAL_GAME_RULES, rulesForGame } from '../gameRules';
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
    it('retain the objective, flow, and scoring when a game adds custom sections', () => {
        for (const [game, rules] of Object.entries(LOCAL_GAME_RULES)) {
            expect(rules.sections.slice(0, 3).map((section) => section.id), game)
                .toEqual(['objective', 'flow', 'scoring']);
            for (const section of rules.sections) expect(section.items.length, `${game}/${section.id}`).toBeGreaterThan(0);
        }
        expect(rulesForGame('mafia')?.sections.map((section) => section.id))
            .toEqual(['objective', 'flow', 'scoring', 'privacy']);
    });

    it('mirror the lobby minimum-player gates', () => {
        for (const gameType of gamesWithNonDefaultMinimums) {
            expect(rulesForGame(gameType)?.player_count?.min).toBe(getMinPlayers(gameType));
        }
    });
});
