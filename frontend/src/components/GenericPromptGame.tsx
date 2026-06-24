import { useMemo, useState } from 'react';
import { type GenericPromptGameType, type GenericPromptState, type PlayerInfo } from '../types';
import { getGameModeConfig } from '../gameModes';

interface GenericPromptGameProps {
    gameType: GenericPromptGameType;
    state: GenericPromptState | null;
    players?: PlayerInfo[];
    viewerName?: string;
    controls?: 'host' | 'player' | 'spectator';
    onChoice?: (choice: string) => void;
    onSubmitText?: (text: string) => void;
    onVote?: (entryId: string) => void;
    onStartVoting?: () => void;
    onReveal?: () => void;
    onNextRound?: () => void;
    onEndGame?: () => void;
}

function phaseCopy(state: GenericPromptState | null) {
    if (!state) return 'Waiting for the room';
    if (state.phase === 'PODIUM') return 'Final results';
    if (state.phase === 'GENERIC_CHOICE') return 'Choose your side';
    if (state.phase === 'GENERIC_VOTING') return 'Vote for your favorite';
    if (state.phase === 'GENERIC_REVEAL') return 'Reveal';
    return state.mode === 'text_group' ? 'Submit your answer' : 'Submit your entry';
}

function shortText(text: string) {
    return text.length > 120 ? `${text.slice(0, 118)}...` : text;
}

function sortedStandings(state: GenericPromptState | null, players: PlayerInfo[]) {
    const avatarByName = new Map(players.map((player) => [player.nickname, player.avatar]));
    return [...(state?.standings || [])]
        .sort((a, b) => a.rank - b.rank)
        .map((row) => ({ ...row, avatar: avatarByName.get(row.player_id) || '' }));
}

export default function GenericPromptGame({
    gameType,
    state,
    players = [],
    viewerName = '',
    controls = 'spectator',
    onChoice,
    onSubmitText,
    onVote,
    onStartVoting,
    onReveal,
    onNextRound,
    onEndGame,
}: GenericPromptGameProps) {
    const [text, setText] = useState('');
    const config = getGameModeConfig(gameType);
    const isHost = controls === 'host';
    const isPlayer = controls === 'player';
    const standings = useMemo(() => sortedStandings(state, players), [state, players]);
    const title = state?.game_title || config.title;
    const roundText = state ? `Round ${Math.min((state.current_round_index || 0) + 1, state.round_count)} of ${state.round_count}` : '';
    const isReveal = state?.phase === 'GENERIC_REVEAL';
    const isPodium = state?.phase === 'PODIUM';
    const canSubmitText = isPlayer && state?.phase === 'GENERIC_SUBMITTING';
    const submitted = Boolean(state?.your_choice || state?.your_submission || state?.your_vote);

    const submitText = () => {
        const clean = text.trim();
        if (!clean) return;
        onSubmitText?.(clean);
        setText('');
    };

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

    const entries = state.entries || [];
    const choiceOptions = state.prompt?.options || [];
    const resultCounts = state.result?.counts || {};
    const voteCounts = state.result?.vote_counts || {};
    const groups = state.result?.groups || [];

    return (
        <div className="container-responsive safe-top safe-bottom animate-in">
            <div className="common-ground-hero">
                <div className="hero-icon">{config.icon}</div>
                <div>
                    <p className="text-[--text-tertiary] text-sm font-bold uppercase tracking-wide">{roundText} · {phaseCopy(state)}</p>
                    <h1 className="hero-title">{title}</h1>
                    <p className="hero-subtitle">{players.length} players · {state.submitted_count || 0} submitted</p>
                </div>
            </div>

            <section className="common-ground-panel">
                <p className="text-[--text-tertiary] text-sm font-bold uppercase tracking-wide">{state.prompt?.hint || config.description}</p>
                <h2>{state.prompt?.prompt}</h2>

                {state.mode === 'choice_vote' && (
                    <div className="grid gap-4 md:grid-cols-2 mt-5">
                        {choiceOptions.map((option) => {
                            const selected = state.your_choice === option;
                            const count = resultCounts[option] || 0;
                            const isWinner = state.result?.winners?.includes(option);
                            return (
                                <button
                                    key={option}
                                    type="button"
                                    className={`btn ${selected || isWinner ? 'btn-primary btn-glow' : 'btn-secondary'}`}
                                    disabled={!isPlayer || isReveal || isPodium}
                                    onClick={() => onChoice?.(option)}
                                >
                                    <span>{option}</span>
                                    {isReveal && <small className="block mt-1 opacity-80">{count} vote{count === 1 ? '' : 's'}</small>}
                                </button>
                            );
                        })}
                    </div>
                )}

                {canSubmitText && (
                    <div className="mt-5 grid gap-3 md:grid-cols-[1fr_auto]">
                        <input
                            className="input-field"
                            value={text}
                            onChange={(event) => setText(event.target.value)}
                            placeholder={state.your_submission || (state.mode === 'text_group' ? 'Your quick answer' : 'Your best response')}
                            maxLength={160}
                        />
                        <button type="button" className="btn btn-primary" disabled={!text.trim()} onClick={submitText}>
                            {state.your_submission ? 'Update' : 'Submit'}
                        </button>
                    </div>
                )}

                {state.phase === 'GENERIC_VOTING' && (
                    <div className="common-ground-scoreboard mt-5">
                        {entries.map((entry) => (
                            <button
                                key={entry.entry_id}
                                type="button"
                                className={`btn ${state.your_vote === entry.entry_id ? 'btn-primary btn-glow' : 'btn-secondary'} text-left`}
                                disabled={!isPlayer || entry.player_id === viewerName}
                                onClick={() => onVote?.(entry.entry_id)}
                            >
                                {shortText(entry.text)}
                            </button>
                        ))}
                    </div>
                )}

                {state.mode === 'text_vote' && isReveal && (
                    <div className="common-ground-scoreboard mt-5">
                        {entries.map((entry) => (
                            <div key={entry.entry_id}>
                                <strong>{entry.text}</strong>
                                <small>{entry.player_id} · {voteCounts[entry.entry_id] || 0} vote{(voteCounts[entry.entry_id] || 0) === 1 ? '' : 's'}</small>
                            </div>
                        ))}
                    </div>
                )}

                {state.mode === 'text_group' && isReveal && (
                    <div className="common-ground-scoreboard mt-5">
                        {groups.length > 0 ? groups.map((group) => (
                            <div key={group.normalized}>
                                <strong>{group.display}</strong>
                                <small>{group.count} player{group.count === 1 ? '' : 's'} · {group.players.join(', ')}</small>
                            </div>
                        )) : <p className="hero-subtitle">No matching groups this round.</p>}
                    </div>
                )}

                {isPlayer && submitted && !isReveal && !isPodium && (
                    <p className="mt-4 text-[--accent-primary] font-bold">Submitted. You can still change it before reveal.</p>
                )}
            </section>

            {isHost && !isPodium && (
                <div className="common-ground-actions mt-5">
                    {state.mode === 'text_vote' && state.phase === 'GENERIC_SUBMITTING' && (
                        <button type="button" className="btn btn-secondary" onClick={onStartVoting}>Start Voting</button>
                    )}
                    {state.phase !== 'GENERIC_REVEAL' && (
                        <button type="button" className="btn btn-secondary" onClick={onReveal}>Reveal</button>
                    )}
                    {state.phase === 'GENERIC_REVEAL' && (
                        <button type="button" className="btn btn-primary btn-glow" onClick={onNextRound}>Next Round</button>
                    )}
                    <button type="button" className="btn btn-secondary" onClick={onEndGame}>End Game</button>
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
