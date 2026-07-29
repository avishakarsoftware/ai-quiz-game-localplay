import { type GameType, type GenericPromptGameType, type QuizVariantGameType } from './types';

export interface GameModeConfig {
    id: GameType;
    runtimeType: 'quiz' | 'wmlt' | 'drawing' | 'housie' | 'bingo' | 'musical_chairs' | 'bluff' | 'poker' | 'two_truths' | 'story_chain' | 'common_ground' | 'find_someone' | 'who_am_i' | 'chit_pull' | 'mafia' | 'party_quests' | 'survey_says' | 'would_you_rather' | 'never_have_i_ever' | 'word_association' | 'acronym' | 'photo_clue' | 'odd_question' | 'impostor' | GenericPromptGameType;
    icon: string;
    title: string;
    description: string;
    /** Pass-and-play (SPEC-PASS-AND-PLAY): ONE shared device, host types the seats. */
    passAndPlay?: boolean;
    promptTitle?: string;
    promptSubtitle?: string;
    promptPlaceholder?: string;
    generateLabel?: string;
    mode?: QuizVariantGameType | 'classic';
}

export const GAME_MODE_CONFIGS: GameModeConfig[] = [
    {
        id: 'quiz',
        runtimeType: 'quiz',
        icon: '⚡',
        title: 'AI Quiz',
        description: 'Test knowledge with AI-generated trivia questions',
        mode: 'classic',
    },
    {
        id: 'rebus',
        runtimeType: 'quiz',
        icon: '🧩',
        title: 'Rebus Rush',
        description: 'Decode emoji and symbol clues before the room catches on',
        promptTitle: 'Rebus Rush',
        promptSubtitle: 'Decode emoji and symbol clues before the room catches on.',
        promptPlaceholder: 'Theme, category, or vibe: movies, travel, 90s hits...',
        generateLabel: 'Generate Rebus',
        mode: 'rebus',
    },
    {
        id: 'emoji_charades',
        runtimeType: 'quiz',
        icon: '🎭',
        title: 'Emoji Charades',
        description: 'Guess movies, songs, sayings, and places from emoji clues',
        promptTitle: 'Emoji Charades',
        promptSubtitle: 'Guess movies, songs, sayings, and places from emoji clues.',
        promptPlaceholder: 'Movies, pop songs, vacation spots, office inside jokes...',
        generateLabel: 'Generate Emoji Rounds',
        mode: 'emoji_charades',
    },
    {
        id: 'fact_fiction',
        runtimeType: 'quiz',
        icon: '🕵️',
        title: 'Fact or Fiction',
        description: 'Spot which surprising claims are real',
        promptTitle: 'Fact or Fiction',
        promptSubtitle: 'Spot which surprising claims are real.',
        promptPlaceholder: 'Science myths, history, sports records, office lore...',
        generateLabel: 'Generate Questions',
        mode: 'fact_fiction',
    },
    {
        id: 'timeline',
        runtimeType: 'quiz',
        icon: '⏳',
        title: 'Timeline Twist',
        description: 'Put events, releases, and moments in the right order',
        promptTitle: 'Timeline Twist',
        promptSubtitle: 'Put events, releases, and moments in the right order.',
        promptPlaceholder: 'Tech milestones, movie releases, family history...',
        generateLabel: 'Generate Timeline',
        mode: 'timeline',
    },
    {
        id: 'odd_one_out',
        runtimeType: 'quiz',
        icon: '🔍',
        title: 'Odd One Out',
        description: 'Find the item that breaks the pattern',
        promptTitle: 'Odd One Out',
        promptSubtitle: 'Find the item that breaks the pattern.',
        promptPlaceholder: 'Animals, food, superheroes, world capitals...',
        generateLabel: 'Generate Patterns',
        mode: 'odd_one_out',
    },
    {
        id: 'impostor',
        runtimeType: 'impostor',
        icon: '🎭',
        title: 'Impostor',
        // The pass-and-play badge is the selling point, not a footnote: it answers the single
        // biggest objection to every party app ("my friends won't install anything").
        description: 'One phone, passed around. Everyone knows the secret word except one',
        passAndPlay: true,
    },
    {
        id: 'odd_question',
        runtimeType: 'odd_question',
        icon: '❓',
        title: 'Odd Question',
        description: 'Everyone answers the same question — except one player. Find who got a different one',
    },
    {
        id: 'wmlt',
        runtimeType: 'wmlt',
        icon: '🎯',
        title: 'Most Likely To',
        description: 'Vote on who is most likely to do hilarious things',
    },
    {
        id: 'drawing',
        runtimeType: 'drawing',
        icon: '🎨',
        title: 'Drawing Game',
        description: 'Draw secret prompts while everyone races to guess',
    },
    {
        id: 'housie',
        runtimeType: 'housie',
        icon: '🎱',
        title: 'Housie',
        description: 'Call numbers, check tickets, and claim classic prizes',
    },
    {
        id: 'bingo',
        runtimeType: 'bingo',
        icon: '▦',
        title: 'Bingo',
        description: 'Create custom boards with words, emojis, and photos',
    },
    {
        id: 'baby_bingo',
        runtimeType: 'bingo',
        icon: '🍼',
        title: 'Baby Bingo',
        description: 'A ready-made baby shower board with gifts, moments, and tiny socks',
    },
    {
        id: 'wedding_bingo',
        runtimeType: 'bingo',
        icon: '💍',
        title: 'Wedding Bingo',
        description: 'A ready-made reception board: first dance, bouquet toss, someone crying',
    },
    {
        id: 'holiday_bingo',
        runtimeType: 'bingo',
        icon: '🎄',
        title: 'Holiday Bingo',
        description: 'Ugly sweaters, tangled lights, and the annual leftovers debate',
    },
    {
        id: 'road_trip_bingo',
        runtimeType: 'bingo',
        icon: '🚗',
        title: 'Road Trip Bingo',
        description: 'Wrong turns, playlist arguments, and cows in a field',
    },
    {
        id: 'musical_chairs',
        runtimeType: 'musical_chairs',
        icon: '🎵',
        title: 'Musical Chairs',
        description: 'Music stops, chairs vanish, and the slowest tap is out',
    },
    {
        id: 'bluff',
        runtimeType: 'bluff',
        icon: '🂡',
        title: 'Bluff',
        description: 'Play cards face down, claim a rank, and dare the room to call you',
    },
    {
        id: 'poker',
        runtimeType: 'poker',
        icon: '♠️',
        title: 'Party Poker',
        description: 'No-money quick Hold’em with play chips and showdowns',
    },
    {
        id: 'two_truths',
        runtimeType: 'two_truths',
        icon: '🤥',
        title: 'Two Truths and a Lie',
        description: 'Submit three statements and see who can spot the lie',
    },
    {
        id: 'story_chain',
        runtimeType: 'story_chain',
        icon: '📖',
        title: 'Story Chain',
        description: 'Take turns adding sentences, then reveal the final story',
    },
    {
        id: 'common_ground',
        runtimeType: 'common_ground',
        icon: '🤝',
        title: 'Common Ground',
        description: 'Teams discover shared facts, reveal them, and vote for favorites',
    },
    {
        id: 'find_someone',
        runtimeType: 'find_someone',
        icon: '🔎',
        title: 'Find Someone Who',
        description: 'Social bingo that gets guests talking throughout the party',
    },
    {
        id: 'who_am_i',
        runtimeType: 'who_am_i',
        icon: '❓',
        title: 'Who Am I?',
        description: 'Reveal clues while everyone races to guess the mystery answer',
    },
    {
        id: 'chit_pull',
        runtimeType: 'chit_pull',
        icon: '🎟️',
        title: 'Random Chit',
        description: 'Randomly pick a player and a funny question, action, or mini challenge',
    },
    {
        id: 'mafia',
        runtimeType: 'mafia',
        icon: '🕵️',
        title: 'Mafia',
        description: 'Secret roles, night kills, and daytime accusations',
    },
    {
        id: 'party_quests',
        runtimeType: 'party_quests',
        icon: '🗺️',
        title: 'Party Quests',
        description: 'Complete mingling quests throughout the party',
    },
    {
        id: 'survey_says',
        runtimeType: 'survey_says',
        icon: '📊',
        title: 'Survey Says',
        description: 'Guess the top survey answers before strikes give the other team a steal',
    },
    {
        id: 'caption_contest',
        runtimeType: 'caption_contest',
        icon: '💬',
        title: 'Caption Contest',
        description: 'Write the funniest caption, then vote for the winner',
    },
    {
        id: 'desert_island',
        runtimeType: 'desert_island',
        icon: '🏝️',
        title: 'Desert Island',
        description: 'Pick your survival favorites and vote for the best answers',
    },
    {
        id: 'emoji_story',
        runtimeType: 'emoji_story',
        icon: '😄',
        title: 'Emoji Story',
        description: 'Turn emoji chains into tiny stories and vote',
    },
    {
        id: 'hot_takes',
        runtimeType: 'hot_takes',
        icon: '🔥',
        title: 'Hot Takes',
        description: 'Agree or disagree, then reveal the room split',
    },
    {
        id: 'memory_lane',
        runtimeType: 'memory_lane',
        icon: '🕰️',
        title: 'Memory Lane',
        description: 'Share short memories and vote for the room favorite',
    },
    {
        id: 'one_word_vibes',
        runtimeType: 'one_word_vibes',
        icon: '🔮',
        title: 'One Word Vibes',
        description: 'Describe prompts in one word and see who matches',
    },
    {
        id: 'pitch_battle',
        runtimeType: 'pitch_battle',
        icon: '📣',
        title: 'Pitch Battle',
        description: 'Invent ridiculous ideas and vote for the best pitch',
    },
    {
        id: 'rapid_fire',
        runtimeType: 'rapid_fire',
        icon: '⚡',
        title: 'Rapid Fire',
        description: 'Answer instantly, then reveal matching groups',
    },
    {
        id: 'roast_toast',
        runtimeType: 'roast_toast',
        icon: '🥂',
        title: 'Roast & Toast',
        description: 'Write playful toasts or gentle roasts and vote',
    },
    {
        id: 'this_or_that',
        runtimeType: 'this_or_that',
        icon: '↔️',
        title: 'This or That',
        description: 'Fast either-or choices with room split reveals',
    },
    {
        id: 'would_you_rather',
        runtimeType: 'would_you_rather',
        icon: '⚖️',
        title: 'Would You Rather',
        description: 'Pick between two choices and reveal where the room lands',
    },
    {
        id: 'never_have_i_ever',
        runtimeType: 'never_have_i_ever',
        icon: '🙋',
        title: 'Never Have I Ever',
        description: 'Answer privately, then reveal the group split',
    },
    {
        id: 'word_association',
        runtimeType: 'word_association',
        icon: '💭',
        title: 'Word Association',
        description: 'Match minds by writing the first word that comes up',
    },
    {
        id: 'acronym',
        runtimeType: 'acronym',
        icon: '🔤',
        title: 'Acronym Game',
        description: 'Turn letters into funny phrases and vote for the best',
    },
    {
        id: 'photo_clue',
        runtimeType: 'photo_clue',
        icon: '📸',
        title: 'Photo Clue',
        description: 'Submit a photo clue while everyone guesses the phrase',
    },
];

export const QUIZ_VARIANT_IDS: QuizVariantGameType[] = [
    'rebus',
    'emoji_charades',
    'fact_fiction',
    'timeline',
    'odd_one_out',
];

export const GENERIC_PROMPT_GAME_IDS: GenericPromptGameType[] = [
    'caption_contest',
    'desert_island',
    'emoji_story',
    'hot_takes',
    'memory_lane',
    'one_word_vibes',
    'pitch_battle',
    'rapid_fire',
    'roast_toast',
    'this_or_that',
];

const LOCAL_AI_GENERATION_GAME_IDS: ReadonlySet<GameType> = new Set([
    'quiz',
    ...QUIZ_VARIANT_IDS,
    'wmlt',
    'drawing',
    'who_am_i',
    'chit_pull',
    'party_quests',
]);

export const MOST_POPULAR_GAME_IDS: GameType[] = [
    'quiz',
    'wmlt',
    'drawing',
    'housie',
    'bingo',
    'baby_bingo',
    'musical_chairs',
    'two_truths',
    'story_chain',
    'find_someone',
    'party_quests',
    'bluff',
    'mafia',
    'photo_clue',
];

const MOST_POPULAR_GAME_RANK = new Map<string, number>(
    MOST_POPULAR_GAME_IDS.map((id, index) => [id, index]),
);

export function getGameModeConfig(gameType: GameType): GameModeConfig {
    return GAME_MODE_CONFIGS.find((item) => item.id === gameType) || GAME_MODE_CONFIGS[0];
}

// Minimum players each runtime needs to start, mirroring the backend
// MIN_*_PLAYERS constants (backend/config.py). Keep these in sync — the backend
// is authoritative and rejects an early START, but the lobby uses these to
// disable/explain the Start button so the host never hits that rejection.
const MIN_PLAYERS_BY_RUNTIME: Partial<Record<GameModeConfig['runtimeType'], number>> = {
    quiz: 1,
    wmlt: 2,
    drawing: 2,
    housie: 2,
    bingo: 2,
    musical_chairs: 3,
    bluff: 3,
    poker: 2,
    two_truths: 3,
    story_chain: 3,
    common_ground: 4,
    find_someone: 1,
    who_am_i: 2,
    chit_pull: 3,
    mafia: 6,
    party_quests: 1,
    survey_says: 2,
    would_you_rather: 2,
    never_have_i_ever: 2,
    word_association: 2,
    acronym: 2,
    photo_clue: 2,
    odd_question: 3,
    impostor: 3,
};

// Generic-prompt party games (caption_contest, hot_takes, …) all require 2.
export function getMinPlayers(gameType: GameType): number {
    return MIN_PLAYERS_BY_RUNTIME[getGameModeConfig(gameType).runtimeType] ?? 2;
}

export function isMostPopularGameId(gameType?: string): boolean {
    return Boolean(gameType && MOST_POPULAR_GAME_RANK.has(gameType));
}

export function mostPopularGameRank(gameType?: string): number {
    return gameType && MOST_POPULAR_GAME_RANK.has(gameType)
        ? MOST_POPULAR_GAME_RANK.get(gameType)!
        : Number.MAX_SAFE_INTEGER;
}

export function supportsLocalAiGeneration(gameType: GameType): boolean {
    return LOCAL_AI_GENERATION_GAME_IDS.has(gameType);
}

export function filterGameModesForCatalog(catalog: Array<{ id: string; launchable?: boolean }> | undefined): GameModeConfig[] {
    if (!catalog) return GAME_MODE_CONFIGS;
    const allowed = new Set(catalog.filter((item) => item.launchable !== false).map((item) => item.id));
    return GAME_MODE_CONFIGS.filter((item) => allowed.has(item.id));
}

export function isQuizRuntimeGame(gameType: GameType): boolean {
    return getGameModeConfig(gameType).runtimeType === 'quiz';
}

export function runtimeGameType(gameType: GameType): GameModeConfig['runtimeType'] {
    return getGameModeConfig(gameType).runtimeType;
}

/**
 * Every tile that runs the shared Bingo runtime — the base game plus each occasion deck.
 *
 * DERIVED, never hand-listed. Three separate hardcoded lists (`GAME_CATEGORY_BY_ID`,
 * `hasAiGeneration`, the `ENABLE_BINGO` gate) all said `['bingo', 'baby_bingo']` and none were
 * updated when Wedding / Holiday / Road Trip Bingo shipped — so the new decks fell out of the
 * Bingo category filter, were offered a nonexistent AI-generation flow (they use curated decks),
 * and stayed visible even with bingo disabled. Adding a sixth occasion deck must not require
 * remembering three more places.
 */
export const BINGO_FAMILY_IDS: GameType[] = GAME_MODE_CONFIGS
    .filter((mode) => mode.runtimeType === 'bingo')
    .map((mode) => mode.id);
