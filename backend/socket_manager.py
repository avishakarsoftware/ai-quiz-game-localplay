from fastapi import WebSocket, WebSocketDisconnect
from typing import Dict, List, Optional
from datetime import datetime, timezone
import copy
import json
import hmac
import hashlib
import secrets
import time
import asyncio
import logging
import re
import uuid
import httpx
import random

import config
import tokens as token_module
from media_store import media_store
from musical_chairs_engine import choose_eliminated, intensity_for_round, rank_grabs, total_rounds as mc_total_rounds, validate_config as validate_musical_chairs_config
from bluff_engine import (
    PHASE_CHALLENGE as BLUFF_PHASE_CHALLENGE,
    PHASE_PODIUM as BLUFF_PHASE_PODIUM,
    PHASE_REVEAL as BLUFF_PHASE_REVEAL,
    challenge_claim as bluff_challenge_claim,
    continue_after_reveal as bluff_continue_after_reveal,
    create_initial_state as bluff_create_initial_state,
    pass_turn as bluff_pass_turn,
    play_cards as bluff_play_cards,
    private_sync as bluff_private_sync,
    public_sync as bluff_public_sync,
    resolve_unchallenged as bluff_resolve_unchallenged,
    validate_config as validate_bluff_config,
)
from two_truths_engine import (
    PHASE_PODIUM as TT_PHASE_PODIUM,
    create_initial_state as tt_create_initial_state,
    final_standings as tt_final_standings,
    next_author as tt_next_author,
    private_sync as tt_private_sync,
    public_sync as tt_public_sync,
    score_current_round as tt_score_current_round,
    start_reveal as tt_start_reveal,
    submit_statements as tt_submit_statements,
    submit_vote as tt_submit_vote,
    validate_config as validate_two_truths_config,
)
from story_chain_engine import (
    PHASE_PODIUM as STORY_PHASE_PODIUM,
    create_initial_state as story_create_initial_state,
    final_standings as story_final_standings,
    next_reveal_step as story_next_reveal_step,
    private_sync as story_private_sync,
    public_sync as story_public_sync,
    submit_sentence as story_submit_sentence,
    timeout_turn as story_timeout_turn,
    validate_config as validate_story_chain_config,
)
from common_ground_engine import (
    PHASE_PODIUM as COMMON_PHASE_PODIUM,
    add_player_to_team as common_add_player_to_team,
    create_initial_state as common_create_initial_state,
    final_standings as common_final_standings,
    next_round as common_next_round,
    private_sync as common_private_sync,
    public_sync as common_public_sync,
    score_round as common_score_round,
    start_reveal as common_start_reveal,
    start_voting as common_start_voting,
    submit_fact as common_submit_fact,
    submit_vote as common_submit_vote,
    validate_config as validate_common_ground_config,
)
from find_someone_engine import (
    PHASE_PODIUM as FIND_PHASE_PODIUM,
    add_player as find_add_player,
    claim_pattern as find_claim_pattern,
    confirm_match as find_confirm_match,
    create_initial_state as find_create_initial_state,
    final_standings as find_final_standings,
    mark_cell as find_mark_cell,
    private_sync as find_private_sync,
    public_sync as find_public_sync,
    validate_config as validate_find_someone_config,
)
from who_am_i_engine import (
    PHASE_PODIUM as WHOAMI_PHASE_PODIUM,
    create_initial_state as whoami_create_initial_state,
    final_standings as whoami_final_standings,
    next_clue as whoami_next_clue,
    next_round as whoami_next_round,
    private_sync as whoami_private_sync,
    public_sync as whoami_public_sync,
    reveal_answer as whoami_reveal_answer,
    submit_guess as whoami_submit_guess,
    validate_config as validate_who_am_i_config,
)
from chit_pull_engine import (
    PHASE_PODIUM as CHIT_PULL_PHASE_PODIUM,
    complete_turn as chit_pull_complete_turn,
    create_initial_state as chit_pull_create_initial_state,
    draw_turn as chit_pull_draw_turn,
    final_standings as chit_pull_final_standings,
    public_sync as chit_pull_public_sync,
    redraw_chit as chit_pull_redraw_chit,
    redraw_player as chit_pull_redraw_player,
    skip_turn as chit_pull_skip_turn,
    validate_config as validate_chit_pull_config,
)
from mafia_engine import (
    PHASE_DAY_DISCUSSION as MAFIA_PHASE_DAY_DISCUSSION,
    PHASE_DAY_VOTE as MAFIA_PHASE_DAY_VOTE,
    PHASE_NIGHT as MAFIA_PHASE_NIGHT,
    PHASE_PODIUM as MAFIA_PHASE_PODIUM,
    PHASE_ROLE_REVEAL as MAFIA_PHASE_ROLE_REVEAL,
    PHASE_VOTE_RESULT as MAFIA_PHASE_VOTE_RESULT,
    advance_after_role_reveal as mafia_advance_after_role_reveal,
    advance_after_vote_result as mafia_advance_after_vote_result,
    all_living_votes_submitted as mafia_all_living_votes_submitted,
    all_required_night_actions_submitted as mafia_all_required_night_actions_submitted,
    create_initial_state as mafia_create_initial_state,
    force_complete as mafia_force_complete,
    private_sync as mafia_private_sync,
    public_sync as mafia_public_sync,
    resolve_night as mafia_resolve_night,
    resolve_vote as mafia_resolve_vote,
    result_summary as mafia_result_summary,
    start_day_vote as mafia_start_day_vote,
    submit_night_action as mafia_submit_night_action,
    submit_night_read as mafia_submit_night_read,
    submit_vote as mafia_submit_vote,
    validate_config as validate_mafia_config,
)
from party_quests_engine import (
    PHASE_PODIUM as QUESTS_PHASE_PODIUM,
    add_player as quests_add_player,
    apply_confirmation as quests_apply_confirmation,
    complete as quests_complete,
    create_confirmation_request as quests_create_confirmation_request,
    create_initial_state as quests_create_initial_state,
    private_sync as quests_private_sync,
    public_sync as quests_public_sync,
    result_summary as quests_result_summary,
    reveal as quests_reveal,
    start_final_call as quests_start_final_call,
    standings as quests_standings,
    validate_config as validate_party_quests_config,
)
from survey_says_engine import (
    PHASE_PODIUM as SURVEY_PHASE_PODIUM,
    add_player as survey_add_player,
    add_strike as survey_add_strike,
    create_initial_state as survey_create_initial_state,
    force_complete as survey_force_complete,
    next_round as survey_next_round,
    public_sync as survey_public_sync,
    reveal_all as survey_reveal_all,
    reveal_answer as survey_reveal_answer,
    standings as survey_standings,
    submit_guess as survey_submit_guess,
    validate_config as validate_survey_says_config,
)
from generic_prompt_engine import (
    GENERIC_PROMPT_GAME_TYPES,
    PHASE_PODIUM as GENERIC_PHASE_PODIUM,
    add_player as generic_add_player,
    create_initial_state as generic_create_initial_state,
    next_round as generic_next_round,
    public_state as generic_public_state,
    reveal_round as generic_reveal_round,
    standings as generic_standings,
    start_voting as generic_start_voting,
    submit_choice as generic_submit_choice,
    submit_text as generic_submit_text,
    submit_vote as generic_submit_vote,
    validate_config as validate_generic_prompt_config,
)
from would_you_rather_engine import (
    PHASE_PODIUM as WYR_PHASE_PODIUM,
    create_initial_state as wyr_create_initial_state,
    next_round as wyr_next_round,
    public_state as wyr_public_state,
    reveal_round as wyr_reveal_round,
    standings as wyr_standings,
    submit_vote as wyr_submit_vote,
    validate_config as validate_would_you_rather_config,
)
from never_have_i_ever_engine import (
    PHASE_PODIUM as NHIE_PHASE_PODIUM,
    create_initial_state as nhie_create_initial_state,
    next_round as nhie_next_round,
    public_state as nhie_public_state,
    reveal_round as nhie_reveal_round,
    standings as nhie_standings,
    submit_answer as nhie_submit_answer,
    validate_config as validate_never_have_i_ever_config,
)
from word_association_engine import (
    PHASE_PODIUM as WORD_PHASE_PODIUM,
    create_initial_state as word_create_initial_state,
    next_round as word_next_round,
    public_state as word_public_state,
    reveal_round as word_reveal_round,
    standings as word_standings,
    submit_word as word_submit_word,
    validate_config as validate_word_association_config,
)
from acronym_engine import (
    PHASE_PODIUM as ACRO_PHASE_PODIUM,
    create_initial_state as acro_create_initial_state,
    next_round as acro_next_round,
    public_state as acro_public_state,
    reveal_round as acro_reveal_round,
    standings as acro_standings,
    start_voting as acro_start_voting,
    submit_expansion as acro_submit_expansion,
    submit_vote as acro_submit_vote,
    validate_config as validate_acronym_config,
)
from photo_clue_engine import (
    PHASE_PODIUM as PHOTO_PHASE_PODIUM,
    create_initial_state as photo_create_initial_state,
    next_round as photo_next_round,
    private_prompt_for_player as photo_private_prompt_for_player,
    public_state as photo_public_state,
    reveal_round as photo_reveal_round,
    submit_guess as photo_submit_guess,
    submit_photo as photo_submit_photo,
    validate_config as validate_photo_clue_config,
)
from poker_engine import (
    PHASE_PODIUM as POKER_PHASE_PODIUM,
    create_initial_state as poker_create_initial_state,
    public_sync as poker_public_sync,
    reveal_hand as poker_reveal_hand,
    start_next_hand as poker_start_next_hand,
    submit_decision as poker_submit_decision,
    validate_config as validate_poker_config,
)
from bingo_engine import (
    BINGO_PATTERN_ORDER,
    create_bingo_call_deck,
    generate_bingo_card,
    validate_bingo_claim,
)
from housie_engine import (
    PATTERN_ORDER,
    create_call_deck,
    generate_ticket,
    validate_claim,
)

logger = logging.getLogger(__name__)


class Room:
    def __init__(self, room_code: str, game_data: dict, time_limit: int = 15,
                 organizer_token: str = "", content_id: str = "",
                 game_type: str = "quiz", billing_mode: str = "localplay_sparks"):
        self.room_code = room_code
        self.quiz = game_data  # generic game content (quiz or WMLT)
        self.content_id = content_id
        self.game_type = game_type  # "quiz", "wmlt", "drawing", "housie", "bingo", or standalone runtimes
        self.time_limit = time_limit
        self.organizer_token = organizer_token  # secret token for organizer auth
        self.players: Dict[str, dict] = {}  # socket_id -> {nickname, score, prev_rank, streak, ...}
        self.organizer: Optional[WebSocket] = None
        self.organizer_id: Optional[str] = None
        self.spectators: Dict[str, WebSocket] = {}  # client_id -> ws
        self.state = "LOBBY"  # LOBBY, INTRO, QUESTION, LEADERBOARD, PODIUM
        self.current_question_index = -1
        self.question_start_time: float = 0
        self.answered_players: set = set()
        self.connections: Dict[str, WebSocket] = {}
        self.timer_task: Optional[asyncio.Task] = None
        self.previous_leaderboard: List[dict] = []
        self.lock = asyncio.Lock()
        self.last_activity = time.time()
        self.wallet_id: Optional[str] = None  # organizer's wallet for spark charges
        self.billing_mode = billing_mode
        self._organizer_just_disconnected = False  # flag for post-disconnect notification
        self._player_event: Optional[tuple] = None  # ('left'|'disconnected'|'reconnected', nickname)
        self.disconnected_players: Dict[str, dict] = {}  # nickname -> {score, prev_rank, streak}
        self.answer_log: List[dict] = []  # game history: per-question answer records
        # WS rate limiting: client_id -> list of timestamps
        self.msg_timestamps: Dict[str, list] = {}
        self._organizer_cleanup_task: Optional[asyncio.Task] = None
        # Team mode
        self.teams: Dict[str, str] = {}  # nickname -> team_name
        # Power-ups
        self.power_ups: Dict[str, dict] = {}  # nickname -> {double_points: bool, fifty_fifty: bool}
        # Session tokens for nickname ownership
        self.player_tokens: Dict[str, str] = {}  # nickname -> session_token
        # Bonus rounds
        self.bonus_questions: set = set()  # indices of bonus round questions (2x points)
        self.locked: bool = False  # True = no new players can join
        # WMLT voting state
        self.votes: Dict[str, str] = {}  # nickname -> voted_for_nickname (per-round)
        self.show_votes: bool = True  # Show vote breakdown after each round
        self.mlt_round_history: List[dict] = []  # per-round vote data for superlatives
        # DrawingGame state
        self.drawer_order: List[str] = []
        self.current_drawer: str = ""
        self.correct_guessers: set = set()
        self.drawing_ops: List[dict] = []
        self.guess_log: List[dict] = []
        self.draw_op_timestamps: Dict[str, list] = {}
        self.drawing_auto_advance: bool = bool(game_data.get("auto_advance", True)) if game_type == "drawing" else True
        self.drawing_inter_round_seconds: int = int(game_data.get("inter_round_seconds") or 5) if game_type == "drawing" else 5
        self.drawing_auto_task: Optional[asyncio.Task] = None
        # Housie state
        self.housie_deck: List[dict] = []
        self.housie_called: List[dict] = []
        self.housie_tickets: Dict[str, dict] = {}  # nickname -> ticket
        self.housie_winners: List[dict] = []
        self.housie_claimed_patterns: set = set()
        self.housie_claim_log: List[dict] = []
        self.housie_play_mode: str = str(game_data.get("play_mode") or "beginner").lower()
        self.housie_caller_mode: str = str(game_data.get("caller_mode") or "manual").lower()
        self.housie_auto_status: str = "stopped"
        self.housie_auto_interval_seconds: int = int(game_data.get("auto_interval_seconds") or 8)
        self.housie_auto_pause_on_claim: bool = bool(game_data.get("auto_pause_on_claim", True))
        self.housie_next_auto_call_at: Optional[str] = None
        self.housie_auto_task: Optional[asyncio.Task] = None
        # Musical Chairs state
        self.mc_config = validate_musical_chairs_config(game_data) if game_type == "musical_chairs" else {}
        self.mc_active_players: List[str] = []
        self.mc_eliminated_players: List[dict] = []
        self.mc_round_number: int = 0
        self.mc_total_rounds: int = 0
        self.mc_stop_time: Optional[float] = None
        self.mc_grab_deadline: Optional[float] = None
        self.mc_grabs: Dict[str, float] = {}
        self.mc_round_results: List[dict] = []
        self.mc_auto_stop_task: Optional[asyncio.Task] = None
        self.mc_grab_task: Optional[asyncio.Task] = None
        # Bluff state
        self.bluff_config = validate_bluff_config(game_data) if game_type == "bluff" else {}
        self.bluff_state: dict = {}
        # Two Truths and a Lie state
        self.tt_config = validate_two_truths_config(game_data) if game_type == "two_truths" else {}
        self.tt_state: dict = {}
        # Story Chain state
        self.story_config = validate_story_chain_config(game_data) if game_type == "story_chain" else {}
        self.story_state: dict = {}
        # Common Ground state
        self.common_config = validate_common_ground_config(game_data) if game_type == "common_ground" else {}
        self.common_state: dict = {}
        # Find Someone Who state
        self.find_someone_config = validate_find_someone_config(game_data) if game_type == "find_someone" else {}
        self.find_someone_state: dict = {}
        # Who Am I? state
        self.who_am_i_config = validate_who_am_i_config(game_data) if game_type == "who_am_i" else {}
        self.who_am_i_state: dict = {}
        # Chit Pull state
        self.chit_pull_config = validate_chit_pull_config(game_data) if game_type == "chit_pull" else {}
        self.chit_pull_state: dict = {}
        # Mafia state
        self.mafia_config = validate_mafia_config(game_data) if game_type == "mafia" else {}
        self.mafia_state: dict = {}
        self.mafia_timer_task: Optional[asyncio.Task] = None
        # Party Quests state
        self.party_quests_config = validate_party_quests_config(game_data) if game_type == "party_quests" else {}
        self.party_quests_state: dict = {}
        # Survey Says state
        self.survey_says_config = validate_survey_says_config(game_data) if game_type == "survey_says" else {}
        self.survey_says_state: dict = {}
        self.survey_says_completed_sent = False
        # Generic prompt party games
        self.generic_prompt_config = validate_generic_prompt_config(game_data, game_type) if game_type in GENERIC_PROMPT_GAME_TYPES else {}
        self.generic_prompt_state: dict = {}
        self.generic_prompt_completed_sent = False
        # Lightweight social round games
        self.wyr_config = validate_would_you_rather_config(game_data) if game_type == "would_you_rather" else {}
        self.wyr_state: dict = {}
        self.nhie_config = validate_never_have_i_ever_config(game_data) if game_type == "never_have_i_ever" else {}
        self.nhie_state: dict = {}
        self.word_config = validate_word_association_config(game_data) if game_type == "word_association" else {}
        self.word_state: dict = {}
        self.acro_config = validate_acronym_config(game_data) if game_type == "acronym" else {}
        self.acro_state: dict = {}
        self.simple_social_completed_sent = False
        # Photo Clue state
        self.photo_clue_config = validate_photo_clue_config(game_data) if game_type == "photo_clue" else {}
        self.photo_clue_state: dict = {}
        self.photo_clue_completed_sent = False
        # Party Poker state
        self.poker_config = validate_poker_config(game_data) if game_type == "poker" else {}
        self.poker_state: dict = {}
        self.poker_completed_sent = False

    def reset_for_new_game(self, new_game_data: dict, new_time_limit: int,
                           game_type: Optional[str] = None,
                           content_id: Optional[str] = None):
        """Reset room for a new game round, keeping players connected."""
        self.quiz = copy.deepcopy(new_game_data)
        self.time_limit = new_time_limit
        if game_type:
            self.game_type = game_type
        if content_id:
            self.content_id = content_id

        self.state = "LOBBY"
        self.locked = False
        self.current_question_index = -1
        self.question_start_time = 0
        self.answered_players = set()
        self.previous_leaderboard = []
        self.answer_log = []
        self.votes = {}

        if self.timer_task:
            self.timer_task.cancel()
            self.timer_task = None

        # Remove players who are no longer connected
        stale = [cid for cid in self.players if cid not in self.connections]
        for cid in stale:
            nickname = self.players[cid]["nickname"]
            self.teams.pop(nickname, None)
            self.power_ups.pop(nickname, None)
            self.player_tokens.pop(nickname, None)
            del self.players[cid]

        for client_id in self.players:
            self.players[client_id]["score"] = 0
            self.players[client_id]["prev_rank"] = 0
            self.players[client_id]["streak"] = 0

        self.disconnected_players.clear()
        self.bonus_questions = set()
        self.mlt_round_history.clear()
        self.msg_timestamps.clear()
        self.drawer_order = []
        self.current_drawer = ""
        self.correct_guessers = set()
        self.drawing_ops = []
        self.guess_log = []
        self.draw_op_timestamps.clear()
        if self.drawing_auto_task:
            self.drawing_auto_task.cancel()
            self.drawing_auto_task = None
        self.drawing_auto_advance = bool(new_game_data.get("auto_advance", True)) if self.game_type == "drawing" else True
        self.drawing_inter_round_seconds = int(new_game_data.get("inter_round_seconds") or 5) if self.game_type == "drawing" else 5
        self.housie_deck = []
        self.housie_called = []
        self.housie_tickets = {}
        self.housie_winners = []
        self.housie_claimed_patterns = set()
        self.housie_claim_log = []
        self.housie_play_mode = str(new_game_data.get("play_mode") or "beginner").lower()
        self.housie_caller_mode = str(new_game_data.get("caller_mode") or "manual").lower()
        self.housie_auto_status = "stopped"
        self.housie_auto_interval_seconds = int(new_game_data.get("auto_interval_seconds") or 8)
        self.housie_auto_pause_on_claim = bool(new_game_data.get("auto_pause_on_claim", True))
        self.housie_next_auto_call_at = None
        if self.housie_auto_task:
            self.housie_auto_task.cancel()
            self.housie_auto_task = None
        if self.mc_auto_stop_task:
            self.mc_auto_stop_task.cancel()
            self.mc_auto_stop_task = None
        if self.mc_grab_task:
            self.mc_grab_task.cancel()
            self.mc_grab_task = None
        self.mc_config = validate_musical_chairs_config(new_game_data) if self.game_type == "musical_chairs" else {}
        self.mc_active_players = []
        self.mc_eliminated_players = []
        self.mc_round_number = 0
        self.mc_total_rounds = 0
        self.mc_stop_time = None
        self.mc_grab_deadline = None
        self.mc_grabs = {}
        self.mc_round_results = []
        self.bluff_config = validate_bluff_config(new_game_data) if self.game_type == "bluff" else {}
        self.bluff_state = {}
        self.tt_config = validate_two_truths_config(new_game_data) if self.game_type == "two_truths" else {}
        self.tt_state = {}
        self.story_config = validate_story_chain_config(new_game_data) if self.game_type == "story_chain" else {}
        self.story_state = {}
        self.common_config = validate_common_ground_config(new_game_data) if self.game_type == "common_ground" else {}
        self.common_state = {}
        self.find_someone_config = validate_find_someone_config(new_game_data) if self.game_type == "find_someone" else {}
        self.find_someone_state = {}
        self.who_am_i_config = validate_who_am_i_config(new_game_data) if self.game_type == "who_am_i" else {}
        self.who_am_i_state = {}
        self.chit_pull_config = validate_chit_pull_config(new_game_data) if self.game_type == "chit_pull" else {}
        self.chit_pull_state = {}
        if self.mafia_timer_task:
            self.mafia_timer_task.cancel()
            self.mafia_timer_task = None
        self.mafia_config = validate_mafia_config(new_game_data) if self.game_type == "mafia" else {}
        self.mafia_state = {}
        self.party_quests_config = validate_party_quests_config(new_game_data) if self.game_type == "party_quests" else {}
        self.party_quests_state = {}
        self.survey_says_config = validate_survey_says_config(new_game_data) if self.game_type == "survey_says" else {}
        self.survey_says_state = {}
        self.survey_says_completed_sent = False
        self.generic_prompt_config = validate_generic_prompt_config(new_game_data, self.game_type) if self.game_type in GENERIC_PROMPT_GAME_TYPES else {}
        self.generic_prompt_state = {}
        self.generic_prompt_completed_sent = False
        self.wyr_config = validate_would_you_rather_config(new_game_data) if self.game_type == "would_you_rather" else {}
        self.wyr_state = {}
        self.nhie_config = validate_never_have_i_ever_config(new_game_data) if self.game_type == "never_have_i_ever" else {}
        self.nhie_state = {}
        self.word_config = validate_word_association_config(new_game_data) if self.game_type == "word_association" else {}
        self.word_state = {}
        self.acro_config = validate_acronym_config(new_game_data) if self.game_type == "acronym" else {}
        self.acro_state = {}
        self.simple_social_completed_sent = False
        self.photo_clue_config = validate_photo_clue_config(new_game_data) if self.game_type == "photo_clue" else {}
        self.photo_clue_state = {}
        self.photo_clue_completed_sent = False
        self.poker_config = validate_poker_config(new_game_data) if self.game_type == "poker" else {}
        self.poker_state = {}
        self.poker_completed_sent = False

        for nickname in self.power_ups:
            self.power_ups[nickname] = {"double_points": True, "fifty_fifty": True}

        self.touch()

    def touch(self):
        """Update last activity timestamp."""
        self.last_activity = time.time()

    def is_expired(self) -> bool:
        return time.time() - self.last_activity > config.ROOM_TTL_SECONDS

    def total_rounds(self) -> int:
        """Total number of rounds (questions for quiz, statements for WMLT)."""
        if self.game_type == "wmlt":
            return len(self.quiz.get("statements", []))
        if self.game_type == "drawing":
            return len(self.quiz.get("prompts", []))
        if self.game_type in ("housie", "bingo"):
            return len(self.quiz.get("deck", [])) or 90
        if self.game_type == "musical_chairs":
            return self.mc_total_rounds or mc_total_rounds(len(self.mc_active_players) + len(self.mc_eliminated_players), int(self.mc_config.get("eliminations_per_round", 1) or 1))
        if self.game_type == "bluff":
            return max(1, len(self.bluff_state.get("winners", [])) + len([p for p in self.bluff_state.get("players", []) if p not in {w.get("player_id") for w in self.bluff_state.get("winners", [])}]))
        if self.game_type == "two_truths":
            return len(self.tt_state.get("reveal_order", [])) or len(self.tt_state.get("submissions_by_player", {})) or len(self.players)
        if self.game_type == "story_chain":
            return len(self.story_state.get("turn_order", [])) or len(self.players)
        if self.game_type == "common_ground":
            return int(self.common_state.get("config", {}).get("rounds", 0)) or int(self.common_config.get("rounds", 5) or 5)
        if self.game_type == "find_someone":
            return 1
        if self.game_type == "who_am_i":
            return len(self.who_am_i_state.get("config", {}).get("rounds", [])) or len(self.who_am_i_config.get("rounds", [])) or 5
        if self.game_type == "chit_pull":
            return int(self.chit_pull_state.get("config", {}).get("rounds", 0)) or int(self.chit_pull_config.get("rounds", 20) or 20)
        if self.game_type == "mafia":
            return int(self.mafia_state.get("round", 1) or 1)
        if self.game_type == "party_quests":
            return 1
        if self.game_type == "survey_says":
            return len(self.survey_says_state.get("config", {}).get("rounds", [])) or len(self.survey_says_config.get("rounds", [])) or 3
        if self.game_type in GENERIC_PROMPT_GAME_TYPES:
            return len(self.generic_prompt_state.get("rounds", [])) or len(self.generic_prompt_config.get("rounds", [])) or 3
        if self.game_type == "would_you_rather":
            return len(self.wyr_state.get("rounds", [])) or len(self.wyr_config.get("prompts", [])) or 3
        if self.game_type == "never_have_i_ever":
            return len(self.nhie_state.get("rounds", [])) or len(self.nhie_config.get("prompts", [])) or 3
        if self.game_type == "word_association":
            return len(self.word_state.get("rounds", [])) or len(self.word_config.get("seeds", [])) or 3
        if self.game_type == "acronym":
            return len(self.acro_state.get("rounds", [])) or len(self.acro_config.get("prompts", [])) or 3
        if self.game_type == "photo_clue":
            return len(self.photo_clue_state.get("assignments", [])) or len(self.photo_clue_config.get("prompts", [])) or 3
        if self.game_type == "poker":
            return int(self.poker_state.get("hand_number", 0)) or 1
        return len(self.quiz.get("questions", []))

    def current_round_data(self) -> Optional[dict]:
        """Current round item (question or statement)."""
        idx = self.current_question_index
        if idx < 0 or idx >= self.total_rounds():
            return None
        if self.game_type == "wmlt":
            return self.quiz["statements"][idx]
        if self.game_type == "drawing":
            return self.quiz["prompts"][idx]
        if self.game_type in ("housie", "bingo"):
            if 0 <= idx < len(self.housie_called):
                return self.housie_called[idx]
            return None
        if self.game_type == "musical_chairs":
            return self.mc_public_state()
        if self.game_type == "bluff":
            return bluff_public_sync(self.bluff_state) if self.bluff_state else None
        if self.game_type == "two_truths":
            return tt_public_sync(self.tt_state, players=self.player_public_list()) if self.tt_state else None
        if self.game_type == "story_chain":
            return story_public_sync(self.story_state, players=self.player_public_list()) if self.story_state else None
        if self.game_type == "common_ground":
            return common_public_sync(self.common_state, players=self.player_public_list()) if self.common_state else None
        if self.game_type == "find_someone":
            return find_public_sync(self.find_someone_state, players=self.player_public_list()) if self.find_someone_state else None
        if self.game_type == "who_am_i":
            return whoami_public_sync(self.who_am_i_state, players=self.player_public_list()) if self.who_am_i_state else None
        if self.game_type == "chit_pull":
            return chit_pull_public_sync(self.chit_pull_state, players=self.player_public_list()) if self.chit_pull_state else None
        if self.game_type == "mafia":
            return mafia_public_sync(self.mafia_state, players=self.player_public_list()) if self.mafia_state else None
        if self.game_type == "party_quests":
            return quests_public_sync(self.party_quests_state, players=self.player_public_list()) if self.party_quests_state else None
        if self.game_type == "survey_says":
            return survey_public_sync(self.survey_says_state, players=self.player_public_list()) if self.survey_says_state else None
        if self.game_type in GENERIC_PROMPT_GAME_TYPES:
            return generic_public_state(self.generic_prompt_state) if self.generic_prompt_state else None
        if self.game_type == "would_you_rather":
            return wyr_public_state(self.wyr_state) if self.wyr_state else None
        if self.game_type == "never_have_i_ever":
            return nhie_public_state(self.nhie_state) if self.nhie_state else None
        if self.game_type == "word_association":
            return word_public_state(self.word_state) if self.word_state else None
        if self.game_type == "acronym":
            return acro_public_state(self.acro_state) if self.acro_state else None
        if self.game_type == "photo_clue":
            return photo_public_state(self.photo_clue_state) if self.photo_clue_state else None
        if self.game_type == "poker":
            return poker_public_sync(self.poker_state) if self.poker_state else None
        return self.quiz["questions"][idx]

    def game_title(self) -> str:
        """Title of the game content."""
        return self.quiz.get("game_title", self.quiz.get("quiz_title", "Untitled"))

    def player_nicknames(self) -> List[str]:
        """List of active player nicknames."""
        return [p["nickname"] for p in self.players.values()]

    def player_avatar_map(self) -> Dict[str, str]:
        return {p["nickname"]: p.get("avatar", "") for p in self.players.values()}

    def player_public_list(self) -> List[dict]:
        return [{"nickname": p["nickname"], "avatar": p.get("avatar", "")} for p in self.players.values()]

    def mc_public_state(self) -> dict:
        avatars = self.player_avatar_map()
        return {
            "game_title": self.mc_config.get("game_title", self.game_title()),
            "phase": self.state,
            "round_number": self.mc_round_number,
            "total_rounds": self.mc_total_rounds,
            "active_players": [{"nickname": name, "avatar": avatars.get(name, "")} for name in self.mc_active_players],
            "eliminated_players": self.mc_eliminated_players,
            "grabbed": len(self.mc_grabs),
            "chairs": max(1, len(self.mc_active_players) - int(self.mc_config.get("eliminations_per_round", 1) or 1)),
            "gameplay_mode": self.mc_config.get("gameplay_mode", "digital"),
            "music_mode": self.mc_config.get("music_mode", "builtin"),
            "music_style": self.mc_config.get("music_style", "upbeat"),
            "music_track_id": self.mc_config.get("music_track_id"),
            "grab_window_seconds": self.mc_config.get("grab_window_seconds", 5),
            "intensity": intensity_for_round(self.mc_round_number or 1, self.mc_total_rounds or 1, bool(self.mc_config.get("intensity_ramp", True))),
        }

    def _remove_connection(self, client_id: str):
        """Remove a connection. During active game, preserve player data for reconnection."""
        # Spectator cleanup: only touch spectator dict, never player/organizer state
        if client_id in self.spectators:
            self.spectators.pop(client_id, None)
            self.msg_timestamps.pop(client_id, None)
            self.draw_op_timestamps.pop(client_id, None)
            return
        self.connections.pop(client_id, None)
        self.msg_timestamps.pop(client_id, None)
        self.draw_op_timestamps.pop(client_id, None)
        if client_id in self.players:
            nickname = self.players[client_id]["nickname"]
            if self.state in ("LOBBY",):
                # In lobby, fully remove the player
                del self.players[client_id]
                self.teams.pop(nickname, None)
                self.power_ups.pop(nickname, None)
                self._player_event = ("left", nickname)
                logger.info("Player '%s' left room %s", nickname, self.room_code)
            else:
                # During active game, preserve data for reconnection
                self.disconnected_players[nickname] = {
                    "score": self.players[client_id]["score"],
                    "prev_rank": self.players[client_id]["prev_rank"],
                    "streak": self.players[client_id].get("streak", 0),
                    "avatar": self.players[client_id].get("avatar", ""),
                    "_answered_client_id": client_id if client_id in self.answered_players else None,
                }
                del self.players[client_id]
                self._player_event = ("disconnected", nickname)
                logger.info("Player '%s' disconnected from room %s (data preserved)", nickname, self.room_code)
        if self.organizer_id == client_id:
            self.organizer = None
            self.organizer_id = None
            self._organizer_just_disconnected = True
            logger.info("Organizer disconnected from room %s", self.room_code)

    async def close_all_connections(self):
        """Close all player, organizer, and spectator websockets."""
        if self.housie_auto_task:
            self.housie_auto_task.cancel()
            self.housie_auto_task = None
        if self.mc_auto_stop_task:
            self.mc_auto_stop_task.cancel()
            self.mc_auto_stop_task = None
        if self.mc_grab_task:
            self.mc_grab_task.cancel()
            self.mc_grab_task = None
        if self.mafia_timer_task:
            self.mafia_timer_task.cancel()
            self.mafia_timer_task = None
        self.housie_auto_status = "stopped"
        self.housie_next_auto_call_at = None
        for ws in list(self.connections.values()):
            try:
                await ws.close()
            except Exception:
                pass
        for ws in list(self.spectators.values()):
            try:
                await ws.close()
            except Exception:
                pass

    async def broadcast(self, message: dict):
        disconnected = []
        for client_id, ws in list(self.connections.items()):
            try:
                await ws.send_json(message)
            except Exception:
                disconnected.append(client_id)
        # Also broadcast to spectators
        spec_disconnected = []
        for client_id, ws in list(self.spectators.items()):
            try:
                await ws.send_json(message)
            except Exception:
                spec_disconnected.append(client_id)
        for client_id in disconnected + spec_disconnected:
            self._remove_connection(client_id)
        await self.emit_pending_player_event()

    async def emit_pending_player_event(self):
        """Publish the corrected roster after any send path removes a player."""
        if not self._player_event:
            return
        event_type, nickname = self._player_event
        self._player_event = None
        msg_type = "PLAYER_LEFT" if event_type == "left" else "PLAYER_DISCONNECTED"
        await self.broadcast({
            "type": msg_type,
            "nickname": nickname,
            "player_count": len(self.players),
            "players": [
                {"nickname": p["nickname"], "avatar": p.get("avatar", "")}
                for p in self.players.values()
            ],
        })

    async def broadcast_to_players(self, message: dict):
        """Broadcast to players only, not organizer."""
        disconnected = []
        for client_id, ws in list(self.connections.items()):
            if client_id in self.players:
                try:
                    await ws.send_json(message)
                except Exception:
                    disconnected.append(client_id)
        for client_id in disconnected:
            self._remove_connection(client_id)
        await self.emit_pending_player_event()

    async def send_to_organizer(self, message: dict):
        if self.organizer:
            try:
                await self.organizer.send_json(message)
            except Exception:
                if self.organizer_id:
                    self._remove_connection(self.organizer_id)


class SocketManager:
    def __init__(self):
        self.rooms: Dict[str, Room] = {}
        self._cleanup_task: Optional[asyncio.Task] = None
        self.allowed_origins: List[str] = []

    def start_cleanup_loop(self):
        """Start the background room cleanup task."""
        if self._cleanup_task is None:
            self._cleanup_task = asyncio.create_task(self._cleanup_expired_rooms())

    def stop_cleanup_loop(self):
        """Cancel the background room cleanup task."""
        if self._cleanup_task is not None:
            self._cleanup_task.cancel()
            self._cleanup_task = None

    async def _cleanup_expired_rooms(self):
        """Periodically remove expired rooms."""
        while True:
            try:
                await asyncio.sleep(60)
                expired = [code for code, room in self.rooms.items() if room.is_expired()]
                for code in expired:
                    room = self.rooms.pop(code, None)
                    if room:
                        if room.timer_task:
                            room.timer_task.cancel()
                        await room.close_all_connections()
                        self._mark_game_session_closed(room, "expired", "This game expired. Ask the host to start a new one.")
                    logger.info("Cleaned up expired room %s", code)
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("Error in room cleanup loop")

    async def _delayed_room_cleanup(self, room_code: str, delay: int = 30):
        """Delete a room after a grace period if the organizer hasn't reconnected."""
        try:
            await asyncio.sleep(delay)
            room = self.rooms.get(room_code)
            if room and room.organizer is None:
                await room.broadcast({"type": "ROOM_CLOSED"})
                self.rooms.pop(room_code, None)
                if room.timer_task:
                    room.timer_task.cancel()
                await room.close_all_connections()
                self._mark_game_session_closed(room, "cancelled", "The host left this game.")
                logger.info("Room %s deleted (organizer did not reconnect within %ds)", room_code, delay)
        except asyncio.CancelledError:
            pass

    async def _send_to_client(self, room: Room, client_id: str, message: dict):
        """Send a JSON message to a specific client in the room."""
        ws = room.connections.get(client_id)
        if ws:
            try:
                await ws.send_json(message)
            except Exception:
                pass

    async def _send_to_organizer_error(self, room: Room, message: str):
        await room.send_to_organizer({"type": "ERROR", "message": message})

    def create_room(self, room_code: str, game_data: dict, time_limit: int = 15,
                    organizer_token: str = "", content_id: str = "",
                    game_type: str = "quiz", billing_mode: str = "localplay_sparks") -> Room:
        room = Room(room_code, game_data, time_limit, organizer_token=organizer_token,
                    content_id=content_id, game_type=game_type, billing_mode=billing_mode)
        self.rooms[room_code] = room
        self.start_cleanup_loop()
        return room

    async def close_room(self, room_code: str, reason: str = "cancelled", message: str = "This game was closed."):
        """Close and remove a runtime room, notifying connected clients first."""
        room = self.rooms.pop(room_code, None)
        if not room:
            return
        await room.broadcast({
            "type": "ROOM_CLOSED",
            "reason": reason,
            "message": message,
        })
        if room.timer_task:
            room.timer_task.cancel()
            room.timer_task = None
        await room.close_all_connections()

    async def _prune_dead_player_connections(self, room: Room):
        """Probe player sockets before lifecycle decisions that depend on live players."""
        for client_id, ws in list(room.connections.items()):
            if client_id not in room.players:
                continue
            try:
                await ws.send_json({"type": "PING"})
            except Exception:
                room._remove_connection(client_id)
        await room.emit_pending_player_event()

    async def connect(self, websocket: WebSocket, room_code: str, client_id: str,
                      is_organizer: bool = False, is_spectator: bool = False):
        # Validate WebSocket origin
        origin = websocket.headers.get("origin", "")
        if self.allowed_origins and origin not in self.allowed_origins:
            logger.warning("Rejected WebSocket from unauthorized origin: %s", origin)
            await websocket.close(code=1008)
            return

        await websocket.accept()
        if room_code not in self.rooms:
            await websocket.send_json({"type": "ERROR", "message": "Room not found"})
            await websocket.close()
            return

        room = self.rooms[room_code]

        # Organizer auth: first-frame AUTH message required
        if is_organizer:
            try:
                auth_msg = await asyncio.wait_for(websocket.receive_json(), timeout=5.0)
                auth_token = auth_msg.get("token", "") if isinstance(auth_msg, dict) and auth_msg.get("type") == "AUTH" else ""
                if not auth_token or not hmac.compare_digest(auth_token, room.organizer_token):
                    await websocket.send_json({"type": "ERROR", "message": "Invalid organizer token"})
                    await websocket.close()
                    return
            except (asyncio.TimeoutError, Exception):
                await websocket.send_json({"type": "ERROR", "message": "Organizer authentication required"})
                await websocket.close()
                return

        room.touch()

        if is_spectator:
            room.spectators[client_id] = websocket
            try:
                # Send current state sync to spectator
                sync: dict = {
                    "type": "SPECTATOR_SYNC",
                    "room_code": room_code,
                    "state": room.state,
                    "game_type": room.game_type,
                    "player_count": len(room.players),
                    "players": [{"nickname": p["nickname"], "avatar": p.get("avatar", "")} for p in room.players.values()],
                    "question_number": room.current_question_index + 1,
                    "total_questions": room.total_rounds(),
                    "leaderboard": self.get_leaderboard(room),
                    "team_leaderboard": self.get_team_leaderboard(room),
                }
                # Include round data if game is in progress
                if room.state == "QUESTION" and room.current_round_data() is not None:
                    round_data = room.current_round_data()
                    if room.game_type == "wmlt":
                        sync["statement"] = round_data
                        sync["vote_count"] = len(room.votes)
                    elif room.game_type == "drawing":
                        sync["drawing_prompt"] = self._drawing_public_prompt(round_data)
                        sync["drawing_clue"] = self._drawing_clue(room, round_data)
                        sync["drawer"] = room.current_drawer
                        sync["drawing_ops"] = room.drawing_ops[-config.MAX_DRAW_OPS_PER_SYNC:]
                        sync["correct_guessers"] = list(room.correct_guessers)
                        sync["guess_log"] = room.guess_log[-10:]
                    else:
                        sync["question"] = {k: v for k, v in round_data.items() if k != "answer_index"}
                    sync["time_limit"] = room.time_limit
                    elapsed = time.time() - room.question_start_time
                    sync["time_remaining"] = max(0, room.time_limit - int(elapsed))
                    sync["is_bonus"] = room.current_question_index in room.bonus_questions
                if room.game_type in ("housie", "bingo"):
                    sync["bingo"] = self._housie_public_state(room)
                if room.game_type == "musical_chairs":
                    sync["musical_chairs"] = room.mc_public_state()
                if room.game_type == "bluff" and room.bluff_state:
                    sync["bluff"] = bluff_public_sync(room.bluff_state)
                if room.game_type == "two_truths" and room.tt_state:
                    sync["two_truths"] = tt_public_sync(room.tt_state, players=room.player_public_list())
                if room.game_type == "story_chain" and room.story_state:
                    sync["story_chain"] = story_public_sync(room.story_state, players=room.player_public_list())
                if room.game_type == "common_ground" and room.common_state:
                    sync["common_ground"] = common_public_sync(room.common_state, players=room.player_public_list())
                if room.game_type == "find_someone" and room.find_someone_state:
                    sync["find_someone"] = find_public_sync(room.find_someone_state, players=room.player_public_list())
                if room.game_type == "who_am_i" and room.who_am_i_state:
                    sync["who_am_i"] = whoami_public_sync(room.who_am_i_state, players=room.player_public_list())
                if room.game_type == "chit_pull" and room.chit_pull_state:
                    sync["chit_pull"] = chit_pull_public_sync(room.chit_pull_state, players=room.player_public_list())
                if room.game_type == "mafia" and room.mafia_state:
                    sync["mafia"] = mafia_public_sync(room.mafia_state, players=room.player_public_list())
                if room.game_type == "party_quests" and room.party_quests_state:
                    sync["party_quests"] = quests_public_sync(room.party_quests_state, players=room.player_public_list())
                if room.game_type == "survey_says" and room.survey_says_state:
                    sync["survey_says"] = survey_public_sync(room.survey_says_state, players=room.player_public_list())
                if room.game_type in GENERIC_PROMPT_GAME_TYPES and room.generic_prompt_state:
                    sync["generic_prompt"] = generic_public_state(room.generic_prompt_state)
                if room.game_type in ("would_you_rather", "never_have_i_ever", "word_association", "acronym"):
                    state = getattr(room, self._simple_social_state_attr(room.game_type), {})
                    if state:
                        sync[self._simple_social_sync_key(room.game_type)] = self._simple_social_public_state(room)
                if room.game_type == "photo_clue" and room.photo_clue_state:
                    sync["photo_clue"] = self._photo_clue_public_state(room)
                if room.game_type == "poker" and room.poker_state:
                    sync["poker"] = self._poker_public_state(room)
                await websocket.send_json(sync)
                while True:
                    try:
                        await asyncio.wait_for(websocket.receive_text(), timeout=60.0)
                    except asyncio.TimeoutError:
                        # No message in 60s — ping to check liveness
                        try:
                            await websocket.send_json({"type": "PING"})
                        except Exception:
                            break  # connection is dead
            except (WebSocketDisconnect, Exception):
                pass
            finally:
                room._remove_connection(client_id)
            return

        room.connections[client_id] = websocket

        if is_organizer:
            # Cancel pending room cleanup if organizer is reconnecting
            was_disconnected = room.organizer is None
            if room._organizer_cleanup_task:
                room._organizer_cleanup_task.cancel()
                room._organizer_cleanup_task = None
                logger.info("Organizer reconnected to room %s, cleanup cancelled", room_code)
            # Close and clean up stale organizer connection if a different client_id
            if room.organizer_id and room.organizer_id != client_id:
                old_org_ws = room.connections.pop(room.organizer_id, None)
                if old_org_ws:
                    try:
                        await old_org_ws.close()
                    except Exception:
                        pass
            room.organizer = websocket
            room.organizer_id = client_id
            # Notify players and spectators that host is back (only on actual reconnect, not first connect)
            if was_disconnected and (room.current_question_index >= 0 or len(room.players) > 0):
                await room.broadcast({"type": "HOST_RECONNECTED"})
            # Detect reconnection: room already has players or game has progressed
            if room.current_question_index >= 0 or len(room.players) > 0:
                await self._send_organizer_sync(room)
            else:
                await websocket.send_json({"type": "ROOM_CREATED", "room_code": room_code})
        else:
            # Don't send JOINED_ROOM yet — wait until JOIN validation succeeds
            # to avoid the client entering LOBBY before nickname is accepted
            pass

        try:
            while True:
                data = await websocket.receive_text()

                # Enforce message size limit
                if len(data) > config.MAX_WS_MESSAGE_SIZE:
                    await websocket.send_json({"type": "ERROR", "message": "Message too large"})
                    continue

                try:
                    message = json.loads(data)
                except json.JSONDecodeError:
                    logger.warning("Malformed JSON from client %s: %s", client_id, data[:100])
                    await websocket.send_json({"type": "ERROR", "message": "Invalid message format"})
                    continue

                msg_type = message.get("type") if isinstance(message, dict) else None
                now = time.time()
                if room.game_type == "drawing" and msg_type == "DRAW_OP":
                    if len(data) > config.MAX_DRAW_OP_MESSAGE_SIZE:
                        await websocket.send_json({"type": "ERROR", "message": "Drawing message too large"})
                        continue
                    timestamps = room.draw_op_timestamps.setdefault(client_id, [])
                    timestamps[:] = [t for t in timestamps if now - t < 1.0]
                    if len(timestamps) >= config.DRAW_OP_RATE_LIMIT_PER_SEC:
                        await websocket.send_json({"type": "ERROR", "message": "Too many drawing messages"})
                        continue
                    timestamps.append(now)
                else:
                    # Per-client rate limiting for non-drawing messages
                    timestamps = room.msg_timestamps.setdefault(client_id, [])
                    timestamps[:] = [t for t in timestamps if now - t < 1.0]
                    if len(timestamps) >= config.WS_RATE_LIMIT_PER_SEC:
                        await websocket.send_json({"type": "ERROR", "message": "Too many messages"})
                        continue
                    timestamps.append(now)

                room.touch()
                # Revoke organizer privileges if this socket was replaced by a newer organizer
                effective_organizer = is_organizer and client_id == room.organizer_id
                await self.handle_message(room, client_id, message, effective_organizer)
        except WebSocketDisconnect:
            logger.info("Client %s disconnected from room %s", client_id, room_code)
        except Exception:
            logger.exception("WebSocket error for client %s in room %s", client_id, room_code)
        finally:
            room._remove_connection(client_id)
            if room._organizer_just_disconnected:
                room._organizer_just_disconnected = False
                # Re-check: organizer may have already reconnected via a new socket
                if room.organizer is None:
                    if room.game_type in ("housie", "bingo") and room.housie_auto_status == "running":
                        await self._set_housie_auto_status(room, "paused")
                    await room.broadcast({"type": "ORGANIZER_DISCONNECTED"})
                    # Start grace period — delete room if organizer doesn't reconnect
                    room._organizer_cleanup_task = asyncio.create_task(
                        self._delayed_room_cleanup(room_code, delay=config.ORGANIZER_RECONNECT_GRACE_SECONDS)
                    )
            if room._player_event:
                event_type, nickname = room._player_event
                room._player_event = None
                msg_type = "PLAYER_LEFT" if event_type == "left" else "PLAYER_DISCONNECTED"
                await room.broadcast({
                    "type": msg_type,
                    "nickname": nickname,
                    "player_count": len(room.players),
                    "players": [{"nickname": p["nickname"], "avatar": p.get("avatar", "")} for p in room.players.values()],
                })
                # Re-evaluate all_answered: if remaining players have all answered,
                # end the question instead of waiting for the full timer
                if room.state == "QUESTION" and len(room.players) > 0:
                    if all(cid in room.answered_players for cid in room.players):
                        await self.end_question(room)

    async def _send_organizer_sync(self, room: Room):
        """Send full game state to a reconnecting organizer."""
        sync = {
            "type": "ORGANIZER_RECONNECTED",
            "room_code": room.room_code,
            "state": room.state,
            "game_type": room.game_type,
            "player_count": len(room.players),
            "players": [
                {"nickname": p["nickname"], "avatar": p.get("avatar", "")}
                for p in room.players.values()
            ],
            "question_number": room.current_question_index + 1,
            "total_questions": room.total_rounds(),
            "leaderboard": self.get_leaderboard(room),
            "team_leaderboard": self.get_team_leaderboard(room),
            "time_limit": room.time_limit,
            "quiz": room.quiz,
            "locked": room.locked,
        }

        if room.state == "QUESTION":
            round_data = room.current_round_data()
            if room.game_type == "wmlt":
                sync["statement"] = round_data
                sync["vote_count"] = len(room.votes)
                sync["voted_count"] = len(room.votes)
            elif room.game_type == "drawing":
                sync["drawing_prompt"] = round_data
                sync["drawing_clue"] = self._drawing_clue(room, round_data)
                sync["drawer"] = room.current_drawer
                sync["drawing_ops"] = room.drawing_ops[-config.MAX_DRAW_OPS_PER_SYNC:]
                sync["correct_guessers"] = list(room.correct_guessers)
                sync["guess_log"] = room.guess_log[-10:]
                sync["answered_count"] = len(room.correct_guessers)
            else:
                sync["question"] = round_data
                sync["answered_count"] = len(room.answered_players)
            sync["is_bonus"] = room.current_question_index in room.bonus_questions
            elapsed = time.time() - room.question_start_time
            sync["time_remaining"] = max(0, room.time_limit - int(elapsed))

        if room.game_type in ("housie", "bingo"):
            sync["bingo"] = self._housie_public_state(room)
        if room.game_type == "musical_chairs":
            sync["musical_chairs"] = room.mc_public_state()
        if room.game_type == "bluff" and room.bluff_state:
            sync["bluff"] = bluff_public_sync(room.bluff_state)
        if room.game_type == "two_truths" and room.tt_state:
            sync["two_truths"] = tt_public_sync(room.tt_state, players=room.player_public_list())
        if room.game_type == "story_chain" and room.story_state:
            sync["story_chain"] = story_public_sync(room.story_state, players=room.player_public_list())
        if room.game_type == "common_ground" and room.common_state:
            sync["common_ground"] = common_public_sync(room.common_state, players=room.player_public_list())
        if room.game_type == "find_someone" and room.find_someone_state:
            sync["find_someone"] = find_public_sync(room.find_someone_state, players=room.player_public_list())
        if room.game_type == "who_am_i" and room.who_am_i_state:
            sync["who_am_i"] = whoami_public_sync(room.who_am_i_state, players=room.player_public_list())
        if room.game_type == "chit_pull" and room.chit_pull_state:
            sync["chit_pull"] = chit_pull_public_sync(room.chit_pull_state, players=room.player_public_list())
        if room.game_type == "mafia" and room.mafia_state:
            sync["mafia"] = mafia_public_sync(room.mafia_state, players=room.player_public_list())
        if room.game_type == "party_quests" and room.party_quests_state:
            sync["party_quests"] = quests_public_sync(room.party_quests_state, players=room.player_public_list())
        if room.game_type == "survey_says" and room.survey_says_state:
            sync["survey_says"] = survey_public_sync(room.survey_says_state, players=room.player_public_list(), host=True)
        if room.game_type in GENERIC_PROMPT_GAME_TYPES and room.generic_prompt_state:
            sync["generic_prompt"] = generic_public_state(room.generic_prompt_state, host=True)
        if room.game_type in ("would_you_rather", "never_have_i_ever", "word_association", "acronym"):
            state = getattr(room, self._simple_social_state_attr(room.game_type), {})
            if state:
                sync[self._simple_social_sync_key(room.game_type)] = self._simple_social_public_state(room)
        if room.game_type == "photo_clue" and room.photo_clue_state:
            sync["photo_clue"] = self._photo_clue_public_state(room)
        if room.game_type == "poker" and room.poker_state:
            sync["poker"] = self._poker_public_state(room)

        if room.organizer:
            await room.organizer.send_json(sync)
        logger.info("Organizer reconnected to room %s (state: %s)", room.room_code, room.state)

    async def handle_message(self, room: Room, client_id: str, message: dict, is_organizer: bool):
        if not isinstance(message, dict):
            return
        msg_type = message.get("type")
        if not isinstance(msg_type, str):
            return

        if is_organizer:
            if msg_type == "START_GAME":
                async with room.lock:
                    if room.state != "LOBBY":
                        return
                    await self._prune_dead_player_connections(room)
                    # Charge sparks to start the game
                    if not room.wallet_id:
                        await self._send_to_client(room, client_id, {
                            "type": "ERROR",
                            "message": "Internal error: wallet not configured.",
                        })
                        return
                    # WMLT requires minimum players — check before charging
                    if room.game_type == "wmlt":
                        player_count = len([p for p in room.players.values() if p.get("nickname")])
                        if player_count < config.MIN_WMLT_PLAYERS:
                            await self._send_to_client(room, client_id, {
                                "type": "ERROR",
                                "message": f"Most Likely To needs at least {config.MIN_WMLT_PLAYERS} players to start",
                            })
                            return
                    elif room.game_type == "drawing":
                        player_count = len([p for p in room.players.values() if p.get("nickname")])
                        if player_count < config.MIN_DRAWING_PLAYERS:
                            await self._send_to_client(room, client_id, {
                                "type": "ERROR",
                                "message": f"Drawing Game needs at least {config.MIN_DRAWING_PLAYERS} players to start",
                            })
                            return
                    elif room.game_type == "housie":
                        player_count = len([p for p in room.players.values() if p.get("nickname")])
                        if player_count < config.MIN_HOUSIE_PLAYERS:
                            await self._send_to_client(room, client_id, {
                                "type": "ERROR",
                                "message": f"Housie needs at least {config.MIN_HOUSIE_PLAYERS} players to start",
                            })
                            return
                    elif room.game_type == "bingo":
                        player_count = len([p for p in room.players.values() if p.get("nickname")])
                        if player_count < config.MIN_BINGO_PLAYERS:
                            await self._send_to_client(room, client_id, {
                                "type": "ERROR",
                                "message": f"Bingo needs at least {config.MIN_BINGO_PLAYERS} players to start",
                            })
                            return
                    elif room.game_type == "musical_chairs":
                        player_count = len([p for p in room.players.values() if p.get("nickname")])
                        if player_count < config.MIN_MUSICAL_CHAIRS_PLAYERS:
                            await self._send_to_client(room, client_id, {
                                "type": "ERROR",
                                "message": f"Musical Chairs needs at least {config.MIN_MUSICAL_CHAIRS_PLAYERS} players to start",
                            })
                            return
                    elif room.game_type == "bluff":
                        player_count = len([p for p in room.players.values() if p.get("nickname")])
                        if player_count < config.MIN_BLUFF_PLAYERS:
                            await self._send_to_client(room, client_id, {
                                "type": "ERROR",
                                "message": f"Bluff needs at least {config.MIN_BLUFF_PLAYERS} players to start",
                            })
                            return
                    elif room.game_type == "two_truths":
                        player_count = len([p for p in room.players.values() if p.get("nickname")])
                        if player_count < config.MIN_TWO_TRUTHS_PLAYERS:
                            await self._send_to_client(room, client_id, {
                                "type": "ERROR",
                                "message": f"Two Truths and a Lie needs at least {config.MIN_TWO_TRUTHS_PLAYERS} players to start",
                            })
                            return
                    elif room.game_type == "story_chain":
                        player_count = len([p for p in room.players.values() if p.get("nickname")])
                        if player_count < config.MIN_STORY_CHAIN_PLAYERS:
                            await self._send_to_client(room, client_id, {
                                "type": "ERROR",
                                "message": f"Story Chain needs at least {config.MIN_STORY_CHAIN_PLAYERS} players to start",
                            })
                            return
                    elif room.game_type == "common_ground":
                        player_count = len([p for p in room.players.values() if p.get("nickname")])
                        if player_count < config.MIN_COMMON_GROUND_PLAYERS:
                            await self._send_to_client(room, client_id, {
                                "type": "ERROR",
                                "message": f"Common Ground needs at least {config.MIN_COMMON_GROUND_PLAYERS} players to start",
                            })
                            return
                    elif room.game_type == "find_someone":
                        player_count = len([p for p in room.players.values() if p.get("nickname")])
                        if player_count < config.MIN_FIND_SOMEONE_PLAYERS:
                            await self._send_to_client(room, client_id, {
                                "type": "ERROR",
                                "message": "Find Someone Who starts when at least one guest has joined",
                            })
                            return
                    elif room.game_type == "who_am_i":
                        player_count = len([p for p in room.players.values() if p.get("nickname")])
                        if player_count < config.MIN_WHO_AM_I_PLAYERS:
                            await self._send_to_client(room, client_id, {
                                "type": "ERROR",
                                "message": f"Who Am I? needs at least {config.MIN_WHO_AM_I_PLAYERS} players to start",
                            })
                            return
                    elif room.game_type == "chit_pull":
                        player_count = len([p for p in room.players.values() if p.get("nickname")])
                        if player_count < config.MIN_CHIT_PULL_PLAYERS:
                            await self._send_to_client(room, client_id, {
                                "type": "ERROR",
                                "message": f"Random Chit needs at least {config.MIN_CHIT_PULL_PLAYERS} players to start",
                            })
                            return
                    elif room.game_type == "mafia":
                        player_count = len([p for p in room.players.values() if p.get("nickname")])
                        if player_count < config.MIN_MAFIA_PLAYERS:
                            await self._send_to_client(room, client_id, {
                                "type": "ERROR",
                                "message": f"Mafia needs at least {config.MIN_MAFIA_PLAYERS} players to start",
                            })
                            return
                    elif room.game_type == "party_quests":
                        player_count = len([p for p in room.players.values() if p.get("nickname")])
                        if player_count < config.MIN_PARTY_QUESTS_PLAYERS:
                            await self._send_to_client(room, client_id, {
                                "type": "ERROR",
                                "message": "Party Quests starts when at least one guest has joined",
                            })
                            return
                    elif room.game_type == "survey_says":
                        player_count = len([p for p in room.players.values() if p.get("nickname")])
                        if player_count < config.MIN_SURVEY_SAYS_PLAYERS:
                            await self._send_to_client(room, client_id, {
                                "type": "ERROR",
                                "message": f"Survey Says needs at least {config.MIN_SURVEY_SAYS_PLAYERS} players to start",
                            })
                            return
                    elif room.game_type in GENERIC_PROMPT_GAME_TYPES:
                        player_count = len([p for p in room.players.values() if p.get("nickname")])
                        if player_count < 2:
                            await self._send_to_client(room, client_id, {
                                "type": "ERROR",
                                "message": "This game needs at least 2 players to start",
                            })
                            return
                    elif room.game_type == "would_you_rather":
                        player_count = len([p for p in room.players.values() if p.get("nickname")])
                        if player_count < config.MIN_WOULD_YOU_RATHER_PLAYERS:
                            await self._send_to_client(room, client_id, {
                                "type": "ERROR",
                                "message": f"Would You Rather needs at least {config.MIN_WOULD_YOU_RATHER_PLAYERS} players to start",
                            })
                            return
                    elif room.game_type == "never_have_i_ever":
                        player_count = len([p for p in room.players.values() if p.get("nickname")])
                        if player_count < config.MIN_NEVER_HAVE_I_EVER_PLAYERS:
                            await self._send_to_client(room, client_id, {
                                "type": "ERROR",
                                "message": f"Never Have I Ever needs at least {config.MIN_NEVER_HAVE_I_EVER_PLAYERS} players to start",
                            })
                            return
                    elif room.game_type == "word_association":
                        player_count = len([p for p in room.players.values() if p.get("nickname")])
                        if player_count < config.MIN_WORD_ASSOCIATION_PLAYERS:
                            await self._send_to_client(room, client_id, {
                                "type": "ERROR",
                                "message": f"Word Association needs at least {config.MIN_WORD_ASSOCIATION_PLAYERS} players to start",
                            })
                            return
                    elif room.game_type == "acronym":
                        player_count = len([p for p in room.players.values() if p.get("nickname")])
                        if player_count < config.MIN_ACRONYM_PLAYERS:
                            await self._send_to_client(room, client_id, {
                                "type": "ERROR",
                                "message": f"Acronym Game needs at least {config.MIN_ACRONYM_PLAYERS} players to start",
                            })
                            return
                    elif room.game_type == "photo_clue":
                        player_count = len([p for p in room.players.values() if p.get("nickname")])
                        if player_count < config.MIN_PHOTO_CLUE_PLAYERS:
                            await self._send_to_client(room, client_id, {
                                "type": "ERROR",
                                "message": f"Photo Clue needs at least {config.MIN_PHOTO_CLUE_PLAYERS} players to start",
                            })
                            return
                    elif room.game_type == "poker":
                        player_count = len([p for p in room.players.values() if p.get("nickname")])
                        if player_count < config.MIN_POKER_PLAYERS:
                            await self._send_to_client(room, client_id, {
                                "type": "ERROR",
                                "message": f"Party Poker needs at least {config.MIN_POKER_PLAYERS} players to start",
                            })
                            return
                        if player_count > 10:
                            await self._send_to_client(room, client_id, {
                                "type": "ERROR",
                                "message": "Party Poker supports up to 10 players",
                            })
                            return
                    if room.billing_mode == "host_app_managed":
                        spent = True
                    else:
                        spent, _ = token_module.spend_room(room.wallet_id)
                    if not spent:
                        await self._send_to_client(room, client_id, {
                            "type": "INSUFFICIENT_SPARKS",
                            "message": f"You need {config.COST_ROOM} sparks to start a game.",
                        })
                        return
                    room.locked = True
                    if room.game_type == "quiz":
                        self._select_bonus_questions(room)
                    self._mark_game_session_started(room)
                    if room.game_type in ("housie", "bingo"):
                        room.locked = True
                        room.state = "BINGO_CALLING"
                        self._start_housie_round(room)
                        await room.broadcast({"type": "GAME_STARTING", "game_type": room.game_type})
                        await self._broadcast_housie_sync(room)
                        if room.housie_caller_mode == "auto":
                            await self._set_housie_auto_status(room, "running")
                    elif room.game_type == "musical_chairs":
                        room.state = "MC_BETWEEN_ROUNDS"
                        self._start_musical_chairs_game(room)
                        await room.broadcast({"type": "GAME_STARTING", "game_type": "musical_chairs"})
                        await room.broadcast({"type": "MC_SYNC", "musical_chairs": room.mc_public_state()})
                    elif room.game_type == "bluff":
                        self._start_bluff_game(room)
                        await room.broadcast({"type": "GAME_STARTING", "game_type": "bluff"})
                        await self._broadcast_bluff_sync(room)
                    elif room.game_type == "two_truths":
                        self._start_two_truths_game(room)
                        await room.broadcast({"type": "GAME_STARTING", "game_type": "two_truths"})
                        await self._broadcast_two_truths_sync(room)
                    elif room.game_type == "story_chain":
                        self._start_story_chain_game(room)
                        await room.broadcast({"type": "GAME_STARTING", "game_type": "story_chain"})
                        await self._broadcast_story_chain_sync(room)
                    elif room.game_type == "common_ground":
                        self._start_common_ground_game(room)
                        await room.broadcast({"type": "GAME_STARTING", "game_type": "common_ground"})
                        await self._broadcast_common_ground_sync(room)
                    elif room.game_type == "find_someone":
                        self._start_find_someone_game(room)
                        await room.broadcast({"type": "GAME_STARTING", "game_type": "find_someone"})
                        await self._broadcast_find_someone_sync(room)
                    elif room.game_type == "who_am_i":
                        self._start_who_am_i_game(room)
                        await room.broadcast({"type": "GAME_STARTING", "game_type": "who_am_i"})
                        await self._broadcast_who_am_i_sync(room)
                    elif room.game_type == "chit_pull":
                        self._start_chit_pull_game(room)
                        await room.broadcast({"type": "GAME_STARTING", "game_type": "chit_pull"})
                        await self._broadcast_chit_pull_sync(room)
                    elif room.game_type == "mafia":
                        self._start_mafia_game(room)
                        await room.broadcast({"type": "GAME_STARTING", "game_type": "mafia"})
                        await self._broadcast_mafia_sync(room)
                    elif room.game_type == "party_quests":
                        self._start_party_quests_game(room)
                        await room.broadcast({"type": "GAME_STARTING", "game_type": "party_quests"})
                        await self._broadcast_party_quests_sync(room)
                    elif room.game_type == "survey_says":
                        self._start_survey_says_game(room)
                        await room.broadcast({"type": "GAME_STARTING", "game_type": "survey_says"})
                        await self._broadcast_survey_says_sync(room)
                    elif room.game_type in GENERIC_PROMPT_GAME_TYPES:
                        self._start_generic_prompt_game(room)
                        await room.broadcast({"type": "GAME_STARTING", "game_type": room.game_type})
                        await self._broadcast_generic_prompt_sync(room)
                    elif room.game_type in ("would_you_rather", "never_have_i_ever", "word_association", "acronym"):
                        self._start_simple_social_game(room)
                        await room.broadcast({"type": "GAME_STARTING", "game_type": room.game_type})
                        await self._broadcast_simple_social_sync(room)
                    elif room.game_type == "photo_clue":
                        self._start_photo_clue_game(room)
                        await room.broadcast({"type": "GAME_STARTING", "game_type": "photo_clue"})
                        await self._broadcast_photo_clue_sync(room)
                    elif room.game_type == "poker":
                        self._start_poker_game(room)
                        await room.broadcast({"type": "GAME_STARTING", "game_type": "poker"})
                        await self._broadcast_poker_sync(room)
                    else:
                        room.state = "INTRO"
                        await room.broadcast({"type": "GAME_STARTING"})

            elif msg_type == "NEXT_QUESTION":
                if room.game_type in ("housie", "bingo", "musical_chairs", "two_truths", "story_chain", "common_ground", "find_someone", "who_am_i", "chit_pull", "mafia", "party_quests", "survey_says", "would_you_rather", "never_have_i_ever", "word_association", "acronym", "photo_clue", "poker") or room.game_type in GENERIC_PROMPT_GAME_TYPES:
                    return
                if room.game_type == "drawing" and room.drawing_auto_task:
                    room.drawing_auto_task.cancel()
                    room.drawing_auto_task = None
                if room.state == "QUESTION":
                    await self.end_question(room)
                elif room.state in ("INTRO", "LEADERBOARD"):
                    await self.start_question(room)

            elif msg_type == "BINGO_CALL_NEXT" and room.game_type in ("housie", "bingo"):
                await self._housie_call_next(room)

            elif msg_type == "BINGO_UNDO_LAST_CALL" and room.game_type in ("housie", "bingo"):
                await self._housie_undo_last_call(room)

            elif msg_type == "BINGO_SET_CALLER_MODE" and room.game_type in ("housie", "bingo"):
                mode = str(message.get("caller_mode") or "").strip().lower()
                if mode not in ("manual", "auto"):
                    await self._send_to_client(room, client_id, {"type": "ERROR", "message": "Invalid caller mode"})
                    return
                interval = message.get("auto_interval_seconds")
                if interval is not None:
                    try:
                        room.housie_auto_interval_seconds = max(3, min(30, int(interval)))
                    except (TypeError, ValueError):
                        pass
                room.housie_caller_mode = mode
                if mode == "auto":
                    await self._set_housie_auto_status(room, "running")
                else:
                    await self._set_housie_auto_status(room, "stopped")

            elif msg_type == "BINGO_PAUSE" and room.game_type in ("housie", "bingo"):
                await self._set_housie_auto_status(room, "paused")

            elif msg_type == "BINGO_RESUME" and room.game_type in ("housie", "bingo"):
                room.housie_caller_mode = "auto"
                await self._set_housie_auto_status(room, "running")

            elif msg_type == "MC_START_ROUND" and room.game_type == "musical_chairs":
                await self._mc_start_round(room)

            elif msg_type == "MC_STOP_MUSIC" and room.game_type == "musical_chairs":
                await self._mc_stop_music(room)

            elif msg_type == "MC_ELIMINATE_PLAYER" and room.game_type == "musical_chairs":
                await self._mc_eliminate_physical(room, str(message.get("nickname") or ""))

            elif msg_type == "MC_NEXT_ROUND" and room.game_type == "musical_chairs":
                await self._mc_start_round(room)

            elif msg_type == "BLUFF_RESOLVE" and room.game_type == "bluff":
                await self._bluff_resolve(room)

            elif msg_type == "BLUFF_CONTINUE" and room.game_type == "bluff":
                await self._bluff_continue(room)

            elif msg_type == "TT_START_REVEAL" and room.game_type == "two_truths":
                await self._tt_start_reveal(room, client_id)

            elif msg_type == "TT_NEXT_AUTHOR" and room.game_type == "two_truths":
                await self._tt_next_step(room)

            elif msg_type == "STORY_SKIP_TURN" and room.game_type == "story_chain":
                await self._story_skip_turn(room)

            elif msg_type == "STORY_NEXT_REVEAL_STEP" and room.game_type == "story_chain":
                await self._story_next_reveal_step(room)

            elif msg_type == "COMMON_START_REVEAL" and room.game_type == "common_ground":
                await self._common_start_reveal(room)

            elif msg_type == "COMMON_START_VOTING" and room.game_type == "common_ground":
                await self._common_start_voting(room)

            elif msg_type == "COMMON_SCORE_ROUND" and room.game_type == "common_ground":
                await self._common_score_round(room)

            elif msg_type == "COMMON_NEXT_ROUND" and room.game_type == "common_ground":
                await self._common_next_round(room)

            elif msg_type in ("WYR_REVEAL", "NHIE_REVEAL", "WORD_REVEAL") and room.game_type in ("would_you_rather", "never_have_i_ever", "word_association"):
                await self._simple_social_reveal(room)

            elif msg_type in ("WYR_NEXT_ROUND", "NHIE_NEXT_ROUND", "WORD_NEXT_ROUND") and room.game_type in ("would_you_rather", "never_have_i_ever", "word_association"):
                await self._simple_social_next_round(room)

            elif msg_type == "ACRO_START_VOTING" and room.game_type == "acronym":
                await self._acronym_start_voting(room)

            elif msg_type == "ACRO_REVEAL" and room.game_type == "acronym":
                await self._simple_social_reveal(room)

            elif msg_type == "ACRO_NEXT_ROUND" and room.game_type == "acronym":
                await self._simple_social_next_round(room)

            elif msg_type == "GENERIC_START_VOTING" and room.game_type in GENERIC_PROMPT_GAME_TYPES:
                await self._generic_prompt_start_voting(room)

            elif msg_type == "GENERIC_REVEAL" and room.game_type in GENERIC_PROMPT_GAME_TYPES:
                await self._generic_prompt_reveal(room)

            elif msg_type == "GENERIC_NEXT_ROUND" and room.game_type in GENERIC_PROMPT_GAME_TYPES:
                await self._generic_prompt_next_round(room)

            elif msg_type == "PHOTO_CLUE_REVEAL" and room.game_type == "photo_clue":
                await self._photo_clue_reveal(room)

            elif msg_type == "PHOTO_CLUE_NEXT_ROUND" and room.game_type == "photo_clue":
                await self._photo_clue_next_round(room)

            elif msg_type == "POKER_REVEAL" and room.game_type == "poker":
                await self._poker_reveal(room)

            elif msg_type == "POKER_NEXT_HAND" and room.game_type == "poker":
                await self._poker_next_hand(room)

            elif msg_type == "WHOAMI_NEXT_CLUE" and room.game_type == "who_am_i":
                await self._who_am_i_next_clue(room)

            elif msg_type == "WHOAMI_REVEAL_ANSWER" and room.game_type == "who_am_i":
                await self._who_am_i_reveal_answer(room)

            elif msg_type == "WHOAMI_NEXT_ROUND" and room.game_type == "who_am_i":
                await self._who_am_i_next_round(room)

            elif msg_type == "CHIT_NEXT" and room.game_type == "chit_pull":
                await self._chit_pull_next(room)

            elif msg_type == "CHIT_COMPLETE" and room.game_type == "chit_pull":
                await self._chit_pull_complete(room, bool(message.get("bonus", False)))

            elif msg_type == "CHIT_SKIP" and room.game_type == "chit_pull":
                await self._chit_pull_skip(room)

            elif msg_type == "CHIT_REDRAW_PLAYER" and room.game_type == "chit_pull":
                await self._chit_pull_redraw_player(room)

            elif msg_type == "CHIT_REDRAW_CHIT" and room.game_type == "chit_pull":
                await self._chit_pull_redraw_chit(room)

            elif msg_type == "MAFIA_SKIP_TIMER" and room.game_type == "mafia":
                await self._advance_mafia_phase(room, reason="manual")

            elif msg_type == "MAFIA_EXTEND_TIMER" and room.game_type == "mafia":
                await self._mafia_extend_timer(room)

            elif msg_type == "QUESTS_FINAL_CALL" and room.game_type == "party_quests":
                await self._party_quests_final_call(room)

            elif msg_type == "QUESTS_REVEAL" and room.game_type == "party_quests":
                await self._party_quests_reveal(room)

            elif msg_type == "SURVEY_REVEAL_ANSWER" and room.game_type == "survey_says":
                await self._survey_says_reveal_answer(room, str(message.get("answer_id") or ""))

            elif msg_type == "SURVEY_STRIKE" and room.game_type == "survey_says":
                await self._survey_says_strike(room)

            elif msg_type == "SURVEY_REVEAL_ALL" and room.game_type == "survey_says":
                await self._survey_says_reveal_all(room)

            elif msg_type == "SURVEY_NEXT_ROUND" and room.game_type == "survey_says":
                await self._survey_says_next_round(room)

            elif msg_type == "SET_TIME_LIMIT":
                if room.state in ("LOBBY", "LEADERBOARD", "PODIUM"):
                    new_limit = message.get("time_limit", 15)
                    if isinstance(new_limit, int) and 5 <= new_limit <= 60:
                        room.time_limit = new_limit

            elif msg_type == "SET_SHOW_VOTES":
                if room.game_type == "wmlt":
                    val = message.get("show_votes")
                    if isinstance(val, bool):
                        room.show_votes = val

            elif msg_type == "END_QUIZ":
                if room.game_type == "musical_chairs":
                    await self._mc_complete_game(room)
                    return
                if room.game_type == "bluff":
                    await self._bluff_complete_game(room)
                    return
                if room.game_type == "two_truths":
                    await self._two_truths_complete_game(room)
                    return
                if room.game_type == "story_chain":
                    await self._story_complete_game(room)
                    return
                if room.game_type == "common_ground":
                    await self._common_complete_game(room)
                    return
                if room.game_type == "find_someone":
                    await self._find_someone_complete_game(room)
                    return
                if room.game_type == "who_am_i":
                    await self._who_am_i_complete_game(room)
                    return
                if room.game_type == "chit_pull":
                    await self._chit_pull_complete_game(room)
                    return
                if room.game_type == "mafia":
                    await self._mafia_complete_game(room)
                    return
                if room.game_type == "party_quests":
                    await self._party_quests_complete_game(room)
                    return
                if room.game_type == "survey_says":
                    await self._survey_says_complete_game(room)
                    return
                if room.game_type in GENERIC_PROMPT_GAME_TYPES:
                    await self._generic_prompt_complete_game(room)
                    return
                if room.game_type in ("would_you_rather", "never_have_i_ever", "word_association", "acronym"):
                    await self._simple_social_complete_game(room)
                    return
                if room.game_type == "photo_clue":
                    await self._photo_clue_complete_game(room)
                    return
                if room.game_type == "poker":
                    await self._poker_complete_game(room)
                    return
                if room.game_type in ("housie", "bingo") and room.state == "BINGO_CALLING":
                    await self._complete_housie(room)
                    return
                if room.state in ("QUESTION", "LEADERBOARD"):
                    if room.timer_task:
                        room.timer_task.cancel()
                        room.timer_task = None
                    if room.game_type == "drawing" and room.drawing_auto_task:
                        room.drawing_auto_task.cancel()
                        room.drawing_auto_task = None
                    room.state = "PODIUM"
                    leaderboard = self.get_leaderboard(room)
                    team_leaderboard = self.get_team_leaderboard(room)
                    podium_msg = {
                        "type": "PODIUM",
                        "leaderboard": leaderboard,
                        "team_leaderboard": team_leaderboard,
                    }
                    if room.game_type == "wmlt":
                        podium_msg["superlatives"] = self._calculate_wmlt_superlatives(room)
                    await room.broadcast(podium_msg)
                    try:
                        from main import game_history
                        summary = self.get_game_summary(room)
                        game_history.append(summary)
                        if len(game_history) > config.MAX_GAME_HISTORY:
                            del game_history[:len(game_history) - config.MAX_GAME_HISTORY]
                        self._mark_game_session_complete(room, summary)
                    except Exception:
                        logger.warning("Could not save game history for room %s", room.room_code)

            elif msg_type == "RESET_ROOM":
                async with room.lock:
                    if room.state != "PODIUM":
                        return
                    new_content_id = message.get("content_id", "")
                    raw_game_type = message.get("game_type", room.game_type)
                    new_game_type = raw_game_type if raw_game_type in ("quiz", "wmlt", "drawing", "housie", "bingo", "musical_chairs", "bluff", "two_truths", "story_chain", "common_ground", "find_someone", "who_am_i", "chit_pull", "mafia", "party_quests", "survey_says", "would_you_rather", "never_have_i_ever", "word_association", "acronym", "photo_clue", "poker") or raw_game_type in GENERIC_PROMPT_GAME_TYPES else room.game_type
                    raw_time_limit = message.get("time_limit", room.time_limit)

                    # Validate time_limit
                    try:
                        new_time_limit = int(raw_time_limit)
                    except (TypeError, ValueError):
                        new_time_limit = room.time_limit
                    new_time_limit = max(5, min(60, new_time_limit))

                    # Validate content BEFORE charging
                    from main import quizzes, mlt_scenarios, drawing_games, housie_games, bingo_games
                    if new_game_type == "wmlt":
                        new_game_data = mlt_scenarios.get(new_content_id)
                    elif new_game_type == "drawing":
                        new_game_data = drawing_games.get(new_content_id)
                    elif new_game_type == "housie":
                        new_game_data = housie_games.get(new_content_id)
                    elif new_game_type == "bingo":
                        new_game_data = bingo_games.get(new_content_id)
                    elif new_game_type == "bluff":
                        new_game_data = validate_bluff_config({})
                    elif new_game_type == "two_truths":
                        new_game_data = validate_two_truths_config({})
                    elif new_game_type == "story_chain":
                        new_game_data = validate_story_chain_config({})
                    elif new_game_type == "common_ground":
                        new_game_data = validate_common_ground_config({})
                    elif new_game_type == "find_someone":
                        new_game_data = validate_find_someone_config({})
                    elif new_game_type == "who_am_i":
                        from main import who_am_i_games
                        new_game_data = who_am_i_games.get(new_content_id) or validate_who_am_i_config({})
                    elif new_game_type == "chit_pull":
                        from main import chit_pull_games
                        new_game_data = chit_pull_games.get(new_content_id) or validate_chit_pull_config({})
                    elif new_game_type == "mafia":
                        new_game_data = validate_mafia_config({})
                    elif new_game_type == "party_quests":
                        new_game_data = validate_party_quests_config({})
                    elif new_game_type == "survey_says":
                        new_game_data = validate_survey_says_config({})
                    elif new_game_type in GENERIC_PROMPT_GAME_TYPES:
                        new_game_data = validate_generic_prompt_config({}, new_game_type)
                    elif new_game_type == "would_you_rather":
                        new_game_data = validate_would_you_rather_config({})
                    elif new_game_type == "never_have_i_ever":
                        new_game_data = validate_never_have_i_ever_config({})
                    elif new_game_type == "word_association":
                        new_game_data = validate_word_association_config({})
                    elif new_game_type == "acronym":
                        new_game_data = validate_acronym_config({})
                    elif new_game_type == "photo_clue":
                        new_game_data = validate_photo_clue_config({})
                    elif new_game_type == "poker":
                        new_game_data = validate_poker_config({})
                    else:
                        new_game_data = quizzes.get(new_content_id)

                    if not new_game_data:
                        logger.warning("RESET_ROOM rejected: content_id %s not found for room %s",
                                       new_content_id, room.room_code)
                        await self._send_to_client(room, client_id, {"type": "ERROR", "message": "Game content not found. Please generate a new game."})
                        return
                    if new_game_type == "drawing":
                        new_game_data = dict(new_game_data)
                        new_game_data["auto_advance"] = bool(message.get("drawing_auto_advance", True))
                        try:
                            inter_round = int(message.get("drawing_inter_round_seconds", 5))
                        except (TypeError, ValueError):
                            inter_round = 5
                        new_game_data["inter_round_seconds"] = max(0, min(30, inter_round))

                    # Check content ownership
                    from main import content_owners, pending_generation_charges
                    owner = content_owners.get(new_content_id)
                    if owner and room.wallet_id and owner != room.wallet_id:
                        logger.warning("RESET_ROOM rejected: content %s owned by %s, room wallet %s",
                                       new_content_id, owner[:8], room.wallet_id[:8])
                        await self._send_to_client(room, client_id, {"type": "ERROR", "message": "You don't have permission to use this content."})
                        return

                    # Charge sparks only after content is validated
                    if not room.wallet_id:
                        await self._send_to_client(room, client_id, {
                            "type": "ERROR",
                            "message": "Internal error: wallet not configured.",
                        })
                        return
                    if (
                        room.billing_mode != "host_app_managed"
                        and pending_generation_charges.get(new_content_id) == room.wallet_id
                    ):
                        required = config.COST_GENERATE + config.COST_ROOM
                        if token_module.db.get_wallet_balance(room.wallet_id) < required:
                            await self._send_to_client(room, client_id, {
                                "type": "INSUFFICIENT_SPARKS",
                                "message": f"You need {required} sparks to use generated content and start a new game.",
                            })
                            return
                        generated_spent, _ = token_module.spend_generate(room.wallet_id)
                        if not generated_spent:
                            await self._send_to_client(room, client_id, {
                                "type": "INSUFFICIENT_SPARKS",
                                "message": f"You need {config.COST_GENERATE} sparks to use generated content.",
                            })
                            return
                        pending_generation_charges.pop(new_content_id, None)
                    if room.billing_mode == "host_app_managed":
                        spent = True
                    else:
                        spent, _ = token_module.spend_room(room.wallet_id)
                    if not spent:
                        await self._send_to_client(room, client_id, {
                            "type": "INSUFFICIENT_SPARKS",
                            "message": f"You need {config.COST_ROOM} sparks to start a new game.",
                        })
                        return

                    room.reset_for_new_game(new_game_data, new_time_limit,
                                            game_type=new_game_type,
                                            content_id=new_content_id)
                    logger.info("Room %s reset for new game (type=%s, content=%s)",
                                room.room_code, new_game_type, new_content_id)
                    await room.broadcast({
                        "type": "ROOM_RESET",
                        "room_code": room.room_code,
                        "game_type": new_game_type,
                        "player_count": len(room.players),
                        "players": [{"nickname": p["nickname"], "avatar": p.get("avatar", "")} for p in room.players.values()],
                    })

            elif msg_type == "TOGGLE_LOCK":
                if room.state == "LOBBY":
                    room.locked = not room.locked
                    await room.broadcast({"type": "ROOM_LOCK_STATUS", "locked": room.locked})

        else:
            if msg_type == "JOIN":
                raw_nick = message.get("nickname", "")
                raw_team = message.get("team", "")
                nickname = (raw_nick if isinstance(raw_nick, str) else "").strip()
                team = (raw_team if isinstance(raw_team, str) else "").strip() or None
                # Sanitize: strip HTML tags and control characters
                nickname = re.sub(r'<[^>]+>', '', nickname)
                nickname = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', nickname).strip()
                if not nickname or len(nickname) > config.MAX_NICKNAME_LENGTH:
                    ws = room.connections.get(client_id)
                    if ws:
                        await ws.send_json({
                            "type": "ERROR",
                            "message": f"Nickname must be 1-{config.MAX_NICKNAME_LENGTH} characters"
                        })
                        await ws.close()
                    return

                # Sanitize team name
                if team:
                    team = re.sub(r'<[^>]+>', '', team)
                    team = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', team).strip()
                    if len(team) > config.MAX_TEAM_NAME_LENGTH:
                        team = team[:config.MAX_TEAM_NAME_LENGTH]
                    if not team:
                        team = None

                # Sanitize and limit avatar length
                avatar = message.get("avatar", "")
                if not isinstance(avatar, str):
                    avatar = ""
                avatar = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', avatar)[:config.MAX_AVATAR_LENGTH]

                # Check for reconnection (disconnected mid-game)
                if nickname in room.disconnected_players:
                    # Verify session token to prevent nickname hijacking
                    provided_token = message.get("session_token", "")
                    expected_token = room.player_tokens.get(nickname, "")
                    if expected_token and not hmac.compare_digest(str(provided_token), expected_token):
                        ws = room.connections.get(client_id)
                        if ws:
                            await ws.send_json({"type": "ERROR", "message": "Nickname is taken"})
                            await ws.close()
                        return
                    saved = room.disconnected_players.pop(nickname)
                    room.players[client_id] = {
                        "nickname": nickname,
                        "score": saved["score"],
                        "prev_rank": saved["prev_rank"],
                        "streak": saved.get("streak", 0),
                        "avatar": saved.get("avatar", avatar),
                    }
                    # Transfer answered status to new client_id
                    old_cid = saved.get("_answered_client_id")
                    if old_cid and old_cid in room.answered_players:
                        room.answered_players.discard(old_cid)
                        room.answered_players.add(client_id)
                    logger.info("Player '%s' reconnected to room %s with score %d", nickname, room.room_code, saved["score"])
                    ws = room.connections.get(client_id)
                    if ws:
                        state_info: dict = {
                            "type": "RECONNECTED",
                            "score": saved["score"],
                            "state": room.state,
                            "game_type": room.game_type,
                            "question_number": room.current_question_index + 1,
                            "total_questions": room.total_rounds(),
                            "avatar": saved.get("avatar", avatar),
                            "players": [{"nickname": p["nickname"], "avatar": p.get("avatar", "")} for p in room.players.values()],
                        }
                        if room.game_type in ("housie", "bingo"):
                            state_info["bingo"] = self._housie_player_state(room, nickname)
                        elif room.game_type == "musical_chairs":
                            state_info["musical_chairs"] = room.mc_public_state()
                        elif room.game_type == "bluff" and room.bluff_state:
                            state_info["bluff"] = bluff_private_sync(room.bluff_state, nickname)
                        elif room.game_type == "two_truths" and room.tt_state:
                            state_info["two_truths"] = tt_private_sync(room.tt_state, nickname, players=room.player_public_list())
                        elif room.game_type == "story_chain" and room.story_state:
                            state_info["story_chain"] = story_private_sync(room.story_state, nickname, players=room.player_public_list())
                        elif room.game_type == "common_ground" and room.common_state:
                            state_info["common_ground"] = common_private_sync(room.common_state, nickname, players=room.player_public_list())
                        elif room.game_type == "find_someone" and room.find_someone_state:
                            state_info["find_someone"] = find_private_sync(room.find_someone_state, nickname, players=room.player_public_list())
                        elif room.game_type == "who_am_i" and room.who_am_i_state:
                            state_info["who_am_i"] = whoami_private_sync(room.who_am_i_state, nickname, players=room.player_public_list())
                        elif room.game_type == "chit_pull" and room.chit_pull_state:
                            state_info["chit_pull"] = chit_pull_public_sync(room.chit_pull_state, players=room.player_public_list())
                        elif room.game_type == "mafia" and room.mafia_state:
                            state_info["mafia"] = mafia_private_sync(room.mafia_state, nickname, players=room.player_public_list())
                        elif room.game_type == "party_quests" and room.party_quests_state:
                            state_info["party_quests"] = quests_private_sync(room.party_quests_state, nickname, players=room.player_public_list())
                        elif room.game_type == "survey_says" and room.survey_says_state:
                            state_info["survey_says"] = survey_public_sync(room.survey_says_state, players=room.player_public_list(), viewer_id=nickname)
                        elif room.game_type in GENERIC_PROMPT_GAME_TYPES and room.generic_prompt_state:
                            state_info["generic_prompt"] = generic_public_state(room.generic_prompt_state, viewer_id=nickname)
                        elif room.game_type in ("would_you_rather", "never_have_i_ever", "word_association", "acronym"):
                            state = getattr(room, self._simple_social_state_attr(room.game_type), {})
                            if state:
                                state_info[self._simple_social_sync_key(room.game_type)] = self._simple_social_public_state(room, nickname)
                        elif room.game_type == "photo_clue" and room.photo_clue_state:
                            state_info["photo_clue"] = self._photo_clue_public_state(room, nickname)
                        elif room.game_type == "poker" and room.poker_state:
                            state_info["poker"] = self._poker_public_state(room, nickname)
                        elif room.state == "QUESTION":
                            round_data = room.current_round_data()
                            if room.game_type == "wmlt":
                                state_info["statement"] = round_data
                                state_info["players"] = [
                                    {"nickname": p["nickname"], "avatar": p.get("avatar", "")}
                                    for p in room.players.values()
                                ]
                            elif room.game_type == "drawing":
                                state_info.update(self._drawing_player_state(room, nickname, round_data))
                            else:
                                player_question = {k: v for k, v in round_data.items() if k != "answer_index"}
                                state_info["question"] = player_question
                                # Include fifty-fifty state if it was used
                                pups = room.power_ups.get(nickname, {})
                                if "fifty_fifty_remove_indices" in pups:
                                    state_info["remove_indices"] = pups["fifty_fifty_remove_indices"]
                            state_info["time_limit"] = room.time_limit
                            elapsed = time.time() - room.question_start_time
                            state_info["time_remaining"] = max(0, room.time_limit - int(elapsed))
                            state_info["is_bonus"] = room.current_question_index in room.bonus_questions
                        state_info["session_token"] = room.player_tokens.get(nickname, "")
                        state_info["power_ups"] = {
                            "double_points": room.power_ups.get(nickname, {}).get("double_points", False),
                            "fifty_fifty": room.power_ups.get(nickname, {}).get("fifty_fifty", False),
                        }
                        await ws.send_json(state_info)
                    await room.broadcast({
                        "type": "PLAYER_RECONNECTED",
                        "nickname": nickname,
                        "player_count": len(room.players),
                        "players": [{"nickname": p["nickname"], "avatar": p.get("avatar", "")} for p in room.players.values()],
                    })
                    return

                # Check for duplicate nickname among active players (case-insensitive)
                existing_id = None
                for pid, pdata in room.players.items():
                    if pdata["nickname"].lower() == nickname.lower():
                        existing_id = pid
                        break

                if existing_id:
                    # Verify session token to prevent nickname hijacking
                    existing_nickname = room.players[existing_id]["nickname"]
                    provided_token = message.get("session_token", "")
                    expected_token = room.player_tokens.get(existing_nickname, "")
                    if expected_token and not hmac.compare_digest(str(provided_token), expected_token):
                        ws = room.connections.get(client_id)
                        if ws:
                            await ws.send_json({"type": "ERROR", "message": "Nickname is taken"})
                            await ws.close()
                        return
                    # Kick the old connection and let the new one take over
                    old_ws = room.connections.pop(existing_id, None)
                    if old_ws:
                        try:
                            await old_ws.send_json({"type": "KICKED", "message": "You joined from another device"})
                            await old_ws.close()
                        except Exception:
                            pass
                    # Transfer player data and answered status to new client_id
                    player_data = room.players.pop(existing_id)
                    room.players[client_id] = player_data
                    if existing_id in room.answered_players:
                        room.answered_players.discard(existing_id)
                        room.answered_players.add(client_id)
                    logger.info("Player '%s' rejoined room %s (replaced old connection)", nickname, room.room_code)

                    ws = room.connections.get(client_id)
                    if ws:
                        state_info = {
                            "type": "RECONNECTED",
                            "score": player_data["score"],
                            "state": room.state,
                            "game_type": room.game_type,
                            "question_number": room.current_question_index + 1,
                            "total_questions": room.total_rounds(),
                            "avatar": player_data.get("avatar", ""),
                            "players": [{"nickname": p["nickname"], "avatar": p.get("avatar", "")} for p in room.players.values()],
                        }
                        if room.game_type in ("housie", "bingo"):
                            state_info["bingo"] = self._housie_player_state(room, player_data["nickname"])
                        elif room.game_type == "musical_chairs":
                            state_info["musical_chairs"] = room.mc_public_state()
                        elif room.game_type == "bluff" and room.bluff_state:
                            state_info["bluff"] = bluff_private_sync(room.bluff_state, player_data["nickname"])
                        elif room.game_type == "two_truths" and room.tt_state:
                            state_info["two_truths"] = tt_private_sync(room.tt_state, player_data["nickname"], players=room.player_public_list())
                        elif room.game_type == "story_chain" and room.story_state:
                            state_info["story_chain"] = story_private_sync(room.story_state, player_data["nickname"], players=room.player_public_list())
                        elif room.game_type == "common_ground" and room.common_state:
                            state_info["common_ground"] = common_private_sync(room.common_state, player_data["nickname"], players=room.player_public_list())
                        elif room.game_type == "find_someone" and room.find_someone_state:
                            state_info["find_someone"] = find_private_sync(room.find_someone_state, player_data["nickname"], players=room.player_public_list())
                        elif room.game_type == "who_am_i" and room.who_am_i_state:
                            state_info["who_am_i"] = whoami_private_sync(room.who_am_i_state, player_data["nickname"], players=room.player_public_list())
                        elif room.game_type == "chit_pull" and room.chit_pull_state:
                            state_info["chit_pull"] = chit_pull_public_sync(room.chit_pull_state, players=room.player_public_list())
                        elif room.game_type == "chit_pull" and room.chit_pull_state:
                            state_info["chit_pull"] = chit_pull_public_sync(room.chit_pull_state, players=room.player_public_list())
                        elif room.game_type == "mafia" and room.mafia_state:
                            state_info["mafia"] = mafia_private_sync(room.mafia_state, player_data["nickname"], players=room.player_public_list())
                        elif room.game_type == "party_quests" and room.party_quests_state:
                            state_info["party_quests"] = quests_private_sync(room.party_quests_state, player_data["nickname"], players=room.player_public_list())
                        elif room.game_type == "survey_says" and room.survey_says_state:
                            state_info["survey_says"] = survey_public_sync(room.survey_says_state, players=room.player_public_list(), viewer_id=player_data["nickname"])
                        elif room.game_type in GENERIC_PROMPT_GAME_TYPES and room.generic_prompt_state:
                            state_info["generic_prompt"] = generic_public_state(room.generic_prompt_state, viewer_id=player_data["nickname"])
                        elif room.game_type in ("would_you_rather", "never_have_i_ever", "word_association", "acronym"):
                            state = getattr(room, self._simple_social_state_attr(room.game_type), {})
                            if state:
                                state_info[self._simple_social_sync_key(room.game_type)] = self._simple_social_public_state(room, player_data["nickname"])
                        elif room.game_type == "photo_clue" and room.photo_clue_state:
                            state_info["photo_clue"] = self._photo_clue_public_state(room, player_data["nickname"])
                        elif room.game_type == "poker" and room.poker_state:
                            state_info["poker"] = self._poker_public_state(room, player_data["nickname"])
                        elif room.state == "QUESTION":
                            round_data = room.current_round_data()
                            if room.game_type == "wmlt":
                                state_info["statement"] = round_data
                                state_info["players"] = [
                                    {"nickname": p["nickname"], "avatar": p.get("avatar", "")}
                                    for p in room.players.values()
                                ]
                            elif room.game_type == "drawing":
                                state_info.update(self._drawing_player_state(room, player_data["nickname"], round_data))
                            else:
                                player_question = {k: v for k, v in round_data.items() if k != "answer_index"}
                                state_info["question"] = player_question
                                # Include fifty-fifty state if it was used
                                pups = room.power_ups.get(nickname, {})
                                if "fifty_fifty_remove_indices" in pups:
                                    state_info["remove_indices"] = pups["fifty_fifty_remove_indices"]
                            state_info["time_limit"] = room.time_limit
                            elapsed = time.time() - room.question_start_time
                            state_info["time_remaining"] = max(0, room.time_limit - int(elapsed))
                            state_info["is_bonus"] = room.current_question_index in room.bonus_questions
                        state_info["session_token"] = room.player_tokens.get(nickname, "")
                        state_info["power_ups"] = {
                            "double_points": room.power_ups.get(nickname, {}).get("double_points", False),
                            "fifty_fifty": room.power_ups.get(nickname, {}).get("fifty_fifty", False),
                        }
                        await ws.send_json(state_info)
                    return

                active_common_ground_join = (
                    room.game_type == "common_ground"
                    and bool(room.common_state)
                    and room.state != "LOBBY"
                    and room.state != COMMON_PHASE_PODIUM
                )
                active_find_someone_join = (
                    room.game_type == "find_someone"
                    and bool(room.find_someone_state)
                    and room.state != "LOBBY"
                    and room.state != FIND_PHASE_PODIUM
                )
                active_party_quests_join = (
                    room.game_type == "party_quests"
                    and bool(room.party_quests_state)
                    and bool(room.party_quests_state.get("config", {}).get("allow_late_join", True))
                    and room.state != "LOBBY"
                    and room.state != QUESTS_PHASE_PODIUM
                )
                active_survey_says_join = (
                    room.game_type == "survey_says"
                    and bool(room.survey_says_state)
                    and bool(room.survey_says_state.get("config", {}).get("allow_late_join", True))
                    and room.state != "LOBBY"
                    and room.state != SURVEY_PHASE_PODIUM
                )
                active_generic_prompt_join = (
                    room.game_type in GENERIC_PROMPT_GAME_TYPES
                    and bool(room.generic_prompt_state)
                    and room.state != "LOBBY"
                    and room.state != GENERIC_PHASE_PODIUM
                )

                if len(room.players) >= config.MAX_PLAYERS_PER_ROOM:
                    conn = room.connections.get(client_id)
                    if conn:
                        await conn.send_json({"type": "ERROR", "message": "Room is full"})
                        await conn.close()
                    return

                if active_common_ground_join:
                    room.players[client_id] = {"nickname": nickname, "score": 0, "prev_rank": 0, "streak": 0, "avatar": avatar}
                    room.power_ups[nickname] = {"double_points": True, "fifty_fifty": True}
                    player_session_token = secrets.token_urlsafe(16)
                    room.player_tokens[nickname] = player_session_token
                    room.common_state = common_add_player_to_team(room.common_state, nickname)
                    self._sync_common_ground_scores_to_players(room)
                    ws = room.connections.get(client_id)
                    if ws:
                        await ws.send_json({
                            "type": "JOINED_ROOM",
                            "room_code": room.room_code,
                            "session_token": player_session_token,
                            "state": room.state,
                            "game_type": "common_ground",
                            "common_ground": common_private_sync(room.common_state, nickname, players=room.player_public_list()),
                        })
                    await room.broadcast({
                        "type": "PLAYER_JOINED",
                        "nickname": nickname,
                        "player_count": len(room.players),
                        "players": [{"nickname": p["nickname"], "avatar": p.get("avatar", "")} for p in room.players.values()]
                    })
                    await self._broadcast_common_ground_sync(room)
                    return

                if active_find_someone_join:
                    room.players[client_id] = {"nickname": nickname, "score": 0, "prev_rank": 0, "streak": 0, "avatar": avatar}
                    room.power_ups[nickname] = {"double_points": True, "fifty_fifty": True}
                    player_session_token = secrets.token_urlsafe(16)
                    room.player_tokens[nickname] = player_session_token
                    room.find_someone_state = find_add_player(room.find_someone_state, nickname, seed=room.find_someone_state.get("started_at"))
                    self._sync_find_someone_scores_to_players(room)
                    ws = room.connections.get(client_id)
                    if ws:
                        await ws.send_json({
                            "type": "JOINED_ROOM",
                            "room_code": room.room_code,
                            "session_token": player_session_token,
                            "state": room.state,
                            "game_type": "find_someone",
                            "find_someone": find_private_sync(room.find_someone_state, nickname, players=room.player_public_list()),
                        })
                    await room.broadcast({
                        "type": "PLAYER_JOINED",
                        "nickname": nickname,
                        "player_count": len(room.players),
                        "players": [{"nickname": p["nickname"], "avatar": p.get("avatar", "")} for p in room.players.values()]
                    })
                    await self._broadcast_find_someone_sync(room)
                    return

                if active_party_quests_join:
                    room.players[client_id] = {"nickname": nickname, "score": 0, "prev_rank": 0, "streak": 0, "avatar": avatar}
                    room.power_ups[nickname] = {"double_points": True, "fifty_fifty": True}
                    player_session_token = secrets.token_urlsafe(16)
                    room.player_tokens[nickname] = player_session_token
                    room.party_quests_state = quests_add_player(room.party_quests_state, nickname, now=time.time())
                    self._sync_party_quests_scores_to_players(room)
                    ws = room.connections.get(client_id)
                    if ws:
                        await ws.send_json({
                            "type": "JOINED_ROOM",
                            "room_code": room.room_code,
                            "session_token": player_session_token,
                            "state": room.state,
                            "game_type": "party_quests",
                            "party_quests": quests_private_sync(room.party_quests_state, nickname, players=room.player_public_list()),
                        })
                    await room.broadcast({
                        "type": "PLAYER_JOINED",
                        "nickname": nickname,
                        "player_count": len(room.players),
                        "players": [{"nickname": p["nickname"], "avatar": p.get("avatar", "")} for p in room.players.values()]
                    })
                    await self._broadcast_party_quests_sync(room)
                    return

                if active_survey_says_join:
                    room.players[client_id] = {"nickname": nickname, "score": 0, "prev_rank": 0, "streak": 0, "avatar": avatar}
                    room.power_ups[nickname] = {"double_points": True, "fifty_fifty": True}
                    player_session_token = secrets.token_urlsafe(16)
                    room.player_tokens[nickname] = player_session_token
                    room.survey_says_state = survey_add_player(room.survey_says_state, nickname)
                    self._sync_survey_says_scores_to_players(room)
                    ws = room.connections.get(client_id)
                    if ws:
                        await ws.send_json({
                            "type": "JOINED_ROOM",
                            "room_code": room.room_code,
                            "session_token": player_session_token,
                            "state": room.state,
                            "game_type": "survey_says",
                            "survey_says": survey_public_sync(room.survey_says_state, players=room.player_public_list(), viewer_id=nickname),
                        })
                    await room.broadcast({
                        "type": "PLAYER_JOINED",
                        "nickname": nickname,
                        "player_count": len(room.players),
                        "players": [{"nickname": p["nickname"], "avatar": p.get("avatar", "")} for p in room.players.values()]
                    })
                    await self._broadcast_survey_says_sync(room)
                    return

                if active_generic_prompt_join:
                    room.players[client_id] = {"nickname": nickname, "score": 0, "prev_rank": 0, "streak": 0, "avatar": avatar}
                    room.power_ups[nickname] = {"double_points": True, "fifty_fifty": True}
                    player_session_token = secrets.token_urlsafe(16)
                    room.player_tokens[nickname] = player_session_token
                    room.generic_prompt_state = generic_add_player(room.generic_prompt_state, nickname)
                    self._sync_generic_prompt_scores_to_players(room)
                    ws = room.connections.get(client_id)
                    if ws:
                        await ws.send_json({
                            "type": "JOINED_ROOM",
                            "room_code": room.room_code,
                            "session_token": player_session_token,
                            "state": room.state,
                            "game_type": room.game_type,
                            "generic_prompt": generic_public_state(room.generic_prompt_state, viewer_id=nickname),
                        })
                    await room.broadcast({
                        "type": "PLAYER_JOINED",
                        "nickname": nickname,
                        "player_count": len(room.players),
                        "players": [{"nickname": p["nickname"], "avatar": p.get("avatar", "")} for p in room.players.values()]
                    })
                    await self._broadcast_generic_prompt_sync(room)
                    return

                # Block new players if room is locked
                if room.locked:
                    conn = room.connections.get(client_id)
                    if conn:
                        await conn.send_json({"type": "ERROR", "message": "Room is locked by the host"})
                        await conn.close()
                    return

                # Block new players if game is in progress
                if room.state != "LOBBY":
                    conn = room.connections.get(client_id)
                    if conn:
                        await conn.send_json({
                            "type": "GAME_IN_PROGRESS",
                            "question_number": room.current_question_index + 1,
                            "total_questions": room.total_rounds(),
                        })
                        await conn.close()
                    return

                room.players[client_id] = {"nickname": nickname, "score": 0, "prev_rank": 0, "streak": 0, "avatar": avatar}
                # Assign team if provided
                if team:
                    room.teams[nickname] = team
                # Initialize power-ups
                room.power_ups[nickname] = {"double_points": True, "fifty_fifty": True}
                # Generate session token for nickname ownership
                player_session_token = secrets.token_urlsafe(16)
                room.player_tokens[nickname] = player_session_token
                # Confirm join to the player (after validation succeeded)
                ws = room.connections.get(client_id)
                if ws:
                    await ws.send_json({"type": "JOINED_ROOM", "room_code": room.room_code, "session_token": player_session_token})
                await room.broadcast({
                    "type": "PLAYER_JOINED",
                    "nickname": nickname,
                    "player_count": len(room.players),
                    "players": [{"nickname": p["nickname"], "avatar": p.get("avatar", "")} for p in room.players.values()]
                })

            elif msg_type == "VOTE" and room.game_type == "wmlt":
                if client_id not in room.players:
                    return
                if room.state != "QUESTION":
                    return
                raw_vote = message.get("voted_for", "")
                voted_for = (raw_vote if isinstance(raw_vote, str) else "").strip()
                nickname = room.players[client_id]["nickname"]
                # Validate voted_for is a player in the room (including disconnected)
                valid_nicknames = set(room.player_nicknames()) | set(room.disconnected_players.keys())
                if voted_for not in valid_nicknames:
                    ws = room.connections.get(client_id)
                    if ws:
                        await ws.send_json({"type": "ERROR", "message": "Invalid vote target"})
                    return

                async with room.lock:
                    if room.state != "QUESTION" or nickname in room.votes:
                        return  # State changed or already voted
                    room.votes[nickname] = voted_for
                    room.answered_players.add(client_id)
                    all_voted = len(room.votes) >= len(room.players)

                ws = room.connections.get(client_id)
                if ws:
                    await ws.send_json({
                        "type": "VOTE_CONFIRMED",
                        "voted_for": voted_for,
                    })

                # Notify organizer about vote progress
                await room.send_to_organizer({
                    "type": "VOTE_COUNT",
                    "voted": len(room.votes),
                    "total": len(room.players),
                })

                if all_voted:
                    await self.end_question(room)

            elif msg_type == "DRAW_OP" and room.game_type == "drawing":
                await self._handle_draw_op(room, client_id, message)

            elif msg_type == "GUESS" and room.game_type == "drawing":
                await self._handle_drawing_guess(room, client_id, message)

            elif msg_type == "BINGO_CLAIM" and room.game_type in ("housie", "bingo"):
                await self._handle_housie_claim(room, client_id, message)

            elif msg_type == "MC_GRAB" and room.game_type == "musical_chairs":
                await self._mc_handle_grab(room, client_id)

            elif msg_type == "BLUFF_PLAY" and room.game_type == "bluff":
                await self._bluff_play(room, client_id, message)

            elif msg_type == "BLUFF_PASS" and room.game_type == "bluff":
                await self._bluff_pass(room, client_id)

            elif msg_type == "BLUFF_CHALLENGE" and room.game_type == "bluff":
                await self._bluff_challenge(room, client_id)

            elif msg_type == "BLUFF_RESOLVE" and room.game_type == "bluff":
                await self._bluff_resolve(room)

            elif msg_type == "BLUFF_CONTINUE" and room.game_type == "bluff":
                await self._bluff_continue(room)

            elif msg_type == "TT_SUBMIT_STATEMENTS" and room.game_type == "two_truths":
                await self._tt_submit_statements(room, client_id, message)

            elif msg_type == "TT_VOTE" and room.game_type == "two_truths":
                await self._tt_vote(room, client_id, message)

            elif msg_type == "STORY_SUBMIT_SENTENCE" and room.game_type == "story_chain":
                await self._story_submit_sentence(room, client_id, message)

            elif msg_type == "COMMON_SUBMIT_FACT" and room.game_type == "common_ground":
                await self._common_submit_fact(room, client_id, message)

            elif msg_type == "COMMON_VOTE" and room.game_type == "common_ground":
                await self._common_vote(room, client_id, message)

            elif msg_type == "FIND_MARK_CELL" and room.game_type == "find_someone":
                await self._find_someone_mark_cell(room, client_id, message)

            elif msg_type == "FIND_CONFIRM_MATCH" and room.game_type == "find_someone":
                await self._find_someone_confirm_match(room, client_id, message)

            elif msg_type == "FIND_CLAIM_PATTERN" and room.game_type == "find_someone":
                await self._find_someone_claim_pattern(room, client_id, message)

            elif msg_type == "WHOAMI_SUBMIT_GUESS" and room.game_type == "who_am_i":
                await self._who_am_i_submit_guess(room, client_id, message)

            elif msg_type == "MAFIA_NIGHT_ACTION" and room.game_type == "mafia":
                await self._mafia_submit_night_action(room, client_id, str(message.get("target") or ""))

            elif msg_type == "MAFIA_NIGHT_READ" and room.game_type == "mafia":
                await self._mafia_submit_night_read(room, client_id, str(message.get("target") or ""))

            elif msg_type == "MAFIA_VOTE" and room.game_type == "mafia":
                await self._mafia_submit_vote(room, client_id, str(message.get("target") or ""))

            elif msg_type == "QUESTS_REQUEST_CONFIRMATION" and room.game_type == "party_quests":
                await self._party_quests_request_confirmation(room, client_id, message)

            elif msg_type == "QUESTS_CONFIRM" and room.game_type == "party_quests":
                await self._party_quests_confirm(room, client_id, message)

            elif msg_type == "SURVEY_SUBMIT_GUESS" and room.game_type == "survey_says":
                await self._survey_says_submit_guess(room, client_id, message)

            elif msg_type in ("GENERIC_CHOICE", "GENERIC_SUBMIT", "GENERIC_VOTE") and room.game_type in GENERIC_PROMPT_GAME_TYPES:
                await self._generic_prompt_player_action(room, client_id, message)

            elif msg_type in ("WYR_VOTE", "NHIE_ANSWER", "WORD_SUBMIT", "ACRO_SUBMIT", "ACRO_VOTE") and room.game_type in ("would_you_rather", "never_have_i_ever", "word_association", "acronym"):
                await self._simple_social_player_action(room, client_id, message)

            elif msg_type in ("PHOTO_CLUE_UPLOAD_READY", "PHOTO_CLUE_GUESS") and room.game_type == "photo_clue":
                await self._photo_clue_player_action(room, client_id, message)

            elif msg_type in ("POKER_STAY", "POKER_FOLD") and room.game_type == "poker":
                await self._poker_player_action(room, client_id, message)

            elif msg_type == "ANSWER":
                if room.game_type in ("wmlt", "drawing", "housie", "bingo", "musical_chairs", "two_truths", "story_chain", "common_ground", "find_someone", "who_am_i", "chit_pull", "mafia", "party_quests", "survey_says", "would_you_rather", "never_have_i_ever", "word_association", "acronym", "photo_clue", "poker") or room.game_type in GENERIC_PROMPT_GAME_TYPES:
                    return  # Other games use their own input messages
                if client_id not in room.players:
                    return
                answer_index = message.get("answer_index")
                # Bounds check to prevent IndexError
                question = room.current_round_data()
                if not question:
                    return
                num_options = len(question.get("options", []))
                if not isinstance(answer_index, int) or not (0 <= answer_index < num_options):
                    return

                async with room.lock:
                    if room.state != "QUESTION" or client_id in room.answered_players:
                        return
                    room.answered_players.add(client_id)
                    all_answered = len(room.answered_players) >= len(room.players)

                # Notify organizer about answer progress
                await room.send_to_organizer({
                    "type": "ANSWER_COUNT",
                    "answered": len(room.answered_players),
                    "total": len(room.players),
                })

                ws = room.connections.get(client_id)
                if not ws:
                    return

                nickname = room.players[client_id]["nickname"]
                correct = answer_index == question["answer_index"]
                time_taken = time.time() - room.question_start_time

                if correct:
                    time_ratio = max(0, 1 - (time_taken / room.time_limit))
                    base_points = int(100 + (900 * time_ratio))  # 100-1000 points

                    # Bonus round (2x base points for everyone)
                    is_bonus = room.current_question_index in room.bonus_questions
                    if is_bonus:
                        base_points *= 2

                    # Streak bonus
                    room.players[client_id]["streak"] = room.players[client_id].get("streak", 0) + 1
                    streak = room.players[client_id]["streak"]
                    multiplier = 1.0
                    for threshold, mult in sorted(config.STREAK_THRESHOLDS.items()):
                        if streak >= threshold:
                            multiplier = mult
                    points = int(base_points * multiplier)

                    # Double points power-up
                    if room.power_ups.get(nickname, {}).get("double_points_active"):
                        points *= 2
                        room.power_ups[nickname]["double_points_active"] = False

                    room.players[client_id]["score"] += points

                    await ws.send_json({
                        "type": "ANSWER_RESULT",
                        "correct": True,
                        "points": points,
                        "streak": streak,
                        "multiplier": multiplier,
                        "is_bonus": is_bonus,
                    })
                else:
                    room.players[client_id]["streak"] = 0
                    await ws.send_json({
                        "type": "ANSWER_RESULT",
                        "correct": False,
                        "points": 0,
                        "streak": 0,
                        "multiplier": 1.0,
                        "is_bonus": room.current_question_index in room.bonus_questions,
                    })

                # Log answer for game history
                room.answer_log.append({
                    "question_index": room.current_question_index,
                    "nickname": nickname,
                    "answer_index": answer_index,
                    "correct": correct,
                    "time_taken": round(time_taken, 2),
                })

                if all_answered:
                    await self.end_question(room)

            elif msg_type == "USE_POWER_UP":
                if room.state != "QUESTION" or room.game_type == "wmlt":
                    return  # Power-ups are quiz-only
                power_up = message.get("power_up")
                nickname = room.players.get(client_id, {}).get("nickname")
                if not nickname or power_up not in ("double_points", "fifty_fifty"):
                    return
                ws = room.connections.get(client_id)
                if not ws:
                    return

                async with room.lock:
                    pups = room.power_ups.get(nickname, {})
                    if not pups.get(power_up):
                        await ws.send_json({"type": "ERROR", "message": "Power-up already used"})
                        return
                    if power_up == "double_points":
                        pups["double_points"] = False
                        pups["double_points_active"] = True
                        await ws.send_json({"type": "POWER_UP_ACTIVATED", "power_up": "double_points"})
                    elif power_up == "fifty_fifty":
                        if room.game_type == "wmlt":
                            return  # 50/50 not applicable to WMLT
                        pups["fifty_fifty"] = False
                        question = room.current_round_data()
                        if not question:
                            return
                        correct_idx = question["answer_index"]
                        wrong_indices = [i for i in range(len(question["options"])) if i != correct_idx]
                        import random
                        remove = random.sample(wrong_indices, min(2, len(wrong_indices)))
                        pups["fifty_fifty_remove_indices"] = remove
                        await ws.send_json({
                            "type": "POWER_UP_ACTIVATED",
                            "power_up": "fifty_fifty",
                            "remove_indices": remove,
                        })

    def _start_housie_round(self, room: Room):
        room.housie_deck = create_bingo_call_deck(room.quiz.get("deck", [])) if room.game_type == "bingo" else create_call_deck()
        room.housie_called = []
        room.housie_winners = []
        room.housie_claimed_patterns = set()
        room.housie_claim_log = []
        room.housie_tickets = {}
        room.housie_play_mode = str(room.quiz.get("play_mode") or "beginner").lower()
        if room.housie_play_mode not in ("beginner", "pro"):
            room.housie_play_mode = "beginner"
        room.housie_caller_mode = str(room.quiz.get("caller_mode") or "manual").lower()
        if room.housie_caller_mode not in ("manual", "auto"):
            room.housie_caller_mode = "manual"
        try:
            room.housie_auto_interval_seconds = max(3, min(30, int(room.quiz.get("auto_interval_seconds") or 8)))
        except (TypeError, ValueError):
            room.housie_auto_interval_seconds = 8
        room.housie_auto_pause_on_claim = bool(room.quiz.get("auto_pause_on_claim", True))
        room.housie_auto_status = "stopped"
        room.housie_next_auto_call_at = None
        for idx, (client_id, player) in enumerate(room.players.items()):
            nickname = player["nickname"]
            ticket_id = f"{room.room_code}-{idx + 1}"
            if room.game_type == "bingo":
                room.housie_tickets[nickname] = generate_bingo_card(
                    ticket_id,
                    client_id,
                    nickname,
                    room.quiz.get("deck", []),
                    free_center=bool(room.quiz.get("free_center", True)),
                    free_center_label=str(room.quiz.get("free_center_label") or "FREE"),
                    seed=secrets.randbits(32),
                )
            else:
                room.housie_tickets[nickname] = generate_ticket(ticket_id, client_id, nickname)

    def _housie_patterns(self, room: Room) -> list[dict]:
        patterns = room.quiz.get("patterns") if isinstance(room.quiz.get("patterns"), list) else []
        known = {pattern["id"]: pattern for pattern in patterns if isinstance(pattern, dict) and pattern.get("id")}
        order = BINGO_PATTERN_ORDER if room.game_type == "bingo" else PATTERN_ORDER
        return [known[pid] for pid in order if pid in known]

    def _housie_can_undo_last_call(self, room: Room) -> bool:
        if room.state != "BINGO_CALLING" or not room.housie_called:
            return False
        last_call_index = len(room.housie_called)
        return not any(w.get("called_count", 0) >= last_call_index for w in room.housie_winners)

    def _housie_terminal_claim_winners(self, room: Room) -> list[dict]:
        terminal_pattern_ids = {
            pattern["id"]
            for pattern in self._housie_patterns(room)
            if pattern.get("terminal", pattern.get("id") == "full_house")
        }
        return [winner for winner in room.housie_winners if winner.get("pattern_id") in terminal_pattern_ids]

    def _housie_terminal_claim_pending(self, room: Room) -> bool:
        return room.state == "BINGO_CALLING" and bool(self._housie_terminal_claim_winners(room))

    def _housie_claim_rejection_message(self, reason: str, pattern_label: str = "that prize") -> str:
        messages = {
            "unknown_pattern": "That prize is not available in this game.",
            "already_awarded": f"{pattern_label} has already been claimed.",
            "already_claimed_by_you": f"You already claimed {pattern_label} for this call.",
            "not_complete": f"{pattern_label} is not complete yet. Keep playing!",
            "no_calls_yet": "No numbers have been called yet.",
            "latest_number_not_in_pattern": f"{pattern_label} must be completed by the latest call.",
            "stale_claim": f"{pattern_label} was completed before the latest call, so it cannot be claimed now.",
        }
        return messages.get(reason, f"{pattern_label} cannot be claimed yet.")

    def _housie_public_state(self, room: Room) -> dict:
        terminal_winners = self._housie_terminal_claim_winners(room)
        return {
            "game_title": room.game_title(),
            "state": room.state,
            "called_items": room.housie_called,
            "latest_item": room.housie_called[-1] if room.housie_called else None,
            "remaining_count": len(room.housie_deck),
            "can_undo_last_call": self._housie_can_undo_last_call(room),
            "patterns": self._housie_patterns(room),
            "winners": room.housie_winners,
            "claim_log": room.housie_claim_log[-10:],
            "play_mode": room.housie_play_mode,
            "caller_mode": room.housie_caller_mode,
            "auto_status": room.housie_auto_status,
            "auto_interval_seconds": room.housie_auto_interval_seconds,
            "auto_pause_on_claim": room.housie_auto_pause_on_claim,
            "next_auto_call_at": room.housie_next_auto_call_at,
            "claim_requires_latest_call": bool(room.quiz.get("claim_requires_latest_call", room.game_type == "housie")),
            "layout": room.quiz.get("layout", "housie_3x9_15" if room.game_type == "housie" else "bingo_5x5_free"),
            "free_center": bool(room.quiz.get("free_center", False)),
            "terminal_claim_pending": bool(terminal_winners) and room.state == "BINGO_CALLING",
            "terminal_claim_called_count": terminal_winners[0].get("called_count") if terminal_winners else None,
        }

    def _housie_player_state(self, room: Room, nickname: str) -> dict:
        return {
            **self._housie_public_state(room),
            "ticket": room.housie_tickets.get(nickname),
        }

    async def _broadcast_housie_sync(self, room: Room):
        base = {
            "type": "BINGO_SYNC",
            "game_type": room.game_type,
            "bingo": self._housie_public_state(room),
            "player_count": len(room.players),
            "players": [{"nickname": p["nickname"], "avatar": p.get("avatar", "")} for p in room.players.values()],
        }
        for client_id, ws in list(room.connections.items()):
            if client_id in room.players:
                nickname = room.players[client_id]["nickname"]
                payload = dict(base)
                payload["bingo"] = self._housie_player_state(room, nickname)
                try:
                    await ws.send_json(payload)
                except Exception:
                    room._remove_connection(client_id)
        await room.emit_pending_player_event()
        await room.send_to_organizer(base)
        for ws in list(room.spectators.values()):
            try:
                await ws.send_json(base)
            except Exception:
                pass

    def _start_bluff_game(self, room: Room):
        nicknames = [player["nickname"] for player in room.players.values()]
        room.bluff_config = validate_bluff_config(room.quiz, player_count=len(nicknames))
        room.bluff_state = bluff_create_initial_state(nicknames, room.bluff_config, seed=secrets.randbits(32))
        room.state = room.bluff_state["phase"]
        room.answer_log = []

    async def _broadcast_bluff_sync(self, room: Room):
        if not room.bluff_state:
            return
        public = {
            "type": "BLUFF_SYNC",
            "game_type": "bluff",
            "bluff": bluff_public_sync(room.bluff_state),
            "player_count": len(room.players),
            "players": [{"nickname": p["nickname"], "avatar": p.get("avatar", "")} for p in room.players.values()],
        }
        for client_id, ws in list(room.connections.items()):
            if client_id in room.players:
                nickname = room.players[client_id]["nickname"]
                payload = dict(public)
                payload["bluff"] = bluff_private_sync(room.bluff_state, nickname)
                try:
                    await ws.send_json(payload)
                except Exception:
                    room._remove_connection(client_id)
        await room.emit_pending_player_event()
        await room.send_to_organizer(public)
        for ws in list(room.spectators.values()):
            try:
                await ws.send_json(public)
            except Exception:
                pass

    def _sync_bluff_phase_to_room(self, room: Room):
        room.state = room.bluff_state.get("phase") or room.state

    async def _bluff_play(self, room: Room, client_id: str, message: dict):
        if client_id not in room.players or not room.bluff_state:
            return
        nickname = room.players[client_id]["nickname"]
        card_ids = message.get("card_ids")
        if not isinstance(card_ids, list):
            await self._send_to_client(room, client_id, {"type": "ERROR", "message": "Choose cards to play"})
            return
        try:
            async with room.lock:
                room.bluff_state = bluff_play_cards(room.bluff_state, nickname, [str(card_id) for card_id in card_ids], now=time.time())
                self._sync_bluff_phase_to_room(room)
                room.answer_log.append({"kind": "play", "nickname": nickname, "count": len(card_ids), "claimed_rank": room.bluff_state.get("last_claim", {}).get("claimed_rank")})
        except ValueError as exc:
            await self._send_to_client(room, client_id, {"type": "ERROR", "message": str(exc)})
            return
        await self._broadcast_bluff_sync(room)

    async def _bluff_pass(self, room: Room, client_id: str):
        if client_id not in room.players or not room.bluff_state:
            return
        nickname = room.players[client_id]["nickname"]
        try:
            async with room.lock:
                room.bluff_state = bluff_pass_turn(room.bluff_state, nickname)
                self._sync_bluff_phase_to_room(room)
                room.answer_log.append({"kind": "pass", "nickname": nickname})
        except ValueError as exc:
            await self._send_to_client(room, client_id, {"type": "ERROR", "message": str(exc)})
            return
        await self._broadcast_bluff_sync(room)

    async def _bluff_challenge(self, room: Room, client_id: str):
        if client_id not in room.players or not room.bluff_state:
            return
        nickname = room.players[client_id]["nickname"]
        try:
            async with room.lock:
                room.bluff_state = bluff_challenge_claim(room.bluff_state, nickname)
                self._sync_bluff_phase_to_room(room)
                claim = room.bluff_state.get("last_claim") or {}
                room.answer_log.append({
                    "kind": "challenge",
                    "challenger": nickname,
                    "actor": claim.get("actor_id"),
                    "truthful": claim.get("truthful"),
                    "loser": claim.get("loser_id"),
                })
        except ValueError as exc:
            await self._send_to_client(room, client_id, {"type": "ERROR", "message": str(exc)})
            return
        await self._broadcast_bluff_sync(room)

    async def _bluff_resolve(self, room: Room):
        if not room.bluff_state:
            return
        try:
            async with room.lock:
                room.bluff_state = bluff_resolve_unchallenged(room.bluff_state)
                self._sync_bluff_phase_to_room(room)
                room.answer_log.append({"kind": "unchallenged"})
        except ValueError:
            return
        await self._broadcast_bluff_sync(room)
        if room.bluff_state.get("phase") == BLUFF_PHASE_PODIUM:
            await self._bluff_complete_game(room)

    async def _bluff_continue(self, room: Room):
        if not room.bluff_state:
            return
        try:
            async with room.lock:
                if room.bluff_state.get("phase") == BLUFF_PHASE_REVEAL:
                    room.bluff_state = bluff_continue_after_reveal(room.bluff_state)
                elif room.bluff_state.get("phase") == BLUFF_PHASE_CHALLENGE:
                    room.bluff_state = bluff_resolve_unchallenged(room.bluff_state)
                else:
                    return
                self._sync_bluff_phase_to_room(room)
        except ValueError:
            return
        await self._broadcast_bluff_sync(room)
        if room.bluff_state.get("phase") == BLUFF_PHASE_PODIUM:
            await self._bluff_complete_game(room)

    async def _bluff_complete_game(self, room: Room):
        if room.state == "PODIUM":
            return
        if room.bluff_state:
            room.bluff_state["phase"] = BLUFF_PHASE_PODIUM
        room.state = "PODIUM"
        leaderboard = self.get_leaderboard(room)
        await room.broadcast({
            "type": "PODIUM",
            "game_type": "bluff",
            "leaderboard": leaderboard,
            "team_leaderboard": [],
            "bluff": bluff_public_sync(room.bluff_state) if room.bluff_state else {},
        })
        try:
            from main import game_history
            summary = self.get_game_summary(room)
            game_history.append(summary)
            if len(game_history) > config.MAX_GAME_HISTORY:
                del game_history[:len(game_history) - config.MAX_GAME_HISTORY]
            self._mark_game_session_complete(room, summary)
        except Exception:
            logger.warning("Could not save Bluff history for room %s", room.room_code)

    def _start_two_truths_game(self, room: Room):
        nicknames = [player["nickname"] for player in room.players.values()]
        room.tt_config = validate_two_truths_config(room.quiz)
        room.tt_state = tt_create_initial_state(nicknames, room.tt_config, seed=secrets.randbits(32))
        room.state = room.tt_state["phase"]
        room.answer_log = []

    def _sync_two_truths_phase_to_room(self, room: Room):
        room.state = room.tt_state.get("phase") or room.state

    def _sync_two_truths_scores_to_players(self, room: Room):
        scores = room.tt_state.get("scores", {}) if room.tt_state else {}
        for player in room.players.values():
            player["score"] = int(scores.get(player.get("nickname"), player.get("score", 0)))

    async def _broadcast_two_truths_sync(self, room: Room):
        if not room.tt_state:
            return
        players = room.player_public_list()
        public = {
            "type": "TT_SYNC",
            "game_type": "two_truths",
            "two_truths": tt_public_sync(room.tt_state, players=players),
            "player_count": len(room.players),
            "players": players,
            "leaderboard": self.get_leaderboard(room),
        }
        for client_id, ws in list(room.connections.items()):
            if client_id in room.players:
                nickname = room.players[client_id]["nickname"]
                payload = dict(public)
                payload["two_truths"] = tt_private_sync(room.tt_state, nickname, players=players)
                try:
                    await ws.send_json(payload)
                except Exception:
                    room._remove_connection(client_id)
        await room.emit_pending_player_event()
        await room.send_to_organizer(public)
        for ws in list(room.spectators.values()):
            try:
                await ws.send_json(public)
            except Exception:
                pass

    async def _tt_submit_statements(self, room: Room, client_id: str, message: dict):
        if client_id not in room.players or not room.tt_state:
            return
        nickname = room.players[client_id]["nickname"]
        try:
            async with room.lock:
                room.tt_state = tt_submit_statements(room.tt_state, nickname, message.get("statements") or [], now=time.time())
                self._sync_two_truths_phase_to_room(room)
                room.answer_log.append({"kind": "submission", "nickname": nickname})
        except ValueError as exc:
            await self._send_to_client(room, client_id, {"type": "ERROR", "message": str(exc)})
            return
        await self._broadcast_two_truths_sync(room)

    async def _tt_start_reveal(self, room: Room, client_id: str):
        if not room.tt_state:
            return
        try:
            async with room.lock:
                room.tt_state = tt_start_reveal(room.tt_state)
                self._sync_two_truths_phase_to_room(room)
        except ValueError as exc:
            await self._send_to_client(room, client_id, {"type": "ERROR", "message": str(exc)})
            return
        await self._broadcast_two_truths_sync(room)

    async def _tt_vote(self, room: Room, client_id: str, message: dict):
        if client_id not in room.players or not room.tt_state:
            return
        nickname = room.players[client_id]["nickname"]
        try:
            async with room.lock:
                room.tt_state = tt_submit_vote(room.tt_state, nickname, str(message.get("statement_id") or ""))
                self._sync_two_truths_phase_to_room(room)
        except ValueError as exc:
            await self._send_to_client(room, client_id, {"type": "ERROR", "message": str(exc)})
            return
        await self._broadcast_two_truths_sync(room)

    async def _tt_next_step(self, room: Room):
        if not room.tt_state:
            return
        try:
            async with room.lock:
                phase = room.tt_state.get("phase")
                if phase == "TT_SUBMISSION":
                    room.tt_state = tt_start_reveal(room.tt_state)
                elif phase == "TT_VOTING":
                    room.tt_state = tt_score_current_round(room.tt_state)
                    self._sync_two_truths_scores_to_players(room)
                    result = room.tt_state.get("round_result") or {}
                    room.answer_log.append({"kind": "round_result", **result})
                elif phase == "TT_RESULT":
                    room.tt_state = tt_next_author(room.tt_state)
                else:
                    return
                self._sync_two_truths_phase_to_room(room)
        except ValueError:
            return
        await self._broadcast_two_truths_sync(room)
        if room.tt_state.get("phase") == TT_PHASE_PODIUM:
            await self._two_truths_complete_game(room)

    async def _two_truths_complete_game(self, room: Room):
        if room.state == "PODIUM":
            return
        if room.tt_state:
            room.tt_state["phase"] = TT_PHASE_PODIUM
        self._sync_two_truths_scores_to_players(room)
        room.state = "PODIUM"
        leaderboard = self.get_leaderboard(room)
        await room.broadcast({
            "type": "PODIUM",
            "game_type": "two_truths",
            "leaderboard": leaderboard,
            "team_leaderboard": [],
            "two_truths": tt_public_sync(room.tt_state, players=room.player_public_list()) if room.tt_state else {},
        })
        try:
            from main import game_history
            summary = self.get_game_summary(room)
            summary["two_truths_standings"] = tt_final_standings(room.tt_state) if room.tt_state else []
            game_history.append(summary)
            if len(game_history) > config.MAX_GAME_HISTORY:
                del game_history[:len(game_history) - config.MAX_GAME_HISTORY]
            self._mark_game_session_complete(room, summary)
        except Exception:
            logger.warning("Could not save Two Truths history for room %s", room.room_code)

    def _poker_public_state(self, room: Room, viewer_id: str | None = None) -> dict:
        return poker_public_sync(room.poker_state, viewer_id) if room.poker_state else {}

    def _start_poker_game(self, room: Room):
        nicknames = [player["nickname"] for player in room.players.values()]
        room.poker_config = validate_poker_config(room.quiz)
        room.poker_state = poker_create_initial_state(nicknames, room.poker_config, seed=room.room_code, now=time.time())
        room.poker_completed_sent = False
        room.state = room.poker_state["phase"]
        room.answer_log = []
        self._sync_poker_scores_to_players(room)

    def _sync_poker_scores_to_players(self, room: Room):
        stacks = room.poker_state.get("stacks", {}) if room.poker_state else {}
        for player in room.players.values():
            player["score"] = int(stacks.get(player.get("nickname"), player.get("score", 0)))

    async def _broadcast_poker_sync(self, room: Room):
        if not room.poker_state:
            return
        players = room.player_public_list()
        public = {
            "type": "POKER_SYNC",
            "game_type": "poker",
            "poker": self._poker_public_state(room),
            "player_count": len(room.players),
            "players": players,
            "leaderboard": self.get_leaderboard(room),
        }
        for client_id, ws in list(room.connections.items()):
            if client_id in room.players:
                nickname = room.players[client_id]["nickname"]
                payload = dict(public)
                payload["poker"] = self._poker_public_state(room, nickname)
                try:
                    await ws.send_json(payload)
                except Exception:
                    room._remove_connection(client_id)
        await room.emit_pending_player_event()
        await room.send_to_organizer(public)
        for ws in list(room.spectators.values()):
            try:
                await ws.send_json(public)
            except Exception:
                pass

    async def _poker_player_action(self, room: Room, client_id: str, message: dict):
        if client_id not in room.players:
            return
        nickname = room.players[client_id]["nickname"]
        decision = "fold" if message.get("type") == "POKER_FOLD" else "stay"
        try:
            async with room.lock:
                room.poker_state = poker_submit_decision(room.poker_state, nickname, decision)
                room.state = room.poker_state.get("phase", room.state)
                room.answer_log.append({"kind": "poker_decision", "nickname": nickname, "decision": decision})
                self._sync_poker_scores_to_players(room)
        except ValueError as exc:
            await self._send_to_client(room, client_id, {"type": "ERROR", "message": str(exc)})
            return
        await self._broadcast_poker_sync(room)
        if room.poker_state.get("phase") == POKER_PHASE_PODIUM:
            await self._poker_complete_game(room)

    async def _poker_reveal(self, room: Room):
        try:
            async with room.lock:
                room.poker_state = poker_reveal_hand(room.poker_state)
                room.state = room.poker_state.get("phase", room.state)
                self._sync_poker_scores_to_players(room)
        except ValueError:
            return
        await self._broadcast_poker_sync(room)
        if room.poker_state.get("phase") == POKER_PHASE_PODIUM:
            await self._poker_complete_game(room)

    async def _poker_next_hand(self, room: Room):
        try:
            async with room.lock:
                room.poker_state = poker_start_next_hand(room.poker_state, now=time.time())
                room.state = room.poker_state.get("phase", room.state)
                self._sync_poker_scores_to_players(room)
        except ValueError:
            return
        await self._broadcast_poker_sync(room)
        if room.poker_state.get("phase") == POKER_PHASE_PODIUM:
            await self._poker_complete_game(room)

    async def _poker_complete_game(self, room: Room):
        if room.poker_completed_sent:
            return
        room.poker_completed_sent = True
        self._sync_poker_scores_to_players(room)
        room.state = "PODIUM"
        leaderboard = self.get_leaderboard(room)
        await room.broadcast({
            "type": "PODIUM",
            "game_type": "poker",
            "leaderboard": leaderboard,
            "team_leaderboard": [],
            "poker": self._poker_public_state(room),
        })
        try:
            from main import game_history
            summary = self.get_game_summary(room)
            game_history.append(summary)
            if len(game_history) > config.MAX_GAME_HISTORY:
                del game_history[:len(game_history) - config.MAX_GAME_HISTORY]
            self._mark_game_session_complete(room, summary)
        except Exception:
            logger.warning("Could not save Party Poker history for room %s", room.room_code)

    def _photo_clue_public_state(self, room: Room, viewer_id: str | None = None) -> dict:
        if not room.photo_clue_state:
            return {}
        state = photo_public_state(room.photo_clue_state)
        if viewer_id:
            state["private_prompts"] = photo_private_prompt_for_player(room.photo_clue_state, viewer_id)
            assignments = room.photo_clue_state.get("assignments") or []
            index = int(room.photo_clue_state.get("current_round_index", 0))
            assignment = assignments[index] if 0 <= index < len(assignments) else None
            if assignment:
                if assignment.get("clue_giver_id") == viewer_id:
                    state["secret_prompt"] = assignment.get("prompt")
                guesses = assignment.get("guesses") or {}
                if viewer_id in guesses:
                    state["your_guess"] = guesses[viewer_id].get("guess", "")
                    state["your_guess_correct"] = bool(guesses[viewer_id].get("correct"))
        return state

    def _start_photo_clue_game(self, room: Room):
        nicknames = [player["nickname"] for player in room.players.values()]
        room.photo_clue_config = validate_photo_clue_config(room.quiz)
        room.photo_clue_state = photo_create_initial_state(nicknames, room.photo_clue_config, now=time.time())
        room.photo_clue_completed_sent = False
        room.state = room.photo_clue_state["phase"]
        room.answer_log = []

    async def _broadcast_photo_clue_sync(self, room: Room):
        if not room.photo_clue_state:
            return
        players = room.player_public_list()
        public = {
            "type": "PHOTO_CLUE_SYNC",
            "game_type": "photo_clue",
            "photo_clue": self._photo_clue_public_state(room),
            "player_count": len(room.players),
            "players": players,
            "leaderboard": self.get_leaderboard(room),
        }
        for client_id, ws in list(room.connections.items()):
            if client_id in room.players:
                nickname = room.players[client_id]["nickname"]
                payload = dict(public)
                payload["photo_clue"] = self._photo_clue_public_state(room, nickname)
                try:
                    await ws.send_json(payload)
                except Exception:
                    room._remove_connection(client_id)
        await room.emit_pending_player_event()
        await room.send_to_organizer(public)
        for ws in list(room.spectators.values()):
            try:
                await ws.send_json(public)
            except Exception:
                pass

    def _sync_photo_scores_to_players(self, room: Room):
        scores = room.photo_clue_state.get("scores", {}) if room.photo_clue_state else {}
        for player in room.players.values():
            player["score"] = int(scores.get(player.get("nickname"), player.get("score", 0)))

    async def _photo_clue_player_action(self, room: Room, client_id: str, message: dict):
        if client_id not in room.players:
            return
        nickname = room.players[client_id]["nickname"]
        try:
            async with room.lock:
                if message.get("type") == "PHOTO_CLUE_UPLOAD_READY":
                    asset_id = str(message.get("asset_id") or "").strip()
                    asset = media_store.get_asset(asset_id) if asset_id else None
                    image_url = getattr(asset, "url", "") if asset else str(message.get("image_url") or "")
                    if asset is not None and getattr(asset, "status", "") not in ("ready", "finalized", "active"):
                        raise ValueError("Photo upload is not ready yet")
                    room.photo_clue_state = photo_submit_photo(room.photo_clue_state, nickname, asset_id, image_url, now=time.time())
                    room.answer_log.append({"kind": "photo", "nickname": nickname, "asset_id": asset_id})
                else:
                    room.photo_clue_state, correct = photo_submit_guess(room.photo_clue_state, nickname, str(message.get("guess") or ""), now=time.time())
                    room.answer_log.append({"kind": "guess", "nickname": nickname, "correct": correct})
                self._sync_photo_scores_to_players(room)
                room.state = room.photo_clue_state.get("phase", room.state)
        except ValueError as exc:
            await self._send_to_client(room, client_id, {"type": "ERROR", "message": str(exc)})
            return
        await self._broadcast_photo_clue_sync(room)

    async def _photo_clue_reveal(self, room: Room):
        try:
            async with room.lock:
                room.photo_clue_state = photo_reveal_round(room.photo_clue_state)
                self._sync_photo_scores_to_players(room)
                room.state = room.photo_clue_state.get("phase", room.state)
        except ValueError:
            return
        await self._broadcast_photo_clue_sync(room)

    async def _photo_clue_next_round(self, room: Room):
        try:
            async with room.lock:
                room.photo_clue_state = photo_next_round(room.photo_clue_state, now=time.time())
                self._sync_photo_scores_to_players(room)
                room.state = room.photo_clue_state.get("phase", room.state)
        except ValueError:
            return
        await self._broadcast_photo_clue_sync(room)
        if room.photo_clue_state.get("phase") == PHOTO_PHASE_PODIUM:
            await self._photo_clue_complete_game(room)

    async def _photo_clue_complete_game(self, room: Room):
        if room.photo_clue_completed_sent:
            return
        room.photo_clue_completed_sent = True
        self._sync_photo_scores_to_players(room)
        room.state = "PODIUM"
        leaderboard = self.get_leaderboard(room)
        await room.broadcast({
            "type": "PODIUM",
            "game_type": "photo_clue",
            "leaderboard": leaderboard,
            "team_leaderboard": [],
            "photo_clue": self._photo_clue_public_state(room),
        })
        try:
            from main import game_history
            summary = self.get_game_summary(room)
            game_history.append(summary)
            if len(game_history) > config.MAX_GAME_HISTORY:
                del game_history[:len(game_history) - config.MAX_GAME_HISTORY]
            self._mark_game_session_complete(room, summary)
        except Exception:
            logger.warning("Could not save Photo Clue history for room %s", room.room_code)

    def _start_generic_prompt_game(self, room: Room):
        nicknames = [player["nickname"] for player in room.players.values()]
        room.generic_prompt_config = validate_generic_prompt_config(room.quiz, room.game_type)
        room.generic_prompt_state = generic_create_initial_state(
            nicknames,
            room.game_type,
            room.generic_prompt_config,
            now=time.time(),
        )
        room.generic_prompt_completed_sent = False
        self._sync_generic_prompt_phase_to_room(room)
        self._sync_generic_prompt_scores_to_players(room)
        room.answer_log = []

    def _sync_generic_prompt_phase_to_room(self, room: Room):
        if room.generic_prompt_state:
            room.state = str(room.generic_prompt_state.get("phase") or "GENERIC_SUBMITTING")
            room.current_question_index = int(room.generic_prompt_state.get("current_round_index", 0))

    def _sync_generic_prompt_scores_to_players(self, room: Room):
        scores = room.generic_prompt_state.get("scores", {}) if room.generic_prompt_state else {}
        for pdata in room.players.values():
            nickname = pdata.get("nickname")
            pdata["score"] = int(scores.get(nickname, pdata.get("score", 0)) or 0)

    async def _broadcast_generic_prompt_sync(self, room: Room):
        if not room.generic_prompt_state:
            return
        players = room.player_public_list()
        self._sync_generic_prompt_phase_to_room(room)
        self._sync_generic_prompt_scores_to_players(room)
        public = {
            "type": "GENERIC_PROMPT_SYNC",
            "game_type": room.game_type,
            "generic_prompt": generic_public_state(room.generic_prompt_state),
            "player_count": len(room.players),
            "players": players,
            "leaderboard": self.get_leaderboard(room),
        }
        if room.organizer:
            host_payload = dict(public)
            host_payload["generic_prompt"] = generic_public_state(room.generic_prompt_state, host=True)
            await room.send_to_organizer(host_payload)
        for spec_id, ws in list(room.spectators.items()):
            try:
                await ws.send_json(public)
            except Exception:
                room._remove_connection(spec_id)
        for client_id, pdata in list(room.players.items()):
            ws = room.connections.get(client_id)
            if not ws:
                continue
            payload = dict(public)
            payload["generic_prompt"] = generic_public_state(room.generic_prompt_state, viewer_id=pdata.get("nickname", ""))
            try:
                await ws.send_json(payload)
            except Exception:
                room._remove_connection(client_id)
        await room.emit_pending_player_event()

    async def _generic_prompt_player_action(self, room: Room, client_id: str, message: dict):
        if client_id not in room.players or not room.generic_prompt_state:
            return
        nickname = room.players[client_id].get("nickname", "")
        try:
            async with room.lock:
                if message.get("type") == "GENERIC_CHOICE":
                    room.generic_prompt_state = generic_submit_choice(
                        room.generic_prompt_state,
                        nickname,
                        str(message.get("choice") or ""),
                    )
                    room.answer_log.append({"kind": "generic_choice", "nickname": nickname})
                elif message.get("type") == "GENERIC_VOTE":
                    room.generic_prompt_state = generic_submit_vote(
                        room.generic_prompt_state,
                        nickname,
                        str(message.get("entry_id") or ""),
                    )
                    room.answer_log.append({"kind": "generic_vote", "nickname": nickname})
                else:
                    room.generic_prompt_state = generic_submit_text(
                        room.generic_prompt_state,
                        nickname,
                        str(message.get("text") or ""),
                    )
                    room.answer_log.append({"kind": "generic_submission", "nickname": nickname})
                self._sync_generic_prompt_phase_to_room(room)
        except ValueError as exc:
            await self._send_to_client(room, client_id, {"type": "ERROR", "message": str(exc)})
            return
        await self._broadcast_generic_prompt_sync(room)

    async def _generic_prompt_start_voting(self, room: Room):
        if not room.generic_prompt_state:
            return
        try:
            async with room.lock:
                room.generic_prompt_state = generic_start_voting(room.generic_prompt_state)
                self._sync_generic_prompt_phase_to_room(room)
        except ValueError as exc:
            await self._send_to_organizer_error(room, str(exc))
            return
        await self._broadcast_generic_prompt_sync(room)

    async def _generic_prompt_reveal(self, room: Room):
        if not room.generic_prompt_state:
            return
        try:
            async with room.lock:
                room.generic_prompt_state = generic_reveal_round(room.generic_prompt_state, now=time.time())
                self._sync_generic_prompt_phase_to_room(room)
                self._sync_generic_prompt_scores_to_players(room)
        except ValueError as exc:
            await self._send_to_organizer_error(room, str(exc))
            return
        await self._broadcast_generic_prompt_sync(room)

    async def _generic_prompt_next_round(self, room: Room):
        if not room.generic_prompt_state:
            return
        try:
            async with room.lock:
                room.generic_prompt_state = generic_next_round(room.generic_prompt_state, now=time.time())
                self._sync_generic_prompt_phase_to_room(room)
                self._sync_generic_prompt_scores_to_players(room)
        except ValueError as exc:
            await self._send_to_organizer_error(room, str(exc))
            return
        await self._broadcast_generic_prompt_sync(room)
        if room.generic_prompt_state.get("phase") == GENERIC_PHASE_PODIUM:
            await self._generic_prompt_complete_game(room)

    async def _generic_prompt_complete_game(self, room: Room):
        if room.generic_prompt_completed_sent:
            return
        room.generic_prompt_completed_sent = True
        if room.generic_prompt_state:
            room.generic_prompt_state["phase"] = GENERIC_PHASE_PODIUM
            room.generic_prompt_state["completed_at"] = room.generic_prompt_state.get("completed_at") or time.time()
        self._sync_generic_prompt_scores_to_players(room)
        room.state = "PODIUM"
        leaderboard = self.get_leaderboard(room)
        await room.broadcast({
            "type": "PODIUM",
            "game_type": room.game_type,
            "leaderboard": leaderboard,
            "team_leaderboard": [],
            "generic_prompt": generic_public_state(room.generic_prompt_state) if room.generic_prompt_state else {},
        })
        try:
            from main import game_history
            summary = self.get_game_summary(room)
            summary["winners"] = generic_standings(room.generic_prompt_state)[:3] if room.generic_prompt_state else []
            game_history.append(summary)
            if len(game_history) > config.MAX_GAME_HISTORY:
                del game_history[:len(game_history) - config.MAX_GAME_HISTORY]
            self._mark_game_session_complete(room, summary)
        except Exception:
            logger.warning("Could not save %s history for room %s", room.game_type, room.room_code)

    def _simple_social_state_attr(self, game_type: str) -> str:
        return {
            "would_you_rather": "wyr_state",
            "never_have_i_ever": "nhie_state",
            "word_association": "word_state",
            "acronym": "acro_state",
        }[game_type]

    def _simple_social_sync_key(self, game_type: str) -> str:
        return {
            "would_you_rather": "would_you_rather",
            "never_have_i_ever": "never_have_i_ever",
            "word_association": "word_association",
            "acronym": "acronym",
        }[game_type]

    def _simple_social_public_state(self, room: Room, viewer_id: str | None = None) -> dict:
        if room.game_type == "would_you_rather":
            return wyr_public_state(room.wyr_state, viewer_id)
        if room.game_type == "never_have_i_ever":
            return nhie_public_state(room.nhie_state, viewer_id)
        if room.game_type == "word_association":
            return word_public_state(room.word_state, viewer_id)
        if room.game_type == "acronym":
            return acro_public_state(room.acro_state, viewer_id)
        return {}

    def _simple_social_standings(self, room: Room) -> list[dict]:
        if room.game_type == "would_you_rather" and room.wyr_state:
            return wyr_standings(room.wyr_state)
        if room.game_type == "never_have_i_ever" and room.nhie_state:
            return nhie_standings(room.nhie_state)
        if room.game_type == "word_association" and room.word_state:
            return word_standings(room.word_state)
        if room.game_type == "acronym" and room.acro_state:
            return acro_standings(room.acro_state)
        return []

    def _start_simple_social_game(self, room: Room):
        nicknames = [player["nickname"] for player in room.players.values()]
        room.simple_social_completed_sent = False
        if room.game_type == "would_you_rather":
            room.wyr_config = validate_would_you_rather_config(room.quiz)
            room.wyr_state = wyr_create_initial_state(nicknames, room.wyr_config, now=time.time())
            room.state = room.wyr_state["phase"]
        elif room.game_type == "never_have_i_ever":
            room.nhie_config = validate_never_have_i_ever_config(room.quiz)
            room.nhie_state = nhie_create_initial_state(nicknames, room.nhie_config, now=time.time())
            room.state = room.nhie_state["phase"]
        elif room.game_type == "word_association":
            room.word_config = validate_word_association_config(room.quiz)
            room.word_state = word_create_initial_state(nicknames, room.word_config, now=time.time())
            room.state = room.word_state["phase"]
        elif room.game_type == "acronym":
            room.acro_config = validate_acronym_config(room.quiz)
            room.acro_state = acro_create_initial_state(nicknames, room.acro_config, now=time.time())
            room.state = room.acro_state["phase"]
        room.answer_log = []

    def _sync_simple_social_phase_to_room(self, room: Room):
        state = getattr(room, self._simple_social_state_attr(room.game_type), {})
        room.state = state.get("phase") or room.state

    def _sync_simple_social_scores_to_players(self, room: Room):
        state = getattr(room, self._simple_social_state_attr(room.game_type), {})
        scores = state.get("scores", {}) if state else {}
        for player in room.players.values():
            player["score"] = int(scores.get(player.get("nickname"), player.get("score", 0)))

    async def _broadcast_simple_social_sync(self, room: Room):
        state = getattr(room, self._simple_social_state_attr(room.game_type), {})
        if not state:
            return
        key = self._simple_social_sync_key(room.game_type)
        players = room.player_public_list()
        public = {
            "type": "SIMPLE_SOCIAL_SYNC",
            "game_type": room.game_type,
            key: self._simple_social_public_state(room),
            "player_count": len(room.players),
            "players": players,
            "leaderboard": self.get_leaderboard(room),
        }
        for client_id, ws in list(room.connections.items()):
            if client_id in room.players:
                nickname = room.players[client_id]["nickname"]
                payload = dict(public)
                payload[key] = self._simple_social_public_state(room, nickname)
                try:
                    await ws.send_json(payload)
                except Exception:
                    room._remove_connection(client_id)
        await room.emit_pending_player_event()
        await room.send_to_organizer(public)
        for ws in list(room.spectators.values()):
            try:
                await ws.send_json(public)
            except Exception:
                pass

    async def _simple_social_player_action(self, room: Room, client_id: str, message: dict):
        if client_id not in room.players:
            return
        nickname = room.players[client_id]["nickname"]
        try:
            async with room.lock:
                if room.game_type == "would_you_rather":
                    room.wyr_state = wyr_submit_vote(room.wyr_state, nickname, str(message.get("choice") or ""))
                    room.answer_log.append({"kind": "vote", "nickname": nickname, "choice": message.get("choice")})
                elif room.game_type == "never_have_i_ever":
                    room.nhie_state = nhie_submit_answer(room.nhie_state, nickname, str(message.get("answer") or ""))
                    room.answer_log.append({"kind": "answer", "nickname": nickname, "answer": message.get("answer")})
                elif room.game_type == "word_association":
                    room.word_state = word_submit_word(room.word_state, nickname, str(message.get("word") or message.get("text") or ""))
                    room.answer_log.append({"kind": "word", "nickname": nickname})
                elif room.game_type == "acronym":
                    if message.get("type") == "ACRO_VOTE":
                        room.acro_state = acro_submit_vote(room.acro_state, nickname, str(message.get("entry_id") or ""))
                        room.answer_log.append({"kind": "vote", "nickname": nickname, "entry_id": message.get("entry_id")})
                    else:
                        room.acro_state = acro_submit_expansion(room.acro_state, nickname, str(message.get("text") or message.get("expansion") or ""))
                        room.answer_log.append({"kind": "submission", "nickname": nickname})
                self._sync_simple_social_phase_to_room(room)
        except ValueError as exc:
            await self._send_to_client(room, client_id, {"type": "ERROR", "message": str(exc)})
            return
        await self._broadcast_simple_social_sync(room)

    async def _simple_social_reveal(self, room: Room):
        try:
            async with room.lock:
                if room.game_type == "would_you_rather":
                    room.wyr_state = wyr_reveal_round(room.wyr_state, now=time.time())
                elif room.game_type == "never_have_i_ever":
                    room.nhie_state = nhie_reveal_round(room.nhie_state, now=time.time())
                elif room.game_type == "word_association":
                    room.word_state = word_reveal_round(room.word_state, now=time.time())
                elif room.game_type == "acronym":
                    room.acro_state = acro_reveal_round(room.acro_state, now=time.time())
                self._sync_simple_social_scores_to_players(room)
                self._sync_simple_social_phase_to_room(room)
        except ValueError:
            return
        await self._broadcast_simple_social_sync(room)

    async def _simple_social_next_round(self, room: Room):
        try:
            async with room.lock:
                if room.game_type == "would_you_rather":
                    room.wyr_state = wyr_next_round(room.wyr_state, now=time.time())
                elif room.game_type == "never_have_i_ever":
                    room.nhie_state = nhie_next_round(room.nhie_state, now=time.time())
                elif room.game_type == "word_association":
                    room.word_state = word_next_round(room.word_state, now=time.time())
                elif room.game_type == "acronym":
                    room.acro_state = acro_next_round(room.acro_state, now=time.time())
                self._sync_simple_social_phase_to_room(room)
        except ValueError:
            return
        await self._broadcast_simple_social_sync(room)
        state = getattr(room, self._simple_social_state_attr(room.game_type), {})
        if state.get("phase") in {WYR_PHASE_PODIUM, NHIE_PHASE_PODIUM, WORD_PHASE_PODIUM, ACRO_PHASE_PODIUM}:
            await self._simple_social_complete_game(room)

    async def _acronym_start_voting(self, room: Room):
        try:
            async with room.lock:
                room.acro_state = acro_start_voting(room.acro_state)
                self._sync_simple_social_phase_to_room(room)
        except ValueError:
            return
        await self._broadcast_simple_social_sync(room)

    async def _simple_social_complete_game(self, room: Room):
        if room.simple_social_completed_sent:
            return
        room.simple_social_completed_sent = True
        self._sync_simple_social_scores_to_players(room)
        room.state = "PODIUM"
        key = self._simple_social_sync_key(room.game_type)
        leaderboard = self.get_leaderboard(room)
        await room.broadcast({
            "type": "PODIUM",
            "game_type": room.game_type,
            "leaderboard": leaderboard,
            "team_leaderboard": [],
            key: self._simple_social_public_state(room),
        })
        try:
            from main import game_history
            summary = self.get_game_summary(room)
            summary["winners"] = self._simple_social_standings(room)[:3]
            game_history.append(summary)
            if len(game_history) > config.MAX_GAME_HISTORY:
                del game_history[:len(game_history) - config.MAX_GAME_HISTORY]
            self._mark_game_session_complete(room, summary)
        except Exception:
            logger.warning("Could not save %s history for room %s", room.game_type, room.room_code)

    def _start_story_chain_game(self, room: Room):
        nicknames = [player["nickname"] for player in room.players.values()]
        room.story_config = validate_story_chain_config(room.quiz)
        room.story_state = story_create_initial_state(nicknames, room.story_config, now=time.time(), seed=secrets.randbits(32))
        room.state = room.story_state["phase"]
        room.answer_log = []

    def _sync_story_chain_phase_to_room(self, room: Room):
        room.state = room.story_state.get("phase") or room.state

    def _sync_story_chain_scores_to_players(self, room: Room):
        scores = room.story_state.get("scores", {}) if room.story_state else {}
        for player in room.players.values():
            player["score"] = int(scores.get(player.get("nickname"), player.get("score", 0)))

    async def _broadcast_story_chain_sync(self, room: Room):
        if not room.story_state:
            return
        players = room.player_public_list()
        public = {
            "type": "STORY_SYNC",
            "game_type": "story_chain",
            "story_chain": story_public_sync(room.story_state, players=players),
            "player_count": len(room.players),
            "players": players,
            "leaderboard": self.get_leaderboard(room),
        }
        for client_id, ws in list(room.connections.items()):
            if client_id in room.players:
                nickname = room.players[client_id]["nickname"]
                payload = dict(public)
                payload["story_chain"] = story_private_sync(room.story_state, nickname, players=players)
                try:
                    await ws.send_json(payload)
                except Exception:
                    room._remove_connection(client_id)
        await room.emit_pending_player_event()
        await room.send_to_organizer(public)
        for ws in list(room.spectators.values()):
            try:
                await ws.send_json(public)
            except Exception:
                pass

    async def _story_submit_sentence(self, room: Room, client_id: str, message: dict):
        if client_id not in room.players or not room.story_state:
            return
        nickname = room.players[client_id]["nickname"]
        try:
            async with room.lock:
                room.story_state = story_submit_sentence(room.story_state, nickname, message.get("text") or "", now=time.time())
                self._sync_story_chain_scores_to_players(room)
                self._sync_story_chain_phase_to_room(room)
                room.answer_log.append({"kind": "story_sentence", "nickname": nickname})
        except ValueError as exc:
            await self._send_to_client(room, client_id, {"type": "ERROR", "message": str(exc)})
            return
        await self._broadcast_story_chain_sync(room)

    async def _story_skip_turn(self, room: Room):
        if not room.story_state:
            return
        try:
            async with room.lock:
                room.story_state = story_timeout_turn(room.story_state, now=time.time())
                self._sync_story_chain_scores_to_players(room)
                self._sync_story_chain_phase_to_room(room)
                room.answer_log.append({"kind": "story_skip"})
        except ValueError:
            return
        await self._broadcast_story_chain_sync(room)

    async def _story_next_reveal_step(self, room: Room):
        if not room.story_state:
            return
        became_podium = False
        try:
            async with room.lock:
                if room.story_state.get("phase") == STORY_PHASE_PODIUM:
                    return
                room.story_state = story_next_reveal_step(room.story_state)
                became_podium = room.story_state.get("phase") == STORY_PHASE_PODIUM
                if not became_podium:
                    self._sync_story_chain_phase_to_room(room)
        except ValueError:
            return
        if became_podium:
            await self._story_complete_game(room)
            return
        await self._broadcast_story_chain_sync(room)

    async def _story_complete_game(self, room: Room):
        if room.state == "PODIUM":
            return
        if room.story_state:
            room.story_state["phase"] = STORY_PHASE_PODIUM
            if room.story_state.get("reveal_index", -1) < len(room.story_state.get("sentences", [])) - 1:
                room.story_state["reveal_index"] = len(room.story_state.get("sentences", [])) - 1
        self._sync_story_chain_scores_to_players(room)
        room.state = "PODIUM"
        leaderboard = self.get_leaderboard(room)
        await room.broadcast({
            "type": "PODIUM",
            "game_type": "story_chain",
            "leaderboard": leaderboard,
            "team_leaderboard": [],
            "story_chain": story_public_sync(room.story_state, players=room.player_public_list()) if room.story_state else {},
        })
        try:
            from main import game_history
            summary = self.get_game_summary(room)
            summary["story_chain_standings"] = story_final_standings(room.story_state) if room.story_state else []
            game_history.append(summary)
            if len(game_history) > config.MAX_GAME_HISTORY:
                del game_history[:len(game_history) - config.MAX_GAME_HISTORY]
            self._mark_game_session_complete(room, summary)
        except Exception:
            logger.warning("Could not save Story Chain history for room %s", room.room_code)

    def _start_common_ground_game(self, room: Room):
        nicknames = [player["nickname"] for player in room.players.values()]
        room.common_config = validate_common_ground_config(room.quiz)
        room.common_state = common_create_initial_state(nicknames, room.common_config, now=time.time(), seed=secrets.randbits(32))
        room.state = room.common_state["phase"]
        room.answer_log = []

    def _sync_common_ground_phase_to_room(self, room: Room):
        room.state = room.common_state.get("phase") or room.state

    def _sync_common_ground_scores_to_players(self, room: Room):
        if not room.common_state:
            return
        scores = room.common_state.get("scores", {})
        player_team = {}
        for team in room.common_state.get("teams", []):
            for player_id in team.get("player_ids", []):
                player_team[player_id] = team.get("id")
        for player in room.players.values():
            team_id = player_team.get(player.get("nickname"))
            player["score"] = int(scores.get(team_id, player.get("score", 0)))

    async def _broadcast_common_ground_sync(self, room: Room):
        if not room.common_state:
            return
        players = room.player_public_list()
        public = {
            "type": "COMMON_SYNC",
            "game_type": "common_ground",
            "common_ground": common_public_sync(room.common_state, players=players),
            "player_count": len(room.players),
            "players": players,
            "leaderboard": self.get_leaderboard(room),
        }
        for client_id, ws in list(room.connections.items()):
            if client_id in room.players:
                nickname = room.players[client_id]["nickname"]
                payload = dict(public)
                payload["common_ground"] = common_private_sync(room.common_state, nickname, players=players)
                try:
                    await ws.send_json(payload)
                except Exception:
                    room._remove_connection(client_id)
        await room.emit_pending_player_event()
        await room.send_to_organizer(public)
        for ws in list(room.spectators.values()):
            try:
                await ws.send_json(public)
            except Exception:
                pass

    async def _common_submit_fact(self, room: Room, client_id: str, message: dict):
        if client_id not in room.players or not room.common_state:
            return
        nickname = room.players[client_id]["nickname"]
        try:
            async with room.lock:
                room.common_state = common_submit_fact(room.common_state, nickname, message.get("text") or "", now=time.time())
                self._sync_common_ground_phase_to_room(room)
                room.answer_log.append({"kind": "common_fact", "nickname": nickname})
        except ValueError as exc:
            await self._send_to_client(room, client_id, {"type": "ERROR", "message": str(exc)})
            return
        await self._broadcast_common_ground_sync(room)

    async def _common_start_reveal(self, room: Room):
        if not room.common_state:
            return
        try:
            async with room.lock:
                room.common_state = common_start_reveal(room.common_state, now=time.time())
                self._sync_common_ground_phase_to_room(room)
        except ValueError:
            return
        await self._broadcast_common_ground_sync(room)

    async def _common_start_voting(self, room: Room):
        if not room.common_state:
            return
        try:
            async with room.lock:
                room.common_state = common_start_voting(room.common_state, now=time.time())
                self._sync_common_ground_phase_to_room(room)
        except ValueError:
            return
        await self._broadcast_common_ground_sync(room)

    async def _common_vote(self, room: Room, client_id: str, message: dict):
        if client_id not in room.players or not room.common_state:
            return
        nickname = room.players[client_id]["nickname"]
        try:
            async with room.lock:
                room.common_state = common_submit_vote(room.common_state, nickname, str(message.get("submission_id") or ""))
                self._sync_common_ground_phase_to_room(room)
        except ValueError as exc:
            await self._send_to_client(room, client_id, {"type": "ERROR", "message": str(exc)})
            return
        await self._broadcast_common_ground_sync(room)

    async def _common_score_round(self, room: Room):
        if not room.common_state:
            return
        try:
            async with room.lock:
                room.common_state = common_score_round(room.common_state, now=time.time())
                self._sync_common_ground_scores_to_players(room)
                self._sync_common_ground_phase_to_room(room)
                room.answer_log.append({"kind": "common_round_result", "round": room.common_state.get("round_index", 0) + 1})
        except ValueError:
            return
        await self._broadcast_common_ground_sync(room)

    async def _common_next_round(self, room: Room):
        if not room.common_state:
            return
        became_podium = False
        try:
            async with room.lock:
                room.common_state = common_next_round(room.common_state, now=time.time())
                became_podium = room.common_state.get("phase") == COMMON_PHASE_PODIUM
                if not became_podium:
                    self._sync_common_ground_phase_to_room(room)
        except ValueError:
            return
        if became_podium:
            await self._common_complete_game(room)
            return
        await self._broadcast_common_ground_sync(room)

    async def _common_complete_game(self, room: Room):
        if room.state == "PODIUM":
            return
        if room.common_state:
            room.common_state["phase"] = COMMON_PHASE_PODIUM
        self._sync_common_ground_scores_to_players(room)
        room.state = "PODIUM"
        leaderboard = self.get_leaderboard(room)
        await room.broadcast({
            "type": "PODIUM",
            "game_type": "common_ground",
            "leaderboard": leaderboard,
            "team_leaderboard": [],
            "common_ground": common_public_sync(room.common_state, players=room.player_public_list()) if room.common_state else {},
        })
        try:
            from main import game_history
            summary = self.get_game_summary(room)
            summary["common_ground_standings"] = common_final_standings(room.common_state) if room.common_state else []
            game_history.append(summary)
            if len(game_history) > config.MAX_GAME_HISTORY:
                del game_history[:len(game_history) - config.MAX_GAME_HISTORY]
            self._mark_game_session_complete(room, summary)
        except Exception:
            logger.warning("Could not save Common Ground history for room %s", room.room_code)

    def _start_find_someone_game(self, room: Room):
        nicknames = [player["nickname"] for player in room.players.values()]
        room.find_someone_config = validate_find_someone_config(room.quiz)
        room.find_someone_state = find_create_initial_state(
            nicknames,
            room.find_someone_config,
            now=time.time(),
            seed=secrets.randbits(32),
        )
        room.state = room.find_someone_state["phase"]
        room.answer_log = []
        self._sync_find_someone_scores_to_players(room)

    def _sync_find_someone_phase_to_room(self, room: Room):
        if room.find_someone_state:
            room.state = room.find_someone_state.get("phase") or room.state

    def _sync_find_someone_scores_to_players(self, room: Room):
        if not room.find_someone_state:
            return
        standings = {row["player_id"]: row for row in find_final_standings(room.find_someone_state)}
        for player in room.players.values():
            row = standings.get(player.get("nickname"), {})
            player["score"] = int(row.get("score", player.get("score", 0)))

    async def _broadcast_find_someone_sync(self, room: Room):
        if not room.find_someone_state:
            return
        players = room.player_public_list()
        self._sync_find_someone_phase_to_room(room)
        public = {
            "type": "FIND_SYNC",
            "game_type": "find_someone",
            "find_someone": find_public_sync(room.find_someone_state, players=players),
            "player_count": len(room.players),
            "players": players,
            "leaderboard": self.get_leaderboard(room),
        }
        for client_id, ws in list(room.connections.items()):
            if client_id in room.players:
                nickname = room.players[client_id]["nickname"]
                payload = dict(public)
                payload["find_someone"] = find_private_sync(room.find_someone_state, nickname, players=players)
                try:
                    await ws.send_json(payload)
                except Exception:
                    room._remove_connection(client_id)
        await room.emit_pending_player_event()
        await room.send_to_organizer(public)
        for ws in list(room.spectators.values()):
            try:
                await ws.send_json(public)
            except Exception:
                pass

    async def _find_someone_mark_cell(self, room: Room, client_id: str, message: dict):
        if client_id not in room.players or not room.find_someone_state:
            return
        nickname = room.players[client_id]["nickname"]
        try:
            async with room.lock:
                room.find_someone_state, _ = find_mark_cell(
                    room.find_someone_state,
                    nickname,
                    str(message.get("prompt_id") or ""),
                    str(message.get("matched_player_id") or ""),
                    now=time.time(),
                )
                self._sync_find_someone_scores_to_players(room)
                self._sync_find_someone_phase_to_room(room)
                room.answer_log.append({"kind": "find_mark", "nickname": nickname})
        except ValueError as exc:
            await self._send_to_client(room, client_id, {"type": "ERROR", "message": str(exc)})
            return
        await self._broadcast_find_someone_sync(room)

    async def _find_someone_confirm_match(self, room: Room, client_id: str, message: dict):
        if client_id not in room.players or not room.find_someone_state:
            return
        nickname = room.players[client_id]["nickname"]
        try:
            async with room.lock:
                room.find_someone_state = find_confirm_match(
                    room.find_someone_state,
                    nickname,
                    str(message.get("request_id") or ""),
                    bool(message.get("accepted", False)),
                    now=time.time(),
                )
                self._sync_find_someone_scores_to_players(room)
                self._sync_find_someone_phase_to_room(room)
        except ValueError as exc:
            await self._send_to_client(room, client_id, {"type": "ERROR", "message": str(exc)})
            return
        await self._broadcast_find_someone_sync(room)

    async def _find_someone_claim_pattern(self, room: Room, client_id: str, message: dict):
        if client_id not in room.players or not room.find_someone_state:
            return
        nickname = room.players[client_id]["nickname"]
        became_podium = False
        try:
            async with room.lock:
                room.find_someone_state, claim = find_claim_pattern(
                    room.find_someone_state,
                    nickname,
                    str(message.get("pattern_id") or ""),
                    now=time.time(),
                )
                became_podium = room.find_someone_state.get("phase") == FIND_PHASE_PODIUM
                self._sync_find_someone_scores_to_players(room)
                self._sync_find_someone_phase_to_room(room)
                room.answer_log.append({"kind": "find_claim", "nickname": nickname, "pattern": claim.get("pattern_label")})
        except ValueError as exc:
            await self._send_to_client(room, client_id, {"type": "ERROR", "message": str(exc)})
            return
        if became_podium:
            await self._find_someone_complete_game(room)
            return
        await self._broadcast_find_someone_sync(room)

    async def _find_someone_complete_game(self, room: Room):
        if room.state == "PODIUM":
            return
        if room.find_someone_state:
            room.find_someone_state["phase"] = FIND_PHASE_PODIUM
            room.find_someone_state["completed_at"] = room.find_someone_state.get("completed_at") or time.time()
        self._sync_find_someone_scores_to_players(room)
        room.state = "PODIUM"
        leaderboard = self.get_leaderboard(room)
        await room.broadcast({
            "type": "PODIUM",
            "game_type": "find_someone",
            "leaderboard": leaderboard,
            "team_leaderboard": [],
            "find_someone": find_public_sync(room.find_someone_state, players=room.player_public_list()) if room.find_someone_state else {},
        })
        try:
            from main import game_history
            summary = self.get_game_summary(room)
            summary["find_someone_standings"] = find_final_standings(room.find_someone_state) if room.find_someone_state else []
            game_history.append(summary)
            if len(game_history) > config.MAX_GAME_HISTORY:
                del game_history[:len(game_history) - config.MAX_GAME_HISTORY]
            self._mark_game_session_complete(room, summary)
        except Exception:
            logger.warning("Could not save Find Someone Who history for room %s", room.room_code)

    def _start_who_am_i_game(self, room: Room):
        room.who_am_i_config = validate_who_am_i_config(room.quiz)
        room.who_am_i_state = whoami_create_initial_state(
            [p["nickname"] for p in room.players.values() if p.get("nickname")],
            room.who_am_i_config,
            now=time.time(),
        )
        room.current_question_index = 0
        self._sync_who_am_i_phase_to_room(room)
        self._sync_who_am_i_scores_to_players(room)

    def _sync_who_am_i_phase_to_room(self, room: Room):
        if room.who_am_i_state:
            room.state = str(room.who_am_i_state.get("phase") or "WHOAMI_ROUND")
            room.current_question_index = int(room.who_am_i_state.get("current_round_index", 0) or 0)

    def _sync_who_am_i_scores_to_players(self, room: Room):
        scores = room.who_am_i_state.get("scores", {}) if room.who_am_i_state else {}
        for pdata in room.players.values():
            nickname = pdata.get("nickname")
            pdata["score"] = int(scores.get(nickname, 0) or 0)

    async def _broadcast_who_am_i_sync(self, room: Room):
        if not room.who_am_i_state:
            return
        players = room.player_public_list()
        public = {
            "type": "WHOAMI_SYNC",
            "game_type": "who_am_i",
            "who_am_i": whoami_public_sync(room.who_am_i_state, players=players),
            "player_count": len(room.players),
            "players": players,
            "leaderboard": self.get_leaderboard(room),
        }
        for client_id, ws in list(room.connections.items()):
            if client_id in room.players:
                nickname = room.players[client_id]["nickname"]
                payload = dict(public)
                payload["who_am_i"] = whoami_private_sync(room.who_am_i_state, nickname, players=players)
                try:
                    await ws.send_json(payload)
                except Exception:
                    room._remove_connection(client_id)
        await room.emit_pending_player_event()
        await room.send_to_organizer(public)
        for ws in list(room.spectators.values()):
            try:
                await ws.send_json(public)
            except Exception:
                pass

    async def _who_am_i_submit_guess(self, room: Room, client_id: str, message: dict):
        if client_id not in room.players or not room.who_am_i_state:
            return
        nickname = room.players[client_id]["nickname"]
        try:
            async with room.lock:
                room.who_am_i_state, result = whoami_submit_guess(
                    room.who_am_i_state,
                    nickname,
                    str(message.get("guess") or ""),
                    now=time.time(),
                )
                self._sync_who_am_i_scores_to_players(room)
                self._sync_who_am_i_phase_to_room(room)
                room.answer_log.append({
                    "kind": "who_am_i_guess",
                    "nickname": nickname,
                    "round": room.who_am_i_state.get("current_round_index", 0) + 1,
                    "correct": bool(result.get("correct")),
                })
        except ValueError as exc:
            await self._send_to_client(room, client_id, {"type": "ERROR", "message": str(exc)})
            return
        await self._send_to_client(room, client_id, {"type": "WHOAMI_GUESS_RESULT", **result})
        await self._broadcast_who_am_i_sync(room)

    async def _who_am_i_next_clue(self, room: Room):
        if not room.who_am_i_state:
            return
        try:
            async with room.lock:
                room.who_am_i_state = whoami_next_clue(room.who_am_i_state, now=time.time())
                self._sync_who_am_i_phase_to_room(room)
        except ValueError:
            return
        await self._broadcast_who_am_i_sync(room)

    async def _who_am_i_reveal_answer(self, room: Room):
        if not room.who_am_i_state:
            return
        try:
            async with room.lock:
                room.who_am_i_state = whoami_reveal_answer(room.who_am_i_state, now=time.time())
                self._sync_who_am_i_phase_to_room(room)
        except ValueError:
            return
        await self._broadcast_who_am_i_sync(room)

    async def _who_am_i_next_round(self, room: Room):
        if not room.who_am_i_state:
            return
        became_podium = False
        try:
            async with room.lock:
                room.who_am_i_state = whoami_next_round(room.who_am_i_state, now=time.time())
                became_podium = room.who_am_i_state.get("phase") == WHOAMI_PHASE_PODIUM
                if not became_podium:
                    self._sync_who_am_i_phase_to_room(room)
        except ValueError:
            return
        if became_podium:
            await self._who_am_i_complete_game(room)
            return
        await self._broadcast_who_am_i_sync(room)

    async def _who_am_i_complete_game(self, room: Room):
        if room.state == "PODIUM":
            return
        if room.who_am_i_state:
            room.who_am_i_state["phase"] = WHOAMI_PHASE_PODIUM
        self._sync_who_am_i_scores_to_players(room)
        room.state = "PODIUM"
        leaderboard = self.get_leaderboard(room)
        await room.broadcast({
            "type": "PODIUM",
            "game_type": "who_am_i",
            "leaderboard": leaderboard,
            "team_leaderboard": [],
            "who_am_i": whoami_public_sync(room.who_am_i_state, players=room.player_public_list()) if room.who_am_i_state else {},
        })
        try:
            from main import game_history
            summary = self.get_game_summary(room)
            summary["who_am_i_standings"] = whoami_final_standings(room.who_am_i_state) if room.who_am_i_state else []
            game_history.append(summary)
            if len(game_history) > config.MAX_GAME_HISTORY:
                del game_history[:len(game_history) - config.MAX_GAME_HISTORY]
            self._mark_game_session_complete(room, summary)
        except Exception:
            logger.warning("Could not save Who Am I? history for room %s", room.room_code)

    def _start_chit_pull_game(self, room: Room):
        room.chit_pull_config = validate_chit_pull_config(room.quiz)
        room.chit_pull_state = chit_pull_create_initial_state(
            [p["nickname"] for p in room.players.values() if p.get("nickname")],
            room.chit_pull_config,
            now=time.time(),
            seed=secrets.randbits(32),
        )
        room.current_question_index = 0
        self._sync_chit_pull_phase_to_room(room)
        self._sync_chit_pull_scores_to_players(room)

    def _sync_chit_pull_phase_to_room(self, room: Room):
        if room.chit_pull_state:
            room.state = str(room.chit_pull_state.get("phase") or "CHIT_READY")
            room.current_question_index = int(room.chit_pull_state.get("round_index", 0) or 0)

    def _sync_chit_pull_scores_to_players(self, room: Room):
        scores = room.chit_pull_state.get("scores", {}) if room.chit_pull_state else {}
        for pdata in room.players.values():
            nickname = pdata.get("nickname")
            pdata["score"] = int(scores.get(nickname, 0) or 0)

    async def _broadcast_chit_pull_sync(self, room: Room):
        if not room.chit_pull_state:
            return
        players = room.player_public_list()
        public = {
            "type": "CHIT_SYNC",
            "game_type": "chit_pull",
            "chit_pull": chit_pull_public_sync(room.chit_pull_state, players=players),
            "player_count": len(room.players),
            "players": players,
            "leaderboard": self.get_leaderboard(room),
        }
        await room.broadcast(public)

    async def _chit_pull_next(self, room: Room):
        if not room.chit_pull_state:
            return
        became_podium = False
        try:
            async with room.lock:
                room.chit_pull_state = chit_pull_draw_turn(room.chit_pull_state, now=time.time())
                became_podium = room.chit_pull_state.get("phase") == CHIT_PULL_PHASE_PODIUM
                if not became_podium:
                    self._sync_chit_pull_phase_to_room(room)
        except ValueError:
            return
        if became_podium:
            await self._chit_pull_complete_game(room)
            return
        await self._broadcast_chit_pull_sync(room)

    async def _chit_pull_complete(self, room: Room, bonus: bool = False):
        if not room.chit_pull_state:
            return
        became_podium = False
        try:
            async with room.lock:
                room.chit_pull_state = chit_pull_complete_turn(room.chit_pull_state, bonus=bonus, now=time.time())
                became_podium = room.chit_pull_state.get("phase") == CHIT_PULL_PHASE_PODIUM
                self._sync_chit_pull_scores_to_players(room)
                if not became_podium:
                    self._sync_chit_pull_phase_to_room(room)
        except ValueError:
            return
        if became_podium:
            await self._chit_pull_complete_game(room)
            return
        await self._broadcast_chit_pull_sync(room)

    async def _chit_pull_skip(self, room: Room):
        if not room.chit_pull_state:
            return
        became_podium = False
        try:
            async with room.lock:
                room.chit_pull_state = chit_pull_skip_turn(room.chit_pull_state, now=time.time())
                became_podium = room.chit_pull_state.get("phase") == CHIT_PULL_PHASE_PODIUM
                self._sync_chit_pull_scores_to_players(room)
                if not became_podium:
                    self._sync_chit_pull_phase_to_room(room)
        except ValueError:
            return
        if became_podium:
            await self._chit_pull_complete_game(room)
            return
        await self._broadcast_chit_pull_sync(room)

    async def _chit_pull_redraw_player(self, room: Room):
        if not room.chit_pull_state:
            return
        try:
            async with room.lock:
                room.chit_pull_state = chit_pull_redraw_player(room.chit_pull_state, now=time.time())
                self._sync_chit_pull_phase_to_room(room)
        except ValueError:
            return
        await self._broadcast_chit_pull_sync(room)

    async def _chit_pull_redraw_chit(self, room: Room):
        if not room.chit_pull_state:
            return
        try:
            async with room.lock:
                room.chit_pull_state = chit_pull_redraw_chit(room.chit_pull_state, now=time.time())
                self._sync_chit_pull_phase_to_room(room)
        except ValueError:
            return
        await self._broadcast_chit_pull_sync(room)

    async def _chit_pull_complete_game(self, room: Room):
        if room.state == "PODIUM":
            return
        if room.chit_pull_state:
            room.chit_pull_state["phase"] = CHIT_PULL_PHASE_PODIUM
        self._sync_chit_pull_scores_to_players(room)
        room.state = "PODIUM"
        leaderboard = self.get_leaderboard(room)
        await room.broadcast({
            "type": "PODIUM",
            "game_type": "chit_pull",
            "leaderboard": leaderboard,
            "team_leaderboard": [],
            "chit_pull": chit_pull_public_sync(room.chit_pull_state, players=room.player_public_list()) if room.chit_pull_state else {},
        })
        try:
            from main import game_history
            summary = self.get_game_summary(room)
            summary["chit_pull_standings"] = chit_pull_final_standings(room.chit_pull_state) if room.chit_pull_state else []
            game_history.append(summary)
            if len(game_history) > config.MAX_GAME_HISTORY:
                del game_history[:len(game_history) - config.MAX_GAME_HISTORY]
            self._mark_game_session_complete(room, summary)
        except Exception:
            logger.warning("Could not save Random Chit history for room %s", room.room_code)

    def _start_mafia_game(self, room: Room):
        room.mafia_config = validate_mafia_config(room.quiz)
        room.mafia_state = mafia_create_initial_state(
            [p["nickname"] for p in room.players.values() if p.get("nickname")],
            room.mafia_config,
            now=time.time(),
            seed=secrets.randbits(32),
        )
        room.current_question_index = 0
        self._sync_mafia_phase_to_room(room)
        self._schedule_mafia_timer(room)

    def _sync_mafia_phase_to_room(self, room: Room):
        if room.mafia_state:
            room.state = str(room.mafia_state.get("phase") or MAFIA_PHASE_ROLE_REVEAL)
            room.current_question_index = max(0, int(room.mafia_state.get("round", 1) or 1) - 1)

    def _cancel_mafia_timer(self, room: Room):
        if room.mafia_timer_task:
            room.mafia_timer_task.cancel()
            room.mafia_timer_task = None

    def _schedule_mafia_timer(self, room: Room):
        self._cancel_mafia_timer(room)
        if not room.mafia_state or room.mafia_state.get("phase") == MAFIA_PHASE_PODIUM:
            return
        deadline = room.mafia_state.get("deadline")
        if not deadline:
            return
        delay = max(0.1, float(deadline) - time.time())
        room.mafia_timer_task = asyncio.create_task(self._mafia_timer_expired(room.room_code, delay))

    async def _mafia_timer_expired(self, room_code: str, delay: float):
        try:
            await asyncio.sleep(delay)
            room = self.rooms.get(room_code)
            if room and room.game_type == "mafia" and room.mafia_state:
                await self._advance_mafia_phase(room, reason="timer")
        except asyncio.CancelledError:
            pass
        except Exception:
            logger.exception("Mafia timer failed for room %s", room_code)

    async def _broadcast_mafia_sync(self, room: Room):
        if not room.mafia_state:
            return
        players = room.player_public_list()
        public = {
            "type": "MAFIA_SYNC",
            "game_type": "mafia",
            "mafia": mafia_public_sync(room.mafia_state, players=players),
            "player_count": len(room.players),
            "players": players,
            "leaderboard": self.get_leaderboard(room),
        }
        if room.organizer:
            await room.send_to_organizer(public)
        for spec_id, ws in list(room.spectators.items()):
            try:
                await ws.send_json(public)
            except Exception:
                room._remove_connection(spec_id)
        for client_id, pdata in list(room.players.items()):
            ws = room.connections.get(client_id)
            if not ws:
                continue
            payload = dict(public)
            payload["mafia"] = mafia_private_sync(room.mafia_state, pdata.get("nickname", ""), players=players)
            try:
                await ws.send_json(payload)
            except Exception:
                room._remove_connection(client_id)
        await room.emit_pending_player_event()

    async def _advance_mafia_phase(self, room: Room, reason: str = "manual"):
        if not room.mafia_state:
            return
        completed = False
        try:
            async with room.lock:
                self._cancel_mafia_timer(room)
                phase = room.mafia_state.get("phase")
                now = time.time()
                if phase == MAFIA_PHASE_ROLE_REVEAL:
                    room.mafia_state = mafia_advance_after_role_reveal(room.mafia_state, now=now)
                elif phase == MAFIA_PHASE_NIGHT:
                    room.mafia_state = mafia_resolve_night(room.mafia_state, now=now)
                elif phase == MAFIA_PHASE_DAY_DISCUSSION:
                    room.mafia_state = mafia_start_day_vote(room.mafia_state, now=now)
                elif phase == MAFIA_PHASE_DAY_VOTE:
                    room.mafia_state = mafia_resolve_vote(room.mafia_state, now=now)
                elif phase == MAFIA_PHASE_VOTE_RESULT:
                    room.mafia_state = mafia_advance_after_vote_result(room.mafia_state, now=now)
                self._sync_mafia_phase_to_room(room)
                completed = room.mafia_state.get("phase") == MAFIA_PHASE_PODIUM
                if not completed:
                    self._schedule_mafia_timer(room)
        except ValueError as exc:
            logger.info("Mafia phase advance ignored for room %s: %s", room.room_code, exc)
            return
        if completed:
            await self._mafia_complete_game(room)
            return
        await self._broadcast_mafia_sync(room)

    async def _mafia_extend_timer(self, room: Room):
        if not room.mafia_state or room.mafia_state.get("phase") != MAFIA_PHASE_DAY_DISCUSSION:
            return
        async with room.lock:
            room.mafia_state["deadline"] = float(room.mafia_state.get("deadline") or time.time()) + 30
            self._sync_mafia_phase_to_room(room)
            self._schedule_mafia_timer(room)
        await self._broadcast_mafia_sync(room)

    async def _mafia_submit_night_action(self, room: Room, client_id: str, target: str):
        if client_id not in room.players or not room.mafia_state:
            return
        nickname = room.players[client_id].get("nickname", "")
        try:
            async with room.lock:
                room.mafia_state = mafia_submit_night_action(room.mafia_state, nickname, target)
                should_advance = mafia_all_required_night_actions_submitted(room.mafia_state)
        except ValueError as exc:
            await self._send_to_client(room, client_id, {"type": "ERROR", "message": str(exc)})
            return
        await self._send_to_client(room, client_id, {"type": "MAFIA_NIGHT_ACTION_ACK", "target": target})
        if should_advance:
            await self._advance_mafia_phase(room, reason="all_actions")
        else:
            await self._broadcast_mafia_sync(room)

    async def _mafia_submit_night_read(self, room: Room, client_id: str, target: str):
        if client_id not in room.players or not room.mafia_state:
            return
        nickname = room.players[client_id].get("nickname", "")
        try:
            async with room.lock:
                room.mafia_state = mafia_submit_night_read(room.mafia_state, nickname, target)
                should_advance = mafia_all_required_night_actions_submitted(room.mafia_state)
        except ValueError as exc:
            await self._send_to_client(room, client_id, {"type": "ERROR", "message": str(exc)})
            return
        await self._send_to_client(room, client_id, {"type": "MAFIA_NIGHT_READ_ACK", "target": target})
        if should_advance:
            await self._advance_mafia_phase(room, reason="all_night_inputs")
        else:
            await self._broadcast_mafia_sync(room)

    async def _mafia_submit_vote(self, room: Room, client_id: str, target: str):
        if client_id not in room.players or not room.mafia_state:
            return
        nickname = room.players[client_id].get("nickname", "")
        try:
            async with room.lock:
                room.mafia_state = mafia_submit_vote(room.mafia_state, nickname, target or "skip")
                should_advance = mafia_all_living_votes_submitted(room.mafia_state)
        except ValueError as exc:
            await self._send_to_client(room, client_id, {"type": "ERROR", "message": str(exc)})
            return
        await self._send_to_client(room, client_id, {"type": "MAFIA_VOTE_ACK", "target": target or "skip"})
        if should_advance:
            await self._advance_mafia_phase(room, reason="all_votes")
        else:
            await self._broadcast_mafia_sync(room)

    async def _mafia_complete_game(self, room: Room, winner: str | None = None):
        self._cancel_mafia_timer(room)
        if room.mafia_state:
            room.mafia_state = mafia_force_complete(room.mafia_state, winner=winner, now=time.time())
        room.state = "PODIUM"
        leaderboard = self.get_leaderboard(room)
        await room.broadcast({
            "type": "PODIUM",
            "game_type": "mafia",
            "leaderboard": leaderboard,
            "team_leaderboard": [],
            "mafia": mafia_public_sync(room.mafia_state, players=room.player_public_list()) if room.mafia_state else {},
        })
        try:
            from main import game_history
            summary = self.get_game_summary(room)
            summary["mafia_result"] = mafia_result_summary(room.mafia_state, players=room.player_public_list()) if room.mafia_state else {}
            game_history.append(summary)
            if len(game_history) > config.MAX_GAME_HISTORY:
                del game_history[:len(game_history) - config.MAX_GAME_HISTORY]
            self._mark_game_session_complete(room, summary)
        except Exception:
            logger.warning("Could not save Mafia history for room %s", room.room_code)

    def _start_party_quests_game(self, room: Room):
        room.party_quests_config = validate_party_quests_config(room.quiz)
        room.party_quests_state = quests_create_initial_state(
            [p["nickname"] for p in room.players.values() if p.get("nickname")],
            room.party_quests_config,
            now=time.time(),
            seed=secrets.randbits(32),
        )
        self._sync_party_quests_phase_to_room(room)
        self._sync_party_quests_scores_to_players(room)

    def _sync_party_quests_phase_to_room(self, room: Room):
        if room.party_quests_state:
            room.state = str(room.party_quests_state.get("phase") or "QUESTS_ACTIVE")
            room.current_question_index = 0

    def _sync_party_quests_scores_to_players(self, room: Room):
        scores = room.party_quests_state.get("scores", {}) if room.party_quests_state else {}
        for pdata in room.players.values():
            nickname = pdata.get("nickname")
            pdata["score"] = int(scores.get(nickname, 0) or 0)

    async def _broadcast_party_quests_sync(self, room: Room):
        if not room.party_quests_state:
            return
        players = room.player_public_list()
        self._sync_party_quests_phase_to_room(room)
        self._sync_party_quests_scores_to_players(room)
        public = {
            "type": "QUESTS_SYNC",
            "game_type": "party_quests",
            "party_quests": quests_public_sync(room.party_quests_state, players=players),
            "player_count": len(room.players),
            "players": players,
            "leaderboard": self.get_leaderboard(room),
        }
        if room.organizer:
            await room.send_to_organizer(public)
        for spec_id, ws in list(room.spectators.items()):
            try:
                await ws.send_json(public)
            except Exception:
                room._remove_connection(spec_id)
        for client_id, pdata in list(room.players.items()):
            ws = room.connections.get(client_id)
            if not ws:
                continue
            payload = dict(public)
            payload["party_quests"] = quests_private_sync(room.party_quests_state, pdata.get("nickname", ""), players=players)
            try:
                await ws.send_json(payload)
            except Exception:
                room._remove_connection(client_id)
        await room.emit_pending_player_event()

    async def _party_quests_request_confirmation(self, room: Room, client_id: str, message: dict):
        if client_id not in room.players or not room.party_quests_state:
            return
        nickname = room.players[client_id].get("nickname", "")
        try:
            async with room.lock:
                room.party_quests_state, request = quests_create_confirmation_request(
                    room.party_quests_state,
                    nickname,
                    str(message.get("quest_id") or ""),
                    str(message.get("partner_player_id") or ""),
                    now=time.time(),
                )
                self._sync_party_quests_scores_to_players(room)
                self._sync_party_quests_phase_to_room(room)
                room.answer_log.append({"kind": "party_quest_request", "nickname": nickname, "quest_id": message.get("quest_id")})
        except ValueError as exc:
            await self._send_to_client(room, client_id, {"type": "ERROR", "message": str(exc)})
            return
        await self._send_to_client(room, client_id, {"type": "QUESTS_REQUEST_ACK", "request_id": request.get("id") if request else ""})
        await self._broadcast_party_quests_sync(room)

    async def _party_quests_confirm(self, room: Room, client_id: str, message: dict):
        if client_id not in room.players or not room.party_quests_state:
            return
        nickname = room.players[client_id].get("nickname", "")
        try:
            async with room.lock:
                room.party_quests_state, result = quests_apply_confirmation(
                    room.party_quests_state,
                    str(message.get("request_id") or ""),
                    nickname,
                    bool(message.get("accepted", False)),
                    now=time.time(),
                )
                self._sync_party_quests_scores_to_players(room)
                self._sync_party_quests_phase_to_room(room)
                room.answer_log.append({"kind": "party_quest_confirm", "nickname": nickname, "accepted": result.get("accepted")})
        except ValueError as exc:
            await self._send_to_client(room, client_id, {"type": "ERROR", "message": str(exc)})
            return
        await self._broadcast_party_quests_sync(room)

    async def _party_quests_final_call(self, room: Room):
        if not room.party_quests_state:
            return
        async with room.lock:
            room.party_quests_state = quests_start_final_call(room.party_quests_state, now=time.time())
            self._sync_party_quests_phase_to_room(room)
        await self._broadcast_party_quests_sync(room)

    async def _party_quests_reveal(self, room: Room):
        if not room.party_quests_state:
            return
        async with room.lock:
            room.party_quests_state = quests_reveal(room.party_quests_state, now=time.time())
            self._sync_party_quests_phase_to_room(room)
            self._sync_party_quests_scores_to_players(room)
        await self._broadcast_party_quests_sync(room)

    async def _party_quests_complete_game(self, room: Room):
        if room.state == "PODIUM":
            return
        if room.party_quests_state:
            room.party_quests_state = quests_complete(room.party_quests_state, now=time.time())
        self._sync_party_quests_scores_to_players(room)
        room.state = "PODIUM"
        leaderboard = self.get_leaderboard(room)
        await room.broadcast({
            "type": "PODIUM",
            "game_type": "party_quests",
            "leaderboard": leaderboard,
            "team_leaderboard": [],
            "party_quests": quests_public_sync(room.party_quests_state, players=room.player_public_list()) if room.party_quests_state else {},
        })
        try:
            from main import game_history
            summary = self.get_game_summary(room)
            summary["party_quests_result"] = quests_result_summary(room.party_quests_state, players=room.player_public_list()) if room.party_quests_state else {}
            summary["party_quests_standings"] = quests_standings(room.party_quests_state) if room.party_quests_state else []
            game_history.append(summary)
            if len(game_history) > config.MAX_GAME_HISTORY:
                del game_history[:len(game_history) - config.MAX_GAME_HISTORY]
            self._mark_game_session_complete(room, summary)
        except Exception:
            logger.warning("Could not save Party Quests history for room %s", room.room_code)

    def _start_survey_says_game(self, room: Room):
        room.survey_says_config = validate_survey_says_config(room.quiz)
        room.survey_says_state = survey_create_initial_state(
            [p["nickname"] for p in room.players.values() if p.get("nickname")],
            room.survey_says_config,
            now=time.time(),
        )
        room.survey_says_completed_sent = False
        self._sync_survey_says_phase_to_room(room)
        self._sync_survey_says_scores_to_players(room)
        room.answer_log = []

    def _sync_survey_says_phase_to_room(self, room: Room):
        if room.survey_says_state:
            room.state = str(room.survey_says_state.get("phase") or "SURVEY_ANSWERING")
            room.current_question_index = int(room.survey_says_state.get("round_index", 0))

    def _sync_survey_says_scores_to_players(self, room: Room):
        if not room.survey_says_state:
            return
        scores = room.survey_says_state.get("scores", {})
        player_team = {}
        for team in room.survey_says_state.get("teams", []):
            for player_id in team.get("player_ids", []):
                player_team[player_id] = team.get("id")
        for pdata in room.players.values():
            nickname = pdata.get("nickname")
            team_id = player_team.get(nickname)
            pdata["score"] = int(scores.get(team_id, 0) or 0)

    async def _broadcast_survey_says_sync(self, room: Room):
        if not room.survey_says_state:
            return
        players = room.player_public_list()
        self._sync_survey_says_phase_to_room(room)
        self._sync_survey_says_scores_to_players(room)
        public = {
            "type": "SURVEY_SYNC",
            "game_type": "survey_says",
            "survey_says": survey_public_sync(room.survey_says_state, players=players),
            "player_count": len(room.players),
            "players": players,
            "leaderboard": self.get_leaderboard(room),
            "team_leaderboard": [
                {"team": row.get("team_name"), "score": row.get("score"), "members": len(row.get("members") or [])}
                for row in survey_standings(room.survey_says_state)
            ],
        }
        if room.organizer:
            host_payload = dict(public)
            host_payload["survey_says"] = survey_public_sync(room.survey_says_state, players=players, host=True)
            await room.send_to_organizer(host_payload)
        for spec_id, ws in list(room.spectators.items()):
            try:
                await ws.send_json(public)
            except Exception:
                room._remove_connection(spec_id)
        for client_id, pdata in list(room.players.items()):
            ws = room.connections.get(client_id)
            if not ws:
                continue
            payload = dict(public)
            payload["survey_says"] = survey_public_sync(room.survey_says_state, players=players, viewer_id=pdata.get("nickname", ""))
            try:
                await ws.send_json(payload)
            except Exception:
                room._remove_connection(client_id)
        await room.emit_pending_player_event()

    async def _survey_says_submit_guess(self, room: Room, client_id: str, message: dict):
        if client_id not in room.players or not room.survey_says_state:
            return
        nickname = room.players[client_id].get("nickname", "")
        try:
            async with room.lock:
                room.survey_says_state = survey_submit_guess(room.survey_says_state, nickname, str(message.get("guess") or ""), now=time.time())
                self._sync_survey_says_phase_to_room(room)
                room.answer_log.append({"kind": "survey_guess", "nickname": nickname})
        except ValueError as exc:
            await self._send_to_client(room, client_id, {"type": "ERROR", "message": str(exc)})
            return
        await self._send_to_client(room, client_id, {"type": "SURVEY_GUESS_ACK"})
        await self._broadcast_survey_says_sync(room)

    async def _survey_says_reveal_answer(self, room: Room, answer_id: str):
        if not room.survey_says_state or not answer_id:
            return
        try:
            async with room.lock:
                room.survey_says_state = survey_reveal_answer(room.survey_says_state, answer_id, now=time.time())
                self._sync_survey_says_phase_to_room(room)
                self._sync_survey_says_scores_to_players(room)
                room.answer_log.append({"kind": "survey_reveal_answer", "answer_id": answer_id})
        except ValueError as exc:
            await self._send_to_organizer_error(room, str(exc))
            return
        await self._broadcast_survey_says_sync(room)

    async def _survey_says_strike(self, room: Room):
        if not room.survey_says_state:
            return
        try:
            async with room.lock:
                room.survey_says_state = survey_add_strike(room.survey_says_state, now=time.time())
                self._sync_survey_says_phase_to_room(room)
                self._sync_survey_says_scores_to_players(room)
                room.answer_log.append({"kind": "survey_strike", "strikes": room.survey_says_state.get("strikes")})
        except ValueError as exc:
            await self._send_to_organizer_error(room, str(exc))
            return
        await self._broadcast_survey_says_sync(room)

    async def _survey_says_reveal_all(self, room: Room):
        if not room.survey_says_state:
            return
        try:
            async with room.lock:
                room.survey_says_state = survey_reveal_all(room.survey_says_state, now=time.time())
                self._sync_survey_says_phase_to_room(room)
                self._sync_survey_says_scores_to_players(room)
                room.answer_log.append({"kind": "survey_reveal_all"})
        except ValueError as exc:
            await self._send_to_organizer_error(room, str(exc))
            return
        await self._broadcast_survey_says_sync(room)

    async def _survey_says_next_round(self, room: Room):
        if not room.survey_says_state:
            return
        try:
            async with room.lock:
                room.survey_says_state = survey_next_round(room.survey_says_state, now=time.time())
                self._sync_survey_says_phase_to_room(room)
                self._sync_survey_says_scores_to_players(room)
        except ValueError as exc:
            await self._send_to_organizer_error(room, str(exc))
            return
        await self._broadcast_survey_says_sync(room)
        if room.survey_says_state.get("phase") == SURVEY_PHASE_PODIUM:
            await self._survey_says_complete_game(room)

    async def _survey_says_complete_game(self, room: Room):
        if room.survey_says_completed_sent:
            return
        room.survey_says_completed_sent = True
        if room.survey_says_state:
            room.survey_says_state = survey_force_complete(room.survey_says_state, now=time.time())
        self._sync_survey_says_scores_to_players(room)
        room.state = "PODIUM"
        leaderboard = self.get_leaderboard(room)
        team_rows = [
            {"team": row.get("team_name"), "score": row.get("score"), "members": len(row.get("members") or [])}
            for row in (survey_standings(room.survey_says_state) if room.survey_says_state else [])
        ]
        await room.broadcast({
            "type": "PODIUM",
            "game_type": "survey_says",
            "leaderboard": leaderboard,
            "team_leaderboard": team_rows,
            "survey_says": survey_public_sync(room.survey_says_state, players=room.player_public_list()) if room.survey_says_state else {},
        })
        try:
            from main import game_history
            summary = self.get_game_summary(room)
            summary["winners"] = survey_standings(room.survey_says_state)[:3] if room.survey_says_state else []
            game_history.append(summary)
            if len(game_history) > config.MAX_GAME_HISTORY:
                del game_history[:len(game_history) - config.MAX_GAME_HISTORY]
            self._mark_game_session_complete(room, summary)
        except Exception:
            logger.warning("Could not save Survey Says history for room %s", room.room_code)

    def _start_musical_chairs_game(self, room: Room):
        room.mc_config = validate_musical_chairs_config(room.quiz)
        room.mc_active_players = sorted([p["nickname"] for p in room.players.values()])
        room.mc_eliminated_players = []
        room.mc_round_results = []
        room.mc_round_number = 0
        room.mc_total_rounds = mc_total_rounds(len(room.mc_active_players), int(room.mc_config.get("eliminations_per_round", 1) or 1))
        room.mc_stop_time = None
        room.mc_grab_deadline = None
        room.mc_grabs = {}

    async def _mc_start_round(self, room: Room):
        async with room.lock:
            if room.game_type != "musical_chairs" or room.state not in ("MC_BETWEEN_ROUNDS", "MC_REVEAL"):
                return
            if len(room.mc_active_players) <= 1:
                asyncio.create_task(self._mc_complete_game(room))
                return
            if room.mc_auto_stop_task:
                room.mc_auto_stop_task.cancel()
                room.mc_auto_stop_task = None
            if room.mc_grab_task:
                room.mc_grab_task.cancel()
                room.mc_grab_task = None
            room.mc_round_number += 1
            room.mc_grabs = {}
            room.mc_stop_time = None
            room.mc_grab_deadline = None
            room.state = "MC_MUSIC"
            min_music = int(room.mc_config.get("min_music_seconds", 5) or 5)
            max_music = int(room.mc_config.get("max_music_seconds", 20) or 20)
            stop_after = random.uniform(min_music, max(min_music + 0.5, max_music))
            await room.broadcast({
                "type": "MC_ROUND_START",
                "musical_chairs": room.mc_public_state(),
                "stop_after_seconds": round(stop_after, 2),
            })
            if bool(room.mc_config.get("auto_stop", True)):
                room.mc_auto_stop_task = asyncio.create_task(self._mc_auto_stop(room, stop_after))

    async def _mc_auto_stop(self, room: Room, delay: float):
        try:
            await asyncio.sleep(delay)
            await self._mc_stop_music(room)
        except asyncio.CancelledError:
            pass

    async def _mc_stop_music(self, room: Room):
        async with room.lock:
            if room.game_type != "musical_chairs" or room.state != "MC_MUSIC":
                return
            if room.mc_auto_stop_task:
                room.mc_auto_stop_task.cancel()
                room.mc_auto_stop_task = None
            room.mc_stop_time = time.time()
            physical_mode = room.mc_config.get("gameplay_mode", "digital") == "physical"
            grab_window = float(room.mc_config.get("grab_window_seconds", 5) or 5)
            room.state = "MC_PHYSICAL_ELIMINATION" if physical_mode else "MC_GRAB"
            room.mc_grab_deadline = None if physical_mode else room.mc_stop_time + grab_window
            await room.broadcast({
                "type": "MC_MUSIC_STOP",
                "grab_deadline_ms": int(grab_window * 1000),
                "musical_chairs": room.mc_public_state(),
            })
            if not physical_mode:
                room.mc_grab_task = asyncio.create_task(self._mc_grab_deadline(room, grab_window))

    async def _mc_grab_deadline(self, room: Room, delay: float):
        try:
            await asyncio.sleep(delay)
            await self._mc_end_round(room)
        except asyncio.CancelledError:
            pass

    async def _mc_handle_grab(self, room: Room, client_id: str):
        if client_id not in room.players:
            return
        nickname = room.players[client_id]["nickname"]
        async with room.lock:
            if room.state != "MC_GRAB" or nickname not in room.mc_active_players or nickname in room.mc_grabs:
                return
            now = time.time()
            if room.mc_grab_deadline and now > room.mc_grab_deadline:
                return
            room.mc_grabs[nickname] = now
            ranked = rank_grabs(room.mc_active_players, room.mc_grabs, room.mc_stop_time or now)
            player_rank = next((item for item in ranked if item["nickname"] == nickname), {"rank": len(room.mc_grabs), "reaction_ms": None})
            await self._send_to_client(room, client_id, {"type": "MC_GRAB_CONFIRMED", "rank": player_rank["rank"], "reaction_ms": player_rank["reaction_ms"]})
            await room.broadcast({
                "type": "MC_GRAB_COUNT",
                "grabbed": len(room.mc_grabs),
                "total": len(room.mc_active_players),
                "musical_chairs": room.mc_public_state(),
            })
            if len(room.mc_grabs) >= len(room.mc_active_players):
                if room.mc_grab_task:
                    room.mc_grab_task.cancel()
                    room.mc_grab_task = None
                asyncio.create_task(self._mc_end_round(room))

    async def _mc_eliminate_physical(self, room: Room, nickname: str):
        async with room.lock:
            if (
                room.game_type != "musical_chairs"
                or room.mc_config.get("gameplay_mode", "digital") != "physical"
                or room.state != "MC_PHYSICAL_ELIMINATION"
                or nickname not in room.mc_active_players
                or len(room.mc_active_players) <= 1
            ):
                return
            avatars = room.player_avatar_map()
            room.mc_eliminated_players.append({
                "nickname": nickname,
                "avatar": avatars.get(nickname, ""),
                "round_number": room.mc_round_number,
                "reaction_ms": None,
                "reason": "physical_elimination",
            })
            for cid, pdata in list(room.players.items()):
                if pdata.get("nickname") == nickname:
                    await self._send_to_client(room, cid, {
                        "type": "MC_ELIMINATED",
                        "round_number": room.mc_round_number,
                        "reaction_ms": None,
                        "reason": "physical_elimination",
                    })
            room.mc_active_players = [name for name in room.mc_active_players if name != nickname]
            room.state = "MC_REVEAL"
            round_result = {
                "round_number": room.mc_round_number,
                "tap_order": [],
                "eliminated": [nickname],
                "remaining_players": room.mc_active_players,
            }
            room.mc_round_results.append(round_result)
            await room.broadcast({
                "type": "MC_ROUND_OVER",
                **round_result,
                "is_final": len(room.mc_active_players) <= 1,
                "musical_chairs": room.mc_public_state(),
            })
            if len(room.mc_active_players) <= 1:
                asyncio.create_task(self._mc_complete_game(room))
            else:
                room.state = "MC_BETWEEN_ROUNDS"
                await room.broadcast({"type": "MC_SYNC", "musical_chairs": room.mc_public_state()})

    async def _mc_end_round(self, room: Room):
        async with room.lock:
            if room.state != "MC_GRAB":
                return
            if room.mc_grab_task:
                room.mc_grab_task.cancel()
                room.mc_grab_task = None
            active = list(room.mc_active_players)
            stop_time = room.mc_stop_time or time.time()
            eliminations = int(room.mc_config.get("eliminations_per_round", 1) or 1)
            eliminated = choose_eliminated(active, room.mc_grabs, stop_time, eliminations)
            tap_order = rank_grabs(active, room.mc_grabs, stop_time)
            avatars = room.player_avatar_map()
            for name in eliminated:
                result = next((item for item in tap_order if item["nickname"] == name), {})
                room.mc_eliminated_players.append({
                    "nickname": name,
                    "avatar": avatars.get(name, ""),
                    "round_number": room.mc_round_number,
                    "reaction_ms": result.get("reaction_ms"),
                    "reason": "no_tap" if result.get("reaction_ms") is None else "slowest_tap",
                })
                for cid, pdata in list(room.players.items()):
                    if pdata.get("nickname") == name:
                        await self._send_to_client(room, cid, {
                            "type": "MC_ELIMINATED",
                            "round_number": room.mc_round_number,
                            "reaction_ms": result.get("reaction_ms"),
                            "reason": "no_tap" if result.get("reaction_ms") is None else "slowest_tap",
                        })
            room.mc_active_players = [name for name in active if name not in set(eliminated)]
            room.state = "MC_REVEAL"
            round_result = {
                "round_number": room.mc_round_number,
                "tap_order": tap_order,
                "eliminated": eliminated,
                "remaining_players": room.mc_active_players,
            }
            room.mc_round_results.append(round_result)
            await room.broadcast({
                "type": "MC_ROUND_OVER",
                **round_result,
                "is_final": len(room.mc_active_players) <= 1,
                "musical_chairs": room.mc_public_state(),
            })
            if len(room.mc_active_players) <= 1:
                asyncio.create_task(self._mc_complete_game(room))
            else:
                room.state = "MC_BETWEEN_ROUNDS"
                await room.broadcast({"type": "MC_SYNC", "musical_chairs": room.mc_public_state()})

    async def _mc_complete_game(self, room: Room):
        if room.mc_auto_stop_task:
            room.mc_auto_stop_task.cancel()
            room.mc_auto_stop_task = None
        if room.mc_grab_task:
            room.mc_grab_task.cancel()
            room.mc_grab_task = None
        if not room.mc_active_players and room.players:
            room.mc_active_players = [p["nickname"] for p in room.players.values()]
        winner = room.mc_active_players[0] if room.mc_active_players else ""
        room.state = "PODIUM"
        leaderboard = self.get_leaderboard(room)
        await room.broadcast({"type": "MC_WINNER", "winner": winner, "total_rounds": room.mc_round_number})
        await room.broadcast({"type": "PODIUM", "game_type": "musical_chairs", "leaderboard": leaderboard, "team_leaderboard": []})
        try:
            from main import game_history
            summary = self.get_game_summary(room)
            game_history.append(summary)
            if len(game_history) > config.MAX_GAME_HISTORY:
                del game_history[:len(game_history) - config.MAX_GAME_HISTORY]
            self._mark_game_session_complete(room, summary)
        except Exception:
            logger.warning("Could not save Musical Chairs history for room %s", room.room_code)

    async def _broadcast_housie_auto_status(self, room: Room):
        await room.broadcast({
            "type": "BINGO_AUTO_STATUS",
            "game_type": room.game_type,
            "caller_mode": room.housie_caller_mode,
            "auto_status": room.housie_auto_status,
            "auto_interval_seconds": room.housie_auto_interval_seconds,
            "auto_pause_on_claim": room.housie_auto_pause_on_claim,
            "next_auto_call_at": room.housie_next_auto_call_at,
        })

    async def _set_housie_auto_status(self, room: Room, status: str):
        if room.housie_auto_task:
            room.housie_auto_task.cancel()
            room.housie_auto_task = None
        room.housie_auto_status = status
        room.housie_next_auto_call_at = None
        if status == "running" and room.state == "BINGO_CALLING" and room.housie_deck:
            room.housie_caller_mode = "auto"
            room.housie_auto_task = asyncio.create_task(self._housie_auto_loop(room))
        elif status == "stopped":
            room.housie_caller_mode = "manual"
        await self._broadcast_housie_auto_status(room)

    async def _housie_auto_loop(self, room: Room):
        try:
            while room.state == "BINGO_CALLING" and room.housie_auto_status == "running" and room.housie_deck:
                next_at = datetime.now(timezone.utc).timestamp() + room.housie_auto_interval_seconds
                room.housie_next_auto_call_at = datetime.fromtimestamp(next_at, tz=timezone.utc).isoformat()
                await self._broadcast_housie_auto_status(room)
                await asyncio.sleep(room.housie_auto_interval_seconds)
                if room.state != "BINGO_CALLING" or room.housie_auto_status != "running":
                    break
                await self._housie_call_next(room, from_auto=True)
        except asyncio.CancelledError:
            pass
        finally:
            if room.housie_auto_task is asyncio.current_task():
                room.housie_auto_task = None

    async def _housie_call_next(self, room: Room, from_auto: bool = False):
        async with room.lock:
            if room.state != "BINGO_CALLING" or not room.housie_deck or self._housie_terminal_claim_pending(room):
                return
            item = room.housie_deck.pop(0)
            room.housie_called.append(item)
            room.current_question_index = len(room.housie_called) - 1
            room.answer_log.append({"kind": "call", "item": item, "index": len(room.housie_called)})
        await room.broadcast({
            "type": "BINGO_CALL",
            "game_type": room.game_type,
            "item": item,
            "called_items": room.housie_called,
            "remaining_count": len(room.housie_deck),
            "call_index": len(room.housie_called),
            "can_undo_last_call": self._housie_can_undo_last_call(room),
            "animation": "latest_call",
            "auto_status": room.housie_auto_status,
        })
        if not room.housie_deck:
            if room.housie_auto_task and not from_auto:
                room.housie_auto_task.cancel()
                room.housie_auto_task = None
            room.housie_auto_status = "stopped"
            room.housie_next_auto_call_at = None
            await self._broadcast_housie_auto_status(room)

    async def _housie_undo_last_call(self, room: Room):
        should_pause_auto = False
        async with room.lock:
            if room.state != "BINGO_CALLING" or not room.housie_called:
                return
            # Block undo if any accepted claim was validated at or after the last call index.
            last_call_index = len(room.housie_called)
            if any(w.get("called_count", 0) >= last_call_index for w in room.housie_winners):
                return
            should_pause_auto = room.housie_auto_status == "running"
            item = room.housie_called.pop()
            room.housie_deck.insert(0, item)
            room.current_question_index = len(room.housie_called) - 1
        if should_pause_auto:
            await self._set_housie_auto_status(room, "paused")
        await self._broadcast_housie_sync(room)

    async def _handle_housie_claim(self, room: Room, client_id: str, message: dict):
        if client_id not in room.players or room.state != "BINGO_CALLING":
            return
        pattern_id = str(message.get("pattern_id") or "").strip()
        if pattern_id not in {pattern["id"] for pattern in self._housie_patterns(room)}:
            await self._send_to_client(room, client_id, {
                "type": "BINGO_CLAIM_REJECTED",
                "pattern_id": pattern_id,
                "reason": "unknown_pattern",
                "message": self._housie_claim_rejection_message("unknown_pattern"),
            })
            return
        pattern = next((p for p in self._housie_patterns(room) if p["id"] == pattern_id), {"label": pattern_id})
        is_terminal = pattern.get("terminal", pattern_id == "full_house")
        nickname = room.players[client_id]["nickname"]
        terminal_winners = [winner for winner in room.housie_winners if winner.get("pattern_id") == pattern_id]
        if pattern_id in room.housie_claimed_patterns:
            same_latest_terminal_window = (
                is_terminal
                and bool(terminal_winners)
                and terminal_winners[0].get("called_count") == len(room.housie_called)
            )
            already_claimed_by_player = any(winner.get("nickname") == nickname for winner in terminal_winners)
            if not same_latest_terminal_window or already_claimed_by_player:
                reason = "already_claimed_by_you" if already_claimed_by_player else "already_awarded"
                await self._send_to_client(room, client_id, {
                    "type": "BINGO_CLAIM_REJECTED",
                    "pattern_id": pattern_id,
                    "reason": reason,
                    "message": self._housie_claim_rejection_message(reason, pattern.get("label", pattern_id)),
                })
                return
        auto_paused_for_claim = room.housie_auto_status == "running" and room.housie_auto_pause_on_claim
        if auto_paused_for_claim:
            await self._set_housie_auto_status(room, "paused")
        ticket = room.housie_tickets.get(nickname)
        if room.game_type == "bingo":
            valid, reason, winning_values = validate_bingo_claim(
                ticket or {},
                room.housie_called,
                pattern_id,
                require_latest=bool(room.quiz.get("claim_requires_latest_call", False)),
            )
        else:
            valid, reason = validate_claim(ticket or {}, room.housie_called, pattern_id, require_latest=True)
            winning_values = []
        if not valid:
            await self._send_to_client(room, client_id, {
                "type": "BINGO_CLAIM_REJECTED",
                "pattern_id": pattern_id,
                "reason": reason,
                "message": self._housie_claim_rejection_message(reason, pattern.get("label", pattern_id)),
            })
            if auto_paused_for_claim:
                await self._set_housie_auto_status(room, "running")
            return
        latest_item = room.housie_called[-1] if room.housie_called else {}
        winner = {
            "pattern_id": pattern_id,
            "label": pattern.get("label", pattern_id),
            "nickname": nickname,
            "called_count": len(room.housie_called),
            "winning_number": latest_item.get("value"),
            "winning_values": winning_values,
        }
        async with room.lock:
            winners_for_pattern = [existing for existing in room.housie_winners if existing.get("pattern_id") == pattern_id]
            same_latest_terminal_window = (
                is_terminal
                and bool(winners_for_pattern)
                and winners_for_pattern[0].get("called_count") == len(room.housie_called)
            )
            already_claimed_by_player = any(existing.get("nickname") == nickname for existing in winners_for_pattern)
            if pattern_id in room.housie_claimed_patterns and (not same_latest_terminal_window or already_claimed_by_player):
                duplicate_claim = True
                duplicate_reason = "already_claimed_by_you" if already_claimed_by_player else "already_awarded"
            else:
                duplicate_claim = False
                duplicate_reason = ""
                room.housie_claimed_patterns.add(pattern_id)
                room.housie_winners.append(winner)
                room.housie_claim_log.append(winner)
                if is_terminal:
                    room.players[client_id]["score"] += 1000
                else:
                    room.players[client_id]["score"] += 250
                room.answer_log.append({"kind": "claim", **winner})
        if duplicate_claim:
            if auto_paused_for_claim:
                await self._set_housie_auto_status(room, "running")
            await self._send_to_client(room, client_id, {
                "type": "BINGO_CLAIM_REJECTED",
                "pattern_id": pattern_id,
                "reason": duplicate_reason,
                "message": self._housie_claim_rejection_message(duplicate_reason, pattern.get("label", pattern_id)),
            })
            return
        await room.broadcast({
            "type": "BINGO_CLAIM_ACCEPTED",
            "game_type": room.game_type,
            "winner": winner,
            "winners": room.housie_winners,
            "leaderboard": self.get_leaderboard(room),
            "can_undo_last_call": self._housie_can_undo_last_call(room),
            "terminal_claim_pending": is_terminal,
            "announce": True,
        })
        if is_terminal:
            await self._set_housie_auto_status(room, "stopped")
            await self._broadcast_housie_sync(room)
        elif auto_paused_for_claim:
            await self._set_housie_auto_status(room, "running")

    async def _complete_housie(self, room: Room):
        if room.state == "PODIUM":
            return
        if room.housie_auto_task and room.housie_auto_task is not asyncio.current_task():
            room.housie_auto_task.cancel()
            room.housie_auto_task = None
        room.housie_auto_status = "stopped"
        room.housie_next_auto_call_at = None
        room.state = "PODIUM"
        leaderboard = self.get_leaderboard(room)
        await room.broadcast({
            "type": "BINGO_COMPLETE",
            "game_type": room.game_type,
            "winners": room.housie_winners,
            "leaderboard": leaderboard,
            "team_leaderboard": self.get_team_leaderboard(room),
        })
        await room.broadcast({
            "type": "PODIUM",
            "leaderboard": leaderboard,
            "team_leaderboard": self.get_team_leaderboard(room),
            "housie_winners": room.housie_winners,
        })
        try:
            from main import game_history
            summary = self.get_game_summary(room)
            game_history.append(summary)
            if len(game_history) > config.MAX_GAME_HISTORY:
                del game_history[:len(game_history) - config.MAX_GAME_HISTORY]
            self._mark_game_session_complete(room, summary)
        except Exception:
            logger.warning("Could not save Housie history for room %s", room.room_code)

    def _drawing_player_state(self, room: Room, nickname: str, prompt: Optional[dict]) -> dict:
        is_drawer = nickname == room.current_drawer
        clue = self._drawing_clue(room, prompt)
        return {
            "drawing_prompt": prompt if is_drawer else ({k: v for k, v in (prompt or {}).items() if k not in ("text", "aliases")}),
            "drawing_clue": clue,
            "drawer": room.current_drawer,
            "is_drawer": is_drawer,
            "drawing_ops": room.drawing_ops[-config.MAX_DRAW_OPS_PER_SYNC:],
            "correct_guessers": list(room.correct_guessers),
            "guess_log": room.guess_log[-10:],
        }

    def _drawing_clue(self, room: Room, prompt: Optional[dict] = None) -> str:
        prompt = prompt or room.current_round_data() or {}
        elapsed = max(0.0, time.time() - room.question_start_time) if room.question_start_time else 0.0
        ratio = elapsed / max(1, room.time_limit)
        from drawing_engine import clue_for_prompt
        return clue_for_prompt(str(prompt.get("text") or ""), ratio)

    def _drawing_public_prompt(self, prompt: Optional[dict]) -> dict:
        return {k: v for k, v in (prompt or {}).items() if k not in ("text", "aliases")}

    def _ensure_drawer_order(self, room: Room):
        current = room.player_nicknames()
        if not room.drawer_order:
            room.drawer_order = current[:]
        for nickname in current:
            if nickname not in room.drawer_order:
                room.drawer_order.append(nickname)
        room.drawer_order = [n for n in room.drawer_order if n in set(current) or n in room.disconnected_players]

    def _drawer_for_round(self, room: Room) -> str:
        self._ensure_drawer_order(room)
        if not room.drawer_order:
            return ""
        return room.drawer_order[room.current_question_index % len(room.drawer_order)]

    async def _broadcast_drawing_question(self, room: Room, prompt: dict, is_bonus: bool):
        public_prompt = self._drawing_public_prompt(prompt)
        clue = self._drawing_clue(room, prompt)
        base = {
            "type": "QUESTION",
            "question_number": room.current_question_index + 1,
            "total_questions": room.total_rounds(),
            "time_limit": room.time_limit,
            "is_bonus": is_bonus,
            "game_type": "drawing",
            "drawer": room.current_drawer,
            "drawing_clue": clue,
            "correct_guessers": [],
            "drawing_ops": [],
            "guess_log": [],
        }
        for client_id, ws in list(room.connections.items()):
            if client_id not in room.players:
                continue
            nickname = room.players[client_id]["nickname"]
            payload = dict(base)
            payload["is_drawer"] = nickname == room.current_drawer
            payload["drawing_prompt"] = prompt if payload["is_drawer"] else public_prompt
            try:
                await ws.send_json(payload)
            except Exception:
                room._remove_connection(client_id)
        await room.emit_pending_player_event()
        await room.send_to_organizer({
            **base,
            "drawing_prompt": prompt,
            "is_drawer": False,
        })
        for ws in list(room.spectators.values()):
            try:
                await ws.send_json({
                    **base,
                    "drawing_prompt": public_prompt,
                    "is_drawer": False,
                })
            except Exception:
                pass

    def _valid_draw_op(self, op: dict) -> bool:
        if not isinstance(op, dict):
            return False
        if op.get("kind") not in ("stroke", "clear", "undo"):
            return False
        if op.get("kind") in ("clear", "undo"):
            return True
        points = op.get("points")
        if not isinstance(points, list) or len(points) == 0 or len(points) > 80:
            return False
        width = op.get("width", 4)
        if not isinstance(width, (int, float)) or width <= 0 or width > 32:
            return False
        color = op.get("color", "#ffffff")
        if not isinstance(color, str) or not re.match(r"^#[0-9a-fA-F]{6}$", color):
            return False
        for point in points:
            if not isinstance(point, list) or len(point) != 2:
                return False
            x, y = point
            if not isinstance(x, (int, float)) or not isinstance(y, (int, float)):
                return False
            if x < 0 or x > 1 or y < 0 or y > 1:
                return False
        return True

    async def _handle_draw_op(self, room: Room, client_id: str, message: dict):
        if client_id not in room.players or room.state != "QUESTION":
            return
        nickname = room.players[client_id]["nickname"]
        if nickname != room.current_drawer:
            await self._send_to_client(room, client_id, {"type": "ERROR", "message": "Only the drawer can draw"})
            return
        op = message.get("op")
        if not self._valid_draw_op(op):
            await self._send_to_client(room, client_id, {"type": "ERROR", "message": "Invalid drawing operation"})
            return
        op = dict(op)
        op["drawer"] = nickname
        op["seq"] = len(room.drawing_ops) + 1
        if op["kind"] == "clear":
            room.drawing_ops.clear()
        elif op["kind"] == "undo":
            if room.drawing_ops:
                room.drawing_ops.pop()
        else:
            room.drawing_ops.append(op)
            if len(room.drawing_ops) > config.MAX_DRAW_OPS_PER_SYNC:
                room.drawing_ops = room.drawing_ops[-config.MAX_DRAW_OPS_PER_SYNC:]
        await room.broadcast({"type": "DRAW_OP", "op": op})

    async def _handle_drawing_guess(self, room: Room, client_id: str, message: dict):
        if client_id not in room.players or room.state != "QUESTION":
            return
        nickname = room.players[client_id]["nickname"]
        if nickname == room.current_drawer or nickname in room.correct_guessers:
            return
        raw_guess = message.get("guess", "")
        guess = (raw_guess if isinstance(raw_guess, str) else "").strip()[:80]
        if not guess:
            return
        prompt = room.current_round_data()
        if not prompt:
            return
        from drawing_engine import is_correct_guess
        correct = is_correct_guess(guess, prompt)
        if correct:
            elapsed = max(0, time.time() - room.question_start_time)
            time_remaining = max(0, room.time_limit - elapsed)
            points = 300 + round(600 * (time_remaining / max(1, room.time_limit)))
            async with room.lock:
                if nickname in room.correct_guessers:
                    return
                room.correct_guessers.add(nickname)
                room.answered_players.add(client_id)
                room.players[client_id]["score"] += points
                drawer_id = next((cid for cid, p in room.players.items() if p["nickname"] == room.current_drawer), None)
                if drawer_id:
                    room.players[drawer_id]["score"] += 200
                all_guessed = len(room.correct_guessers) >= max(0, len(room.players) - 1)
            room.guess_log.append({"nickname": nickname, "guess": guess, "correct": True})
            await self._send_to_client(room, client_id, {"type": "GUESS_RESULT", "correct": True, "points": points})
            await room.broadcast({
                "type": "GUESS_ACCEPTED",
                "nickname": nickname,
                "correct_guessers": list(room.correct_guessers),
                "guess": guess,
            })
            await room.send_to_organizer({
                "type": "ANSWER_COUNT",
                "answered": len(room.correct_guessers),
                "total": max(0, len(room.players) - 1),
            })
            if all_guessed:
                if drawer_id:
                    room.players[drawer_id]["score"] += 500
                await self.end_question(room)
        else:
            room.guess_log.append({"nickname": nickname, "guess": guess, "correct": False})
            room.guess_log = room.guess_log[-20:]
            await self._send_to_client(room, client_id, {"type": "GUESS_RESULT", "correct": False, "points": 0})
            await room.broadcast({"type": "GUESS_LOG", "guess_log": room.guess_log[-10:]})

    def get_team_leaderboard(self, room: Room) -> List[dict]:
        """Aggregate player scores by team. Solo players use their nickname."""
        team_scores: Dict[str, list] = {}
        for player in self._all_players_for_leaderboard(room):
            team = room.teams.get(player["nickname"]) or player["nickname"]
            team_scores.setdefault(team, []).append(player["score"])
        result = []
        for team_name, scores in team_scores.items():
            result.append({
                "team": team_name,
                "score": int(sum(scores) / len(scores)) if scores else 0,  # average
                "members": len(scores),
            })
        return sorted(result, key=lambda x: x["score"], reverse=True)

    def get_game_summary(self, room: Room) -> dict:
        """Build a game summary for history storage."""
        all_player_count = len(room.players) + len(room.disconnected_players)
        summary = {
            "room_code": room.room_code,
            "game_type": room.game_type,
            "game_title": room.game_title(),
            "total_questions": room.total_rounds(),
            "player_count": all_player_count,
            "leaderboard": self.get_leaderboard(room),
            "team_leaderboard": self.get_team_leaderboard(room),
            "answer_log": room.answer_log,
            "completed_at": time.time(),
            "wallet_id": room.wallet_id or "",
        }
        if room.game_type in ("housie", "bingo"):
            summary["total_questions"] = len(room.housie_called)
            summary["total_rounds"] = len(room.housie_called)
            summary["winners"] = room.housie_winners
            summary["top_results"] = [
                {
                    "nickname": winner.get("nickname"),
                    "score": next((p.get("score", 0) for p in self._all_players_for_leaderboard(room) if p.get("nickname") == winner.get("nickname")), 0),
                    "prize": winner.get("label"),
                }
                for winner in room.housie_winners[:5]
            ]
        if room.game_type == "musical_chairs":
            summary["total_questions"] = room.mc_round_number
            summary["total_rounds"] = room.mc_round_number
            summary["elimination_order"] = room.mc_eliminated_players
            summary["round_results"] = room.mc_round_results
            summary["music_mode"] = room.mc_config.get("music_mode")
            summary["music_style"] = room.mc_config.get("music_style")
        if room.game_type == "bluff" and room.bluff_state:
            summary["total_questions"] = len(room.answer_log)
            summary["total_rounds"] = len(room.answer_log)
            summary["winners"] = room.bluff_state.get("winners", [])
            summary["pile_count"] = len(room.bluff_state.get("pile", []))
        if room.game_type == "who_am_i" and room.who_am_i_state:
            summary["total_questions"] = len(room.who_am_i_state.get("config", {}).get("rounds", []))
            summary["total_rounds"] = summary["total_questions"]
            summary["winners"] = whoami_final_standings(room.who_am_i_state)[:3]
        if room.game_type == "chit_pull" and room.chit_pull_state:
            summary["total_questions"] = len(room.chit_pull_state.get("turn_results", []))
            summary["total_rounds"] = summary["total_questions"]
            summary["winners"] = chit_pull_final_standings(room.chit_pull_state)[:3]
            summary["completed_count"] = len([item for item in room.chit_pull_state.get("turn_results", []) if item.get("outcome") == "completed"])
            summary["skipped_count"] = len([item for item in room.chit_pull_state.get("turn_results", []) if item.get("outcome") == "skipped"])
        if room.game_type == "find_someone" and room.find_someone_state:
            standings = find_final_standings(room.find_someone_state)
            summary["total_questions"] = sum(row.get("confirmed_cells", 0) for row in standings)
            summary["total_rounds"] = 1
            summary["winners"] = standings[:3]
            summary["claims"] = room.find_someone_state.get("accepted_claims", [])
        if room.game_type == "mafia" and room.mafia_state:
            mafia_summary = mafia_result_summary(room.mafia_state, players=room.player_public_list())
            summary["total_questions"] = mafia_summary.get("rounds_played", 1)
            summary["total_rounds"] = mafia_summary.get("rounds_played", 1)
            summary["winner"] = mafia_summary.get("winner")
            summary["mafia_result"] = mafia_summary
        if room.game_type == "survey_says" and room.survey_says_state:
            survey_rows = survey_standings(room.survey_says_state)
            summary["total_questions"] = len(room.survey_says_state.get("round_results", []))
            summary["total_rounds"] = summary["total_questions"]
            summary["winners"] = survey_rows[:3]
            summary["team_leaderboard"] = [
                {"team": row.get("team_name"), "score": row.get("score"), "members": len(row.get("members") or [])}
                for row in survey_rows
            ]
        if room.game_type in GENERIC_PROMPT_GAME_TYPES and room.generic_prompt_state:
            standings = generic_standings(room.generic_prompt_state)
            summary["total_questions"] = len(room.generic_prompt_state.get("rounds", []))
            summary["total_rounds"] = summary["total_questions"]
            summary["winners"] = standings[:3]
            summary["mode"] = room.generic_prompt_state.get("config", {}).get("mode")
        if room.game_type in ("would_you_rather", "never_have_i_ever", "word_association", "acronym"):
            standings = self._simple_social_standings(room)
            summary["total_questions"] = room.total_rounds()
            summary["total_rounds"] = room.total_rounds()
            summary["winners"] = standings[:3]
        if room.game_type == "photo_clue" and room.photo_clue_state:
            summary["total_questions"] = room.total_rounds()
            summary["total_rounds"] = room.total_rounds()
            summary["photos_submitted"] = len([item for item in room.photo_clue_state.get("assignments", []) if item.get("image_asset_id")])
            scores = room.photo_clue_state.get("scores", {})
            summary["winners"] = [
                {"nickname": player_id, "score": score}
                for player_id, score in sorted(scores.items(), key=lambda item: item[1], reverse=True)[:3]
            ]
        if room.game_type == "poker" and room.poker_state:
            summary["total_questions"] = int(room.poker_state.get("hand_number", 0))
            summary["total_rounds"] = int(room.poker_state.get("hand_number", 0))
            summary["variant"] = room.poker_state.get("config", {}).get("variant")
            summary["final_standings"] = room.poker_state.get("standings", [])
            summary["winners"] = [
                {"nickname": row.get("player_id"), "score": row.get("stack", 0), "place": row.get("place")}
                for row in room.poker_state.get("standings", [])[:3]
            ]
        return summary

    def _callback_event_type(self, event_type: str) -> str:
        return {
            "session.created": "game.session_created",
            "session.started": "game.started",
            "session.completed": "game.completed",
            "session.cancelled": "game.cancelled",
            "session.expired": "game.expired",
            "session.superseded": "game.superseded",
        }.get(event_type, event_type)

    def _callback_signing_secret(self) -> str:
        return config.REVELRY_INTEGRATION_SECRET or config.REVELRY_CALLBACK_SECRET

    def _callback_retry_delay(self, response: Optional[httpx.Response], attempt: int) -> float:
        if response is not None:
            retry_after = response.headers.get("Retry-After", "")
            try:
                return max(0.0, min(float(retry_after), 5.0))
            except ValueError:
                pass
        return min(0.25 * (2 ** attempt), 2.0)

    def _safe_result_summary(self, summary: Optional[dict]) -> Optional[dict]:
        if not isinstance(summary, dict):
            return None
        if isinstance(summary.get("top_results"), list):
            top_results = summary["top_results"][:5]
            return {
                "title": summary.get("title") or summary.get("game_title") or "LocalPlay results",
                "game_type": summary.get("game_type"),
                "total_rounds": summary.get("total_rounds") or summary.get("total_questions"),
                "player_count": summary.get("player_count"),
                "top_results": top_results,
                "players": top_results,
                "leaderboard": top_results,
                "winner": summary.get("winner") if isinstance(summary.get("winner"), dict) else (top_results[0] if top_results else None),
                "completed_at": summary.get("completed_at"),
            }
        leaderboard = summary.get("leaderboard") if isinstance(summary.get("leaderboard"), list) else []
        top_results = []
        for row in leaderboard[:5]:
            if not isinstance(row, dict):
                continue
            top_results.append({
                "nickname": row.get("nickname"),
                "avatar": row.get("avatar"),
                "score": row.get("score"),
            })
        return {
            "title": summary.get("title") or summary.get("game_title") or "LocalPlay results",
            "game_type": summary.get("game_type"),
            "total_rounds": summary.get("total_questions") or summary.get("total_rounds"),
            "player_count": summary.get("player_count"),
            "top_results": top_results,
            "players": top_results,
            "leaderboard": top_results,
            "winner": top_results[0] if top_results else None,
            "completed_at": summary.get("completed_at"),
        }

    def _safe_actor_payload(self, session: dict) -> Optional[dict]:
        actor = {
            "external_user_id": session.get("external_host_user_id") or "",
            "display_name": session.get("external_host_display_name") or "",
            "role": "host",
        }
        actor = {key: value for key, value in actor.items() if value}
        return actor or None

    def _mark_game_session_complete(self, room: Room, summary: dict):
        """Attach completed result metadata to an integration session, if present."""
        try:
            import db
            session = db.get_game_session_by_room(room.room_code)
            if not session:
                return
            if session.get("status") in ("complete", "superseded", "cancelled", "expired"):
                return
            now = int(time.time())
            safe_summary = self._safe_result_summary(summary)
            updated = db.update_game_session(session["id"], {
                "status": "complete",
                "joinable": False,
                "result_summary": safe_summary,
                "completed_at": now,
                "last_activity_at": now,
            })
            self._send_integration_callback("session.completed", updated or session, safe_summary)
        except Exception:
            logger.warning("Could not update game session for room %s", room.room_code)

    def _send_integration_callback(self, event_type: str, session: dict, result_summary: Optional[dict] = None):
        if not config.REVELRY_CALLBACK_URL or session.get("host_app") != "revelry":
            return
        event_type = self._callback_event_type(event_type)
        session_id = session.get("id")
        result_summary = self._safe_result_summary(result_summary) if result_summary else None
        actor_payload = self._safe_actor_payload(session)
        body = {
            "event_id": f"lp_evt_{uuid.uuid4().hex}",
            "event_type": event_type,
            "occurred_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "host_app": session.get("host_app"),
            "external_container_type": session.get("external_container_type"),
            "external_container_id": session.get("external_container_id"),
            "session_id": session_id,
            "idempotency_key": f"{event_type}:{session_id or uuid.uuid4().hex}:v1",
            "payload": {
                "room_code": session.get("room_code"),
                "status": session.get("status"),
                "actor": actor_payload,
                "game_type": session.get("game_type"),
                "game_title": session.get("game_title"),
                "result_summary": result_summary,
                "feed_card": session.get("feed_card"),
                "closed_reason": session.get("closed_reason"),
                "closed_message": session.get("closed_message"),
                "superseded_by_session_id": session.get("superseded_by_session_id"),
            },
        }
        body["payload"] = {key: value for key, value in body["payload"].items() if value is not None}
        body = {key: value for key, value in body.items() if value is not None}
        raw = json.dumps(body, separators=(",", ":")).encode()
        timestamp = str(int(time.time()))
        headers = {
            "Content-Type": "application/json",
            "X-LocalPlay-Event-Id": body["event_id"],
            "X-LocalPlay-Timestamp": timestamp,
        }
        signing_secret = self._callback_signing_secret()
        if signing_secret:
            signature = hmac.new(
                signing_secret.encode(),
                f"{timestamp}.".encode() + raw,
                hashlib.sha256,
            ).hexdigest()
            headers["X-LocalPlay-Signature"] = f"sha256={signature}"
        with httpx.Client(timeout=5.0) as client:
            for attempt in range(3):
                try:
                    response = client.post(config.REVELRY_CALLBACK_URL, content=raw, headers=headers)
                    response.raise_for_status()
                    return
                except httpx.HTTPStatusError as exc:
                    status = exc.response.status_code
                    if status not in (429, 500, 502, 503, 504) or attempt == 2:
                        logger.warning("Integration callback failed for %s: %s", event_type, exc)
                        return
                    time.sleep(self._callback_retry_delay(exc.response, attempt))
                except httpx.HTTPError as exc:
                    if attempt == 2:
                        logger.warning("Integration callback failed for %s: %s", event_type, exc)
                        return
                    time.sleep(self._callback_retry_delay(None, attempt))

    def _mark_game_session_started(self, room: Room):
        try:
            import db
            session = db.get_game_session_by_room(room.room_code)
            if not session or session.get("started_at"):
                return
            now = int(time.time())
            updated = db.update_game_session(session["id"], {
                "status": "active",
                "started_at": now,
                "expires_at": now + config.REVELRY_SESSION_IDLE_TTL_SECONDS,
                "last_activity_at": now,
            })
            self._send_integration_callback("session.started", updated or session)
        except Exception:
            logger.warning("Could not mark game session started for room %s", room.room_code)

    def _mark_game_session_closed(self, room: Room, reason: str, message: str):
        try:
            import db
            session = db.get_game_session_by_room(room.room_code)
            if not session or session.get("status") in ("complete", "superseded", "cancelled", "expired"):
                return
            now = int(time.time())
            updated = db.update_game_session(session["id"], {
                "status": reason,
                "joinable": False,
                "closed_reason": reason,
                "closed_message": message,
                "last_activity_at": now,
            })
            self._send_integration_callback(f"session.{reason}", updated or session)
        except Exception:
            logger.warning("Could not mark game session closed for room %s", room.room_code)

    def _select_bonus_questions(self, room: Room):
        """Pre-select which rounds will be bonus rounds (2x points)."""
        import random
        total = room.total_rounds()
        if total < 4:
            room.bonus_questions = set()
            return
        # Eligible: exclude first and last question
        eligible = list(range(1, total - 1))
        num_bonus = max(1, int(total * config.BONUS_ROUND_FRACTION))
        num_bonus = min(num_bonus, len(eligible))
        room.bonus_questions = set(random.sample(eligible, num_bonus))
        logger.info("Room %s bonus questions: %s", room.room_code, room.bonus_questions)

    async def start_question(self, room: Room):
        if (
            room.game_type == "drawing"
            and room.drawing_auto_task
            and room.drawing_auto_task is not asyncio.current_task()
        ):
            room.drawing_auto_task.cancel()
            room.drawing_auto_task = None
        if room.timer_task:
            room.timer_task.cancel()

        room.current_question_index += 1

        if room.current_question_index >= room.total_rounds():
            room.state = "PODIUM"
            leaderboard = self.get_leaderboard(room)
            team_leaderboard = self.get_team_leaderboard(room)
            podium_msg: dict = {
                "type": "PODIUM",
                "leaderboard": leaderboard,
                "team_leaderboard": team_leaderboard,
            }
            if room.game_type == "wmlt":
                podium_msg["superlatives"] = self._calculate_wmlt_superlatives(room)
            await room.broadcast(podium_msg)
            # Save game history — import here to avoid circular dependency
            try:
                from main import game_history
                summary = self.get_game_summary(room)
                game_history.append(summary)
                if len(game_history) > config.MAX_GAME_HISTORY:
                    del game_history[:len(game_history) - config.MAX_GAME_HISTORY]
                self._mark_game_session_complete(room, summary)
                logger.info("Game history saved for room %s", room.room_code)
            except Exception:
                logger.warning("Could not save game history for room %s", room.room_code)
            return

        # Store previous leaderboard for animation
        room.previous_leaderboard = self.get_leaderboard(room)

        room.answered_players = set()
        room.votes = {}  # Clear WMLT votes for new round
        room.correct_guessers = set()
        room.drawing_ops = []
        room.guess_log = []

        # Clear per-question power-up state from previous question
        for pups in room.power_ups.values():
            pups.pop("fifty_fifty_remove_indices", None)
            pups.pop("double_points_active", None)

        is_bonus = room.current_question_index in room.bonus_questions

        # Set state to QUESTION before broadcast so answers/votes are accepted immediately
        room.state = "QUESTION"

        if room.game_type == "wmlt":
            statement = room.current_round_data()
            if not statement:
                return
            await room.broadcast({
                "type": "QUESTION",
                "statement": statement,
                "question_number": room.current_question_index + 1,
                "total_questions": room.total_rounds(),
                "time_limit": room.time_limit,
                "is_bonus": is_bonus,
                "game_type": "wmlt",
                "players": [
                    {"nickname": p["nickname"], "avatar": p.get("avatar", "")}
                    for p in room.players.values()
                ],
            })
        elif room.game_type == "drawing":
            prompt = room.current_round_data()
            if not prompt:
                return
            room.current_drawer = self._drawer_for_round(room)
            await self._broadcast_drawing_question(room, prompt, is_bonus)
        else:
            question = room.current_round_data()
            if not question:
                return
            player_question = {k: v for k, v in question.items() if k != "answer_index"}
            await room.broadcast({
                "type": "QUESTION",
                "question": player_question,
                "question_number": room.current_question_index + 1,
                "total_questions": room.total_rounds(),
                "time_limit": room.time_limit,
                "is_bonus": is_bonus,
            })

        # Delay timer start for bonus rounds so the splash animation plays first
        if is_bonus:
            await asyncio.sleep(2)

        # If all players answered during the bonus splash, end_question was
        # already called — don't start the timer.
        if room.state != "QUESTION":
            return

        room.question_start_time = time.time()
        room.timer_task = asyncio.create_task(self.question_timer(room))

    async def question_timer(self, room: Room):
        """Timer that ends the question after time_limit seconds."""
        try:
            for remaining in range(room.time_limit, -1, -1):
                payload = {"type": "TIMER", "remaining": remaining}
                if room.game_type == "drawing" and room.state == "QUESTION":
                    payload["drawing_clue"] = self._drawing_clue(room)
                    payload["drawer"] = room.current_drawer
                await room.broadcast(payload)
                if remaining > 0:
                    await asyncio.sleep(1)

            await self.end_question(room)
        except asyncio.CancelledError:
            pass

    async def end_question(self, room: Room):
        # Guard against double-fire (timer + all-answered race)
        if room.state != "QUESTION":
            return

        room.state = "LEADERBOARD"

        if room.timer_task:
            room.timer_task.cancel()
            room.timer_task = None

        if room.game_type == "wmlt":
            await self._end_wmlt_round(room)
            return
        if room.game_type == "drawing":
            await self._end_drawing_round(room)
            return

        # Reset streak for players who didn't answer
        for cid, player in room.players.items():
            if cid not in room.answered_players:
                player["streak"] = 0

        question = room.current_round_data()
        if not question:
            return
        current_leaderboard = self.get_leaderboard_with_changes(room)
        is_final = room.current_question_index >= room.total_rounds() - 1

        await room.broadcast({
            "type": "QUESTION_OVER",
            "answer": question["answer_index"],
            "leaderboard": current_leaderboard,
            "previous_leaderboard": room.previous_leaderboard,
            "is_final": is_final
        })

    async def _end_drawing_round(self, room: Room):
        prompt = room.current_round_data()
        if not prompt:
            return
        current_leaderboard = self.get_leaderboard_with_changes(room)
        is_final = room.current_question_index >= room.total_rounds() - 1
        room.answer_log.append({
            "question_index": room.current_question_index,
            "game_type": "drawing",
            "prompt": prompt.get("text", ""),
            "drawer": room.current_drawer,
            "correct_guessers": list(room.correct_guessers),
            "guess_log": room.guess_log[-20:],
        })
        await room.broadcast({
            "type": "QUESTION_OVER",
            "game_type": "drawing",
            "prompt": prompt.get("text", ""),
            "drawer": room.current_drawer,
            "correct_guessers": list(room.correct_guessers),
            "leaderboard": current_leaderboard,
            "previous_leaderboard": room.previous_leaderboard,
            "is_final": is_final,
        })
        if room.drawing_auto_task:
            room.drawing_auto_task.cancel()
            room.drawing_auto_task = None
        if room.drawing_auto_advance:
            room.drawing_auto_task = asyncio.create_task(self._drawing_auto_advance_after_pause(room, is_final))

    async def _drawing_auto_advance_after_pause(self, room: Room, is_final: bool):
        delay = max(0, min(30, int(room.drawing_inter_round_seconds or 5)))
        try:
            for remaining in range(delay, 0, -1):
                if room.state != "LEADERBOARD" or room.game_type != "drawing":
                    return
                await room.broadcast({
                    "type": "DRAWING_NEXT_ROUND_PENDING",
                    "remaining": remaining,
                    "is_final": is_final,
                    "next_label": "Final results" if is_final else "Next round",
                })
                await asyncio.sleep(1)
            if room.state == "LEADERBOARD" and room.game_type == "drawing":
                await self.start_question(room)
        except asyncio.CancelledError:
            pass
        finally:
            if room.drawing_auto_task is asyncio.current_task():
                room.drawing_auto_task = None

    async def _end_wmlt_round(self, room: Room):
        """Handle end-of-round scoring and results for Who's Most Likely To."""
        statement = room.current_round_data()

        # Tally votes: voted_for_nickname -> list of voter nicknames
        vote_tally: Dict[str, List[str]] = {}
        for voter, voted_for in room.votes.items():
            vote_tally.setdefault(voted_for, []).append(voter)

        # Find winner(s) — all players tied for most votes are winners
        winners: List[str] = []
        winner_votes = 0
        if vote_tally:
            max_votes = max(len(voters) for voters in vote_tally.values())
            winners = sorted(n for n, voters in vote_tally.items() if len(voters) == max_votes)
            winner_votes = max_votes

        is_bonus = room.current_question_index in room.bonus_questions
        is_unanimous = winner_votes == len(room.votes) and winner_votes > 1 and len(winners) == 1

        # Score players
        winners_set = set(winners)
        for cid, player in room.players.items():
            nickname = player["nickname"]
            voted_for = room.votes.get(nickname)

            if voted_for is None:
                # Didn't vote — break streak
                player["streak"] = 0
                continue

            if voted_for in winners_set:
                # Voted for a winner
                base_points = 500
                if is_bonus:
                    base_points *= 2
                if is_unanimous:
                    base_points += 200

                # Streak bonus
                player["streak"] = player.get("streak", 0) + 1
                streak = player["streak"]
                multiplier = 1.0
                for threshold, mult in sorted(config.STREAK_THRESHOLDS.items()):
                    if streak >= threshold:
                        multiplier = mult
                points = int(base_points * multiplier)
                player["score"] += points
            else:
                # Voted for someone else — break streak
                player["streak"] = 0

        # Bonus for each winner (most-voted person) if they're a player
        for cid, player in room.players.items():
            if player["nickname"] in winners_set:
                player["score"] += 100

        # Build round podium: all voted-for players sorted by vote count
        player_avatars = {p["nickname"]: p.get("avatar", "") for p in room.players.values()}
        round_podium = []
        for nickname, voters in sorted(vote_tally.items(), key=lambda x: len(x[1]), reverse=True):
            round_podium.append({
                "nickname": nickname,
                "avatar": player_avatars.get(nickname, ""),
                "vote_count": len(voters),
                "voters": voters if room.show_votes else [],
            })

        # Store round data for superlatives
        room.mlt_round_history.append({
            "votes": dict(room.votes),  # voter -> target
            "winner": winners[0] if winners else None,
            "winners": winners,
            "winner_votes": winner_votes,
            "round_podium": round_podium,
        })

        # Log for game history
        room.answer_log.append({
            "question_index": room.current_question_index,
            "game_type": "wmlt",
            "statement": statement.get("text", "") if statement else "",
            "votes": dict(room.votes),
            "winners": winners,
            "winner_votes": winner_votes,
            "unanimous": is_unanimous,
        })

        current_leaderboard = self.get_leaderboard_with_changes(room)
        is_final = room.current_question_index >= room.total_rounds() - 1

        # winner = first for backward compat, winners = full list for tie display
        await room.broadcast({
            "type": "QUESTION_OVER",
            "game_type": "wmlt",
            "statement": statement.get("text", "") if statement else "",
            "votes": vote_tally if room.show_votes else {},
            "round_podium": round_podium,
            "winner": winners[0] if winners else None,
            "winners": winners,
            "winner_votes": winner_votes,
            "unanimous": is_unanimous,
            "show_votes": room.show_votes,
            "leaderboard": current_leaderboard,
            "previous_leaderboard": room.previous_leaderboard,
            "is_final": is_final,
            "is_bonus": is_bonus,
        })

    def _calculate_wmlt_superlatives(self, room: Room) -> List[dict]:
        """Calculate fun end-of-game superlatives for WMLT."""
        from collections import Counter
        superlatives = []
        if not room.mlt_round_history:
            return superlatives

        player_avatars = {p["nickname"]: p.get("avatar", "") for p in room.players.values()}
        for nickname, data in room.disconnected_players.items():
            player_avatars[nickname] = data.get("avatar", "")

        # "Most Likely To Everything" — most total votes received
        total_votes_received: Counter = Counter()
        for rnd in room.mlt_round_history:
            for voter, target in rnd.get("votes", {}).items():
                total_votes_received[target] += 1
        if total_votes_received and total_votes_received.most_common(1):
            top = total_votes_received.most_common(1)[0]
            superlatives.append({
                "title": "Most Likely To Everything",
                "icon": "🏆",
                "winner": top[0],
                "avatar": player_avatars.get(top[0], ""),
                "detail": f"Received {top[1]} total votes",
            })

        # "Narcissist Award" — most self-votes
        self_votes: Counter = Counter()
        for rnd in room.mlt_round_history:
            for voter, target in rnd.get("votes", {}).items():
                if voter == target:
                    self_votes[voter] += 1
        if self_votes and self_votes.most_common(1):
            top = self_votes.most_common(1)[0]
            if top[1] > 0:
                superlatives.append({
                    "title": "Narcissist Award",
                    "icon": "🪞",
                    "winner": top[0],
                    "avatar": player_avatars.get(top[0], ""),
                    "detail": f"Voted for themselves {top[1]} time{'s' if top[1] != 1 else ''}",
                })

        # "Mind Reader" — voted with the majority most often
        majority_counts: Counter = Counter()
        for rnd in room.mlt_round_history:
            round_winners = set(rnd.get("winners", []))
            if not round_winners and rnd.get("winner"):
                round_winners = {rnd["winner"]}
            if round_winners:
                for voter, target in rnd.get("votes", {}).items():
                    if target in round_winners:
                        majority_counts[voter] += 1
        if majority_counts and majority_counts.most_common(1):
            top = majority_counts.most_common(1)[0]
            if top[1] > 0:
                superlatives.append({
                    "title": "Mind Reader",
                    "icon": "🔮",
                    "winner": top[0],
                    "avatar": player_avatars.get(top[0], ""),
                    "detail": f"Voted with the majority {top[1]} time{'s' if top[1] != 1 else ''}",
                })

        # "Most Controversial" — involved in closest vote splits
        controversial: Counter = Counter()
        for rnd in room.mlt_round_history:
            podium = rnd.get("round_podium", [])
            if len(podium) >= 2:
                top_two = sorted(podium, key=lambda x: x["vote_count"], reverse=True)[:2]
                if top_two[0]["vote_count"] - top_two[1]["vote_count"] <= 1:
                    controversial[top_two[0]["nickname"]] += 1
                    controversial[top_two[1]["nickname"]] += 1
        if controversial and controversial.most_common(1):
            top = controversial.most_common(1)[0]
            if top[1] > 0:
                superlatives.append({
                    "title": "Most Controversial",
                    "icon": "🔥",
                    "winner": top[0],
                    "avatar": player_avatars.get(top[0], ""),
                    "detail": f"Part of {top[1]} close vote{'s' if top[1] != 1 else ''}",
                })

        return superlatives

    def _all_players_for_leaderboard(self, room: Room) -> List[dict]:
        """Combine active and disconnected players for leaderboard inclusion."""
        all_players = list(room.players.values())
        for nickname, data in room.disconnected_players.items():
            all_players.append({
                "nickname": nickname,
                "score": data["score"],
                "avatar": data.get("avatar", ""),
                "prev_rank": data.get("prev_rank", 0),
                "streak": data.get("streak", 0),
            })
        return all_players

    def get_leaderboard(self, room: Room) -> List[dict]:
        if room.game_type == "musical_chairs":
            avatars = room.player_avatar_map()
            ordered = []
            if room.mc_active_players:
                ordered.extend(room.mc_active_players)
            ordered.extend([item["nickname"] for item in reversed(room.mc_eliminated_players)])
            seen = set()
            result = []
            total = len(ordered)
            for index, nickname in enumerate(ordered):
                if nickname in seen:
                    continue
                seen.add(nickname)
                result.append({
                    "nickname": nickname,
                    "score": max(0, total - index),
                    "avatar": avatars.get(nickname, next((item.get("avatar", "") for item in room.mc_eliminated_players if item.get("nickname") == nickname), "")),
                })
            return result
        if room.game_type == "bluff" and room.bluff_state:
            avatars = room.player_avatar_map()
            for nickname, data in room.disconnected_players.items():
                avatars[nickname] = data.get("avatar", "")
            hands = room.bluff_state.get("hands", {})
            winners = room.bluff_state.get("winners", [])
            winner_places = {winner["player_id"]: int(winner.get("place", 99)) for winner in winners}
            all_names = list(room.bluff_state.get("players", []))
            ordered = sorted(
                all_names,
                key=lambda name: (winner_places.get(name, 99), len(hands.get(name, []))),
            )
            total = len(all_names)
            return [
                {
                    "nickname": name,
                    "score": max(0, total - index) if name in winner_places else max(0, 52 - len(hands.get(name, []))),
                    "avatar": avatars.get(name, ""),
                }
                for index, name in enumerate(ordered)
            ]
        sorted_players = sorted(
            self._all_players_for_leaderboard(room),
            key=lambda x: x["score"],
            reverse=True
        )
        return [{"nickname": p["nickname"], "score": p["score"], "avatar": p.get("avatar", "")} for p in sorted_players]

    def get_leaderboard_with_changes(self, room: Room) -> List[dict]:
        prev_rankings = {p["nickname"]: i for i, p in enumerate(room.previous_leaderboard)}

        sorted_players = sorted(
            self._all_players_for_leaderboard(room),
            key=lambda x: x["score"],
            reverse=True
        )

        result = []
        for i, player in enumerate(sorted_players):
            prev_rank = prev_rankings.get(player["nickname"], len(prev_rankings) + 1)
            result.append({
                "nickname": player["nickname"],
                "score": player["score"],
                "avatar": player.get("avatar", ""),
                "prev_rank": prev_rank,
                "rank_change": prev_rank - i  # positive = moved up
            })

        return result


socket_manager = SocketManager()
