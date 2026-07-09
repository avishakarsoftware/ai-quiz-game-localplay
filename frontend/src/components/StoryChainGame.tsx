import { useEffect, useMemo, useState } from 'react';
import { type StoryChainState } from '../types';

interface StoryChainGameProps {
    state: StoryChainState | null;
    viewerName?: string;
    controls?: 'host' | 'player' | 'spectator';
    onSubmitSentence?: (text: string) => void;
    onSkipTurn?: () => void;
    onNextReveal?: () => void;
    onEndGame?: () => void;
}

function playerAvatar(state: StoryChainState | null, nickname?: string): string {
    return state?.players.find((player) => player.nickname === nickname)?.avatar || '📖';
}

function toneLabel(value?: string): string {
    const label = String(value || 'funny').replace(/_/g, ' ');
    return label.charAt(0).toUpperCase() + label.slice(1);
}

export default function StoryChainGame({
    state,
    viewerName = '',
    controls = 'spectator',
    onSubmitSentence,
    onSkipTurn,
    onNextReveal,
    onEndGame,
}: StoryChainGameProps) {
    const [sentence, setSentence] = useState('');

    useEffect(() => {
        if (state?.is_active) setSentence('');
    }, [state?.active_player_id, state?.is_active]);

    const maxChars = state?.config?.sentence_max_chars || 180;
    const validSentence = sentence.trim().length >= 8 && sentence.trim().split(/\s+/).length >= 3;
    const isPlayer = controls === 'player';
    const isHost = controls === 'host';
    const isActive = Boolean(state?.is_active || (viewerName && viewerName === state?.active_player_id && state?.phase === 'STORY_TURN'));
    const title = state?.config?.game_title || 'Story Chain';
    const revealedSentences = state?.sentences || [];
    const activeName = state?.active_player_id || 'Someone';
    const fullStory = useMemo(() => {
        if (!state) return [];
        return [state.starter_prompt, ...revealedSentences.map((item) => item.text)];
    }, [state, revealedSentences]);

    if (!state) {
        return (
            <div className="story-chain-shell container-responsive safe-top safe-bottom animate-in">
                <div className="screen-hero">
                    <div className="hero-icon mb-4">📖</div>
                    <h1 className="hero-title">Story Chain</h1>
                    <p className="hero-subtitle">Waiting for the room</p>
                </div>
            </div>
        );
    }

    const submit = () => {
        if (!onSubmitSentence || !validSentence) return;
        onSubmitSentence(sentence.trim());
    };

    return (
        <div className="story-chain-shell container-responsive safe-top safe-bottom animate-in">
            <div className="story-chain-hero">
                <div className="hero-icon">📖</div>
                <div>
                    <p className="text-[--text-tertiary] text-sm font-bold uppercase tracking-wide">
                        {toneLabel(state.config?.tone)} story
                    </p>
                    <h1 className="hero-title">{title}</h1>
                    <p className="hero-subtitle">
                        {state.phase === 'STORY_TURN'
                            ? `Turn ${Math.min(state.current_turn_index + 1, state.total_turns)} of ${state.total_turns}`
                            : state.phase === 'STORY_REVEAL'
                                ? `${Math.max(0, state.reveal_index + 1)} of ${state.sentences_count} sentences revealed`
                                : 'Final story'}
                    </p>
                </div>
            </div>

            {state.phase === 'STORY_TURN' && (
                <div className="story-chain-panel">
                    <div className="story-chain-prompt">
                        <span>Starter</span>
                        <strong>{state.starter_prompt}</strong>
                    </div>

                    <div className="story-chain-turn-card">
                        <div className="story-chain-active">
                            <span>{playerAvatar(state, state.active_player_id)}</span>
                            <div>
                                <small>{isPlayer && isActive ? 'Your turn now' : 'Writing now'}</small>
                                <strong>{isPlayer && isActive ? 'You' : activeName}</strong>
                            </div>
                        </div>

                        {isPlayer && isActive ? (
                            <>
                                <div className="turn-handoff-banner active">
                                    <strong>Your turn</strong>
                                    <span>Add one sentence, then control passes to the next player.</span>
                                </div>
                                <div className="story-chain-context">
                                    <small>{state.config?.visibility_mode === 'full_context' ? 'Story so far' : 'Last sentence'}</small>
                                    {state.visible_context?.length ? (
                                        state.visible_context.map((line, index) => <p key={`${line}-${index}`}>{line}</p>)
                                    ) : (
                                        <p>Start the story from the prompt.</p>
                                    )}
                                </div>
                                <label className="story-chain-writer">
                                    <span className="sr-only">Your sentence</span>
                                    <textarea
                                        value={sentence}
                                        onChange={(event) => setSentence(event.target.value.slice(0, maxChars))}
                                        placeholder="Add one sentence..."
                                        maxLength={maxChars}
                                    />
                                    <small>{sentence.length}/{maxChars}</small>
                                </label>
                                <button className="btn btn-primary btn-glow" onClick={submit} disabled={!validSentence}>
                                    Add Sentence
                                </button>
                            </>
                        ) : (
                            <div className="story-chain-waiting">
                                <div className="turn-handoff-banner">
                                    <strong>{activeName} is writing</strong>
                                    <span>{isPlayer ? 'Your turn will unlock automatically when control reaches you.' : 'The writing box is only active for the current player.'}</span>
                                </div>
                                <div className="story-chain-order">
                                    {state.turn_order.map((name, index) => (
                                        <span key={name} className={name === state.active_player_id ? 'active' : index < state.current_turn_index ? 'done' : ''}>
                                            {playerAvatar(state, name)} {name}
                                        </span>
                                    ))}
                                </div>
                            </div>
                        )}
                    </div>
                </div>
            )}

            {(state.phase === 'STORY_REVEAL' || state.phase === 'PODIUM') && (
                <div className="story-chain-panel story-chain-reveal">
                    <div className="story-chain-prompt">
                        <span>Once upon a time</span>
                        <strong>{state.starter_prompt}</strong>
                    </div>
                    <div className="story-chain-pages">
                        {revealedSentences.length ? revealedSentences.map((item) => (
                            <article key={item.id} className="story-chain-sentence">
                                <span>{item.position + 1}</span>
                                <p>{item.text}</p>
                                <small>{playerAvatar(state, item.player_id)} {item.player_id}</small>
                            </article>
                        )) : (
                            <article className="story-chain-sentence muted">
                                <span>?</span>
                                <p>The story is ready. Let the host reveal it.</p>
                            </article>
                        )}
                    </div>
                    {state.phase === 'PODIUM' && (
                        <div className="story-chain-final">
                            <small>Full story</small>
                            <p>{fullStory.join(' ')}</p>
                        </div>
                    )}
                </div>
            )}

            <div className="story-chain-scoreboard">
                {Object.entries(state.scores).sort((a, b) => b[1] - a[1]).slice(0, 6).map(([name, score], index) => (
                    <div key={name}>
                        <span>{index + 1}</span>
                        <strong>{name}</strong>
                        <small>{score}</small>
                    </div>
                ))}
            </div>

            {isHost && (
                <div className="story-chain-actions">
                    {state.phase === 'STORY_TURN' && <button className="btn btn-secondary" onClick={onSkipTurn}>Skip Turn</button>}
                    {state.phase === 'STORY_REVEAL' && <button className="btn btn-primary btn-glow" onClick={onNextReveal}>Reveal Next</button>}
                    <button className="btn btn-secondary" onClick={onEndGame} data-testid="organizer-end-game">End Game</button>
                </div>
            )}
        </div>
    );
}
