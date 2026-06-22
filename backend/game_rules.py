from __future__ import annotations

import copy
from typing import Any


def _rules(
    title: str,
    summary: str,
    objective: list[str],
    flow: list[str],
    scoring: list[str],
    *,
    players: dict[str, Any] | None = None,
    setup: list[str] | None = None,
    privacy: list[str] | None = None,
    late_join_policy: str = "Late joiners can wait in the lobby or join the next room unless this game explicitly supports mid-game joins.",
    host_notes: list[str] | None = None,
    player_notes: list[str] | None = None,
    physical_setup: list[str] | None = None,
) -> dict[str, Any]:
    sections = [
        {"id": "objective", "title": "Objective", "items": objective},
    ]
    if setup:
        sections.append({"id": "setup", "title": "Setup", "items": setup})
    sections.extend([
        {"id": "flow", "title": "How it works", "items": flow},
        {"id": "scoring", "title": "Scoring and winning", "items": scoring},
    ])
    if privacy:
        sections.append({"id": "privacy", "title": "Keep private", "items": privacy})
    sections.append({"id": "late_join", "title": "Late joins", "items": [late_join_policy]})
    return {
        "version": 1,
        "title": title,
        "summary": summary,
        "player_count": players or {},
        "sections": sections,
        "host_notes": host_notes or [],
        "player_notes": player_notes or [],
        "physical_setup": physical_setup or [],
        "late_join_policy": late_join_policy,
    }


GAME_RULES: dict[str, dict[str, Any]] = {
    "quiz": _rules(
        "AI Quiz Rules",
        "Answer multiple-choice questions as quickly and accurately as you can.",
        ["Score points by choosing the correct answer before time runs out."],
        ["The host starts each question.", "Players answer on their own phones.", "The room sees results between questions."],
        ["Correct answers score points.", "Faster correct answers can rank higher when tiebreakers apply.", "Highest score wins."],
        players={"min": 1, "recommended": "3-20"},
        host_notes=["Review generated questions before starting when using AI."],
    ),
    "wmlt": _rules(
        "Most Likely To Rules",
        "Vote for the person who best matches each prompt.",
        ["Match each prompt to the player who fits it best."],
        ["The host reveals a prompt.", "Everyone votes on their phone.", "The winning player is revealed after voting."],
        ["Winners score for being selected.", "The final podium ranks players by round wins or points."],
        players={"min": 2, "recommended": "4-20"},
        privacy=["Votes may be anonymous depending on the host setting."],
    ),
    "drawing": _rules(
        "Drawing Game Rules",
        "One player draws a secret prompt while everyone else guesses.",
        ["Guess the drawing before the timer runs out."],
        ["A drawer is assigned each round.", "Only the drawer sees the secret prompt.", "Guessers type answers on their phones."],
        ["Correct guessers score points.", "The drawer can earn credit when people guess correctly.", "Most points wins."],
        players={"min": 2, "recommended": "4-12"},
        privacy=["Drawers should not say or write the exact answer unless the host allows it."],
    ),
    "housie": _rules(
        "Housie Rules",
        "Mark called numbers on your ticket and claim prizes when patterns complete.",
        ["Complete prize patterns on your ticket before other players claim them."],
        ["The caller draws numbers.", "Players mark matching numbers.", "Claim a prize when your marked ticket satisfies that pattern."],
        ["Valid claims award the prize.", "Invalid claims are rejected with a reason.", "Full House or the configured final prize ends the game."],
        players={"min": 1, "recommended": "4-50"},
        setup=["Each player receives a server-generated ticket."],
    ),
    "bingo": _rules(
        "Bingo Rules",
        "Mark called items on your board and claim the configured patterns.",
        ["Complete a line, corners, blackout, or other host-selected pattern."],
        ["The host calls items from the deck.", "Players mark matching board cells.", "Players claim when a pattern is complete."],
        ["Valid claims award prizes.", "The host can continue until the final configured prize."],
        players={"min": 1, "recommended": "4-50"},
        setup=["Boards can use text, emoji, or image items depending on the setup."],
    ),
    "baby_bingo": _rules(
        "Baby Bingo Rules",
        "Play Bingo with baby-shower gifts, moments, and tiny surprises.",
        ["Mark baby-shower items and moments as they are called."],
        ["The host calls items.", "Players mark matching cells.", "Claim when your board completes a prize pattern."],
        ["Valid claims win prizes.", "The host can keep calling until the final prize."],
        players={"min": 1, "recommended": "4-50"},
        setup=["Works best with a shared gift-opening or shower activity moment."],
    ),
    "musical_chairs": _rules(
        "Musical Chairs Rules",
        "Music plays, then stops at a random time. The last player standing wins.",
        ["Survive each round until only one player remains."],
        ["The host starts music.", "When music stops, players either grab real chairs or tap on their phones depending on mode.", "One player is eliminated each round."],
        ["Eliminated players are ranked by round.", "The final remaining player wins."],
        players={"min": 3, "recommended": "6-30"},
        setup=["Physical mode needs one fewer chair than active players.", "Phone-tap mode needs every player on their own device."],
        physical_setup=["Clear space around chairs before starting."],
    ),
    "bluff": _rules(
        "Bluff Rules",
        "Play cards face down, claim a rank, and decide whether to challenge.",
        ["Get rid of your cards by bluffing, telling the truth, and calling other players at the right time."],
        ["Players take turns playing cards face down.", "The active player claims what rank they played.", "Other players may challenge the claim."],
        ["A failed bluff makes the bluffer pick up cards.", "A wrong challenge punishes the challenger.", "First player to empty their hand wins."],
        players={"min": 3, "recommended": "4-12"},
        privacy=["Keep your hand private."],
    ),
    "two_truths": _rules(
        "Two Truths and a Lie Rules",
        "Submit two true statements and one lie. Everyone guesses the lie.",
        ["Fool the room with a believable lie and spot other players' lies."],
        ["Each player submits three statements.", "One player is revealed at a time.", "Everyone votes for the statement they think is the lie."],
        ["Guessers score for finding the lie.", "Authors score when players are fooled.", "Highest score wins."],
        players={"min": 2, "recommended": "4-20"},
        privacy=["Do not reveal your lie before voting ends."],
    ),
    "story_chain": _rules(
        "Story Chain Rules",
        "Each player adds one sentence to build a shared story.",
        ["Create the funniest or most surprising story together."],
        ["Players take turns adding a sentence.", "Depending on mode, writers may see the full story or only the latest sentence.", "The final story is revealed at the end."],
        ["This is usually scored by completion or host choice.", "The group wins when the final story lands."],
        players={"min": 2, "recommended": "4-12"},
    ),
    "common_ground": _rules(
        "Common Ground Rules",
        "Teams find things they all have in common.",
        ["Discover shared facts that are specific, surprising, or funny."],
        ["Players are assigned to teams.", "Teams discuss and submit common-ground answers.", "The room reveals and may vote on favorites."],
        ["Teams score for valid submissions and votes.", "Highest team score wins."],
        players={"min": 2, "recommended": "6-30"},
        late_join_policy="Late joiners can be assigned to a team while the game is active.",
    ),
    "find_someone": _rules(
        "Find Someone Who Rules",
        "Complete a social Bingo grid by finding people who match each prompt.",
        ["Meet people and complete board patterns by confirming matches."],
        ["Players get a grid of prompts.", "Find someone who matches a square.", "Ask them to confirm on their phone when required."],
        ["Claim patterns such as a line, corners, or blackout.", "The final scoreboard rewards completed squares and claims."],
        players={"min": 1, "recommended": "8-100"},
        late_join_policy="Late joiners can receive a board while the activity is active.",
    ),
    "who_am_i": _rules(
        "Who Am I? Rules",
        "Use clues to guess the mystery answer.",
        ["Guess the person, place, object, or phrase using as few clues as possible."],
        ["A clue appears each step.", "Players submit guesses.", "More clues appear until someone solves it or the round ends."],
        ["Earlier correct guesses score more points.", "Highest score wins after all rounds."],
        players={"min": 1, "recommended": "3-20"},
    ),
    "chit_pull": _rules(
        "Chit Pull Rules",
        "A random player gets a random prompt, action, or mini challenge.",
        ["Complete the chit when your name is picked."],
        ["The host starts a turn.", "The app picks a player and a chit.", "The host marks completed, skipped, or redraw."],
        ["Completed chits score points.", "Bonus completions can score extra.", "Highest score wins."],
        players={"min": 2, "recommended": "4-30"},
        host_notes=["Choose a safe level that fits the room."],
    ),
    "mafia": _rules(
        "Mafia Rules",
        "Find the Mafia before they outnumber the town.",
        ["Town wins by eliminating all Mafia.", "Mafia wins when they equal or outnumber the living Town."],
        ["Everyone gets a secret role.", "At night, every player receives a private prompt so action roles are not socially exposed.", "During the day, players discuss and vote to eliminate someone."],
        ["Eliminated players leave the vote.", "The game ends when Town or Mafia reaches its win condition."],
        players={"min": 5, "recommended": "7-15"},
        privacy=["Keep your role private unless the game reveals it.", "Mafia should coordinate only through private prompts."],
    ),
    "party_quests": _rules(
        "Party Quests Rules",
        "Complete mingling quests throughout the party and confirm each other.",
        ["Meet people, complete your quest board, and collect confirmations."],
        ["Each player receives a private quest board.", "Find another player who completes a quest condition.", "Ask them to confirm on their phone, or use honor mode if selected."],
        ["Confirmed quests score points.", "Unique partners and completed boards can earn bonuses.", "The host reveals the podium at the end."],
        players={"min": 1, "recommended": "8-100"},
        late_join_policy="Late joiners can receive a quest board while the activity is active if the host allows late joins.",
    ),
}


def rules_for_game(game_id: str) -> dict[str, Any]:
    return copy.deepcopy(GAME_RULES.get(game_id, {}))


def attach_rules(catalog: list[dict[str, Any]]) -> list[dict[str, Any]]:
    for game in catalog:
        game_id = str(game.get("id") or game.get("game_type") or "")
        rules = rules_for_game(game_id)
        if rules:
            game["rules"] = rules
    return catalog
