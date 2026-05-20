import { type GameType, type QuizVariantGameType } from './types';

export interface GameModeConfig {
    id: GameType;
    runtimeType: 'quiz' | 'wmlt' | 'drawing';
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
        generateLabel: 'Generate Claims',
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

export function isQuizRuntimeGame(gameType: GameType): boolean {
    return getGameModeConfig(gameType).runtimeType === 'quiz';
}

export function runtimeGameType(gameType: GameType): 'quiz' | 'wmlt' | 'drawing' {
    return getGameModeConfig(gameType).runtimeType;
}
