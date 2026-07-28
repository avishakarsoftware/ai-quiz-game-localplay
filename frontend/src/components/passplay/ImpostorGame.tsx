import { useCallback, useMemo, useState } from 'react';
import type { ImpostorState, PassPlaySeat } from '../../types';
import GroupScreenFrame from './GroupScreenFrame';
import PassScreen from './PassScreen';
import PrivacyGate from './PrivacyGate';

interface ImpostorGameProps {
    state: ImpostorState;
    onRoleSeen: (seatId: string) => void;
    onClueSpoken: (seatId: string) => void;
    onVote: (voterId: string, accusedId: string) => void;
    onCloseVote: () => void;
    onAccusedGuess: (guess: string) => void;
    onNextRound: () => void;
}

/**
 * Impostor's host-side flow (SPEC-PASS-AND-PLAY §2), built entirely from the shared primitives.
 *
 * The phase sequence maps onto the two viewing contexts:
 *   REVEAL_ROLES → PassScreen + PrivacyGate  (private, one person at a time)
 *   CLUES        → GroupScreenFrame           (face-up on the table, spoken aloud)
 *   VOTING       → GroupScreenFrame           (face-up, tapped by the table)
 *   ACCUSED_GUESS→ GroupScreenFrame           (face-up; the caught player speaks)
 *   REVEAL       → GroupScreenFrame           (face-up; secret finally shown)
 *
 * Clues are SPOKEN, not typed. The clue screen only tracks whose turn it is — typing every clue
 * would slow the game to a crawl and leak information to whoever reads the screen next.
 */
export default function ImpostorGame({
    state,
    onRoleSeen,
    onClueSpoken,
    onVote,
    onCloseVote,
    onAccusedGuess,
    onNextRound,
}: ImpostorGameProps) {
    // Two steps per seat during reveal: "pass to X", then X holds to reveal.
    const [handedOver, setHandedOver] = useState(false);
    const [guess, setGuess] = useState('');

    const seatById = useMemo(() => {
        const map = new Map<string, PassPlaySeat>();
        for (const s of state.seats) map.set(s.id, s);
        return map;
    }, [state.seats]);

    const nameOf = useCallback(
        (id: string) => seatById.get(id)?.name ?? '',
        [seatById],
    );
    const emojiOf = useCallback((id: string) => seatById.get(id)?.emoji ?? '', [seatById]);

    const roundContext = `Round ${state.round_number} of ${state.total_rounds}`;

    // --- Phase: secret role reveal ---------------------------------------------------------
    if (state.phase === 'IMP_REVEAL_ROLES') {
        const seatId = state.next_unrevealed;
        if (!seatId) return <p data-testid="impostor-waiting">Starting…</p>;

        if (!handedOver) {
            return (
                <PassScreen
                    seatName={nameOf(seatId)}
                    seatEmoji={emojiOf(seatId)}
                    context={roundContext}
                    onReady={() => setHandedOver(true)}
                />
            );
        }

        // `roles` is populated by the backend only in this phase — see ImpostorState.roles.
        const role = state.roles?.[seatId] ?? null;
        return (
            <PrivacyGate
                seatName={nameOf(seatId)}
                seatEmoji={emojiOf(seatId)}
                onDone={() => {
                    setHandedOver(false);   // next seat starts from the pass screen again
                    onRoleSeen(seatId);
                }}
            >
                {role?.is_impostor ? (
                    <div data-testid="impostor-role-impostor">
                        <p className="passplay-role__tag">You are the IMPOSTOR</p>
                        {role.hint_mode && role.word && (
                            <p className="passplay-role__hint">
                                Others may be thinking of something like <strong>{role.word}</strong>
                            </p>
                        )}
                        <p className="passplay-role__advice">Blend in. Don't get caught.</p>
                    </div>
                ) : (
                    <div data-testid="impostor-role-knower">
                        <p className="passplay-role__label">The secret word is</p>
                        <p className="passplay-role__word">{role?.word}</p>
                    </div>
                )}
            </PrivacyGate>
        );
    }

    // --- Phase: spoken clues ---------------------------------------------------------------
    if (state.phase === 'IMP_CLUES') {
        const current = state.turn.current;
        const clueRound = state.turn.completed_rounds + 1;
        return (
            <GroupScreenFrame
                title={`${nameOf(current)}, say your word`}
                subtitle={`Clue round ${clueRound} of ${state.clue_rounds} — one word, out loud`}
            >
                <div className="passplay-clues" data-testid="impostor-clues">
                    <p className="passplay-clues__turn">
                        {emojiOf(current)} <strong>{nameOf(current)}</strong>
                    </p>
                    <button
                        type="button"
                        className="btn btn-primary"
                        onClick={() => onClueSpoken(current)}
                        data-testid="impostor-clue-done"
                    >
                        Said it — next player
                    </button>
                    <p className="passplay-clues__order">
                        {state.turn.order.map((id) => (
                            <span key={id} className={id === current ? 'is-current' : ''}>
                                {nameOf(id)}
                            </span>
                        ))}
                    </p>
                </div>
            </GroupScreenFrame>
        );
    }

    // --- Phase: the vote -------------------------------------------------------------------
    if (state.phase === 'IMP_VOTING') {
        const votesCast = Object.keys(state.votes).length;
        return (
            <GroupScreenFrame
                title="Who's the impostor?"
                subtitle={`Discuss, then everyone tap a name · ${votesCast}/${state.seats.length} voted`}
            >
                <div className="passplay-vote" data-testid="impostor-vote">
                    {state.seats.map((seat) => {
                        const votesFor = Object.values(state.votes).filter((v) => v === seat.id).length;
                        return (
                            <button
                                key={seat.id}
                                type="button"
                                className="btn btn-secondary passplay-vote__option"
                                onClick={() => {
                                    // Each remaining voter votes for this seat in turn; the host
                                    // taps once per person as the table calls it out.
                                    const voter = state.turn.order.find((id) => !(id in state.votes) && id !== seat.id);
                                    if (voter) onVote(voter, seat.id);
                                }}
                                data-testid={`impostor-vote-${seat.id}`}
                            >
                                {seat.emoji} {seat.name}
                                {votesFor > 0 && <span className="passplay-vote__count"> · {votesFor}</span>}
                            </button>
                        );
                    })}
                    <button
                        type="button"
                        className="btn btn-primary"
                        onClick={onCloseVote}
                        data-testid="impostor-close-vote"
                    >
                        Lock in the vote
                    </button>
                </div>
            </GroupScreenFrame>
        );
    }

    // --- Phase: the caught impostor's one guess --------------------------------------------
    if (state.phase === 'IMP_ACCUSED_GUESS') {
        return (
            <GroupScreenFrame
                title={`${nameOf(state.accused_id)} was caught!`}
                subtitle="One chance: name the secret word and you still win"
            >
                <div className="passplay-guess" data-testid="impostor-guess">
                    <input
                        className="passplay-roster__input"
                        value={guess}
                        onChange={(e) => setGuess(e.target.value)}
                        placeholder="The secret word was…"
                        aria-label="Secret word guess"
                        maxLength={40}
                        data-testid="impostor-guess-input"
                    />
                    <button
                        type="button"
                        className="btn btn-primary"
                        onClick={() => {
                            onAccusedGuess(guess);
                            setGuess('');
                        }}
                        data-testid="impostor-guess-submit"
                    >
                        Lock in the guess
                    </button>
                </div>
            </GroupScreenFrame>
        );
    }

    // --- Phase: reveal ---------------------------------------------------------------------
    if (state.phase === 'IMP_REVEAL') {
        const outcomeCopy: Record<string, string> = {
            impostor_caught: 'Caught! The table wins this round.',
            impostor_survived: 'The impostor got away!',
            impostor_guessed: 'Caught — but they named the word. Impostor wins!',
        };
        return (
            <GroupScreenFrame
                title={outcomeCopy[state.outcome] ?? 'Round over'}
                subtitle={`The word was “${state.secret_word}”`}
            >
                <div className="passplay-reveal" data-testid="impostor-reveal">
                    <p className="passplay-reveal__who">
                        The impostor was <strong>{nameOf(state.impostor_id)}</strong>
                    </p>
                    <ul className="passplay-reveal__scores">
                        {state.standings.map((row) => (
                            <li key={row.seat_id}>
                                <span>{row.emoji} {row.nickname}</span>
                                <span>{row.score}</span>
                            </li>
                        ))}
                    </ul>
                    <button
                        type="button"
                        className="btn btn-primary"
                        onClick={onNextRound}
                        data-testid="impostor-next-round"
                    >
                        {state.round_number >= state.total_rounds ? 'See final scores' : 'Next round'}
                    </button>
                </div>
            </GroupScreenFrame>
        );
    }

    return null;
}
