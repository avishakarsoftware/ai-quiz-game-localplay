import { useEffect, useMemo, useState } from 'react';
import { type WhoAmIState } from '../types';

interface WhoAmIGameProps {
    state: WhoAmIState | null;
    viewerName?: string;
    controls?: 'host' | 'player' | 'spectator';
    onSubmitGuess?: (guess: string) => void;
    onNextClue?: () => void;
    onRevealAnswer?: () => void;
    onNextRound?: () => void;
    onEndGame?: () => void;
}

export default function WhoAmIGame({
    state,
    viewerName = '',
    controls = 'spectator',
    onSubmitGuess,
    onNextClue,
    onRevealAnswer,
    onNextRound,
    onEndGame,
}: WhoAmIGameProps) {
    const [guess, setGuess] = useState('');

    useEffect(() => {
        setGuess('');
    }, [state?.round_number, state?.clue_index]);

    const title = state?.config?.game_title || 'Who Am I?';
    const isHost = controls === 'host';
    const isPlayer = controls === 'player';
    const isRevealed = state?.phase === 'WHOAMI_REVEAL' || state?.phase === 'PODIUM' || state?.round_revealed;
    const visibleClues = state?.clues.filter((clue) => clue.revealed) || [];
    const maxGuesses = state?.config?.max_guesses_per_clue || 2;
    const guessesThisClue = state?.my_guesses?.filter((item) => item.clue_index === state.clue_index).length || 0;
    const canGuess = Boolean(isPlayer && state?.phase === 'WHOAMI_ROUND' && !state?.my_correct && guessesThisClue < maxGuesses && guess.trim().length >= 2);
    const scoreboard = useMemo(() => {
        if (!state) return [];
        return [...state.players]
            .map((player) => ({ ...player, score: state.scores[player.nickname] || 0 }))
            .sort((a, b) => b.score - a.score || a.nickname.localeCompare(b.nickname));
    }, [state]);

    if (!state) {
        return (
            <div className="who-am-i-shell container-responsive safe-top safe-bottom animate-in">
                <div className="screen-hero">
                    <div className="hero-icon mb-4">❓</div>
                    <h1 className="hero-title">Who Am I?</h1>
                    <p className="hero-subtitle">Waiting for the room</p>
                </div>
            </div>
        );
    }

    const submit = () => {
        if (!canGuess || !onSubmitGuess) return;
        onSubmitGuess(guess.trim());
    };

    return (
        <div className="who-am-i-shell container-responsive safe-top safe-bottom animate-in">
            <div className="common-ground-hero">
                <div className="hero-icon">❓</div>
                <div>
                    <p className="text-[--text-tertiary] text-sm font-bold uppercase tracking-wide">{state.category || 'Clue rush'}</p>
                    <h1 className="hero-title">{title}</h1>
                    <p className="hero-subtitle">Round {state.round_number} of {state.total_rounds}</p>
                </div>
            </div>

            <div className={`turn-handoff-banner ${state.phase === 'WHOAMI_ROUND' ? 'active' : 'warning'}`}>
                <strong>{isRevealed ? 'Answer revealed' : `Clue ${state.clue_index + 1}`}</strong>
                <span>{isRevealed ? state.answer : 'Guess early for more points.'}</span>
            </div>

            <section className="who-am-i-clues" aria-label="Revealed clues">
                {state.clues.map((clue) => (
                    <div key={clue.index} className={`who-am-i-clue ${clue.revealed ? 'revealed' : ''}`}>
                        <span>{clue.index + 1}</span>
                        <strong>{clue.revealed ? clue.text : 'Locked clue'}</strong>
                    </div>
                ))}
            </section>

            {visibleClues.length === 0 && (
                <div className="common-ground-panel">
                    <h2>Ready for the first clue</h2>
                    <p className="text-[--text-secondary]">The host will reveal clues one by one.</p>
                </div>
            )}

            {isPlayer && state.phase === 'WHOAMI_ROUND' && (
                <div className="common-ground-panel">
                    <h2>{state.my_correct ? 'You got it' : 'Your guess'}</h2>
                    {state.my_correct ? (
                        <p className="text-[--text-secondary]">Nice. Wait for the host to reveal the answer.</p>
                    ) : (
                        <>
                            <input
                                value={guess}
                                onChange={(event) => setGuess(event.target.value.slice(0, 80))}
                                onKeyDown={(event) => {
                                    if (event.key === 'Enter') submit();
                                }}
                                placeholder="Type your guess"
                                className="who-am-i-guess-input"
                            />
                            <div className="common-ground-panel-footer">
                                <small>{Math.max(0, maxGuesses - guessesThisClue)} guesses left for this clue</small>
                                <button type="button" className="btn btn-primary btn-glow" onClick={submit} disabled={!canGuess}>Submit Guess</button>
                            </div>
                        </>
                    )}
                    {Boolean(state.my_guesses?.length) && (
                        <div className="who-am-i-guess-list">
                            {state.my_guesses?.slice(-5).map((item, index) => (
                                <span key={`${item.guess}-${index}`} className={item.correct ? 'correct' : ''}>
                                    {item.guess}{item.correct ? ` +${item.points}` : ''}
                                </span>
                            ))}
                        </div>
                    )}
                </div>
            )}

            {isRevealed && (
                <div className="who-am-i-answer">
                    <small>Answer</small>
                    <strong>{state.answer}</strong>
                    <span>{state.correct_players.length ? `${state.correct_players.join(', ')} guessed correctly` : 'No correct guesses this round'}</span>
                </div>
            )}

            <div className="common-ground-scoreboard">
                {scoreboard.map((player, index) => (
                    <div key={player.nickname} className={player.nickname === viewerName ? 'mine' : ''}>
                        <span>{index + 1}</span>
                        <strong>{player.avatar} {player.nickname}</strong>
                        <small>{player.score}</small>
                    </div>
                ))}
            </div>

            {isHost && (
                <div className="common-ground-actions">
                    {state.phase === 'WHOAMI_ROUND' && <button type="button" className="btn btn-secondary" onClick={onNextClue}>Next Clue</button>}
                    {state.phase === 'WHOAMI_ROUND' && <button type="button" className="btn btn-primary btn-glow" onClick={onRevealAnswer}>Reveal Answer</button>}
                    {state.phase === 'WHOAMI_REVEAL' && <button type="button" className="btn btn-primary btn-glow" onClick={onNextRound}>{state.round_number >= state.total_rounds ? 'Show Podium' : 'Next Round'}</button>}
                    <button type="button" className="btn btn-secondary" onClick={onEndGame} data-testid="organizer-end-game">End Game</button>
                </div>
            )}
        </div>
    );
}
