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
    status?: 'connected' | 'reconnecting' | 'offline';
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

export type SimpleSocialGameType = 'would_you_rather' | 'never_have_i_ever' | 'word_association' | 'acronym' | 'odd_question';

export type GenericPromptGameType = 'hot_takes' | 'this_or_that' | 'caption_contest' | 'pitch_battle' | 'roast_toast' | 'desert_island' | 'memory_lane' | 'rapid_fire' | 'one_word_vibes' | 'emoji_story';

/**
 * Pass-and-play games (SPEC-PASS-AND-PLAY): ONE shared device, seats typed by the host, no
 * per-player sockets. Kept as its own alias so the picker can badge the family and so the next
 * pass game is added in one place rather than appended to a long union.
 */
export type PassAndPlayGameType = 'impostor';

export type GameType = 'quiz' | 'wmlt' | 'drawing' | 'housie' | 'bingo' | 'baby_bingo' | 'wedding_bingo' | 'holiday_bingo' | 'road_trip_bingo' | 'musical_chairs' | 'bluff' | 'poker' | 'two_truths' | 'story_chain' | 'common_ground' | 'find_someone' | 'who_am_i' | 'chit_pull' | 'mafia' | 'party_quests' | 'survey_says' | 'photo_clue' | PassAndPlayGameType | GenericPromptGameType | SimpleSocialGameType | QuizVariantGameType;

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

export interface PokerState {
    phase: 'POKER_DECISION' | 'POKER_SHOWDOWN' | 'PODIUM' | string;
    config?: { game_title?: string; variant?: string; starting_stack?: number; ante?: number; decision_time_seconds?: number };
    players: string[];
    stacks: Record<string, number>;
    statuses: Record<string, string>;
    hand_number: number;
    dealer_index?: number;
    community_cards: PlayingCard[];
    hole_cards: Record<string, PlayingCard[]>;
    pot: number;
    decisions: Record<string, 'pending' | 'stay' | 'fold' | string>;
    hand_result?: {
        winner_id?: string;
        winner_ids?: string[];
        payouts?: Record<string, number>;
        pot?: number;
        ranked?: Array<{ player_id: string; place: number; evaluation?: { category?: string } | null }>;
        decisions?: Record<string, string>;
    } | null;
    standings?: Array<{ player_id: string; place: number; stack?: number }>;
    deadline?: number | null;
    your_decision?: string | null;
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

export interface SurveySaysTeam {
    id: string;
    name: string;
    player_ids: string[];
}

export interface SurveySaysAnswer {
    id: string;
    rank: number;
    revealed: boolean;
    text: string;
    points: number;
    aliases?: string[];
}

export interface SurveySaysGuess {
    player_id: string;
    team_id?: string;
    guess: string;
    at?: number;
}

export interface SurveySaysState {
    phase: 'SURVEY_ANSWERING' | 'SURVEY_STEAL' | 'SURVEY_REVEAL' | 'PODIUM' | string;
    config: {
        game_title?: string;
        max_strikes?: number;
        guess_time_seconds?: number;
    };
    players: PlayerInfo[];
    teams: SurveySaysTeam[];
    round_number: number;
    total_rounds: number;
    question: string;
    answers: SurveySaysAnswer[];
    active_team_id?: string | null;
    stealing_team_id?: string | null;
    strikes: number;
    round_bank: number;
    scores: Record<string, number>;
    standings: Array<{ team_id: string; team_name: string; score: number; members: string[]; rank: number }>;
    guesses: SurveySaysGuess[];
    round_results: Array<{ round_number: number; winner_team_id?: string; outcome?: string; bank?: number; scores?: Record<string, number> }>;
    deadline?: number | null;
    my_team_id?: string | null;
}

export interface SimpleSocialStanding {
    player_id: string;
    score: number;
    rank: number;
}

export interface WouldYouRatherState {
    phase: 'WYR_VOTING' | 'WYR_REVEAL' | 'PODIUM' | string;
    game_title?: string;
    current_round_index: number;
    round_count: number;
    prompt?: { id?: string; question: string; option_a: string; option_b: string; category?: string };
    submitted_votes: number;
    scores: Record<string, number>;
    standings?: SimpleSocialStanding[];
    your_vote?: 'A' | 'B';
    result?: { count_a: number; count_b: number; total_votes: number; percent_a: number; percent_b: number; majority?: 'A' | 'B' | null; tie?: boolean };
    votes?: Record<string, 'A' | 'B'>;
    completed_at?: number | null;
}

export interface NeverHaveIEverState {
    phase: 'NHIE_ANSWERING' | 'NHIE_REVEAL' | 'PODIUM' | string;
    game_title?: string;
    current_round_index: number;
    round_count: number;
    prompt?: { id?: string; statement: string; category?: string };
    submitted_answers: number;
    scores: Record<string, number>;
    standings?: SimpleSocialStanding[];
    your_answer?: 'have' | 'never';
    result?: { have_count: number; never_count: number; total_answers: number; have_percent: number; never_percent: number; minority?: string | null; tie?: boolean };
    answers?: Record<string, 'have' | 'never'>;
    completed_at?: number | null;
}

export interface WordAssociationState {
    phase: 'WORD_ASSOC_SUBMITTING' | 'WORD_ASSOC_REVEAL' | 'PODIUM' | string;
    game_title?: string;
    current_round_index: number;
    round_count: number;
    seed?: { id?: string; seed: string; category?: string };
    submitted_count: number;
    scores: Record<string, number>;
    standings?: SimpleSocialStanding[];
    your_submission?: string;
    groups?: Array<{ normalized: string; display: string; count: number; players: Array<{ player_id: string; text: string }> }>;
    submissions?: Record<string, { text: string; normalized: string }>;
    completed_at?: number | null;
}

export interface AcronymState {
    phase: 'ACRONYM_SUBMITTING' | 'ACRONYM_VOTING' | 'ACRONYM_REVEAL' | 'PODIUM' | string;
    game_title?: string;
    current_round_index: number;
    round_count: number;
    prompt?: { id?: string; acronym: string; hint?: string; category?: string };
    submitted_count: number;
    vote_count: number;
    scores: Record<string, number>;
    standings?: SimpleSocialStanding[];
    your_entry_id?: string;
    your_submission?: string;
    your_vote?: string;
    entries?: Array<{ entry_id: string; text: string }>;
    submissions?: Record<string, { entry_id: string; text: string }>;
    votes?: Record<string, string>;
    vote_counts?: Record<string, number>;
    completed_at?: number | null;
}

export interface OddQuestionAnswer {
    player_id: string;
    text: string;
}

/** A pass-and-play seat: a person the host typed in, with NO device, socket or session. */
export interface PassPlaySeat {
    id: string;
    name: string;
    emoji: string;
}

export interface ImpostorTurn {
    order: string[];
    /** Seat id, NOT an index — removing a seat must not shift whose turn it is. */
    current: string;
    completed_rounds: number;
}

export interface ImpostorStanding {
    seat_id: string;
    nickname: string;
    emoji: string;
    score: number;
}

/**
 * Impostor (SPEC-PASS-AND-PLAY §2). One device serves the whole table.
 *
 * `secret_word` and `impostor_id` arrive EMPTY until the round resolves — the clue phase sits
 * face-up on a table, so the backend withholds them rather than trusting the UI to hide them.
 * In-round secrecy is the PrivacyGate's job, not this payload's.
 */
export interface ImpostorState {
    phase: 'IMP_REVEAL_ROLES' | 'IMP_CLUES' | 'IMP_VOTING' | 'IMP_ACCUSED_GUESS' | 'IMP_REVEAL' | 'PODIUM' | string;
    round_number: number;
    total_rounds: number;
    clue_rounds: number;
    seats: PassPlaySeat[];
    turn: ImpostorTurn;
    revealed_to: string[];
    next_unrevealed: string;
    /**
     * Per-seat roles, populated ONLY during IMP_REVEAL_ROLES — the phase where the UI has a
     * PrivacyGate mounted to hold them. Empty in every face-up phase, so a face-up screen can
     * never render a secret even by accident.
     */
    roles: Record<string, { is_impostor: boolean; word: string; hint_mode: boolean }>;
    clues: Array<{ seat_id: string; word: string; round: number }>;
    votes: Record<string, string>;
    accused_id: string;
    outcome: '' | 'impostor_caught' | 'impostor_survived' | 'impostor_guessed' | string;
    standings: ImpostorStanding[];
    secret_word: string;
    impostor_id: string;
    accused_guess: string;
}

export interface OddQuestionState {
    phase: 'ODDQ_ANSWERING' | 'ODDQ_VOTING' | 'ODDQ_REVEAL' | 'PODIUM' | string;
    game_title?: string;
    current_round_index: number;
    round_count: number;
    /**
     * The prompt THIS viewer was given. The backend resolves it per viewer — the odd one out
     * receives a different question and nobody else ever sees it, so this field is deliberately
     * not the same string for every player.
     */
    prompt?: string;
    you_are_odd?: boolean;
    your_answer?: string;
    your_vote?: string;
    answer_count: number;
    vote_count: number;
    player_count: number;
    /** Present from the voting phase onward. */
    answers?: OddQuestionAnswer[];
    standings?: SimpleSocialStanding[];
    round_result?: {
        odd_player_id: string;
        caught: boolean;
        vote_counts: Record<string, number>;
        majority_prompt: string;
        minority_prompt: string;
        answers: Record<string, string>;
        votes: Record<string, string>;
    };
    is_final_round?: boolean;
    /** Host view only — who still owes an answer. Never includes prompts. */
    awaiting?: string[];
}

export type SimpleSocialState = WouldYouRatherState | NeverHaveIEverState | WordAssociationState | AcronymState | OddQuestionState;

export interface GenericPromptEntry {
    entry_id: string;
    // Authorship fields are redacted during blind voting; present at reveal/podium.
    player_id?: string;
    is_mine?: boolean;
    text: string;
    normalized?: string;
    at?: number;
}

export interface GenericPromptState {
    phase: 'GENERIC_CHOICE' | 'GENERIC_SUBMITTING' | 'GENERIC_VOTING' | 'GENERIC_REVEAL' | 'PODIUM' | string;
    game_type: GenericPromptGameType | string;
    game_title?: string;
    mode: 'choice_vote' | 'text_vote' | 'text_group' | string;
    current_round_index: number;
    round_count: number;
    prompt?: { id?: string; prompt: string; hint?: string; options?: string[] };
    submitted_count: number;
    entries?: GenericPromptEntry[];
    scores: Record<string, number>;
    standings?: SimpleSocialStanding[];
    result?: {
        counts?: Record<string, number>;
        winners?: string[];
        total?: number;
        vote_counts?: Record<string, number>;
        total_votes?: number;
        groups?: Array<{ normalized: string; display: string; count: number; players: string[] }>;
    } | null;
    your_choice?: string;
    your_submission?: string;
    your_vote?: string;
    your_entry_id?: string;
    completed_at?: number | null;
}

export interface PhotoClueState {
    phase: 'PHOTO_WAITING_FOR_PHOTO' | 'PHOTO_GUESSING' | 'PHOTO_REVEAL' | 'PODIUM';
    config?: {
        game_title?: string;
        theme?: string;
        photo_time_seconds?: number;
        guess_time_seconds?: number;
        correct_guess_points?: number;
        clue_giver_points?: number;
        allow_late_join?: boolean;
    };
    players?: string[];
    current_round_index: number;
    round_count: number;
    clue_giver_id?: string;
    image_asset_id?: string;
    image_url?: string;
    answer?: string;
    category?: string;
    correct_guessers?: string[];
    guess_count?: number;
    scores?: Record<string, number>;
    deadline?: number | null;
    completed_at?: number | null;
    private_prompts?: Array<{ round_index: number; prompt: { id?: string; answer: string; aliases?: string[]; category?: string; photo_tip?: string } }>;
    secret_prompt?: { id?: string; answer: string; aliases?: string[]; category?: string; photo_tip?: string };
    your_guess?: string;
    your_guess_correct?: boolean;
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
