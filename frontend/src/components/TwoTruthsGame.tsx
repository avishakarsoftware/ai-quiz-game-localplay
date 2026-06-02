import { useEffect, useState } from 'react';
import { type TwoTruthsState } from '../types';

interface TwoTruthsGameProps {
    state: TwoTruthsState | null;
    viewerName?: string;
    controls?: 'host' | 'player' | 'spectator';
    onSubmitStatements?: (statements: Array<{ text: string; is_lie: boolean }>) => void;
    onVote?: (statementId: string) => void;
    onStartReveal?: () => void;
    onNext?: () => void;
    onEndGame?: () => void;
}

const DEFAULT_ROWS = ['', '', ''];
const MIN_STATEMENT_CHARS = 3;

function statementLetter(index: number): string {
    return String.fromCharCode(65 + index);
}

function authorAvatar(state: TwoTruthsState | null): string {
    const author = state?.players.find((player) => player.nickname === state.current_author_id);
    return author?.avatar || '🤥';
}

export default function TwoTruthsGame({
    state,
    viewerName = '',
    controls = 'spectator',
    onSubmitStatements,
    onVote,
    onStartReveal,
    onNext,
    onEndGame,
}: TwoTruthsGameProps) {
    const [texts, setTexts] = useState(DEFAULT_ROWS);
    const [lieIndex, setLieIndex] = useState(2);

    useEffect(() => {
        if (!state?.my_submission) return;
        const ordered = [...state.my_submission.statements].sort((a, b) => a.display_order - b.display_order);
        setTexts(ordered.map((item) => item.text));
        const found = ordered.findIndex((item) => item.is_lie);
        if (found >= 0) setLieIndex(found);
    }, [state?.my_submission]);

    if (!state) {
        return (
            <div className="two-truths-shell container-responsive safe-top safe-bottom animate-in">
                <div className="screen-hero">
                    <div className="hero-icon mb-4">🤥</div>
                    <h1 className="hero-title">Two Truths and a Lie</h1>
                    <p className="hero-subtitle">Waiting for the room</p>
                </div>
            </div>
        );
    }

    const title = state.config?.game_title || 'Two Truths and a Lie';
    const submitted = new Set(state.submitted_players);
    const isPlayer = controls === 'player';
    const isAuthor = Boolean(state.is_author || (viewerName && viewerName === state.current_author_id));
    const hasSubmitted = Boolean(state.my_submission || (viewerName && submitted.has(viewerName)));
    const canSubmit = isPlayer && state.phase === 'TT_SUBMISSION' && onSubmitStatements;
    const canVote = isPlayer && state.phase === 'TT_VOTING' && !isAuthor && onVote;
    const lieId = state.round_result?.lie_statement_id || '';
    const nextLabel = state.phase === 'TT_SUBMISSION' ? 'Start Reveals' : state.phase === 'TT_VOTING' ? 'Reveal Lie' : 'Next Player';
    const trimmedTexts = texts.map((text) => text.trim());
    const filledCount = trimmedTexts.filter((text) => text.length >= MIN_STATEMENT_CHARS).length;
    const uniqueCount = new Set(trimmedTexts.map((text) => text.toLowerCase()).filter(Boolean)).size;
    const hasDuplicateStatements = uniqueCount < trimmedTexts.filter(Boolean).length;
    const validSubmission = filledCount === 3 && !hasDuplicateStatements;
    const submissionHint = filledCount < 3
        ? `Write all three statements (${MIN_STATEMENT_CHARS}+ characters each).`
        : hasDuplicateStatements
            ? 'Make each statement different.'
            : 'Pick one lie, then submit.';

    const submit = () => {
        if (!canSubmit || !validSubmission) return;
        onSubmitStatements(texts.map((text, index) => ({ text: text.trim(), is_lie: index === lieIndex })));
    };

    return (
        <div className="two-truths-shell container-responsive safe-top safe-bottom animate-in">
            <div className="two-truths-hero">
                <div className="hero-icon">🤥</div>
                <div>
                    <p className="text-[--text-tertiary] text-sm font-bold uppercase tracking-wide">Party confession</p>
                    <h1 className="hero-title">{title}</h1>
                    <p className="hero-subtitle">
                        {state.phase === 'TT_SUBMISSION'
                            ? `${state.submitted_count} of ${state.total_players} players ready`
                            : state.phase === 'TT_RESULT'
                                ? `${state.current_author_id}'s lie revealed`
                                : `${state.current_author_id}'s turn`}
                    </p>
                </div>
            </div>

            {state.phase === 'TT_SUBMISSION' && (
                <div className="two-truths-panel">
                    {isPlayer ? (
                        <>
                            <h2>Your three statements</h2>
                            <div className="two-truths-form">
                                {texts.map((text, index) => (
                                    <label key={index} className="two-truths-statement-input">
                                        <span>{statementLetter(index)}</span>
                                        <textarea
                                            value={text}
                                            onChange={(event) => setTexts((current) => current.map((item, idx) => idx === index ? event.target.value : item))}
                                            maxLength={180}
                                            placeholder={index === 0 ? 'I once met a celebrity at an airport.' : index === 1 ? 'I can cook five kinds of pasta.' : 'I am terrified of elevators.'}
                                            disabled={state.phase !== 'TT_SUBMISSION'}
                                        />
                                        <button type="button" className={lieIndex === index ? 'selected' : ''} onClick={() => setLieIndex(index)}>
                                            Lie
                                        </button>
                                    </label>
                                ))}
                            </div>
                            <p className={`two-truths-submit-hint ${validSubmission ? 'ready' : ''}`}>{submissionHint}</p>
                            <button className="btn btn-primary btn-glow" onClick={submit} disabled={!validSubmission || !canSubmit}>
                                {hasSubmitted ? 'Update Statements' : 'Submit Statements'}
                            </button>
                        </>
                    ) : (
                        <>
                            <h2>Waiting for submissions</h2>
                            <div className="two-truths-roster">
                                {state.players.map((player) => (
                                    <div key={player.nickname} className={submitted.has(player.nickname) ? 'ready' : ''}>
                                        <span>{player.avatar || '🙂'}</span>
                                        <strong>{player.nickname}</strong>
                                        <small>{submitted.has(player.nickname) ? 'Ready' : 'Writing'}</small>
                                    </div>
                                ))}
                            </div>
                        </>
                    )}
                </div>
            )}

            {(state.phase === 'TT_VOTING' || state.phase === 'TT_RESULT') && (
                <div className="two-truths-panel two-truths-vote-panel">
                    <div className="two-truths-author">
                        <span>{authorAvatar(state)}</span>
                        <div>
                            <small>Guess the lie</small>
                            <strong>{state.current_author_id}</strong>
                        </div>
                    </div>
                    <div className="two-truths-options">
                        {state.statements.map((statement, index) => {
                            const selected = state.my_vote === statement.id;
                            const isLie = state.phase === 'TT_RESULT' && statement.id === lieId;
                            const tally = state.round_result?.vote_tally?.[statement.id] || 0;
                            return (
                                <button
                                    type="button"
                                    key={statement.id}
                                    className={`${selected ? 'selected' : ''} ${isLie ? 'lie' : ''}`}
                                    onClick={() => canVote && onVote(statement.id)}
                                    disabled={!canVote || Boolean(state.my_vote)}
                                >
                                    <span>{statementLetter(index)}</span>
                                    <strong>{statement.text}</strong>
                                    {state.phase === 'TT_RESULT' && <small>{tally} votes</small>}
                                </button>
                            );
                        })}
                    </div>
                    {isPlayer && state.phase === 'TT_VOTING' && (
                        <p className="two-truths-status">
                            {isAuthor ? 'This one is yours. Watch the room guess.' : state.my_vote ? 'Vote locked.' : 'Pick the statement you think is the lie.'}
                        </p>
                    )}
                    {state.phase === 'TT_RESULT' && state.round_result && (
                        <div className="two-truths-result">
                            <strong>{state.round_result.correct_voters.length} found the lie</strong>
                            <span>{state.round_result.author_points} points for {state.current_author_id}</span>
                        </div>
                    )}
                </div>
            )}

            <div className="two-truths-scoreboard">
                {Object.entries(state.scores).sort((a, b) => b[1] - a[1]).slice(0, 6).map(([name, score], index) => (
                    <div key={name}>
                        <span>{index + 1}</span>
                        <strong>{name}</strong>
                        <small>{score}</small>
                    </div>
                ))}
            </div>

            {controls === 'host' && (
                <div className="two-truths-actions">
                    {(state.phase === 'TT_SUBMISSION' || state.phase === 'TT_VOTING' || state.phase === 'TT_RESULT') && (
                        <button className="btn btn-primary btn-glow" onClick={state.phase === 'TT_SUBMISSION' ? onStartReveal : onNext} disabled={state.phase === 'TT_SUBMISSION' && state.submitted_count === 0}>
                            {nextLabel}
                        </button>
                    )}
                    <button className="btn btn-secondary" onClick={onEndGame}>End Game</button>
                </div>
            )}
        </div>
    );
}
