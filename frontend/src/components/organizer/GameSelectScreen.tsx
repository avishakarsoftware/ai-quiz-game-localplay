import { type GameType } from '../../types';
import { GAME_MODE_CONFIGS } from '../../gameModes';

interface GameSelectScreenProps {
    onSelect: (gameType: GameType) => void;
}

export default function GameSelectScreen({ onSelect }: GameSelectScreenProps) {
    return (
        <div className="min-h-dvh flex flex-col container-responsive safe-top safe-bottom animate-in">
            <div className="flex-1 flex flex-col justify-center py-8">
                <div className="text-center mb-8">
                    <div className="hero-icon mb-4" style={{ background: 'none', boxShadow: 'none' }}>
                        <img src={`${import.meta.env.BASE_URL}icons/icon-192.png`} alt="Revelry" style={{ width: '100%', height: '100%', borderRadius: '20px' }} />
                    </div>
                    <h1 className="hero-title">Choose a Game</h1>
                    <p className="text-[--text-tertiary] mt-2">Pick a game to play with your group</p>
                </div>

                <div className="space-y-4">
                    {GAME_MODE_CONFIGS.map((game) => (
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
