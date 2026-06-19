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

export type GameType = 'quiz' | 'wmlt' | 'drawing' | 'housie' | 'bingo' | 'baby_bingo' | 'musical_chairs' | 'bluff' | 'two_truths' | 'story_chain' | 'common_ground' | 'find_someone' | 'who_am_i' | 'chit_pull' | 'mafia' | 'party_quests' | QuizVariantGameType;

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
    auto_advance?: boolean;
    inter_round_seconds?: number;
}

export interface HousiePattern {
    id: string;
    label: string;
    description?: string;
    terminal?: boolean;
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
    music_track_id?: string;
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
    music_track_id?: string;
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

export interface TwoTruthsStatement {
    id: string;
    text: string;
    display_order: number;
    is_lie?: boolean;
}

export interface TwoTruthsSubmission {
    player_id: string;
    statements: TwoTruthsStatement[];
}

export interface TwoTruthsState {
    phase: 'TT_SUBMISSION' | 'TT_VOTING' | 'TT_RESULT' | 'PODIUM' | string;
    config: { game_title?: string; submission_time_seconds?: number; vote_time_seconds?: number };
    players: PlayerInfo[];
    submitted_players: string[];
    submitted_count: number;
    total_players: number;
    current_author_id: string;
    current_round: number;
    total_rounds: number;
    statements: TwoTruthsStatement[];
    votes_count: number;
    scores: Record<string, number>;
    round_result?: {
        author_id: string;
        lie_statement_id: string;
        votes: Record<string, string>;
        vote_tally: Record<string, number>;
        correct_voters: string[];
        fooled_voters: string[];
        author_points: number;
    } | null;
    my_submission?: TwoTruthsSubmission;
    my_vote?: string;
    is_author?: boolean;
}

export interface StorySentence {
    id: string;
    player_id: string;
    text: string;
    position: number;
    created_at: number;
    timed_out?: boolean;
}

export interface StoryChainState {
    phase: 'STORY_TURN' | 'STORY_REVEAL' | 'PODIUM' | string;
    config: {
        game_title?: string;
        starter_prompt?: string;
        tone?: string;
        visibility_mode?: 'full_context' | 'last_sentence_only' | string;
        turn_time_seconds?: number;
        sentence_max_chars?: number;
    };
    players: PlayerInfo[];
    chain_id: string;
    turn_order: string[];
    active_player_id: string;
    current_turn_index: number;
    total_turns: number;
    starter_prompt: string;
    sentences_count: number;
    sentences: StorySentence[];
    deadline?: number | null;
    reveal_index: number;
    scores: Record<string, number>;
    is_active?: boolean;
    visible_context?: string[];
}

export interface CommonGroundTeam {
    id: string;
    name: string;
    player_ids: string[];
}

export interface CommonGroundPrompt {
    id: string;
    text: string;
    category?: string;
}

export interface CommonGroundSubmission {
    id: string;
    team_id: string;
    team_name: string;
    submitted_by: string;
    created_at?: number | null;
    updated_at?: number | null;
    has_submission: boolean;
    vote_count: number;
    text?: string;
}

export interface CommonGroundState {
    phase: 'COMMON_DISCUSSION' | 'COMMON_REVEAL' | 'COMMON_VOTING' | 'COMMON_ROUND_RESULT' | 'PODIUM' | string;
    config: {
        game_title?: string;
        mode?: string;
        team_size?: number;
        rounds?: number;
        discussion_time_seconds?: number;
        vote_time_seconds?: number;
        voting_enabled?: boolean;
        vote_category?: string;
        theme?: string;
    };
    players: PlayerInfo[];
    teams: CommonGroundTeam[];
    round_number: number;
    total_rounds: number;
    prompt: CommonGroundPrompt;
    deadline?: number | null;
    submissions: CommonGroundSubmission[];
    votes_count: number;
    scores: Record<string, number>;
    round_results: Array<{
        round_number: number;
        prompt: CommonGroundPrompt;
        round_scores: Record<string, number>;
        scores: Record<string, number>;
        submissions: CommonGroundSubmission[];
    }>;
    my_team_id?: string;
    my_vote?: string;
    my_submission?: {
        id: string;
        team_id: string;
        text: string;
        submitted_by: string;
        created_at: number;
        updated_at: number;
    } | null;
}

export interface FindSomeoneCell {
    prompt_id: string;
    display: string;
    row: number;
    column: number;
    marked: boolean;
    matched_player_id?: string;
    matched_player_name?: string;
    confirmation_status?: 'unmarked' | 'pending' | 'confirmed' | 'denied' | string;
    request_id?: string;
    free?: boolean;
}

export interface FindSomeoneClaim {
    id: string;
    player_id: string;
    pattern_id: string;
    pattern_label: string;
    accepted_at?: number;
}

export interface FindSomeoneConfirmation {
    id: string;
    requester_id: string;
    matched_player_id: string;
    prompt_id: string;
    display: string;
    created_at?: number;
}

export interface FindSomeoneState {
    phase: 'FIND_ACTIVE' | 'PODIUM' | string;
    config: {
        game_title?: string;
        layout?: 'bingo_5x5_free' | 'bingo_5x5' | 'bingo_4x4' | string;
        confirmation_mode?: 'tap_confirm' | 'honor' | string;
        claim_patterns?: Array<{ id: string; label: string; terminal?: boolean }>;
        round_time_seconds?: number;
    };
    players: PlayerInfo[];
    player_count: number;
    deadline?: number | null;
    accepted_claims: FindSomeoneClaim[];
    claim_log: FindSomeoneClaim[];
    leaderboard: Array<{
        player_id: string;
        rank: number;
        score: number;
        claims: number;
        confirmed_cells: number;
    }>;
    my_card?: {
        card_id: string;
        player_id: string;
        cells: FindSomeoneCell[][];
    } | null;
    my_pending_confirmations?: FindSomeoneConfirmation[];
    my_claimed_patterns?: string[];
}

export interface WhoAmIClue {
    index: number;
    text: string;
    revealed: boolean;
}

export interface WhoAmIGuess {
    guess: string;
    clue_index: number;
    correct: boolean;
    points: number;
    created_at?: number;
}

export interface WhoAmIState {
    phase: 'WHOAMI_ROUND' | 'WHOAMI_REVEAL' | 'PODIUM' | string;
    config: {
        game_title?: string;
        clue_count?: number;
        points_by_clue?: number[];
        max_guesses_per_clue?: number;
    };
    players: PlayerInfo[];
    round_number: number;
    total_rounds: number;
    clue_index: number;
    clues: WhoAmIClue[];
    answer?: string | null;
    category?: string;
    scores: Record<string, number>;
    correct_players: string[];
    guesses_count: number;
    round_revealed: boolean;
    deadline?: number | null;
    my_guesses?: WhoAmIGuess[];
    my_correct?: boolean;
}

export interface WhoAmIRound {
    id: string;
    answer: string;
    aliases?: string[];
    category?: string;
    difficulty?: string;
    clues: string[];
}

export interface WhoAmIGameContent {
    game_title: string;
    theme?: string;
    round_count?: number;
    clues_per_round?: number;
    rounds: WhoAmIRound[];
}

export type ChitPullCategory = 'question' | 'action' | 'funny_face' | 'mini_challenge' | 'group';
export type ChitPullSafeLevel = 'kids' | 'family' | 'work_safe' | 'spicy';

export interface ChitPullChit {
    id: string;
    text: string;
    category: ChitPullCategory;
    safe_level?: ChitPullSafeLevel;
}

export interface ChitPullGameContent {
    game_title: string;
    rounds: number;
    turn_time_seconds?: number;
    safe_level?: ChitPullSafeLevel;
    chits: ChitPullChit[];
}

export interface ChitPullState {
    phase: 'CHIT_READY' | 'CHIT_ACTIVE' | 'CHIT_RESULT' | 'PODIUM' | string;
    config: {
        game_title?: string;
        rounds?: number;
        turn_time_seconds?: number;
        chit_count?: number;
        scoring_enabled?: boolean;
        completion_points?: number;
        bonus_points?: number;
        safe_level?: ChitPullSafeLevel;
    };
    players: PlayerInfo[];
    round_number: number;
    total_rounds: number;
    selected_player_id: string;
    current_chit?: ChitPullChit | null;
    used_chit_ids: string[];
    player_turn_counts: Record<string, number>;
    skips_by_player: Record<string, number>;
    scores: Record<string, number>;
    turn_results: Array<{
        round_number: number;
        player_id: string;
        chit_id: string;
        chit_text?: string;
        category?: ChitPullCategory;
        outcome: 'completed' | 'skipped' | string;
        bonus?: boolean;
        points_awarded: number;
    }>;
    deadline?: number | null;
}

export type MafiaRole = 'villager' | 'detective' | 'doctor' | 'mafia';
export type MafiaWinner = 'town' | 'mafia' | null;

export interface MafiaPlayer {
    nickname: string;
    avatar?: string;
    alive: boolean;
    role?: MafiaRole | null;
    eliminated_round?: number | null;
}

export interface MafiaAction {
    kind: 'mafia_kill' | 'investigate' | 'protect' | 'none' | string;
    eligible_targets: string[];
    submitted_target?: string;
    mafia_teammates?: string[];
    night_read?: {
        prompt_id: string;
        label: string;
        question: string;
        eligible_targets: string[];
        submitted_target?: string;
    };
}

export interface MafiaState {
    phase: 'MAFIA_ROLE_REVEAL' | 'MAFIA_NIGHT' | 'MAFIA_DAY_DISCUSSION' | 'MAFIA_DAY_VOTE' | 'MAFIA_VOTE_RESULT' | 'PODIUM' | string;
    config: {
        game_title?: string;
        theme?: 'classic' | 'werewolf' | 'none' | string;
        night_timer_seconds?: number;
        discussion_timer_seconds?: number;
        vote_timer_seconds?: number;
        role_reveal_seconds?: number;
    };
    round: number;
    players: MafiaPlayer[];
    alive_count: number;
    eliminated_count: number;
    deadline?: number | null;
    vote_progress?: { submitted: number; eligible: number };
    last_night?: {
        round: number;
        killed?: string | null;
        killed_role?: MafiaRole | null;
        saved?: boolean;
        narration?: string;
        night_read_highlights?: Array<{
            prompt_id: string;
            label: string;
            player_id: string;
            count: number;
            total: number;
            tied?: boolean;
        }>;
    } | null;
    last_vote?: {
        round: number;
        tally: Record<string, number>;
        eliminated?: string | null;
        eliminated_role?: MafiaRole | null;
        tied?: boolean;
    } | null;
    winner?: MafiaWinner;
    my_role?: MafiaRole;
    my_action?: MafiaAction;
    my_vote?: string;
    my_investigations?: Array<{ round: number; target: string; result: 'town' | 'mafia' | string }>;
    ghost?: boolean;
}

export interface PartyQuestItem {
    quest_id: string;
    display: string;
    category?: string;
    points: number;
    status: 'open' | 'pending_confirmation' | 'confirmed' | string;
    confirmed_by_player_id?: string;
    confirmed_by_name?: string;
    request_id?: string;
    completed_at?: number | null;
}

export interface PartyQuestConfirmation {
    id: string;
    requester_id: string;
    partner_player_id: string;
    quest_id: string;
    display: string;
    points?: number;
    created_at?: number;
    expires_at?: number;
}

export interface PartyQuestsState {
    phase: 'QUESTS_ACTIVE' | 'QUESTS_FINAL_CALL' | 'QUESTS_REVEAL' | 'PODIUM' | string;
    config: {
        game_title?: string;
        duration_minutes?: number;
        quests_per_player?: number;
        confirmation_mode?: 'tap_confirm' | 'honor' | 'pair_code' | string;
        allow_late_join?: boolean;
        theme?: string;
    };
    players: PlayerInfo[];
    started_at?: number;
    ends_at?: number | null;
    player_count: number;
    completed_count: number;
    pending_count: number;
    leaderboard: Array<{
        player_id: string;
        nickname?: string;
        avatar?: string;
        rank: number;
        score: number;
        completed: number;
        total: number;
        unique_partners: number;
    }>;
    standings: Array<{
        player_id: string;
        nickname?: string;
        avatar?: string;
        rank: number;
        score: number;
        completed: number;
        total: number;
        unique_partners: number;
    }>;
    awards: Array<{ id: string; label: string; player_id: string }>;
    my_board?: PartyQuestItem[];
    my_score?: number;
    incoming_requests?: PartyQuestConfirmation[];
    outgoing_requests?: PartyQuestConfirmation[];
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
