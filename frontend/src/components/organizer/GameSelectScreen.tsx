import { Info, Search } from 'lucide-react';
import { useMemo, useState } from 'react';
import { type GameType } from '../../types';
import { BINGO_FAMILY_IDS, filterGameModesForCatalog, GAME_MODE_CONFIGS, isMostPopularGameId, mostPopularGameRank, type GameModeConfig } from '../../gameModes';
import { ENABLE_BINGO } from '../../config';
import { useRemoteConfigContext } from '../../context/RemoteConfigContext';
import GameRulesModal from '../GameRulesModal';
import { rulesForGame, type CatalogGameWithRules, type GameRules } from '../../gameRules';

interface GameSelectScreenProps {
    onSelect: (gameType: GameType) => void;
    catalog?: CatalogGameWithRules[];
}

type GameCategory = 'all' | 'popular' | 'one_phone' | 'quiz' | 'creative' | 'bingo_housie' | 'cards';

const CATEGORY_OPTIONS: Array<{ id: GameCategory; label: string }> = [
    { id: 'all', label: 'All' },
    { id: 'popular', label: 'Most Popular' },
    { id: 'one_phone', label: '📱 One phone' },
    { id: 'quiz', label: 'Quiz/Trivia' },
    { id: 'creative', label: 'Creative' },
    { id: 'bingo_housie', label: 'Bingo/Housie' },
    { id: 'cards', label: 'Cards' },
];

const GAME_CATEGORY_BY_ID: Partial<Record<GameType, GameCategory>> = {
    quiz: 'quiz',
    rebus: 'quiz',
    emoji_charades: 'quiz',
    fact_fiction: 'quiz',
    timeline: 'quiz',
    odd_one_out: 'quiz',
    wmlt: 'creative',
    drawing: 'creative',
    musical_chairs: 'creative',
    two_truths: 'creative',
    story_chain: 'creative',
    common_ground: 'creative',
    find_someone: 'creative',
    who_am_i: 'quiz',
    chit_pull: 'creative',
    party_quests: 'creative',
    survey_says: 'quiz',
    caption_contest: 'creative',
    desert_island: 'creative',
    emoji_story: 'creative',
    hot_takes: 'quiz',
    memory_lane: 'creative',
    one_word_vibes: 'creative',
    pitch_battle: 'creative',
    rapid_fire: 'quiz',
    roast_toast: 'creative',
    this_or_that: 'quiz',
    would_you_rather: 'creative',
    never_have_i_ever: 'creative',
    word_association: 'creative',
    acronym: 'creative',
    photo_clue: 'creative',
    mafia: 'cards',
    bluff: 'cards',
    poker: 'cards',
    housie: 'bingo_housie',
    // Every bingo-family tile (base + occasion decks) shares the Bingo/Housie category.
    ...Object.fromEntries(BINGO_FAMILY_IDS.map((id) => [id, 'bingo_housie' as GameCategory])),
};

function getGameCategory(game: GameModeConfig): GameCategory {
    return GAME_CATEGORY_BY_ID[game.id] || 'all';
}

function hasAiGeneration(game: GameModeConfig): boolean {
    return ![...BINGO_FAMILY_IDS, 'housie', 'musical_chairs', 'bluff', 'poker', 'two_truths', 'story_chain', 'common_ground', 'find_someone', 'mafia', 'party_quests', 'survey_says', 'caption_contest', 'desert_island', 'emoji_story', 'hot_takes', 'memory_lane', 'one_word_vibes', 'pitch_battle', 'rapid_fire', 'roast_toast', 'this_or_that', 'would_you_rather', 'never_have_i_ever', 'word_association', 'acronym', 'photo_clue'].includes(game.id);
}

export default function GameSelectScreen({ onSelect, catalog }: GameSelectScreenProps) {
    const [activeCategory, setActiveCategory] = useState<GameCategory>('all');
    const [searchQuery, setSearchQuery] = useState('');
    const [activeRules, setActiveRules] = useState<GameRules | null>(null);
    const { config: remoteConfig } = useRemoteConfigContext();
    const hasCatalog = Boolean(catalog?.length);
    const gameModes = useMemo(() => {
        // Remote-config catalog gating: when enabled_game_types is present + non-empty, only those ids show.
        const enabledIds = Array.isArray(remoteConfig.enabled_game_types) && remoteConfig.enabled_game_types.length
            ? new Set(remoteConfig.enabled_game_types)
            : null;
        const availableGames = (hasCatalog ? filterGameModesForCatalog(catalog) : GAME_MODE_CONFIGS)
            .filter((game) => ENABLE_BINGO || !BINGO_FAMILY_IDS.includes(game.id))
            .filter((game) => !enabledIds || enabledIds.has(game.id));
        return [...availableGames].sort((a, b) => a.title.localeCompare(b.title));
    }, [catalog, hasCatalog, remoteConfig.enabled_game_types]);
    const aiCapable = useMemo(() => new Set((catalog || []).filter((item) => item.supports_ai_generation).map((item) => item.id)), [catalog]);
    const query = searchQuery.trim().toLowerCase();
    const filteredGameModes = useMemo(() => {
        const filtered = gameModes.filter((game) => {
            const matchesCategory = activeCategory === 'all'
                || (activeCategory === 'popular' ? isMostPopularGameId(game.id)
                // Derived from the catalog flag, deliberately NOT from GAME_CATEGORY_BY_ID: that
                // map allows one category per game, but "needs only one phone" is orthogonal to
                // genre. Impostor is social deduction AND one-phone; forcing a choice would drop
                // it from whichever list the host looked in.
                : activeCategory === 'one_phone' ? Boolean(game.passAndPlay)
                : getGameCategory(game) === activeCategory);
            if (!matchesCategory) return false;
            if (!query) return true;
            return `${game.title} ${game.description} ${game.runtimeType}`.toLowerCase().includes(query);
        });
        if (activeCategory !== 'popular') return filtered;
        return [...filtered].sort((a, b) => mostPopularGameRank(a.id) - mostPopularGameRank(b.id) || a.title.localeCompare(b.title));
    }, [activeCategory, gameModes, query]);

    return (
        <div className="min-h-dvh flex flex-col container-responsive safe-top safe-bottom animate-in game-catalog-shell">
            <div className="flex-1 flex flex-col py-8">
                <div className="text-center game-catalog-header">
                    <div className="hero-icon mb-4" style={{ background: 'none', boxShadow: 'none' }}>
                        <img src={`${import.meta.env.BASE_URL}icons/icon-192.png`} alt="Revelry Games" style={{ width: '100%', height: '100%', borderRadius: '20px' }} />
                    </div>
                    <h1 className="hero-title">Choose a Game</h1>
                    <p className="text-[--text-tertiary] mt-2">Pick a game to play with your group</p>
                </div>

                <div className="game-catalog-tools" role="search">
                    <label className="game-search">
                        <Search size={18} aria-hidden="true" />
                        <span className="sr-only">Search games</span>
                        <input
                            type="search"
                            value={searchQuery}
                            onChange={(event) => setSearchQuery(event.target.value)}
                            placeholder="Search games"
                        />
                    </label>

                    <div className="game-category-tabs" aria-label="Filter games by category">
                        {CATEGORY_OPTIONS.map((category) => (
                            <button
                                key={category.id}
                                type="button"
                                className={`game-category-tab ${activeCategory === category.id ? 'active' : ''}`}
                                onClick={() => setActiveCategory(category.id)}
                                aria-pressed={activeCategory === category.id}
                                data-testid={`category-chip-${category.id}`}
                            >
                                {category.label}
                            </button>
                        ))}
                    </div>
                </div>

                {filteredGameModes.length > 0 ? (
                    <div className="game-select-grid">
                        {filteredGameModes.map((game) => (
                        <article
                            key={game.id}
                            className="game-select-card"
                            data-testid={`game-card-${game.id}`}
                        >
                            <button type="button" onClick={() => onSelect(game.id)} className="game-select-main">
                                <span className="game-select-icon">{game.icon}</span>
                                <div className="game-select-info">
                                    <span className="game-select-title">
                                        {game.title}{(hasCatalog ? aiCapable.has(game.id) : hasAiGeneration(game)) ? ' ✨' : ''}
                                        {/* Pass-and-play needs ONE device, which is the answer to the
                                            commonest objection to any party app ("my friends won't
                                            install anything"). Among 38 games that has to be visible
                                            at a glance, not buried in the description. */}
                                        {game.passAndPlay && (
                                            <span className="game-select-badge" data-testid={`one-phone-badge-${game.id}`}>
                                                1 phone
                                            </span>
                                        )}
                                    </span>
                                    <span className="game-select-desc">{game.description}</span>
                                </div>
                                <span className="game-select-arrow">›</span>
                            </button>
                            <button
                                type="button"
                                className="game-select-rules"
                                onClick={() => setActiveRules(rulesForGame(game.id, hasCatalog ? catalog : undefined))}
                                aria-label="Rules"
                                title={`Rules for ${game.title}`}
                            >
                                <Info size={19} aria-hidden="true" />
                            </button>
                        </article>
                        ))}
                    </div>
                ) : (
                    <div className="game-empty-state" role="status">
                        <span>No games found</span>
                        <button type="button" onClick={() => { setSearchQuery(''); setActiveCategory('all'); }}>
                            Clear search
                        </button>
                    </div>
                )}
            </div>
            <GameRulesModal rules={activeRules} onClose={() => setActiveRules(null)} />
        </div>
    );
}
