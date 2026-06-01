import { type MusicalChairsState } from '../../types';
import MusicalChairsVisualizer from '../musical-chairs/MusicalChairsVisualizer';

export default function MusicalChairsPlayer({
    state,
    grabbed,
    eliminated,
    reactionMs,
    onGrab,
}: {
    state: MusicalChairsState | null;
    grabbed: boolean;
    eliminated: boolean;
    reactionMs: number | null;
    onGrab: () => void;
}) {
    const phase = state?.phase || 'LOBBY';
    const physicalMode = state?.gameplay_mode === 'physical';
    if (eliminated) {
        return (
            <div className="min-h-dvh flex flex-col items-center justify-center container-responsive animate-in text-center">
                <div className="hero-icon mb-4">🪑</div>
                <h1 className="hero-title">You're out</h1>
                <p className="text-[--text-secondary] text-lg">Watch the rest of the game.</p>
            </div>
        );
    }
    return (
        <div className="min-h-dvh flex flex-col container-responsive safe-top safe-bottom animate-in text-center">
            <div className="flex-1 flex flex-col justify-center">
                <MusicalChairsVisualizer players={state?.active_players || []} intensity={state?.intensity || 0.35} phase={phase} />
                {phase === 'MC_GRAB' && !physicalMode ? (
                    <button type="button" onClick={onGrab} disabled={grabbed} className="mc-grab-button">
                        {grabbed ? 'Grabbed!' : 'GRAB A CHAIR!'}
                    </button>
                ) : phase === 'MC_PHYSICAL_ELIMINATION' || (phase === 'MC_GRAB' && physicalMode) ? (
                    <>
                        <h1 className="hero-title">Find a chair!</h1>
                        <p className="text-[--text-tertiary] mt-2">The host will mark who is out.</p>
                    </>
                ) : (
                    <>
                        <h1 className="hero-title">{phase === 'MC_MUSIC' ? 'Listen...' : 'Get ready'}</h1>
                        <p className="text-[--text-tertiary] mt-2">{physicalMode ? 'Move when the music stops.' : 'Tap only when the music stops.'}</p>
                    </>
                )}
                {reactionMs !== null && <p className="text-[--text-secondary] mt-4">Reaction: {reactionMs} ms</p>}
            </div>
        </div>
    );
}
