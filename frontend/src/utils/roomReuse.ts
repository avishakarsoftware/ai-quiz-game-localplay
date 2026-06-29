import { GENERIC_PROMPT_GAME_IDS } from '../gameModes';
import { type GameType } from '../types';

// Default/config-driven games that can be replayed in-place via RESET_ROOM even
// without a generated content_id, so players still on the final-results screen
// receive ROOM_RESET and move into the next lobby without rescanning.
export const RESETTABLE_DEFAULT_GAME_TYPES = new Set<GameType>([
    'musical_chairs',
    'bluff',
    'poker',
    'two_truths',
    'story_chain',
    'common_ground',
    'find_someone',
    'who_am_i',
    'chit_pull',
    'mafia',
    'party_quests',
    'survey_says',
    'would_you_rather',
    'never_have_i_ever',
    'word_association',
    'acronym',
    'photo_clue',
]);

// Whether a finished room can be reused in place for the next game. Content-based
// games qualify when they have a content id; generic-prompt and the default/
// config-driven games qualify without one. Quiz-family games without a content
// id must go through a fresh /room/create.
export function canResetFinishedRoomWithGame(type: GameType, contentId?: string): boolean {
    if (contentId) return true;
    if ((GENERIC_PROMPT_GAME_IDS as string[]).includes(type)) return true;
    return RESETTABLE_DEFAULT_GAME_TYPES.has(type);
}
