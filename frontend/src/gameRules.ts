import { type GameType } from './types';

export interface GameRuleSection {
    id: string;
    title: string;
    items: string[];
}

export interface GameRules {
    version: number;
    title: string;
    summary: string;
    player_count?: {
        min?: number;
        recommended?: string;
        max?: number;
    };
    sections: GameRuleSection[];
    host_notes?: string[];
    player_notes?: string[];
    physical_setup?: string[];
    late_join_policy?: string;
}

export interface CatalogGameWithRules {
    id: string;
    game_type?: string;
    title?: string;
    description?: string;
    launchable?: boolean;
    supports_ai_generation?: boolean;
    rules?: GameRules;
}

function rules(title: string, summary: string, objective: string[], flow: string[], scoring: string[], extra?: Partial<GameRules>): GameRules {
    return {
        version: 1,
        title,
        summary,
        sections: [
            { id: 'objective', title: 'Objective', items: objective },
            { id: 'flow', title: 'How it works', items: flow },
            { id: 'scoring', title: 'Scoring and winning', items: scoring },
            ...(extra?.sections || []),
        ],
        ...extra,
    };
}

export const LOCAL_GAME_RULES: Partial<Record<GameType, GameRules>> = {
    quiz: rules('AI Quiz Rules', 'Answer multiple-choice questions as quickly and accurately as you can.', ['Pick the correct answer before time runs out.'], ['The host starts each question.', 'Players answer on their phones.', 'Results show between questions.'], ['Correct answers score points.', 'Highest score wins.'], { player_count: { min: 1, recommended: '3-20' } }),
    rebus: rules('Rebus Rush Rules', 'Decode emoji and symbol clues before the room catches on.', ['Guess the hidden phrase represented by symbols.'], ['Each round shows a rebus clue.', 'Players choose or enter the answer.', 'The answer is revealed after the timer.'], ['Correct answers score points.', 'Highest score wins.'], { player_count: { min: 1, recommended: '3-20' } }),
    emoji_charades: rules('Emoji Charades Rules', 'Guess movies, songs, sayings, or places from emoji clues.', ['Decode the emoji clue faster than the room.'], ['Each round shows an emoji clue.', 'Players answer on their phones.', 'The answer is revealed after voting or timeout.'], ['Correct answers score points.', 'Highest score wins.'], { player_count: { min: 1, recommended: '3-20' } }),
    fact_fiction: rules('Fact or Fiction Rules', 'Decide whether each surprising claim is true or false.', ['Spot which claims are real.'], ['Each round shows one claim.', 'Players choose Fact or Fiction.', 'The correct answer appears after the timer.'], ['Correct answers score points.', 'Highest score wins.'], { player_count: { min: 1, recommended: '3-20' } }),
    timeline: rules('Timeline Twist Rules', 'Put events, releases, or moments in the correct order.', ['Choose the correct position or order for each timeline prompt.'], ['Each round asks about sequence or timing.', 'Players answer on their phones.', 'The correct order is revealed.'], ['Correct answers score points.', 'Highest score wins.'], { player_count: { min: 1, recommended: '3-20' } }),
    odd_one_out: rules('Odd One Out Rules', 'Find the item that breaks the pattern.', ['Choose the option that does not belong.'], ['Each round shows a set of related items.', 'Players pick the odd one out.', 'The pattern and answer are revealed.'], ['Correct answers score points.', 'Highest score wins.'], { player_count: { min: 1, recommended: '3-20' } }),
    wmlt: rules('Most Likely To Rules', 'Vote for the person who best matches each prompt.', ['Match each prompt to a player.'], ['The host reveals a prompt.', 'Everyone votes.', 'The winner is revealed.'], ['Round winners score points.', 'Highest score wins.'], { player_count: { min: 2, recommended: '4-20' } }),
    drawing: rules('Drawing Game Rules', 'One player draws a secret prompt while everyone else guesses.', ['Guess the drawing before time runs out.'], ['A drawer is assigned each round.', 'Only the drawer sees the prompt.', 'Others guess on their phones.'], ['Correct guessers score points.', 'The final podium ranks total points.'], { player_count: { min: 2, recommended: '4-12' } }),
    housie: rules('Housie Rules', 'Mark called numbers and claim prizes when patterns complete.', ['Complete prize patterns on your ticket.'], ['The caller draws numbers.', 'Players mark tickets.', 'Claim when a prize pattern is complete.'], ['Valid claims award prizes.', 'The configured final prize ends the game.'], { player_count: { min: 1, recommended: '4-50' } }),
    bingo: rules('Bingo Rules', 'Mark called items and claim configured patterns.', ['Complete a line, corners, blackout, or another selected pattern.'], ['The host calls items.', 'Players mark matching board cells.', 'Players claim complete patterns.'], ['Valid claims win prizes.', 'The host can continue to the final prize.'], { player_count: { min: 1, recommended: '4-50' } }),
    baby_bingo: rules('Baby Bingo Rules', 'Play Bingo with baby-shower gifts, moments, and tiny surprises.', ['Mark baby-shower items as they are called.'], ['The host calls items.', 'Players mark matching cells.', 'Claim completed patterns.'], ['Valid claims win prizes.', 'The host decides when to stop.'], { player_count: { min: 1, recommended: '4-50' } }),
    musical_chairs: rules('Musical Chairs Rules', 'Music plays, then stops at a random time. Last player standing wins.', ['Survive each round until only one player remains.'], ['The host starts music.', 'When music stops, players grab chairs or tap depending on mode.', 'One player is eliminated each round.'], ['Eliminated players are ranked by round.', 'The final remaining player wins.'], { player_count: { min: 3, recommended: '6-30' }, physical_setup: ['Physical mode needs one fewer chair than active players.'] }),
    bluff: rules('Bluff Rules', 'Play cards face down, claim a rank, and decide whether to challenge.', ['Get rid of your cards by bluffing or telling the truth.'], ['Players take turns playing cards face down.', 'The active player claims a rank.', 'Others may challenge.'], ['Failed bluffs and wrong challenges are punished.', 'First player out of cards wins.'], { player_count: { min: 3, recommended: '4-12' } }),
    two_truths: rules('Two Truths and a Lie Rules', 'Submit two truths and one lie. Everyone guesses the lie.', ['Fool the room and spot lies from other players.'], ['Each player submits three statements.', 'One player is revealed at a time.', 'Everyone votes for the lie.'], ['Guessers score for finding lies.', 'Authors score when voters are fooled.'], { player_count: { min: 2, recommended: '4-20' } }),
    story_chain: rules('Story Chain Rules', 'Each player adds one sentence to build a shared story.', ['Create a funny or surprising story together.'], ['Players take turns adding a sentence.', 'The final story is revealed at the end.'], ['Usually scored by completion or host choice.', 'The group wins if the story lands.'], { player_count: { min: 2, recommended: '4-12' } }),
    common_ground: rules('Common Ground Rules', 'Teams find things they all have in common.', ['Discover shared facts that are specific or surprising.'], ['Players are assigned to teams.', 'Teams discuss and submit answers.', 'The room reveals and may vote.'], ['Teams score for valid submissions and votes.', 'Highest team score wins.'], { player_count: { min: 2, recommended: '6-30' } }),
    find_someone: rules('Find Someone Who Rules', 'Complete a social Bingo grid by finding people who match prompts.', ['Meet people and complete board patterns.'], ['Players get a grid of prompts.', 'Find someone who matches a square.', 'Ask them to confirm when required.'], ['Completed squares and claims score.', 'Final reveal ranks players.'], { player_count: { min: 1, recommended: '8-100' } }),
    who_am_i: rules('Who Am I? Rules', 'Use clues to guess the mystery answer.', ['Guess the answer using as few clues as possible.'], ['A clue appears each step.', 'Players submit guesses.', 'More clues appear until solved or time runs out.'], ['Earlier correct guesses score more.', 'Highest score wins.'], { player_count: { min: 1, recommended: '3-20' } }),
    chit_pull: rules('Random Chit Rules', 'A random player gets a random question, action, or mini challenge.', ['Complete the chit when your name is picked.'], ['The app picks a player and chit.', 'The selected player answers, acts, or performs the prompt.', 'The host marks completed, bonus completed, skipped, or redraw.'], ['Completed chits score points.', 'Bonus completions score extra.', 'Highest score wins.'], { player_count: { min: 3, recommended: '4-30' } }),
    mafia: rules('Mafia Rules', 'Find the Mafia before they outnumber the town.', ['Town wins by eliminating all Mafia.', 'Mafia wins when they equal or outnumber Town.'], ['Everyone gets a secret role.', 'Night prompts are private: action roles choose targets, and every living player answers a quiet Night Read.', 'Daytime discussion ends in a vote.'], ['Eliminated players leave the vote.', 'The game ends when a side reaches its win condition.'], { player_count: { min: 6, recommended: '7-15' }, sections: [{ id: 'privacy', title: 'Keep private', items: ['Do not show your role screen unless the game reveals it.', 'Everyone checks their phone at night so roles are harder to infer.', 'Mafia coordinate only through private target votes.'] }] }),
    party_quests: rules('Party Quests Rules', 'Complete mingling quests throughout the party and confirm each other.', ['Meet people, finish quests, and collect confirmations.'], ['Each player receives a private quest board.', 'Find another player who completes a quest condition.', 'Ask them to confirm on their phone.'], ['Confirmed quests score points.', 'The host reveals the podium at the end.'], { player_count: { min: 1, recommended: '8-100' } }),
    survey_says: rules('Survey Says Rules', 'Teams guess the top survey answers while the host reveals the board.', ['Win rounds by finding high-value answers and protecting the bank.'], ['Players submit guesses on their phones.', 'The host reveals matching answers or gives strikes.', 'After max strikes, the other team gets one steal chance.'], ['Revealed answers build a round bank.', 'Clearing the board wins the bank.', 'A successful steal wins the bank for the stealing team.'], { player_count: { min: 2, recommended: '6-30' }, host_notes: ['The host adjudicates close guesses and can reveal all answers to end a round.'] }),
    hot_takes: rules('Hot Takes Rules', 'Agree or disagree with party-safe hot takes, then reveal where the room lands.', ['Choose your side and see whether you are with the majority.'], ['Each round shows one take.', 'Players pick one option on their phones.', 'The host reveals the vote split and advances.'], ['Players on a single majority side score one point.', 'Ties do not score.', 'Highest score wins.'], { player_count: { min: 2, recommended: '4-30' } }),
    this_or_that: rules('This or That Rules', 'Pick between two fast options and compare the room split.', ['Choose the side that fits you best each round.'], ['Each round shows two options.', 'Players choose on their phones.', 'The host reveals the split and moves on.'], ['Players on a single majority side score one point.', 'Highest score wins.'], { player_count: { min: 2, recommended: '4-30' } }),
    caption_contest: rules('Caption Contest Rules', 'Write the funniest caption for the prompt and vote for the winner.', ['Submit a caption the room will want to vote for.'], ['Each round shows a caption setup.', 'Players submit short captions.', 'The host opens voting, then reveals results.'], ['Each vote on your caption scores one point.', 'Highest score wins.'], { player_count: { min: 2, recommended: '4-20' } }),
    pitch_battle: rules('Pitch Battle Rules', 'Invent a ridiculous product, app, or idea and vote for the best pitch.', ['Create the pitch the room likes most.'], ['Each round gives a pitch brief.', 'Players submit one short pitch.', 'The room votes for the strongest or funniest pitch.'], ['Each vote on your pitch scores one point.', 'Highest score wins.'], { player_count: { min: 2, recommended: '4-20' } }),
    roast_toast: rules('Roast & Toast Rules', 'Write playful compliments or gentle roasts and vote for the best line.', ['Land the most memorable toast or room-safe roast.'], ['Each round gives a toast or gentle-roast prompt.', 'Players submit short lines.', 'The room votes for the favorite.'], ['Each vote on your line scores one point.', 'Keep it kind enough for the room.'], { player_count: { min: 2, recommended: '4-20' } }),
    desert_island: rules('Desert Island Rules', 'Answer survival-style favorites and vote for the room\'s best pick.', ['Submit the answer the room would most want to bring along.'], ['Each round asks what you would bring to a desert island.', 'Players submit answers.', 'The room votes for the favorite.'], ['Each vote scores one point for the answer author.', 'Highest score wins.'], { player_count: { min: 2, recommended: '4-20' } }),
    memory_lane: rules('Memory Lane Rules', 'Share tiny memories or mini stories and vote for the favorite.', ['Write a short memory the room enjoys.'], ['Each round asks for a memory or mini story.', 'Players submit short responses.', 'The room votes for the favorite.'], ['Each vote scores one point for the author.', 'Highest score wins.'], { player_count: { min: 2, recommended: '4-20' } }),
    rapid_fire: rules('Rapid Fire Rules', 'Submit the first answer that comes to mind and reveal matching groups.', ['Match as many players as possible with your instinctive answer.'], ['Each round shows a quick prompt.', 'Players submit short answers.', 'The host reveals grouped matches.'], ['Players in the largest matching group score one point.', 'No score is awarded if nobody matches.'], { player_count: { min: 2, recommended: '4-30' } }),
    one_word_vibes: rules('One Word Vibes Rules', 'Describe a prompt in one word and see who matches your vibe.', ['Match the room\'s instinct with one-word answers.'], ['Each round shows a vibe prompt.', 'Players submit one short answer.', 'The host reveals grouped matches.'], ['Players in the largest matching group score one point.', 'Highest score wins.'], { player_count: { min: 2, recommended: '4-30' } }),
    emoji_story: rules('Emoji Story Rules', 'Turn an emoji chain into a tiny story and vote for the best one.', ['Write the best mini story inspired by the emojis.'], ['Each round shows an emoji chain.', 'Players submit short stories.', 'The room votes for the favorite.'], ['Each vote scores one point for the story author.', 'Highest score wins.'], { player_count: { min: 2, recommended: '4-20' } }),
    would_you_rather: rules('Would You Rather Rules', 'Pick between two options and reveal how the room splits.', ['Choose the option you prefer each round.'], ['The host starts a round.', 'Players vote A or B on their phones.', 'The host reveals the split, then advances.'], ['Majority voters score when scoring is enabled.', 'Highest score wins after the final round.'], { player_count: { min: 2, recommended: '4-30' } }),
    never_have_i_ever: rules('Never Have I Ever Rules', 'Answer each prompt privately, then reveal the group split.', ['Be honest and see what the room has or has not done.'], ['Each round shows a statement.', 'Players choose “I have” or “Never”.', 'The host reveals the split and advances.'], ['Default mode is mostly for laughs.', 'Optional minority scoring rewards rare answers.'], { player_count: { min: 2, recommended: '4-30' } }),
    word_association: rules('Word Association Rules', 'Write the first word that comes to mind from a seed.', ['Match minds with other players.'], ['Each round shows a seed word.', 'Players submit one word.', 'The host reveals grouped matches.'], ['Players matching the largest group score in majority mode.', 'Highest score wins.'], { player_count: { min: 2, recommended: '4-30' } }),
    acronym: rules('Acronym Game Rules', 'Turn letters into funny phrases and vote for the best expansion.', ['Create the funniest matching phrase.'], ['Each round shows an acronym.', 'Players submit one phrase with matching first letters.', 'The host opens voting, then reveals results.'], ['Each vote on your expansion scores one point.', 'Highest score wins after the final round.'], { player_count: { min: 2, recommended: '4-20' } }),
    photo_clue: rules('Photo Clue Rules', 'Submit a photo clue for a secret phrase while everyone else guesses.', ['Use photos you are comfortable showing to this room.', 'Do not include written text or the answer in your photo.'], ['The clue giver receives a private prompt.', 'They upload one photo clue.', 'Guessers type guesses from the photo.', 'The host reveals the answer and advances.'], ['Correct guessers score points.', 'The clue giver scores when people guess correctly.', 'Highest score wins.'], { player_count: { min: 2, recommended: '4-12' } }),
    poker: rules('Party Poker Rules', 'Play a fast no-money Hold\'em tournament with equal play-chip stacks.', ['Play chips exist only in this room.', 'There are no buy-ins, cash-outs, prizes, or spark rewards.'], ['Everyone posts the same play-chip ante.', 'Players get two private cards and share five table cards.', 'Choose Stay or Fold each hand.', 'The best remaining hand wins the pot.'], ['Zero-chip players are eliminated.', 'Last player with chips wins.'], { player_count: { min: 2, recommended: '4-10' } }),
};

export function rulesForGame(gameType: GameType, catalog?: CatalogGameWithRules[]): GameRules | null {
    const catalogRules = catalog?.find((game) => game.id === gameType || game.game_type === gameType)?.rules;
    return catalogRules || LOCAL_GAME_RULES[gameType] || null;
}
