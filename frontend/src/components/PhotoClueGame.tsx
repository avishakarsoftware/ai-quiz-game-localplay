import { useRef, useState } from 'react';
import type { LeaderboardEntry, PhotoClueState } from '../types';
import { apiFetch } from '../utils/api';
import { mediaUrl } from '../utils/media';
import GameImage from './media/GameImage';

interface PhotoClueGameProps {
    state: PhotoClueState;
    role: 'organizer' | 'player' | 'spectator';
    nickname?: string;
    leaderboard?: LeaderboardEntry[];
    onPhotoReady?: (assetId: string, imageUrl?: string) => void;
    onGuess?: (guess: string) => void;
    onReveal?: () => void;
    onNextRound?: () => void;
}

function phaseLabel(phase: PhotoClueState['phase']): string {
    if (phase === 'PHOTO_WAITING_FOR_PHOTO') return 'Photo clue';
    if (phase === 'PHOTO_GUESSING') return 'Guessing';
    if (phase === 'PHOTO_REVEAL') return 'Reveal';
    return 'Final results';
}

function roundLabel(state: PhotoClueState): string {
    return `Round ${Math.min((state.current_round_index || 0) + 1, state.round_count || 1)} of ${state.round_count || 1}`;
}

export default function PhotoClueGame({
    state,
    role,
    nickname = '',
    leaderboard = [],
    onPhotoReady,
    onGuess,
    onReveal,
    onNextRound,
}: PhotoClueGameProps) {
    const [guess, setGuess] = useState('');
    const [uploadStatus, setUploadStatus] = useState('');
    const fileRef = useRef<HTMLInputElement | null>(null);

    const isClueGiver = Boolean(nickname && state.clue_giver_id === nickname);
    const isPlayer = role === 'player';
    const isOrganizer = role === 'organizer';
    const isWaitingForPhoto = state.phase === 'PHOTO_WAITING_FOR_PHOTO';
    const isGuessing = state.phase === 'PHOTO_GUESSING';
    const isReveal = state.phase === 'PHOTO_REVEAL' || state.phase === 'PODIUM';
    const canUpload = isPlayer && isClueGiver && isWaitingForPhoto;
    const canGuess = isPlayer && !isClueGiver && isGuessing;
    const title = state.config?.game_title || 'Photo Clue';
    const imageUrl = state.image_url ? mediaUrl(state.image_url) : '';

    const submitGuess = () => {
        const clean = guess.trim();
        if (!clean || !onGuess) return;
        onGuess(clean);
        setGuess('');
    };

    const uploadPhoto = async (file: File) => {
        if (!onPhotoReady) return;
        setUploadStatus('Uploading photo...');
        try {
            const signRes = await apiFetch('/media/upload-url', {
                method: 'POST',
                body: JSON.stringify({
                    filename: file.name,
                    mime_type: file.type,
                    bytes: file.size,
                    purpose: 'photo_clue_submission',
                }),
            });
            if (!signRes.ok) throw new Error('sign_failed');
            const signed = await signRes.json();
            const form = new FormData();
            Object.entries(signed.upload.fields as Record<string, string>).forEach(([key, value]) => form.append(key, value));
            form.append('file', file);
            const uploadRes = await fetch(signed.upload.url, { method: 'POST', body: form });
            if (!uploadRes.ok) throw new Error('upload_failed');
            const finalizeRes = await apiFetch(`/media/${signed.asset.id}/finalize`, {
                method: 'POST',
                body: JSON.stringify({ bytes: file.size, alt_text: state.secret_prompt?.answer || title }),
            });
            if (!finalizeRes.ok) throw new Error('finalize_failed');
            const finalized = await finalizeRes.json();
            onPhotoReady(finalized.asset.id, finalized.asset.public_url);
            setUploadStatus('Photo submitted');
        } catch {
            setUploadStatus('Photo upload failed. Try another image.');
        }
    };

    return (
        <div className="simple-social-game min-h-dvh safe-top safe-bottom animate-in">
            <section className="simple-social-hero">
                <div className="hero-icon mb-4">📸</div>
                <p className="text-sm uppercase tracking-widest opacity-60">{roundLabel(state)} · {phaseLabel(state.phase)}</p>
                <h1 className="hero-title">{title}</h1>
                <p>{state.clue_giver_id ? `${state.clue_giver_id} is giving the photo clue` : 'Waiting for the clue giver'}</p>
            </section>

            <section className="simple-social-panel space-y-4">
                {isClueGiver && state.secret_prompt && !isReveal && (
                    <div className="rounded-lg border border-pink-400/30 bg-pink-500/10 p-4">
                        <p className="text-sm uppercase opacity-60">Your secret prompt</p>
                        <h2 className="text-3xl">{state.secret_prompt.answer}</h2>
                        {state.secret_prompt.photo_tip && <p className="mt-2 opacity-70">{state.secret_prompt.photo_tip}</p>}
                    </div>
                )}

                {imageUrl ? (
                    <GameImage src={imageUrl} alt={state.answer || 'Photo clue'} aspect="4:3" mode={role === 'spectator' ? 'tv' : 'question'} />
                ) : (
                    <div className="rounded-lg border border-dashed border-white/20 bg-black/20 p-8 text-center">
                        <div className="text-5xl mb-3">📷</div>
                        <p>{isWaitingForPhoto ? 'Waiting for the photo clue.' : 'Photo clue will appear here.'}</p>
                    </div>
                )}

                {canUpload && (
                    <div className="space-y-3">
                        <input
                            ref={fileRef}
                            type="file"
                            accept="image/png,image/jpeg,image/webp"
                            className="hidden"
                            onChange={(event) => {
                                const file = event.target.files?.[0];
                                if (file) void uploadPhoto(file);
                                event.currentTarget.value = '';
                            }}
                        />
                        <button type="button" className="btn btn-primary w-full" onClick={() => fileRef.current?.click()}>
                            Choose Photo
                        </button>
                        {uploadStatus && <p className="text-center opacity-70">{uploadStatus}</p>}
                    </div>
                )}

                {canGuess && (
                    <div className="space-y-3">
                        <input
                            className="input-field"
                            value={guess}
                            onChange={(event) => setGuess(event.target.value)}
                            onKeyDown={(event) => {
                                if (event.key === 'Enter') submitGuess();
                            }}
                            placeholder="Type your guess"
                        />
                        <button type="button" className="btn btn-primary w-full" onClick={submitGuess} disabled={!guess.trim()}>
                            Submit Guess
                        </button>
                    </div>
                )}

                {isPlayer && state.your_guess && (
                    <div className={`rounded-lg p-3 ${state.your_guess_correct ? 'bg-emerald-500/15' : 'bg-white/5'}`}>
                        Your guess: <strong>{state.your_guess}</strong>{state.your_guess_correct ? ' · correct' : ''}
                    </div>
                )}

                {isReveal && (
                    <div className="rounded-lg border border-white/10 bg-white/5 p-4 text-center">
                        <p className="opacity-60">Answer</p>
                        <h2 className="text-4xl">{state.answer || 'No answer revealed'}</h2>
                        <p className="mt-2 opacity-70">{state.correct_guessers?.length || 0} correct guesses</p>
                    </div>
                )}

                {isOrganizer && (
                    <div className="flex flex-col sm:flex-row gap-3 pt-2">
                        <button type="button" className="btn btn-secondary flex-1" onClick={onReveal} disabled={state.phase === 'PODIUM'}>
                            Reveal
                        </button>
                        <button type="button" className="btn btn-primary flex-1" onClick={onNextRound} disabled={state.phase !== 'PHOTO_REVEAL'}>
                            Next Round
                        </button>
                    </div>
                )}
            </section>

            <section className="simple-social-panel">
                <h2 className="text-2xl mb-3">Scoreboard</h2>
                <div className="space-y-2">
                    {(leaderboard.length ? leaderboard : Object.entries(state.scores || {}).map(([name, score]) => ({ nickname: name, score }))).slice(0, 8).map((row, index) => (
                        <div key={row.nickname} className="flex justify-between rounded-lg bg-white/5 px-4 py-3">
                            <span>{index + 1}. {row.nickname}</span>
                            <strong>{row.score}</strong>
                        </div>
                    ))}
                </div>
            </section>
        </div>
    );
}
