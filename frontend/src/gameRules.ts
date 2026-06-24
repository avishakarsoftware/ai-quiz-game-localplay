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
};

export function rulesForGame(gameType: GameType, catalog?: CatalogGameWithRules[]): GameRules | null {
    const catalogRules = catalog?.find((game) => game.id === gameType || game.game_type === gameType)?.rules;
    return catalogRules || LOCAL_GAME_RULES[gameType] || null;
}
