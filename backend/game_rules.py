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
        players={"min": 2, "recommended": "4-50"},
        setup=["Each player receives a server-generated ticket."],
    ),
    "bingo": _rules(
        "Bingo Rules",
        "Mark called items on your board and claim the configured patterns.",
        ["Complete a line, corners, blackout, or other host-selected pattern."],
        ["The host calls items from the deck.", "Players mark matching board cells.", "Players claim when a pattern is complete."],
        ["Valid claims award prizes.", "The host can continue until the final configured prize."],
        players={"min": 2, "recommended": "4-50"},
        setup=["Boards can use text, emoji, or image items depending on the setup."],
    ),
    "baby_bingo": _rules(
        "Baby Bingo Rules",
        "Play Bingo with baby-shower gifts, moments, and tiny surprises.",
        ["Mark baby-shower items and moments as they are called."],
        ["The host calls items.", "Players mark matching cells.", "Claim when your board completes a prize pattern."],
        ["Valid claims win prizes.", "The host can keep calling until the final prize."],
        players={"min": 2, "recommended": "4-50"},
        setup=["Works best with a shared gift-opening or shower activity moment."],
    ),
    "wedding_bingo": _rules(
        "Wedding Bingo Rules",
        "Play Bingo with the reception moments everyone is already watching for.",
        ["Mark wedding moments as they happen or as the host calls them."],
        ["The host calls items.", "Players mark matching cells.", "Claim when your board completes a prize pattern."],
        ["Valid claims win prizes.", "The host can keep calling until the final prize."],
        players={"min": 2, "recommended": "6-60"},
        setup=["Great during the reception — guests play between courses without leaving their seats."],
    ),
    "holiday_bingo": _rules(
        "Holiday Bingo Rules",
        "Play Bingo with the family-gathering moments that happen every single year.",
        ["Mark holiday moments as they happen or as the host calls them."],
        ["The host calls items.", "Players mark matching cells.", "Claim when your board completes a prize pattern."],
        ["Valid claims win prizes.", "The host can keep calling until the final prize."],
        players={"min": 2, "recommended": "4-30"},
        setup=["Works as an ambient game across a whole evening, not just one sitting."],
    ),
    "road_trip_bingo": _rules(
        "Road Trip Bingo Rules",
        "Play Bingo with what you actually see and hear on a long drive.",
        ["Mark road-trip sights and moments as they happen."],
        ["The host calls items, or players self-mark on the honour system.", "Players mark matching cells.", "Claim when your board completes a prize pattern."],
        ["Valid claims win prizes.", "The host can keep calling until the final prize."],
        players={"min": 2, "recommended": "2-8"},
        setup=["Designed for passengers — the driver should not be playing."],
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
        players={"min": 3, "recommended": "4-20"},
        privacy=["Do not reveal your lie before voting ends."],
    ),
    "story_chain": _rules(
        "Story Chain Rules",
        "Each player adds one sentence to build a shared story.",
        ["Create the funniest or most surprising story together."],
        ["Players take turns adding a sentence.", "Depending on mode, writers may see the full story or only the latest sentence.", "The final story is revealed at the end."],
        ["This is usually scored by completion or host choice.", "The group wins when the final story lands."],
        players={"min": 3, "recommended": "4-12"},
    ),
    "common_ground": _rules(
        "Common Ground Rules",
        "Teams find things they all have in common.",
        ["Discover shared facts that are specific, surprising, or funny."],
        ["Players are assigned to teams.", "Teams discuss and submit common-ground answers.", "The room reveals and may vote on favorites."],
        ["Teams score for valid submissions and votes.", "Highest team score wins."],
        players={"min": 4, "recommended": "6-30"},
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
        players={"min": 2, "recommended": "3-20"},
    ),
    "chit_pull": _rules(
        "Random Chit Rules",
        "A random player gets a random prompt, action, or mini challenge.",
        ["Complete the chit when your name is picked."],
        ["The host starts a turn.", "The app picks a player and a chit.", "The selected player answers, acts, or performs the prompt.", "The host marks completed, bonus completed, skipped, or redraw."],
        ["Completed chits score points.", "Bonus completions can score extra.", "Highest score wins."],
        players={"min": 3, "recommended": "4-30"},
        host_notes=["Choose a safe level that fits the room."],
    ),
    "mafia": _rules(
        "Mafia Rules",
        "Find the Mafia before they outnumber the town.",
        ["Town wins by eliminating all Mafia.", "Mafia wins when they equal or outnumber the living Town."],
        ["Everyone gets a secret role.", "At night, action roles choose targets and every living player answers a quiet Night Read, so roles are not socially exposed.", "During the day, players discuss and vote to eliminate someone."],
        ["Eliminated players leave the vote.", "The game ends when Town or Mafia reaches its win condition."],
        players={"min": 6, "recommended": "7-15"},
        privacy=["Keep your role private unless the game reveals it.", "Everyone checks their phone at night so roles are harder to infer.", "Mafia coordinate only through private target votes."],
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
    "survey_says": _rules(
        "Survey Says Rules",
        "Teams guess the top survey answers while the host reveals the board and tracks strikes.",
        ["Win rounds by finding high-value answers and protecting the bank."],
        ["Players submit guesses on their phones.", "The host reveals matching answers or gives strikes.", "After max strikes, the other team gets one steal chance."],
        ["Revealed answers build a round bank.", "Clearing the board wins the bank.", "A successful steal wins the bank for the stealing team."],
        players={"min": 2, "recommended": "6-30"},
        late_join_policy="Late joiners can be added to the smaller team while the game is active.",
        host_notes=["The host adjudicates close guesses and can reveal all answers to end a round."],
    ),
    "hot_takes": _rules(
        "Hot Takes Rules",
        "Agree or disagree with party-safe hot takes, then reveal where the room lands.",
        ["Choose your side and see whether you are with the majority."],
        ["Each round shows one take.", "Players pick one option on their phones.", "The host reveals the vote split and advances."],
        ["Players on a single majority side score one point.", "Ties are fun drama but do not score.", "Highest score wins after the final round."],
        players={"min": 2, "recommended": "4-30"},
    ),
    "this_or_that": _rules(
        "This or That Rules",
        "Pick between two fast options and compare the room split.",
        ["Choose the side that fits you best each round."],
        ["Each round shows a prompt with two options.", "Players choose on their phones.", "The host reveals the split and moves on."],
        ["Players on a single majority side score one point.", "Highest score wins."],
        players={"min": 2, "recommended": "4-30"},
    ),
    "caption_contest": _rules(
        "Caption Contest Rules",
        "Write the funniest caption for the prompt and vote for the winner.",
        ["Submit a caption the room will want to vote for."],
        ["Each round shows a caption setup.", "Players submit short captions.", "The host opens voting, then reveals results."],
        ["Each vote on your caption scores one point.", "Highest score wins after the final round."],
        players={"min": 2, "recommended": "4-20"},
    ),
    "pitch_battle": _rules(
        "Pitch Battle Rules",
        "Invent a ridiculous product, app, or idea and vote for the best pitch.",
        ["Create the pitch the room likes most."],
        ["Each round gives a pitch brief.", "Players submit one short pitch.", "The room votes for the strongest or funniest pitch."],
        ["Each vote on your pitch scores one point.", "Highest score wins."],
        players={"min": 2, "recommended": "4-20"},
    ),
    "roast_toast": _rules(
        "Roast & Toast Rules",
        "Write playful compliments or gentle roasts and vote for the best line.",
        ["Land the most memorable toast or room-safe roast."],
        ["Each round gives a toast or gentle-roast prompt.", "Players submit short lines.", "The room votes for the favorite."],
        ["Each vote on your line scores one point.", "Keep it kind enough for the room."],
        players={"min": 2, "recommended": "4-20"},
        host_notes=["Use only with a room that is comfortable with playful teasing."],
    ),
    "desert_island": _rules(
        "Desert Island Rules",
        "Answer survival-style favorites and vote for the room's best pick.",
        ["Submit the answer the room would most want to bring along."],
        ["Each round asks what you would bring to a desert island.", "Players submit answers.", "The room votes for the favorite."],
        ["Each vote scores one point for the answer author.", "Highest score wins."],
        players={"min": 2, "recommended": "4-20"},
    ),
    "memory_lane": _rules(
        "Memory Lane Rules",
        "Share tiny memories or mini stories and vote for the favorite.",
        ["Write a short memory the room enjoys."],
        ["Each round asks for a memory or mini story.", "Players submit short responses.", "The room votes for the favorite."],
        ["Each vote scores one point for the author.", "Highest score wins."],
        players={"min": 2, "recommended": "4-20"},
    ),
    "rapid_fire": _rules(
        "Rapid Fire Rules",
        "Submit the first answer that comes to mind and reveal matching groups.",
        ["Match as many players as possible with your instinctive answer."],
        ["Each round shows a quick prompt.", "Players submit short answers.", "The host reveals grouped matches."],
        ["Players in the largest matching group score one point.", "No score is awarded if nobody matches."],
        players={"min": 2, "recommended": "4-30"},
    ),
    "one_word_vibes": _rules(
        "One Word Vibes Rules",
        "Describe a prompt in one word and see who matches your vibe.",
        ["Match the room's instinct with one-word answers."],
        ["Each round shows a vibe prompt.", "Players submit one short answer.", "The host reveals grouped matches."],
        ["Players in the largest matching group score one point.", "Highest score wins."],
        players={"min": 2, "recommended": "4-30"},
    ),
    "emoji_story": _rules(
        "Emoji Story Rules",
        "Turn an emoji chain into a tiny story and vote for the best one.",
        ["Write the best mini story inspired by the emojis."],
        ["Each round shows an emoji chain.", "Players submit short stories.", "The room votes for the favorite."],
        ["Each vote scores one point for the story author.", "Highest score wins."],
        players={"min": 2, "recommended": "4-20"},
    ),
    "impostor": _rules(
        "Impostor Rules",
        "Everyone answers the same question — except one player, who got a different one.",
        [
            "Spot the player whose question was different.",
            "If you are the odd one out, blend in and survive the vote.",
        ],
        [
            "Everyone gets a question on their phone. One player's is secretly different.",
            "Everyone submits a short answer.",
            "All answers are revealed, and everyone votes for who they think was the odd one.",
            "The odd one and both questions are revealed, then the host advances.",
        ],
        [
            "Guess the odd one correctly: 2 points.",
            "Odd one survives without a majority naming them: 3 points.",
            "Odd one also gets 1 bonus point for voting with the crowd against someone innocent.",
            "Being the odd one rotates, so everyone gets a turn.",
        ],
        players={"min": 3, "recommended": "4-10"},
    ),
    "would_you_rather": _rules(
        "Would You Rather Rules",
        "Pick between two options and reveal how the room splits.",
        ["Choose the option you prefer each round."],
        ["The host starts a round.", "Players vote A or B on their phones.", "The host reveals the split, then advances."],
        ["Majority voters score when scoring is enabled.", "Highest score wins after the final round."],
        players={"min": 2, "recommended": "4-30"},
    ),
    "never_have_i_ever": _rules(
        "Never Have I Ever Rules",
        "Answer each prompt privately, then reveal the group split.",
        ["Be honest and see what the room has or has not done."],
        ["Each round shows a statement.", "Players choose I have or Never.", "The host reveals the split, then advances."],
        ["Default mode is mostly for laughs.", "Optional minority scoring rewards rare answers."],
        players={"min": 2, "recommended": "4-30"},
    ),
    "word_association": _rules(
        "Word Association Rules",
        "Write the first word that comes to mind from a seed.",
        ["Match minds with other players."],
        ["Each round shows a seed word.", "Players submit one word.", "The host reveals grouped matches."],
        ["Players matching the largest group score in majority mode.", "Highest score wins."],
        players={"min": 2, "recommended": "4-30"},
    ),
    "acronym": _rules(
        "Acronym Game Rules",
        "Turn letters into funny phrases and vote for the best expansion.",
        ["Create the funniest matching phrase."],
        ["Each round shows an acronym.", "Players submit one phrase with matching first letters.", "The host opens voting, then reveals results."],
        ["Each vote on your expansion scores one point.", "Highest score wins after the final round."],
        players={"min": 2, "recommended": "4-20"},
    ),
    "photo_clue": _rules(
        "Photo Clue Rules",
        "One player receives a secret phrase, submits a photo clue, and the room guesses from the photo.",
        ["Use photos you are comfortable showing to this room.", "Do not include written text or the answer in your photo."],
        ["The server assigns clue givers and secret prompts up front.", "The clue giver uploads one photo clue.", "Everyone else types guesses until the host reveals the answer.", "The next round rotates to another clue giver."],
        ["Correct guessers score points.", "The clue giver scores when people guess their clue.", "Highest score wins after the final reveal."],
        players={"min": 2, "recommended": "4-12"},
        late_join_policy="Late joiners can watch and guess future photo rounds but do not receive new clue-giver assignments in the active game.",
    ),
    "poker": _rules(
        "Party Poker Rules",
        "Play a fast no-money Hold'em tournament with equal play-chip stacks.",
        ["Play chips exist only inside this room.", "There are no buy-ins, cash-outs, prizes, or spark rewards."],
        ["Every active player posts the same play-chip ante.", "Each player gets two private cards and the table gets five community cards.", "Players choose Stay or Fold.", "The best remaining Hold'em hand wins the pot, then the next hand starts."],
        ["Players with zero chips are eliminated.", "The last player with chips wins, with runner-up and third based on elimination order."],
        players={"min": 2, "recommended": "4-10"},
    ),
}


def rules_for_game(game_id: str) -> dict[str, Any]:
    return copy.deepcopy(GAME_RULES.get(game_id, {}))


def validate_rules(rules: dict[str, Any], game_id: str) -> list[str]:
    errors: list[str] = []
    if not isinstance(rules, dict):
        return [f"{game_id}: rules must be an object"]
    if rules.get("version") != 1:
        errors.append(f"{game_id}: rules.version must be 1")
    for field in ("title", "summary"):
        if not isinstance(rules.get(field), str) or not rules[field].strip():
            errors.append(f"{game_id}: rules.{field} is required")
    sections = rules.get("sections")
    if not isinstance(sections, list) or not sections:
        errors.append(f"{game_id}: rules.sections must be a non-empty list")
        return errors
    section_ids: set[str] = set()
    for index, section in enumerate(sections):
        if not isinstance(section, dict):
            errors.append(f"{game_id}: rules.sections[{index}] must be an object")
            continue
        section_id = section.get("id")
        if not isinstance(section_id, str) or not section_id.strip():
            errors.append(f"{game_id}: rules.sections[{index}].id is required")
        elif section_id in section_ids:
            errors.append(f"{game_id}: duplicate rules section id {section_id}")
        else:
            section_ids.add(section_id)
        if not isinstance(section.get("title"), str) or not section["title"].strip():
            errors.append(f"{game_id}: rules.sections[{index}].title is required")
        items = section.get("items")
        if not isinstance(items, list) or not items or not all(isinstance(item, str) and item.strip() for item in items):
            errors.append(f"{game_id}: rules.sections[{index}].items must contain text")
    return errors


def validate_catalog_rules(catalog: list[dict[str, Any]]) -> None:
    errors: list[str] = []
    for game in catalog:
        if not game.get("enabled", True) or not game.get("launchable"):
            continue
        game_id = str(game.get("id") or game.get("game_type") or "")
        rules = game.get("rules")
        if not rules:
            errors.append(f"{game_id or '<unknown>'}: launchable game is missing rules")
            continue
        errors.extend(validate_rules(rules, game_id))
        configured_players = (game.get("config_schema") or {}).get("players") or {}
        rules_players = rules.get("player_count") or {}
        configured_min = configured_players.get("min")
        rules_min = rules_players.get("min")
        if configured_min is not None and rules_min != configured_min:
            errors.append(
                f"{game_id}: rules.player_count.min ({rules_min}) must match config_schema.players.min ({configured_min})"
            )
    if errors:
        raise ValueError("Invalid game rules metadata: " + "; ".join(errors))


def attach_rules(catalog: list[dict[str, Any]]) -> list[dict[str, Any]]:
    for game in catalog:
        game_id = str(game.get("id") or game.get("game_type") or "")
        rules = rules_for_game(game_id)
        if rules:
            game["rules"] = rules
    validate_catalog_rules(catalog)
    return catalog
