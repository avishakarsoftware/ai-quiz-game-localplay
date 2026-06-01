export interface Question {
    id: number;
    text: string;
    options: string[];
    answer_index: number;
    image_prompt: string;
    image_asset_id?: string;
    image_url?: string;
    image_alt?: string;
}

export interface Quiz {
    quiz_title: string;
    questions: Question[];
}

export interface QuizPack {
    id: string;
    owner_wallet_id: string;
    title: string;
    status: string;
    question_count: number;
    created_at: number;
    updated_at: number;
    questions?: Array<{
        id: string;
        position: number;
        question_type: 'multiple_choice' | 'true_false';
        text: string;
        options: string[];
        answer_index: number;
        image_asset_id?: string;
        image_url?: string;
        image_alt?: string;
    }>;
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

export type QuizVariantGameType = 'rebus' | 'emoji_charades' | 'fact_fiction' | 'timeline' | 'odd_one_out';

export type GameType = 'quiz' | 'wmlt' | 'drawing' | 'housie' | 'bingo' | 'baby_bingo' | 'musical_chairs' | 'bluff' | QuizVariantGameType;

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

export interface HousiePattern {
    id: string;
    label: string;
    description?: string;
}

export interface HousieGame {
    game_title: string;
    patterns: HousiePattern[];
    play_mode?: 'beginner' | 'pro';
    caller_mode?: 'manual' | 'auto';
    auto_interval_seconds?: number;
    auto_pause_on_claim?: boolean;
}

export interface BingoDeckItem {
    id: string;
    kind: 'text' | 'emoji' | 'image';
    value: string;
    display: string;
    image_asset_id?: string;
    image_url?: string;
    alt_text?: string;
}

export interface BingoGame {
    game_title: string;
    ruleset?: string;
    layout?: 'bingo_5x5_free' | 'bingo_5x5';
    free_center?: boolean;
    free_center_label?: string;
    deck: BingoDeckItem[];
    patterns: HousiePattern[];
    caller_mode?: 'manual' | 'auto';
    claim_requires_latest_call?: boolean;
}

export type MusicalChairsMusicMode = 'builtin' | 'external';
export type MusicalChairsMusicStyle = 'upbeat' | 'jazzy' | 'suspenseful' | 'retro' | 'tropical';
export type MusicalChairsGameplayMode = 'digital' | 'physical';

export interface MusicalChairsConfig {
    game_title: string;
    gameplay_mode: MusicalChairsGameplayMode;
    music_mode: MusicalChairsMusicMode;
    music_style: MusicalChairsMusicStyle;
    min_music_seconds: number;
    max_music_seconds: number;
    grab_window_seconds: number;
    eliminations_per_round: number;
    auto_stop: boolean;
    intensity_ramp: boolean;
}

export interface MusicalChairsPlayer {
    nickname: string;
    avatar?: string;
}

export interface MusicalChairsState {
    game_title: string;
    phase: string;
    round_number: number;
    total_rounds: number;
    active_players: MusicalChairsPlayer[];
    eliminated_players: Array<MusicalChairsPlayer & { round_number?: number; reaction_ms?: number | null; reason?: string }>;
    grabbed: number;
    chairs: number;
    gameplay_mode: MusicalChairsGameplayMode;
    music_mode: MusicalChairsMusicMode;
    music_style: MusicalChairsMusicStyle;
    grab_window_seconds: number;
    intensity: number;
}

export interface PlayingCard {
    id: string;
    rank?: string;
    suit?: string;
    label?: string;
    color?: 'red' | 'black';
    hidden?: boolean;
}

export interface BluffState {
    phase: 'BLUFF_TURN' | 'BLUFF_CHALLENGE' | 'BLUFF_REVEAL' | 'PODIUM' | string;
    players: string[];
    active_player_id?: string | null;
    required_rank?: string;
    pile_count: number;
    hands: Record<string, { count: number; cards?: PlayingCard[] }>;
    last_claim?: {
        actor_id: string;
        claimed_rank: string;
        claimed_count: number;
        challenger_id?: string;
        truthful?: boolean;
        loser_id?: string;
    } | null;
    revealed_cards: PlayingCard[];
    winners: Array<{ player_id: string; place: number }>;
}

export interface HousieCell {
    kind: 'number' | 'text' | 'emoji' | 'image' | 'free';
    value: number | string;
    display: string;
    sort_value?: number;
    row?: number;
    col?: number;
    id?: string;
    item_id?: string;
    image_asset_id?: string;
    image_url?: string;
    alt_text?: string;
}

export interface HousieTicket {
    id: string;
    player_id: string;
    player_name: string;
    layout: string;
    rows: Array<Array<HousieCell | null>>;
}

export interface HousieWinner {
    pattern_id: string;
    label: string;
    nickname: string;
    called_count: number;
    winning_number?: number | string;
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
