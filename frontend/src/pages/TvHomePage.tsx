import { useEffect, useMemo, useState } from 'react';
import { Camera, Info, Search, Smartphone, Tv } from 'lucide-react';
import { QRCodeSVG } from 'qrcode.react';
import GameRulesModal from '../components/GameRulesModal';
import { GAME_MODE_CONFIGS, type GameModeConfig } from '../gameModes';
import { rulesForGame, type CatalogGameWithRules, type GameRules } from '../gameRules';
import { type GameType } from '../types';
import { apiFetch } from '../utils/api';
import { useTvRoom } from './useTvRoom';
import { ANDROID_APP_URL, IOS_APP_URL, hasAndroidApp, hasAnyAppStoreLink, hasIosApp } from '../storeLinks';

type TvCompanionMode = 'none' | 'shared_phone' | 'per_player_phone' | 'phone_host';
type TvFilter = 'play_now' | 'all' | 'phones' | 'phone_host';

interface TvCapability {
    hostable: boolean;
    bucket?: 'tv_remote' | 'shared_phone' | 'per_player_phone' | 'phone_host';
    companion_mode: TvCompanionMode;
    min_companion_devices: number;
    private_screen: boolean;
    text_input_for_customization: boolean;
    requirement_label?: string;
    reason_chip: string;
    tv_play_note?: string;
}

interface TvCatalogGame extends CatalogGameWithRules {
    runtime_type?: string;
    game_type?: string;
    tv_capability?: TvCapability;
    default_content_available?: boolean;
}

interface TvGameCard {
    id: GameType;
    title: string;
    description: string;
    icon: string;
    capability: TvCapability;
    catalog?: TvCatalogGame;
}


function fallbackCapability(mode: GameModeConfig): TvCapability {
    if (mode.id === 'photo_clue') {
        return {
            hostable: false,
            companion_mode: 'phone_host',
            min_companion_devices: 0,
            private_screen: false,
            text_input_for_customization: true,
            requirement_label: 'Start on phone',
            reason_chip: 'Start from a phone',
        };
    }
    if (mode.passAndPlay) {
        return {
            hostable: true,
            companion_mode: 'shared_phone',
            min_companion_devices: 1,
            private_screen: true,
            text_input_for_customization: false,
            requirement_label: 'TV + 1 shared phone',
            reason_chip: 'Needs 1 shared phone',
        };
    }
    const tvReady = new Set([
        'housie',
        'bingo',
        'musical_chairs',
        'two_truths',
        'story_chain',
        'survey_says',
        'would_you_rather',
        'never_have_i_ever',
        'word_association',
        'hot_takes',
        'this_or_that',
        'rapid_fire',
        'one_word_vibes',
        'memory_lane',
    ]);
    if (tvReady.has(mode.runtimeType)) {
        return {
            hostable: true,
            companion_mode: 'none',
            min_companion_devices: 0,
            private_screen: false,
            text_input_for_customization: false,
            requirement_label: 'TV only',
            reason_chip: 'TV ready',
        };
    }
    return {
        hostable: true,
        companion_mode: 'per_player_phone',
        min_companion_devices: 2,
        private_screen: false,
        text_input_for_customization: false,
        requirement_label: 'TV + player phones',
        reason_chip: 'Needs phones',
    };
}

function availability(game: TvGameCard, connectedPhones: number): 'ready' | 'locked' | 'phone-host' {
    if (!game.capability.hostable) return 'phone-host';
    return connectedPhones >= game.capability.min_companion_devices ? 'ready' : 'locked';
}

function companionLabel(capability: TvCapability): string {
    if (capability.requirement_label) return capability.requirement_label;
    if (capability.companion_mode === 'none') return 'TV only';
    if (capability.companion_mode === 'shared_phone') return '1 shared phone';
    if (capability.companion_mode === 'phone_host') return 'Phone host';
    return capability.min_companion_devices > 1 ? `${capability.min_companion_devices}+ phones` : 'Phones';
}

function TvGameSheet({
    game,
    connectedPhones,
    roomCode,
    joinUrl: liveJoinUrl,
    hosting,
    hostError,
    onHost,
    onClose,
    onRules,
}: {
    game: TvGameCard;
    connectedPhones: number;
    roomCode: string;
    joinUrl: string;
    hosting: boolean;
    hostError: string;
    onHost: () => void;
    onClose: () => void;
    onRules: () => void;
}) {
    const state = availability(game, connectedPhones);
    // Only ever render a join QR once a room EXISTS. A bare `/join` sends the guest to a code
    // prompt with no code to type — a dead end that looks like a broken app.
    const joinUrl = liveJoinUrl;
    const setupUrl = `${window.location.origin}/?tv=1&game=${encodeURIComponent(game.id)}`;

    return (
        <div className="tv-sheet-backdrop" role="dialog" aria-modal="true" aria-labelledby="tv-sheet-title" onClick={onClose}>
            <section className="tv-sheet" onClick={(event) => event.stopPropagation()}>
                <button type="button" className="tv-sheet__close" onClick={onClose} aria-label="Close">x</button>
                <div className="tv-sheet__icon" aria-hidden="true">{game.icon}</div>
                <div>
                    <p className="tv-sheet__eyebrow">{companionLabel(game.capability)}</p>
                    <h2 id="tv-sheet-title">{game.title}</h2>
                    <p>{game.description}</p>
                </div>

                {state === 'phone-host' ? (
                    /* SPEC-TV-APP §4b: the TV can NEVER host this, so the host is leaving the TV
                       to play. That makes the app the right destination — a join link would be
                       wrong, because there is nothing on the TV to join. */
                    <div className="tv-sheet__handoff">
                        <Camera size={34} aria-hidden="true" />
                        <div>
                            <h3>Play this one on your phone</h3>
                            <p>{game.capability.tv_play_note || 'This game needs a phone camera.'}</p>
                            {/* Without this line a host who bought sparks on the TV account assumes
                                installing on a phone means paying twice. get_wallet_id resolves to
                                the same user_id wallet, so it genuinely does not. */}
                            <p className="tv-sheet__reassure">
                                Your sparks come with you — sign in with the same account.
                            </p>
                        </div>
                        {hasAnyAppStoreLink() ? (
                            <div className="tv-sheet__stores">
                                {hasAndroidApp() && (
                                    <figure>
                                        <QRCodeSVG value={ANDROID_APP_URL} size={112} />
                                        <figcaption>Google Play</figcaption>
                                    </figure>
                                )}
                                {hasIosApp() && (
                                    <figure>
                                        <QRCodeSVG value={IOS_APP_URL} size={112} />
                                        <figcaption>App Store</figcaption>
                                    </figure>
                                )}
                            </div>
                        ) : (
                            <p className="tv-sheet__reassure">
                                Open <strong>games.revelryapp.me</strong> on your phone to play it there.
                            </p>
                        )}
                    </div>
                ) : state === 'locked' ? (
                    <div className="tv-sheet__handoff">
                        <Smartphone size={34} aria-hidden="true" />
                        <div>
                            <h3>{game.capability.reason_chip}</h3>
                            {roomCode ? (
                                <>
                                    <p>Scan to join — no app needed, it opens in the browser.</p>
                                    <p className="tv-sheet__code">Room <strong>{roomCode}</strong></p>
                                </>
                            ) : (
                                <p>Open the room first, then guests can scan to join and this unlocks.</p>
                            )}
                        </div>
                        {roomCode ? <QRCodeSVG value={joinUrl} size={132} /> : null}
                    </div>
                ) : (
                    <div className="tv-sheet__ready">
                        <Tv size={34} aria-hidden="true" />
                        <div>
                            <h3>Ready on TV</h3>
                            <p>This game can be launched from the TV-primary flow.</p>
                        </div>
                    </div>
                )}

                {hostError && <p className="tv-sheet__error" role="alert">{hostError}</p>}

                <div className="tv-sheet__actions">
                    {state !== 'phone-host' && !roomCode && (
                        <button
                            type="button"
                            className="btn btn-primary"
                            onClick={onHost}
                            disabled={hosting}
                            data-testid="tv-open-room"
                        >
                            {hosting ? 'Opening room…' : 'Open room on this TV'}
                        </button>
                    )}
                    <a className="btn btn-secondary" href={setupUrl}>Open setup on phone</a>
                    <button type="button" className="btn btn-secondary" onClick={onRules}>Rules</button>
                </div>
            </section>
        </div>
    );
}

export default function TvHomePage() {
    const [catalog, setCatalog] = useState<TvCatalogGame[] | null>(null);
    const [query, setQuery] = useState('');
    const [filter, setFilter] = useState<TvFilter>('play_now');
    // Live from the TV's own organizer socket, so locked tiles un-grey as guests arrive.
    // Was previously useState(0) and never updated, which made every phone-requiring game
    // permanently unavailable.
    const room = useTvRoom();
    const connectedPhones = room.connectedPhones;
    const [selectedGame, setSelectedGame] = useState<TvGameCard | null>(null);
    const [activeRules, setActiveRules] = useState<GameRules | null>(null);

    useEffect(() => {
        let cancelled = false;
        apiFetch('/catalog')
            .then((res) => res.ok ? res.json() : Promise.reject(new Error('catalog')))
            .then((data) => {
                if (!cancelled) setCatalog(Array.isArray(data.games) ? data.games : []);
            })
            .catch(() => {
                if (!cancelled) setCatalog([]);
            });
        return () => { cancelled = true; };
    }, []);

    const games = useMemo<TvGameCard[]>(() => {
        const byId = new Map((catalog || []).map((game) => [game.id, game]));
        return GAME_MODE_CONFIGS
            .map((mode) => {
                const remote = byId.get(mode.id);
                if (catalog && catalog.length > 0 && !remote) return null;
                if (remote?.launchable === false) return null;
                return {
                    id: mode.id,
                    title: remote?.title || mode.title,
                    description: remote?.description || mode.description,
                    icon: mode.icon,
                    capability: remote?.tv_capability || fallbackCapability(mode),
                    catalog: remote,
                };
            })
            .filter(Boolean)
            .sort((a, b) => a!.title.localeCompare(b!.title)) as TvGameCard[];
    }, [catalog]);

    const visibleGames = games.filter((game) => {
        const text = `${game.title} ${game.description}`.toLowerCase();
        if (query.trim() && !text.includes(query.trim().toLowerCase())) return false;
        const state = availability(game, connectedPhones);
        if (filter === 'play_now') return state === 'ready';
        if (filter === 'phones') return game.capability.companion_mode === 'per_player_phone' || game.capability.companion_mode === 'shared_phone';
        if (filter === 'phone_host') return state === 'phone-host';
        return true;
    });

    const playNowCount = games.filter((game) => availability(game, connectedPhones) === 'ready').length;

    return (
        <main className="tv-home" data-testid="tv-home">
            <section className="tv-home__header">
                <div className="tv-home__brand">
                    <div className="tv-home__logo" aria-hidden="true">R</div>
                    <div>
                        <p>Revelry Games</p>
                        <h1>Games on TV</h1>
                    </div>
                </div>
                <div className="tv-home__phone-meter" aria-label={`${connectedPhones} connected phones`}>
                    <Smartphone size={26} aria-hidden="true" />
                    <span>{connectedPhones}</span>
                </div>
            </section>

            <section className="tv-home__controls">
                <label className="tv-home__search">
                    <Search size={26} aria-hidden="true" />
                    <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search games" />
                </label>
                <div className="tv-home__chips" role="tablist" aria-label="Game filters">
                    {[
                        ['play_now', `Play now (${playNowCount})`],
                        ['all', 'All games'],
                        ['phones', 'Needs phones'],
                        ['phone_host', 'Phone host'],
                    ].map(([id, label]) => (
                        <button
                            key={id}
                            type="button"
                            className={filter === id ? 'active' : ''}
                            onClick={() => setFilter(id as TvFilter)}
                        >
                            {label}
                        </button>
                    ))}
                </div>
            </section>

            <section className="tv-home__grid" aria-label="TV game catalog">
                {visibleGames.map((game) => {
                    const state = availability(game, connectedPhones);
                    return (
                        <button
                            key={game.id}
                            type="button"
                            className={`tv-game-card tv-game-card--${state}`}
                            onClick={() => setSelectedGame(game)}
                        >
                            <span className="tv-game-card__icon" aria-hidden="true">{game.icon}</span>
                            <span className="tv-game-card__body">
                                <span className="tv-game-card__title">{game.title}</span>
                                <span className="tv-game-card__desc">{game.description}</span>
                            </span>
                            <span className="tv-game-card__meta">
                                <span>{game.capability.reason_chip}</span>
                                {game.capability.private_screen && <Info size={18} aria-label="Private screen needed" />}
                            </span>
                        </button>
                    );
                })}
            </section>

            {selectedGame && (
                <TvGameSheet
                    game={selectedGame}
                    connectedPhones={connectedPhones}
                    roomCode={room.roomCode}
                    joinUrl={room.joinUrl}
                    hosting={room.status === 'creating'}
                    hostError={room.status === 'error' ? room.error : ''}
                    onHost={() => { void room.host(selectedGame.id); }}
                    onClose={() => setSelectedGame(null)}
                    onRules={() => setActiveRules(rulesForGame(selectedGame.id, catalog || undefined))}
                />
            )}
            <GameRulesModal rules={activeRules} onClose={() => setActiveRules(null)} />
        </main>
    );
}
