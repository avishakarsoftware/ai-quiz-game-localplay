import { type GameType } from '../../types';

interface GameSelectScreenProps {
    onSelect: (gameType: GameType) => void;
}

const GAME_TYPES = [
    {
        id: 'quiz' as GameType,
        icon: '⚡',
        title: 'AI Quiz',
        description: 'Test knowledge with AI-generated trivia questions',
    },
    {
        id: 'wmlt' as GameType,
        icon: '🎯',
        title: 'Most Likely To',
        description: 'Vote on who\'s most likely to do hilarious things',
    },
];

export default function GameSelectScreen({ onSelect }: GameSelectScreenProps) {
    return (
        <div className="min-h-dvh flex flex-col container-responsive safe-top safe-bottom animate-in">
            <div className="flex-1 flex flex-col justify-center py-8">
                <div className="text-center mb-8">
                    <div className="hero-icon mb-4">🎮</div>
                    <h1 className="hero-title">Choose a Game</h1>
                    <p className="text-[--text-tertiary] mt-2">Pick a game to play with your group</p>
                </div>

                <div className="space-y-4">
                    {GAME_TYPES.map((game) => (
                        <button
                            key={game.id}
                            onClick={() => onSelect(game.id)}
                            className="game-select-card"
                        >
                            <span className="game-select-icon">{game.icon}</span>
                            <div className="game-select-info">
                                <span className="game-select-title">{game.title}</span>
                                <span className="game-select-desc">{game.description}</span>
                            </div>
                            <span className="game-select-arrow">›</span>
                        </button>
                    ))}
                </div>
            </div>
        </div>
    );
}
