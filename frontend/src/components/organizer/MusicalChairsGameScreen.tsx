import { useEffect, useMemo, useRef, useState } from 'react';
import { type MusicalChairsState } from '../../types';
import { getMusicalChairsTrack, tracksForMusicalChairsStyle } from '../../audio/musicalChairsTracks';
import MusicalChairsVisualizer from '../musical-chairs/MusicalChairsVisualizer';

export default function MusicalChairsGameScreen({
    state,
    onStartRound,
    onStopMusic,
    onEliminatePlayer,
    onEndGame,
}: {
    state: MusicalChairsState | null;
    onStartRound: () => void;
    onStopMusic: () => void;
    onEliminatePlayer: (nickname: string) => void;
    onEndGame: () => void;
}) {
    const phase = state?.phase || 'MC_BETWEEN_ROUNDS';
    const canStart = phase === 'MC_BETWEEN_ROUNDS' || phase === 'MC_REVEAL';
    const canStop = phase === 'MC_MUSIC';
    const selectingPhysicalOut = phase === 'MC_PHYSICAL_ELIMINATION';
    const eliminated = state?.eliminated_players?.[state.eliminated_players.length - 1];
    const audioRef = useRef<HTMLAudioElement | null>(null);
    const [audioStatus, setAudioStatus] = useState<'idle' | 'playing' | 'blocked' | 'error'>('idle');
    const selectedTrack = useMemo(() => {
        const style = state?.music_style || 'upbeat';
        const styleTracks = tracksForMusicalChairsStyle(style);
        const startingTrack = getMusicalChairsTrack(state?.music_track_id, style);
        const startingIndex = Math.max(0, styleTracks.findIndex((track) => track.id === startingTrack.id));
        const roundNumber = Math.max(1, (state?.round_number || 0) + (phase === 'MC_MUSIC' || phase === 'MC_GRAB' || phase === 'MC_PHYSICAL_ELIMINATION' ? 0 : 1));
        return styleTracks[(startingIndex + roundNumber - 1) % styleTracks.length] || startingTrack;
    }, [phase, state?.music_style, state?.music_track_id, state?.round_number]);

    const stopHostedMusic = () => {
        const audio = audioRef.current;
        if (!audio) return;
        audio.pause();
        audio.currentTime = 0;
        setAudioStatus('idle');
    };

    const playHostedMusic = () => {
        if (state?.music_mode !== 'builtin') return;
        const existing = audioRef.current;
        const audio = existing && existing.src === selectedTrack.url ? existing : new Audio(selectedTrack.url);
        audio.loop = true;
        audio.preload = 'auto';
        audio.volume = 0.95;
        audioRef.current = audio;
        const playResult = audio.play();
        if (playResult && typeof playResult.then === 'function') {
            void playResult
                .then(() => setAudioStatus('playing'))
                .catch(() => setAudioStatus('blocked'));
            return;
        }
        setAudioStatus('playing');
    };

    useEffect(() => {
        if (phase === 'MC_MUSIC' && state?.music_mode === 'builtin') {
            playHostedMusic();
            return;
        }
        stopHostedMusic();
    }, [phase, selectedTrack.url, state?.music_mode]);

    useEffect(() => () => stopHostedMusic(), []);

    const handleMainAction = () => {
        if (canStop) {
            stopHostedMusic();
            onStopMusic();
            return;
        }
        if (canStart) {
            playHostedMusic();
            onStartRound();
        }
    };

    return (
        <div className="min-h-dvh flex flex-col container-responsive safe-top safe-bottom animate-in">
            <div className="flex-1 py-6 mc-game-shell">
                <div className="text-center mb-5">
                    <div className="hero-icon mb-4">🎵</div>
                    <h1 className="hero-title">{state?.game_title || 'Musical Chairs'}</h1>
                    <p className="text-[--text-tertiary] mt-2">
                        Round {state?.round_number || 0} of {state?.total_rounds || '-'} · {state?.active_players.length || 0} players left
                    </p>
                    <p className="text-[--text-tertiary] text-sm mt-1">
                        {state?.gameplay_mode === 'physical' ? 'Physical chairs mode' : 'Phone tap mode'}
                    </p>
                    {state?.music_mode === 'builtin' && (
                        <p className="text-[--text-tertiary] text-sm mt-1">
                            Track: {selectedTrack.title}{audioStatus === 'blocked' ? ' · tap Start Round to enable audio' : ''}
                        </p>
                    )}
                </div>

                <MusicalChairsVisualizer players={state?.active_players || []} intensity={state?.intensity || 0.35} phase={phase} />

                <div className="mc-status-card">
                    {phase === 'MC_MUSIC' && <h2>Music is playing</h2>}
                    {phase === 'MC_GRAB' && <h2>Grab phase: {state?.grabbed || 0}/{state?.active_players.length || 0}</h2>}
                    {phase === 'MC_PHYSICAL_ELIMINATION' && <h2>Pick who did not get a chair</h2>}
                    {phase === 'MC_BETWEEN_ROUNDS' && <h2>{state?.round_number ? 'Ready for next round' : 'Ready to start'}</h2>}
                    {phase === 'MC_REVEAL' && <h2>{eliminated ? `${eliminated.nickname} is out` : 'Round over'}</h2>}
                    <p>{state?.chairs || 0} chair{state?.chairs === 1 ? '' : 's'} available</p>
                </div>

                <div className="mc-player-list">
                    {(state?.active_players || []).map((player) => (
                        selectingPhysicalOut ? (
                            <button key={player.nickname} type="button" className="mc-player-chip mc-player-chip-button" onClick={() => onEliminatePlayer(player.nickname)}>
                                {player.avatar || '🎵'} {player.nickname}
                            </button>
                        ) : (
                            <span key={player.nickname} className="mc-player-chip">{player.avatar || '🎵'} {player.nickname}</span>
                        )
                    ))}
                </div>
            </div>

            <div className="review-footer-actions pb-4">
                <button type="button" onClick={onEndGame} className="btn btn-secondary">End</button>
                <button type="button" onClick={handleMainAction} disabled={!canStart && !canStop} className="btn btn-primary btn-glow" style={{ gridColumn: 'span 2' }}>
                    {canStop ? 'Stop Music' : state?.round_number ? 'Start Next Round' : 'Start Round'}
                </button>
            </div>
        </div>
    );
}
