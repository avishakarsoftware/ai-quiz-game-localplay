import { Search } from 'lucide-react';
import { useMemo, useState } from 'react';
import { type GameType } from '../../types';
import { filterGameModesForCatalog, GAME_MODE_CONFIGS, type GameModeConfig } from '../../gameModes';
import { ENABLE_BINGO } from '../../config';

interface GameSelectScreenProps {
    onSelect: (gameType: GameType) => void;
    catalog?: Array<{ id: string; launchable?: boolean }>;
}

type GameCategory = 'all' | 'quiz' | 'creative' | 'bingo_housie' | 'cards';

const CATEGORY_OPTIONS: Array<{ id: GameCategory; label: string }> = [
    { id: 'all', label: 'All' },
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
    bluff: 'cards',
    housie: 'bingo_housie',
    bingo: 'bingo_housie',
    baby_bingo: 'bingo_housie',
};

function getGameCategory(game: GameModeConfig): GameCategory {
    return GAME_CATEGORY_BY_ID[game.id] || 'all';
}

function hasAiGeneration(game: GameModeConfig): boolean {
    return !['housie', 'bingo', 'baby_bingo', 'musical_chairs', 'bluff'].includes(game.id);
}

export default function GameSelectScreen({ onSelect, catalog }: GameSelectScreenProps) {
    const [activeCategory, setActiveCategory] = useState<GameCategory>('all');
    const [searchQuery, setSearchQuery] = useState('');
    const gameModes = (catalog ? filterGameModesForCatalog(catalog) : GAME_MODE_CONFIGS)
        .filter((game) => ENABLE_BINGO || !['bingo', 'baby_bingo'].includes(game.id));
    const query = searchQuery.trim().toLowerCase();
    const filteredGameModes = useMemo(() => {
        return gameModes.filter((game) => {
            const matchesCategory = activeCategory === 'all' || getGameCategory(game) === activeCategory;
            if (!matchesCategory) return false;
            if (!query) return true;
            return `${game.title} ${game.description} ${game.runtimeType}`.toLowerCase().includes(query);
        });
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
                            >
                                {category.label}
                            </button>
                        ))}
                    </div>
                </div>

                {filteredGameModes.length > 0 ? (
                    <div className="game-select-grid">
                        {filteredGameModes.map((game) => (
                        <button
                            key={game.id}
                            onClick={() => onSelect(game.id)}
                            className="game-select-card"
                        >
                            <span className="game-select-icon">{game.icon}</span>
                            <div className="game-select-info">
                                <span className="game-select-title">
                                    {game.title}{hasAiGeneration(game) ? ' ✨' : ''}
                                </span>
                                <span className="game-select-desc">{game.description}</span>
                            </div>
                            <span className="game-select-arrow">›</span>
                        </button>
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
        </div>
    );
}
