import {
    BINGO_FAMILY_IDS,
    GAME_MODE_CONFIGS,
    MOST_POPULAR_GAME_IDS,
    getGameModeConfig,
    getMinPlayers,
    mostPopularGameRank,
    runtimeGameType,
    supportsLocalAiGeneration,
    type GameModeConfig,
} from '../../gameModes';
import type { GameType } from '../../types';

/**
 * Pick the 3 games to offer a host at the podium (REVIEW-2026-08 P4).
 *
 * The between-games moment is the retention lever, and today the only "what next" is *Choose Another
 * Game*, which drops the host into a 38-card grid. That is a decision cost at the precise moment the
 * party has momentum — and a host holding a phone in front of bored friends will often just stop.
 * Three concrete, tappable suggestions remove the choosing.
 *
 * Pure function, chosen entirely from catalog metadata already in the client — no backend, no new
 * endpoint, and therefore trivially testable. Ranking rules, in order:
 *
 *  1. Never suggest the game just played (that is what "Play Again" is for).
 *  2. Only games the CURRENT group size can actually start — suggesting a game that then refuses to
 *     start is worse than suggesting nothing.
 *  3. Prefer a DIFFERENT kind of game: after trivia, offer something social. Repeating the same
 *     runtime is how a party stops feeling varied.
 *  4. Prefer games that need no AI generation, so the next round starts instantly (and costs no
 *     sparks — relevant when the host is near zero).
 *  5. Break remaining ties by curated popularity, which is the best "will a group enjoy this" signal
 *     available client-side.
 *
 * Deliberately excludes pass-and-play: those need the host to type a seat roster, which is a
 * different setup mode, not a one-tap continuation.
 */
export const NEXT_GAME_SUGGESTION_COUNT = 3;

export interface NextGameSuggestion {
    id: GameType;
    title: string;
    icon: string;
    /** Short reason shown under the title, so the choice feels considered rather than random. */
    reason: string;
}

function isEligible(config: GameModeConfig, playerCount: number, justPlayed: GameType): boolean {
    if (config.id === justPlayed) return false;
    if (config.passAndPlay) return false;
    // A suggestion the group cannot start is a broken promise.
    return playerCount >= getMinPlayers(config.id);
}

export function suggestNextGames(
    justPlayed: GameType,
    playerCount: number,
    available: GameModeConfig[] = GAME_MODE_CONFIGS,
    limit: number = NEXT_GAME_SUGGESTION_COUNT,
): NextGameSuggestion[] {
    const previousRuntime = (() => {
        try {
            return runtimeGameType(justPlayed);
        } catch {
            return undefined;
        }
    })();

    const eligible = available.filter((config) => isEligible(config, playerCount, justPlayed));

    const scored = eligible.map((config) => {
        let score = 0;
        const differentKind = previousRuntime !== undefined && runtimeGameType(config.id) !== previousRuntime;
        if (differentKind) score -= 100;                                   // rule 3 (lower sorts first)
        if (!supportsLocalAiGeneration(config.id)) score -= 25;            // rule 4: instant start
        score += mostPopularGameRank(config.id);                           // rule 5: curated order
        return { config, score, differentKind };
    });

    scored.sort((a, b) => a.score - b.score || a.config.title.localeCompare(b.config.title));

    // Rule 6, added after seeing the real output: the first pass suggested Housie, Bingo AND Baby
    // Bingo together — all one family. Each was a valid "different kind than quiz", so nothing in the
    // scoring stopped them stacking. Three near-identical options is a WORSE set than one, because
    // the host still has to choose and the party sees no variety. So take at most one game per
    // family, where the whole bingo/housie group counts as a single family.
    const chosen: typeof scored = [];
    const usedFamilies = new Set<string>();
    for (const candidate of scored) {
        const family = familyOf(candidate.config.id);
        if (usedFamilies.has(family)) continue;
        usedFamilies.add(family);
        chosen.push(candidate);
        if (chosen.length >= limit) break;
    }

    return chosen.map(({ config, differentKind }) => ({
        id: config.id,
        title: config.title,
        icon: config.icon,
        reason: reasonFor(config, differentKind),
    }));
}

/** Family key for diversity — a PLAYER-facing notion, not a code one.
 *
 * `runtimeType` is the wrong grain on its own: Housie is runtime `housie` and Bingo is runtime
 * `bingo`, so the rule below let both through as "different kinds" — and the visual diff duly showed
 * a host being offered Housie AND Bingo side by side, which to a guest is the same game twice.
 * Number-calling games therefore collapse into one family regardless of runtime. */
const NUMBER_CALLING_RUNTIMES = new Set(['bingo', 'housie']);

function familyOf(id: GameType): string {
    if (BINGO_FAMILY_IDS.includes(id)) return 'number-calling';
    try {
        const runtime = runtimeGameType(id);
        return NUMBER_CALLING_RUNTIMES.has(runtime) ? 'number-calling' : runtime;
    } catch {
        return String(id);
    }
}

function reasonFor(config: GameModeConfig, differentKind: boolean): string {
    if (!supportsLocalAiGeneration(config.id)) {
        return differentKind ? 'Different vibe · starts instantly' : 'Starts instantly';
    }
    if (differentKind) return 'Change of pace';
    return MOST_POPULAR_GAME_IDS.includes(config.id) ? 'Crowd favourite' : 'Another round';
}

/** Convenience for callers that hold only an id. */
export function suggestionTitle(id: GameType): string {
    return getGameModeConfig(id).title;
}
