import { type GameType, type QuizVariantGameType } from './types';

export interface GameModeConfig {
    id: GameType;
    runtimeType: 'quiz' | 'wmlt' | 'drawing' | 'housie' | 'bingo' | 'musical_chairs' | 'bluff' | 'two_truths' | 'story_chain' | 'common_ground' | 'find_someone' | 'who_am_i' | 'chit_pull' | 'mafia';
    icon: string;
    title: string;
    description: string;
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
        title: 'Chit Pull',
        description: 'Randomly pick a player and a funny question, action, or mini challenge',
    },
    {
        id: 'mafia',
        runtimeType: 'mafia',
        icon: '🕵️',
        title: 'Mafia',
        description: 'Secret roles, night kills, and daytime accusations',
    },
];

export const QUIZ_VARIANT_IDS: QuizVariantGameType[] = [
    'rebus',
    'emoji_charades',
    'fact_fiction',
    'timeline',
    'odd_one_out',
];

export function getGameModeConfig(gameType: GameType): GameModeConfig {
    return GAME_MODE_CONFIGS.find((item) => item.id === gameType) || GAME_MODE_CONFIGS[0];
}

export function filterGameModesForCatalog(catalog: Array<{ id: string; launchable?: boolean }> | undefined): GameModeConfig[] {
    if (!catalog) return GAME_MODE_CONFIGS;
    const allowed = new Set(catalog.filter((item) => item.launchable !== false).map((item) => item.id));
    return GAME_MODE_CONFIGS.filter((item) => allowed.has(item.id));
}

export function isQuizRuntimeGame(gameType: GameType): boolean {
    return getGameModeConfig(gameType).runtimeType === 'quiz';
}

export function runtimeGameType(gameType: GameType): 'quiz' | 'wmlt' | 'drawing' | 'housie' | 'bingo' | 'musical_chairs' | 'bluff' | 'two_truths' | 'story_chain' | 'common_ground' | 'find_someone' | 'who_am_i' | 'chit_pull' | 'mafia' {
    return getGameModeConfig(gameType).runtimeType;
}
