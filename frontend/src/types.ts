export interface Question {
    id: number;
    text: string;
    options: string[];
    answer_index: number;
    image_prompt: string;
    image_url?: string;
}

export interface Quiz {
    quiz_title: string;
    questions: Question[];
}

export interface PlayerInfo {
    nickname: string;
    avatar: string;
}

export interface LeaderboardEntry {
    nickname: string;
    score: number;
    avatar?: string;
    rank_change?: number;
    streak?: number;
}

export interface TeamLeaderboardEntry {
    team: string;
    score: number;
    members: number;
}

export interface GameHistoryEntry {
    room_code: string;
    game_title: string;
    game_type?: GameType;
    total_questions: number;
    player_count: number;
    leaderboard: LeaderboardEntry[];
    team_leaderboard: TeamLeaderboardEntry[];
    completed_at: number;
}

export type GameType = 'quiz' | 'wmlt' | 'drawing';

export interface MLTStatement {
    id: number;
    text: string;
}

export interface MLTGame {
    game_title: string;
    statements: MLTStatement[];
}

export interface DrawingPrompt {
    id: number;
    text: string;
    aliases?: string[];
    difficulty?: 'easy' | 'medium' | 'hard';
}

export interface DrawingGame {
    game_title: string;
    prompts: DrawingPrompt[];
}

export interface DrawOperation {
    kind: 'stroke' | 'clear' | 'undo';
    points?: [number, number][];
    color?: string;
    width?: number;
    seq?: number;
    drawer?: string;
}

export interface PowerUps {
    double_points: boolean;
    fifty_fifty: boolean;
}

export const AVATAR_EMOJIS = [
    '🐶', '🐱', '🐸', '🦊', '🐻', '🐼', '🐨', '🦁',
    '🐯', '🐮', '🐷', '🐵', '🐰', '🐔', '🦋', '🐙',
    '🦈', '🐢', '🦜', '🐝', '🦩', '🐺', '🦉', '🐧',
    '🍕', '🌮', '🍩', '🍦', '🍔', '🧁', '🍿', '🥑',
    '🎸', '🚀', '⚡', '🔥', '🌈', '🎯', '💎', '🎲',
    '🦄', '👾', '🤖', '🎃', '👻', '🧠', '🦖', '🐉',
    '🏀', '⚽', '🎱', '🛹', '🎭', '🎨', '🧊', '💫',
];

export const ANSWER_STYLES = [
    { bg: '#FF3B30', shape: '\u25B2', className: 'answer-red' },   // Red triangle
    { bg: '#007AFF', shape: '\u25C6', className: 'answer-blue' },  // Blue diamond
    { bg: '#FF9500', shape: '\u25CF', className: 'answer-yellow' }, // Orange circle
    { bg: '#34C759', shape: '\u25A0', className: 'answer-green' },  // Green square
];
