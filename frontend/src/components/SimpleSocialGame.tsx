import { useMemo, useState } from 'react';
import {
    type AcronymState,
    type GameType,
    type NeverHaveIEverState,
    type OddQuestionState,
    type PlayerInfo,
    type SimpleSocialState,
    type WordAssociationState,
    type WouldYouRatherState,
} from '../types';
import { getGameModeConfig } from '../gameModes';

interface SimpleSocialGameProps {
    gameType: Extract<GameType, 'would_you_rather' | 'never_have_i_ever' | 'word_association' | 'acronym' | 'odd_question'>;
    state: SimpleSocialState | null;
    players?: PlayerInfo[];
    viewerName?: string;
    controls?: 'host' | 'player' | 'spectator';
    onWouldYouRatherVote?: (choice: 'A' | 'B') => void;
    onNeverHaveIEverAnswer?: (answer: 'have' | 'never') => void;
    onWordSubmit?: (word: string) => void;
    onAcronymSubmit?: (text: string) => void;
    onAcronymVote?: (entryId: string) => void;
    onOddAnswer?: (text: string) => void;
    onOddVote?: (accused: string) => void;
    onReveal?: () => void;
    onStartVoting?: () => void;
    onNextRound?: () => void;
    onEndGame?: () => void;
}

function roundLabel(state: SimpleSocialState | null) {
    if (!state) return '';
    return `Round ${Math.min((state.current_round_index || 0) + 1, state.round_count)} of ${state.round_count}`;
}

function phaseCopy(gameType: SimpleSocialGameProps['gameType'], phase?: string) {
    if (phase === 'PODIUM') return 'Final results';
    if (gameType === 'acronym' && phase === 'ACRONYM_VOTING') return 'Vote for the best expansion';
    if (phase?.includes('REVEAL')) return 'Reveal';
    if (gameType === 'would_you_rather') return 'Choose your side';
    if (gameType === 'never_have_i_ever') return 'Answer privately';
    if (gameType === 'word_association') return 'Submit your first thought';
    if (gameType === 'odd_question') return phase === 'ODDQ_VOTING' ? 'Spot the odd one out' : 'Answer your question';
    return 'Create your expansion';
}

function sortedStandings(state: SimpleSocialState | null, players: PlayerInfo[]) {
    const avatarByName = new Map(players.map((player) => [player.nickname, player.avatar]));
    return [...(state?.standings || [])]
        .sort((a, b) => a.rank - b.rank)
        .map((row) => ({ ...row, avatar: avatarByName.get(row.player_id) || '' }));
}

function voteLabel(entryText: string) {
    return entryText.length > 90 ? `${entryText.slice(0, 88)}...` : entryText;
}

export default function SimpleSocialGame({
    gameType,
    state,
    players = [],
    viewerName = '',
    controls = 'spectator',
    onWouldYouRatherVote,
    onNeverHaveIEverAnswer,
    onWordSubmit,
    onAcronymSubmit,
    onAcronymVote,
    onOddAnswer,
    onOddVote,
    onReveal,
    onStartVoting,
    onNextRound,
    onEndGame,
}: SimpleSocialGameProps) {
    const [text, setText] = useState('');
    const config = getGameModeConfig(gameType);
    const isHost = controls === 'host';
    const isPlayer = controls === 'player';
    const standings = useMemo(() => sortedStandings(state, players), [state, players]);
    const title = state?.game_title || config.title;

    if (!state) {
        return (
            <div className="container-responsive safe-top safe-bottom animate-in">
                <div className="screen-hero">
                    <div className="hero-icon mb-4">{config.icon}</div>
                    <h1 className="hero-title">{config.title}</h1>
                    <p className="hero-subtitle">Waiting for the room</p>
                </div>
            </div>
        );
    }

    const isReveal = state.phase.includes('REVEAL');
    const isPodium = state.phase === 'PODIUM';
    const wyr = state as WouldYouRatherState;
    const nhie = state as NeverHaveIEverState;
    const word = state as WordAssociationState;
    const acro = state as AcronymState;
    const odd = state as OddQuestionState;
    const submitted =
        gameType === 'would_you_rather' ? Boolean(wyr.your_vote)
            : gameType === 'never_have_i_ever' ? Boolean(nhie.your_answer)
                : gameType === 'word_association' ? Boolean(word.your_submission)
                    : gameType === 'odd_question' ? Boolean(odd.your_answer)
                        : Boolean(acro.your_submission);
    const counts = state as { submitted_votes?: number; submitted_answers?: number; submitted_count?: number };
    const submittedCount = counts.submitted_votes ?? counts.submitted_answers ?? counts.submitted_count
        ?? (gameType === 'odd_question' ? (odd.phase === 'ODDQ_VOTING' ? odd.vote_count : odd.answer_count) : 0)
        ?? 0;

    const submitText = () => {
        const clean = text.trim();
        if (!clean) return;
        if (gameType === 'word_association') onWordSubmit?.(clean);
        if (gameType === 'acronym') onAcronymSubmit?.(clean);
        if (gameType === 'odd_question') onOddAnswer?.(clean);
        setText('');
    };

    return (
        <div className="container-responsive safe-top safe-bottom animate-in">
            <div className="common-ground-hero">
                <div className="hero-icon">{config.icon}</div>
                <div>
                    <p className="text-[--text-tertiary] text-sm font-bold uppercase tracking-wide">{roundLabel(state)} · {phaseCopy(gameType, state.phase)}</p>
                    <h1 className="hero-title">{title}</h1>
                    <p className="hero-subtitle">{players.length} players · {isPodium ? 'Game complete' : `${submittedCount} submitted`}</p>
                </div>
            </div>

            <section className="common-ground-panel">
                {gameType === 'would_you_rather' && (
                    <>
                        <h2>{wyr.prompt?.question}</h2>
                        <div className="grid gap-4 md:grid-cols-2 mt-5">
                            <button type="button" className={`btn ${wyr.your_vote === 'A' ? 'btn-primary btn-glow' : 'btn-secondary'}`} disabled={!isPlayer || isReveal || isPodium} onClick={() => onWouldYouRatherVote?.('A')}>
                                {wyr.prompt?.option_a}
                            </button>
                            <button type="button" className={`btn ${wyr.your_vote === 'B' ? 'btn-primary btn-glow' : 'btn-secondary'}`} disabled={!isPlayer || isReveal || isPodium} onClick={() => onWouldYouRatherVote?.('B')}>
                                {wyr.prompt?.option_b}
                            </button>
                        </div>
                        {wyr.result && (
                            <div className="mt-5 grid gap-3 md:grid-cols-2">
                                <div className="rounded-xl bg-white/10 p-4"><strong>{wyr.result.percent_a}%</strong><br />{wyr.prompt?.option_a}</div>
                                <div className="rounded-xl bg-white/10 p-4"><strong>{wyr.result.percent_b}%</strong><br />{wyr.prompt?.option_b}</div>
                            </div>
                        )}
                    </>
                )}

                {gameType === 'never_have_i_ever' && (
                    <>
                        <h2>{nhie.prompt?.statement}</h2>
                        <div className="grid gap-4 md:grid-cols-2 mt-5">
                            <button type="button" className={`btn ${nhie.your_answer === 'have' ? 'btn-primary btn-glow' : 'btn-secondary'}`} disabled={!isPlayer || isReveal || isPodium} onClick={() => onNeverHaveIEverAnswer?.('have')}>
                                I have
                            </button>
                            <button type="button" className={`btn ${nhie.your_answer === 'never' ? 'btn-primary btn-glow' : 'btn-secondary'}`} disabled={!isPlayer || isReveal || isPodium} onClick={() => onNeverHaveIEverAnswer?.('never')}>
                                Never
                            </button>
                        </div>
                        {nhie.result && (
                            <div className="mt-5 grid gap-3 md:grid-cols-2">
                                <div className="rounded-xl bg-white/10 p-4"><strong>{nhie.result.have_percent}%</strong><br />I have</div>
                                <div className="rounded-xl bg-white/10 p-4"><strong>{nhie.result.never_percent}%</strong><br />Never</div>
                            </div>
                        )}
                    </>
                )}

                {gameType === 'word_association' && (
                    <>
                        <p className="text-[--text-tertiary] text-sm font-bold uppercase tracking-wide">Seed word</p>
                        <h2 className="text-5xl md:text-7xl">{word.seed?.seed}</h2>
                        {isPlayer && !isReveal && !isPodium && (
                            <div className="mt-5 grid gap-3 md:grid-cols-[1fr_auto]">
                                <input className="input-field" value={text} onChange={(event) => setText(event.target.value)} placeholder={word.your_submission || 'First word that comes to mind'} />
                                <button type="button" className="btn btn-primary" disabled={!text.trim()} onClick={submitText}>{word.your_submission ? 'Update' : 'Submit'}</button>
                            </div>
                        )}
                        {isReveal && word.groups && (
                            <div className="common-ground-scoreboard mt-5">
                                {word.groups.map((group) => (
                                    <div key={group.normalized}>
                                        <strong>{group.display}</strong>
                                        <small>{group.count} player{group.count === 1 ? '' : 's'} · {group.players.map((item) => item.player_id).join(', ')}</small>
                                    </div>
                                ))}
                            </div>
                        )}
                    </>
                )}

                {gameType === 'odd_question' && (
                    <>
                        {/* The prompt is per-viewer: the odd one out is shown a DIFFERENT question and
                            nobody else ever sees it. The host view intentionally has no prompt at all,
                            because the host screen is usually visible to the whole room. */}
                        {odd.prompt ? (
                            <>
                                {odd.you_are_odd && (
                                    <p className="text-[--accent-primary] text-sm font-bold uppercase tracking-wide" data-testid="odd-question-you-are-odd">
                                        Your question is different — blend in
                                    </p>
                                )}
                                <h2 className="text-2xl md:text-4xl">{odd.prompt}</h2>
                            </>
                        ) : (
                            !isReveal && !isPodium && (
                                <p className="text-[--text-tertiary]">
                                    Everyone has a question on their phone. One of them is different.
                                </p>
                            )
                        )}

                        {isPlayer && odd.phase === 'ODDQ_ANSWERING' && (
                            <div className="mt-5 grid gap-3 md:grid-cols-[1fr_auto]">
                                <input
                                    className="input-field"
                                    value={text}
                                    onChange={(event) => setText(event.target.value)}
                                    placeholder={odd.your_answer || 'One short answer'}
                                    aria-label="Your answer"
                                />
                                <button type="button" className="btn btn-primary" disabled={!text.trim()} onClick={submitText}>
                                    {odd.your_answer ? 'Update' : 'Submit'}
                                </button>
                            </div>
                        )}

                        {odd.phase === 'ODDQ_VOTING' && (
                            <div className="common-ground-scoreboard mt-5">
                                {(odd.answers || []).map((answer) => {
                                    const isMine = answer.player_id === viewerName;
                                    const isVoted = odd.your_vote === answer.player_id;
                                    return (
                                        <button
                                            key={answer.player_id}
                                            type="button"
                                            className={`common-ground-vote ${isVoted ? 'is-selected' : ''}`}
                                            // You cannot accuse yourself — the backend rejects it too.
                                            disabled={!isPlayer || isMine}
                                            onClick={() => onOddVote?.(answer.player_id)}
                                            data-testid={`odd-question-vote-${answer.player_id}`}
                                        >
                                            <strong>{answer.player_id}{isMine ? ' (you)' : ''}</strong>
                                            <small>{voteLabel(answer.text)}</small>
                                        </button>
                                    );
                                })}
                            </div>
                        )}

                        {isReveal && odd.round_result && (
                            <div className="common-ground-scoreboard mt-5" data-testid="odd-question-reveal">
                                <div>
                                    <strong>
                                        {odd.round_result.odd_player_id} was the odd one out —{' '}
                                        {odd.round_result.caught ? 'caught!' : 'they got away'}
                                    </strong>
                                </div>
                                {/* Showing BOTH questions is the payoff: it makes the round legible in hindsight. */}
                                <div>
                                    <strong>Everyone else</strong>
                                    <small>{odd.round_result.majority_prompt}</small>
                                </div>
                                <div>
                                    <strong>{odd.round_result.odd_player_id}</strong>
                                    <small>{odd.round_result.minority_prompt}</small>
                                </div>
                            </div>
                        )}
                    </>
                )}

                {gameType === 'acronym' && (
                    <>
                        <p className="text-[--text-tertiary] text-sm font-bold uppercase tracking-wide">{acro.prompt?.hint || 'Make it funny'}</p>
                        <h2 className="text-5xl md:text-7xl tracking-wide">{acro.prompt?.acronym}</h2>
                        {isPlayer && acro.phase === 'ACRONYM_SUBMITTING' && (
                            <div className="mt-5 grid gap-3 md:grid-cols-[1fr_auto]">
                                <input className="input-field" value={text} onChange={(event) => setText(event.target.value)} placeholder={acro.your_submission || 'Party Animals Really Tell Yarns'} />
                                <button type="button" className="btn btn-primary" disabled={!text.trim()} onClick={submitText}>{acro.your_submission ? 'Update' : 'Submit'}</button>
                            </div>
                        )}
                        {acro.phase === 'ACRONYM_VOTING' && (
                            (acro.entries || []).filter((entry) => entry.entry_id !== acro.your_entry_id).length === 0 ? (
                                <p className="mt-5 text-[--text-tertiary]">Not enough entries to vote on this round.</p>
                            ) : (
                                <div className="common-ground-scoreboard mt-5">
                                    {(acro.entries || []).map((entry) => {
                                        const isMine = entry.entry_id === acro.your_entry_id;
                                        const isVoted = acro.your_vote === entry.entry_id;
                                        return (
                                            <button
                                                key={entry.entry_id}
                                                type="button"
                                                className={`btn ${isVoted ? 'btn-primary btn-glow' : 'btn-secondary'} text-left`}
                                                disabled={!isPlayer || isMine || Boolean(acro.your_vote)}
                                                onClick={() => onAcronymVote?.(entry.entry_id)}
                                            >
                                                {voteLabel(entry.text)}{isMine ? ' · your entry' : ''}
                                            </button>
                                        );
                                    })}
                                </div>
                            )
                        )}
                        {isPlayer && acro.phase === 'ACRONYM_VOTING' && acro.your_vote && (
                            <p className="mt-4 text-[--accent-primary] font-bold">Vote locked.</p>
                        )}
                        {acro.phase === 'ACRONYM_REVEAL' && (
                            <div className="common-ground-scoreboard mt-5">
                                {Object.values(acro.submissions || {}).map((entry) => (
                                    <div key={entry.entry_id}>
                                        <strong>{entry.text}</strong>
                                        <small>{acro.vote_counts?.[entry.entry_id] || 0} vote{(acro.vote_counts?.[entry.entry_id] || 0) === 1 ? '' : 's'}</small>
                                    </div>
                                ))}
                            </div>
                        )}
                    </>
                )}
                {isPlayer && submitted && !isReveal && !isPodium && acro.phase !== 'ACRONYM_VOTING' && <p className="mt-4 text-[--accent-primary] font-bold">Submitted. You can still change it before reveal.</p>}
            </section>

            {isHost && !isPodium && (
                <div className="common-ground-actions mt-5">
                    {gameType === 'acronym' && acro.phase === 'ACRONYM_SUBMITTING' && <button type="button" className="btn btn-secondary" disabled={submittedCount === 0} onClick={onStartVoting}>Start Voting</button>}
                    {/* Odd One Out has the same two-step shape as Acronym: close answering, then reveal. */}
                    {gameType === 'odd_question' && odd.phase === 'ODDQ_ANSWERING' && <button type="button" className="btn btn-secondary" disabled={submittedCount === 0} onClick={onStartVoting}>Start Voting</button>}
                    {gameType === 'odd_question' && odd.phase === 'ODDQ_VOTING' && <button type="button" className="btn btn-secondary" onClick={onReveal}>Reveal</button>}
                    {((!['acronym', 'odd_question'].includes(gameType) && !isReveal) || acro.phase === 'ACRONYM_VOTING') && <button type="button" className="btn btn-secondary" disabled={!['acronym', 'odd_question'].includes(gameType) && submittedCount === 0} onClick={onReveal}>Reveal</button>}
                    {isReveal && <button type="button" className="btn btn-primary btn-glow" onClick={onNextRound}>Next Round</button>}
                    <button type="button" className="btn btn-secondary" onClick={onEndGame} data-testid="organizer-end-game">End Game</button>
                </div>
            )}

            <section className="common-ground-panel mt-5">
                <h2>Scores</h2>
                <div className="common-ground-scoreboard mt-4">
                    {standings.map((row) => (
                        <div key={row.player_id} className={row.player_id === viewerName ? 'mine' : ''}>
                            <strong>{row.rank}. {row.avatar || ''} {row.player_id}</strong>
                            <small>{row.score} point{row.score === 1 ? '' : 's'}</small>
                        </div>
                    ))}
                </div>
            </section>
        </div>
    );
}
