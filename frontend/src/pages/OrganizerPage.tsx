import { useState, useRef, useEffect, useCallback, useMemo } from 'react';
import { API_URL, WS_URL } from '../config';
import { type Quiz, type QuizPack, type MLTGame, type DrawingGame, type GameType, type GenericPromptGameType, type GenericPromptState, type LeaderboardEntry, type PlayerInfo, type TeamLeaderboardEntry, type Question, type HousiePattern, type HousieWinner, type BingoDeckItem, type MusicalChairsConfig, type MusicalChairsState, type BluffState, type PokerState, type TwoTruthsState, type StoryChainState, type CommonGroundState, type FindSomeoneState, type WhoAmIState, type WhoAmIGameContent, type ChitPullCategory, type ChitPullGameContent, type ChitPullSafeLevel, type ChitPullState, type MafiaState, type PartyQuestsState, type SurveySaysState, type SimpleSocialGameType, type SimpleSocialState, type PhotoClueState } from '../types';
import { soundManager } from '../utils/sound';
import { track } from '../utils/analytics';
import { getCheckoutPending, clearCheckoutPending, saveOrganizerSession, getSavedOrganizerSession, clearOrganizerSession } from '../utils/storage';
import { apiHeaders, apiUrl, generateIdempotencyKey } from '../utils/api';
import { mediaUrl } from '../utils/media';
import { canResetFinishedRoomWithGame } from '../utils/roomReuse';
import GameSelectScreen from '../components/organizer/GameSelectScreen';
import PromptScreen, { randomQuizTopic, type AIProvider } from '../components/organizer/PromptScreen';
import QuizVariantPromptScreen from '../components/organizer/QuizVariantPromptScreen';
import CustomQuizEditor from '../components/organizer/CustomQuizEditor';
import MLTPromptScreen from '../components/organizer/MLTPromptScreen';
import DrawingPromptScreen from '../components/organizer/DrawingPromptScreen';
import WhoAmIPromptScreen from '../components/organizer/WhoAmIPromptScreen';
import WhoAmIReviewScreen from '../components/organizer/WhoAmIReviewScreen';
import ChitPullPromptScreen from '../components/organizer/ChitPullPromptScreen';
import ChitPullReviewScreen from '../components/organizer/ChitPullReviewScreen';
import LoadingScreen, { PREPARING_MESSAGES } from '../components/organizer/LoadingScreen';
import ReviewScreen from '../components/organizer/ReviewScreen';
import MLTReviewScreen from '../components/organizer/MLTReviewScreen';
import DrawingReviewScreen from '../components/organizer/DrawingReviewScreen';
import HousieSetupScreen from '../components/organizer/HousieSetupScreen';
import BingoPromptScreen from '../components/organizer/BingoPromptScreen';
import BingoSetupScreen from '../components/organizer/BingoSetupScreen';
import MusicalChairsSetupScreen, { defaultMusicalChairsConfig } from '../components/organizer/MusicalChairsSetupScreen';
import PartyQuestsSetupScreen, { defaultPartyQuestsConfig, type PartyQuestSetupConfig } from '../components/organizer/PartyQuestsSetupScreen';
import MusicalChairsGameScreen from '../components/organizer/MusicalChairsGameScreen';
import BluffTable from '../components/BluffTable';
import PokerGame from '../components/PokerGame';
import TwoTruthsGame from '../components/TwoTruthsGame';
import StoryChainGame from '../components/StoryChainGame';
import CommonGroundGame from '../components/CommonGroundGame';
import FindSomeoneGame from '../components/FindSomeoneGame';
import WhoAmIGame from '../components/WhoAmIGame';
import ChitPullGame from '../components/ChitPullGame';
import MafiaGame from '../components/MafiaGame';
import PartyQuestsGame from '../components/PartyQuestsGame';
import SurveySaysGame from '../components/SurveySaysGame';
import GenericPromptGame from '../components/GenericPromptGame';
import SimpleSocialGame from '../components/SimpleSocialGame';
import PhotoClueGame from '../components/PhotoClueGame';
import GameRulesModal from '../components/GameRulesModal';
import { HousieCalledBoard, HousieWinners } from '../components/HousieBoard';
import { BingoCalledList, BingoCallOverlay } from '../components/BingoBoard';
import ImageGenerationScreen from '../components/organizer/ImageGenerationScreen';
import LobbyScreen from '../components/organizer/LobbyScreen';
import GameQuestionScreen from '../components/organizer/GameQuestionScreen';
import LeaderboardScreen from '../components/organizer/LeaderboardScreen';
import LeaderboardBarChart from '../components/LeaderboardBarChart';
import PodiumScreen from '../components/organizer/PodiumScreen';
import { shareGameResult } from '../utils/shareResult';
import BonusSplash from '../components/BonusSplash';
import ErrorModal from '../components/ErrorModal';
import SparkPurchaseModal from '../components/SparkPurchaseModal';
import { useRemoteConfigContext } from '../context/RemoteConfigContext';
import { GENERIC_PROMPT_GAME_IDS, getGameModeConfig, getMinPlayers, isQuizRuntimeGame, runtimeGameType } from '../gameModes';
import { rulesForGame, type CatalogGameWithRules, type GameRules } from '../gameRules';
import { returnToHostApp as returnToHostAppParent } from '../utils/hostAppReturn';

type OrganizerState = 'SELECT_GAME' | 'PROMPT' | 'QUIZ_VARIANT_PROMPT' | 'CUSTOM_QUIZ' | 'QUIZ_LIBRARY' | 'MLT_PROMPT' | 'DRAWING_PROMPT' | 'WHO_AM_I_PROMPT' | 'WHO_AM_I_REVIEW' | 'CHIT_PULL_PROMPT' | 'CHIT_PULL_REVIEW' | 'HOUSIE_SETUP' | 'BINGO_PROMPT' | 'BINGO_SETUP' | 'MUSICAL_CHAIRS_SETUP' | 'PARTY_QUESTS_SETUP' | 'LOADING' | 'REVIEW' | 'MLT_REVIEW' | 'DRAWING_REVIEW' | 'GENERATING_IMAGES' | 'ROOM' | 'QUESTION' | 'BINGO_CALLING' | 'MUSICAL_CHAIRS' | 'BLUFF' | 'POKER' | 'TWO_TRUTHS' | 'STORY_CHAIN' | 'COMMON_GROUND' | 'FIND_SOMEONE' | 'WHO_AM_I' | 'CHIT_PULL' | 'MAFIA' | 'PARTY_QUESTS' | 'SURVEY_SAYS' | 'GENERIC_PROMPT' | 'SIMPLE_SOCIAL' | 'PHOTO_CLUE' | 'ANSWER_REVEAL' | 'LEADERBOARD' | 'PODIUM';

function isGenericPromptGame(type: GameType): type is GenericPromptGameType {
    return (GENERIC_PROMPT_GAME_IDS as string[]).includes(type);
}

function defaultTimeLimitForGame(type: GameType): number {
    if (type === 'housie' || type === 'bingo' || type === 'baby_bingo') return 15;
    if (type === 'musical_chairs') return 5;
    if (type === 'bluff') return 30;
    if (type === 'poker') return 30;
    if (type === 'two_truths') return 30;
    if (type === 'story_chain') return 45;
    if (type === 'common_ground') return 30;
    if (type === 'find_someone') return 30;
    if (type === 'who_am_i') return 25;
    if (type === 'chit_pull') return 30;
    if (type === 'mafia') return 30;
    if (type === 'party_quests') return 30;
    if (type === 'survey_says') return 30;
    if (isGenericPromptGame(type)) return 30;
    if (type === 'would_you_rather' || type === 'never_have_i_ever' || type === 'word_association' || type === 'acronym' || type === 'photo_clue' || type === 'odd_question') return 30;
    return type === 'drawing' ? 30 : 15;
}

const STARTER_BINGO_ITEMS = [
    'Dance floor', 'Group photo', 'Someone laughs', 'Snack table', 'Party playlist',
    'Inside joke', 'A toast', 'Late arrival', 'New friend', 'Dessert',
    'Someone sings', 'Sparkly outfit', 'Favorite song', 'Big hug', 'Phone photo',
    'Someone cheers', 'Cake', 'Gift bag', 'Funny story', 'Matching colors',
    'Table games', 'A surprise', 'Best dressed', 'Last call', 'Confetti',
];

const BABY_BINGO_ITEMS = [
    'Baby bottle', 'Tiny socks', 'Diaper cake', 'Pacifier', 'Baby blanket',
    'Stroller', 'Nursery rhyme', 'Onesie', 'Baby name guess', 'Pregnancy craving',
    'Late-night feeding', 'Baby monitor', 'Rubber duck', 'Gift wrap', 'Lullaby',
    'Baby shoes', 'Cute bib', 'Wipes pack', 'Parent advice', 'Photo moment',
    'Stuffed toy', 'Storybook', 'Teether', 'Baby giggles', 'Nap time',
];

const WEDDING_BINGO_ITEMS = [
    'First dance', 'Someone cries', 'Bouquet toss', 'Speech goes long', 'Ring bearer',
    'Cake cutting', 'Confetti', 'Photo booth', 'Kids on the dance floor', 'Toast with champagne',
    'Something borrowed', 'Groomsmen photo', 'Flower crown', 'Slow song', 'Guest book',
    'Late-night snack', 'Sparklers', 'Dress twirl', 'Awkward relative', 'Bridesmaid fixes a dress',
    'Someone loses a shoe', 'Group selfie', 'Conga line', 'Last dance', 'Getaway car',
];

const HOLIDAY_BINGO_ITEMS = [
    'Ugly sweater', 'Fairy lights', 'Mismatched wrapping', 'Someone regifts', 'Burnt cookies',
    'Carols on repeat', 'Family photo', 'Leftovers debate', 'Board game argument', 'Nap on the couch',
    'Hot chocolate', 'Tangled lights', 'Secret Santa reveal', 'Too much cheese', 'Tinsel everywhere',
    'Snow talk', 'Old home video', 'Pet in a costume', 'Second helping', 'Cracker joke',
    'Someone falls asleep', 'Mystery casserole', 'Group toast', 'Wrapping paper fight', 'Last-minute gift',
];

const ROAD_TRIP_BINGO_ITEMS = [
    'Wrong turn', 'Petrol station snack', 'Someone sleeps', 'Playlist argument', 'Cows in a field',
    'Toll booth', 'Bug on the windscreen', 'Are we there yet', 'Roadworks', 'Scenic viewpoint',
    'Rest stop coffee', 'Licence plate game', 'Phone dies', 'Detour sign', 'Snack crumbs everywhere',
    'Singing along', 'Truck horn', 'Map disagreement', 'Sunset drive', 'Motorway services',
    'Someone needs a loo', 'Weird roadside statue', 'Windows down', 'Traffic jam', 'Arrival photo',
];

/**
 * Build a bingo deck from a list of display strings.
 *
 * One builder rather than a near-identical mapper per deck — there are five occasion decks now,
 * and the only thing that ever differed between copies was the id prefix.
 */
function bingoDeckFrom(prefix: string, items: readonly string[]): BingoDeckItem[] {
    return items.map((display, index) => ({
        id: `${prefix}_${index + 1}`,
        kind: 'text',
        value: display.toLowerCase(),
        display,
    }));
}

const OCCASION_BINGO = {
    baby_bingo: { title: 'Baby Bingo', prefix: 'baby', items: BABY_BINGO_ITEMS, prompt: 'baby shower' },
    wedding_bingo: { title: 'Wedding Bingo', prefix: 'wedding', items: WEDDING_BINGO_ITEMS, prompt: 'wedding reception' },
    holiday_bingo: { title: 'Holiday Bingo', prefix: 'holiday', items: HOLIDAY_BINGO_ITEMS, prompt: 'holiday party' },
    road_trip_bingo: { title: 'Road Trip Bingo', prefix: 'roadtrip', items: ROAD_TRIP_BINGO_ITEMS, prompt: 'road trip' },
} as const;

function starterBingoDeck(): BingoDeckItem[] {
    return bingoDeckFrom('starter', STARTER_BINGO_ITEMS);
}

export default function OrganizerPage() {
    const { config: remoteConfig } = useRemoteConfigContext();
    const [state, setState] = useState<OrganizerState>('SELECT_GAME');
    const [gameType, setGameType] = useState<GameType>('quiz');
    const [prompt, setPrompt] = useState('');
    const [difficulty, setDifficulty] = useState('medium');
    const [numQuestions, setNumQuestions] = useState(10);
    const [generateQuizImages, setGenerateQuizImages] = useState(false);
    const [quiz, setQuiz] = useState<Quiz | null>(null);
    const [quizOrigin, setQuizOrigin] = useState<'ai' | 'custom'>('ai');
    const [editingPackId, setEditingPackId] = useState<string | undefined>(undefined);
    const [libraryPacks, setLibraryPacks] = useState<QuizPack[]>([]);
    const [libraryLoading, setLibraryLoading] = useState(false);
    const [mltGame, setMltGame] = useState<MLTGame | null>(null);
    const [drawingGame, setDrawingGame] = useState<DrawingGame | null>(null);
    const [contentId, setContentId] = useState('');
    const [roomCode, setRoomCode] = useState('');
    const [hostAppJoinUrl, setHostAppJoinUrl] = useState('');
    const [hostAppJoinLabel, setHostAppJoinLabel] = useState('Scan to join from Revelry');
    const [hostAppReturnUrl, setHostAppReturnUrl] = useState('');
    const [hostAppPartyHubUrl, setHostAppPartyHubUrl] = useState('');
    const [timeLimit, setTimeLimit] = useState(15);
    const [playerCount, setPlayerCount] = useState(0);
    const [currentQuestion, setCurrentQuestion] = useState(0);
    const [totalQuestions, setTotalQuestions] = useState(0);
    const [revealedAnswer, setRevealedAnswer] = useState<number | null>(null);
    const [timeRemaining, setTimeRemaining] = useState(15);
    const [leaderboard, setLeaderboard] = useState<LeaderboardEntry[]>([]);
    const [teamLeaderboard, setTeamLeaderboard] = useState<TeamLeaderboardEntry[]>([]);
    const [sdAvailable, setSdAvailable] = useState(false);
    const [imageProgress, setImageProgress] = useState(0);
    const [questionImages, setQuestionImages] = useState<Record<number, string>>({});
    const [liveQuestion, setLiveQuestion] = useState<Question | null>(null);
    const [players, setPlayers] = useState<PlayerInfo[]>([]);
    const [answeredCount, setAnsweredCount] = useState(0);
    const [provider, setProvider] = useState('ollama');
    const [providers, setProviders] = useState<AIProvider[]>([]);
    const [loadingCopy, setLoadingCopy] = useState<{ title: string; messages?: string[] }>({ title: 'Generating Quiz' });
    const [isBonus, setIsBonus] = useState(false);
    const [showBonusSplash, setShowBonusSplash] = useState(false);
    const [roomLocked, setRoomLocked] = useState(false);
    // WMLT-specific state for organizer question screen
    const [currentStatement, setCurrentStatement] = useState('');
    const [showVotes, setShowVotes] = useState(true);
    const [wmltRoundResult, setWmltRoundResult] = useState<{ winner: string; winners: string[]; round_podium: { nickname: string; avatar: string; vote_count: number; voters: string[] }[]; unanimous: boolean; show_votes: boolean; statement: string } | null>(null);
    const [drawingRoundResult, setDrawingRoundResult] = useState<{ prompt: string; drawer: string; correct_guessers: string[] } | null>(null);
    const [drawingAutoAdvance, setDrawingAutoAdvance] = useState(true);
    const [drawingNextRoundCountdown, setDrawingNextRoundCountdown] = useState<number | null>(null);
    const [drawingActiveDrawer, setDrawingActiveDrawer] = useState('');
    const [drawingClue, setDrawingClue] = useState('');
    const [housieTitle, setHousieTitle] = useState('Housie');
    const [housiePatterns, setHousiePatterns] = useState(['quick_5', 'four_corners', 'top_row', 'middle_row', 'bottom_row', 'full_house']);
    const [housiePlayMode, setHousiePlayMode] = useState<'beginner' | 'pro'>('beginner');
    const [housieCallerMode, setHousieCallerMode] = useState<'manual' | 'auto'>('manual');
    const [housieAutoStatus, setHousieAutoStatus] = useState<'running' | 'paused' | 'stopped'>('stopped');
    const [housieAutoInterval, setHousieAutoInterval] = useState(8);
    const [housieAutoPauseOnClaim, setHousieAutoPauseOnClaim] = useState(true);
    const [housieCalled, setHousieCalled] = useState<Array<{ value: number | string; display: string }>>([]);
    const [housieLatest, setHousieLatest] = useState<{ value: number | string; display: string } | null>(null);
    const [housieCanUndoLastCall, setHousieCanUndoLastCall] = useState(false);
    const [housieTerminalClaimPending, setHousieTerminalClaimPending] = useState(false);
    const [housieWinners, setHousieWinners] = useState<HousieWinner[]>([]);
    const [housieCallFlash, setHousieCallFlash] = useState<{ item: { value?: number | string; display: string; kind?: string; image_url?: string; alt_text?: string }; key: number } | null>(null);
    const [housieAnnouncement, setHousieAnnouncement] = useState<{ text: string; key: number } | null>(null);
    const [bingoTitle, setBingoTitle] = useState('Bingo');
    const [bingoDeck, setBingoDeck] = useState<BingoDeckItem[]>(starterBingoDeck);
    const [generatedBingoId, setGeneratedBingoId] = useState('');
    const [bingoFreeCenter, setBingoFreeCenter] = useState(true);
    const [bingoClaimRequiresLatest, setBingoClaimRequiresLatest] = useState(false);
    const [musicalChairsConfig, setMusicalChairsConfig] = useState<MusicalChairsConfig>(defaultMusicalChairsConfig);
    const [musicalChairsState, setMusicalChairsState] = useState<MusicalChairsState | null>(null);
    const [bluffState, setBluffState] = useState<BluffState | null>(null);
    const [pokerState, setPokerState] = useState<PokerState | null>(null);
    const [twoTruthsState, setTwoTruthsState] = useState<TwoTruthsState | null>(null);
    const [storyChainState, setStoryChainState] = useState<StoryChainState | null>(null);
    const [commonGroundState, setCommonGroundState] = useState<CommonGroundState | null>(null);
    const [findSomeoneState, setFindSomeoneState] = useState<FindSomeoneState | null>(null);
    const [whoAmIState, setWhoAmIState] = useState<WhoAmIState | null>(null);
    const [whoAmIGame, setWhoAmIGame] = useState<WhoAmIGameContent | null>(null);
    const [chitPullGame, setChitPullGame] = useState<ChitPullGameContent | null>(null);
    const [chitPullState, setChitPullState] = useState<ChitPullState | null>(null);
    const [chitPullSafeLevel, setChitPullSafeLevel] = useState<ChitPullSafeLevel>('family');
    const [mafiaState, setMafiaState] = useState<MafiaState | null>(null);
    const [partyQuestsState, setPartyQuestsState] = useState<PartyQuestsState | null>(null);
    const [surveySaysState, setSurveySaysState] = useState<SurveySaysState | null>(null);
    const [genericPromptState, setGenericPromptState] = useState<GenericPromptState | null>(null);
    const [simpleSocialState, setSimpleSocialState] = useState<SimpleSocialState | null>(null);
    const [photoClueState, setPhotoClueState] = useState<PhotoClueState | null>(null);
    const [partyQuestsConfig, setPartyQuestsConfig] = useState<PartyQuestSetupConfig>(defaultPartyQuestsConfig());
    const [catalog, setCatalog] = useState<CatalogGameWithRules[]>([]);
    const [activeRules, setActiveRules] = useState<GameRules | null>(null);
    const [reviewPeekOpen, setReviewPeekOpen] = useState(false);
    const [superlatives, setSuperlatives] = useState<{ title: string; icon: string; winner: string; avatar: string; detail: string }[]>([]);
    const [errorModal, setErrorModal] = useState<{ title: string; message: string; upgradeAvailable?: boolean; returnToHostApp?: boolean } | null>(null);
    const [showPurchase, setShowPurchase] = useState(false);
    const wsRef = useRef<WebSocket | null>(null);
    const stateRef = useRef<OrganizerState>('SELECT_GAME');
    const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
    const roomCodeRef = useRef('');
    const organizerTokenRef = useRef('');
    const flowEpochRef = useRef(0);
    const mountedRef = useRef(true);
    const connectWsRef = useRef<(code: string) => void>(() => {});
    const gameTypeRef = useRef<GameType>('quiz');
    const finishedRoomCanResetRef = useRef(false);
    const checkoutPollRef = useRef<ReturnType<typeof setInterval> | null>(null);
    const hostAppMode = useMemo(() => {
        const params = new URLSearchParams(window.location.search);
        return params.get('embed') === '1' || params.has('launch_token') || params.has('session_id');
    }, []);

    useEffect(() => { stateRef.current = state; }, [state]);
    useEffect(() => { roomCodeRef.current = roomCode; }, [roomCode]);
    useEffect(() => { gameTypeRef.current = gameType; }, [gameType]);
    const persistOrganizerSession = useCallback((overrides: Record<string, unknown> = {}) => {
        const code = String(overrides?.roomCode || roomCodeRef.current || roomCode || '');
        const token = String(overrides?.organizerToken || organizerTokenRef.current || '');
        if (!code || !token) return;
        saveOrganizerSession({
            roomCode: code,
            organizerToken: token,
            gameType: String(overrides?.gameType || gameTypeRef.current || gameType),
            contentId: String(overrides?.contentId || contentId || ''),
            hostAppJoinUrl: String(overrides?.hostAppJoinUrl || hostAppJoinUrl || ''),
            hostAppJoinLabel: String(overrides?.hostAppJoinLabel || hostAppJoinLabel || ''),
            hostAppReturnUrl: String(overrides?.hostAppReturnUrl || hostAppReturnUrl || ''),
            hostAppPartyHubUrl: String(overrides?.hostAppPartyHubUrl || hostAppPartyHubUrl || ''),
        });
    }, [contentId, gameType, hostAppJoinLabel, hostAppJoinUrl, hostAppPartyHubUrl, hostAppReturnUrl, roomCode]);
    useEffect(() => {
        let cancelled = false;
        fetch(apiUrl('/catalog'), { headers: apiHeaders() })
            .then((res) => res.ok ? res.json() : null)
            .then((body) => {
                if (!cancelled && Array.isArray(body?.games)) setCatalog(body.games as CatalogGameWithRules[]);
            })
            .catch(() => {
                if (!cancelled) setCatalog([]);
            });
        return () => { cancelled = true; };
    }, []);
    useEffect(() => {
        window.scrollTo({ top: 0, left: 0, behavior: 'auto' });
        document.documentElement.scrollTop = 0;
        document.body.scrollTop = 0;
    }, [state, gameType]);
    useEffect(() => {
        if (!hostAppMode && errorModal?.upgradeAvailable) track('paywall_shown', { source: 'error_modal' });
    }, [errorModal, hostAppMode]);

    // Listen for home navigation from hamburger menu
    useEffect(() => {
        const handler = () => {
            const homeSafeStates: OrganizerState[] = [
                'SELECT_GAME',
                'PROMPT',
                'QUIZ_VARIANT_PROMPT',
                'CUSTOM_QUIZ',
                'QUIZ_LIBRARY',
                'MLT_PROMPT',
                'DRAWING_PROMPT',
                'WHO_AM_I_PROMPT',
                'WHO_AM_I_REVIEW',
                'CHIT_PULL_PROMPT',
                'CHIT_PULL_REVIEW',
                'HOUSIE_SETUP',
                'BINGO_PROMPT',
                'BINGO_SETUP',
                'MUSICAL_CHAIRS_SETUP',
                'PARTY_QUESTS_SETUP',
                'LOADING',
                'REVIEW',
                'MLT_REVIEW',
                'DRAWING_REVIEW',
                'GENERATING_IMAGES',
            ];
            const homeActiveStates: OrganizerState[] = ['ROOM', 'QUESTION', 'BINGO_CALLING', 'MUSICAL_CHAIRS', 'BLUFF', 'POKER', 'TWO_TRUTHS', 'STORY_CHAIN', 'COMMON_GROUND', 'FIND_SOMEONE', 'WHO_AM_I', 'CHIT_PULL', 'MAFIA', 'PARTY_QUESTS', 'SURVEY_SAYS', 'GENERIC_PROMPT', 'SIMPLE_SOCIAL', 'PHOTO_CLUE', 'ANSWER_REVEAL', 'LEADERBOARD', 'PODIUM'];
            if (homeSafeStates.includes(stateRef.current)) {
                flowEpochRef.current += 1;
                clearOrganizerSession();
                setQuiz(null);
                setMltGame(null);
                setDrawingGame(null);
                setHousieCalled([]);
                setHousieLatest(null);
                setHousieCanUndoLastCall(false);
                setHousieWinners([]);
                setTwoTruthsState(null);
                setStoryChainState(null);
                setCommonGroundState(null);
                setFindSomeoneState(null);
                setWhoAmIState(null);
                setWhoAmIGame(null);
                setChitPullState(null);
                setChitPullGame(null);
                setMafiaState(null);
                setPartyQuestsState(null);
                setSurveySaysState(null);
                setGenericPromptState(null);
                setEditingPackId(undefined);
                setContentId('');
                setQuestionImages({});
                setState('SELECT_GAME');
            } else if (homeActiveStates.includes(stateRef.current)) {
                const confirmed = window.confirm('Going home will leave this active room. Players may be interrupted if the game is in progress. Continue?');
                if (!confirmed) return;
                flowEpochRef.current += 1;
                clearOrganizerSession();
                wsRef.current?.close();
                wsRef.current = null;
                setRoomCode('');
                setPlayerCount(0);
                setPlayers([]);
                setQuiz(null);
                setMltGame(null);
                setDrawingGame(null);
                setHousieCalled([]);
                setHousieLatest(null);
                setHousieCanUndoLastCall(false);
                setHousieWinners([]);
                setTwoTruthsState(null);
                setStoryChainState(null);
                setCommonGroundState(null);
                setFindSomeoneState(null);
                setWhoAmIState(null);
                setWhoAmIGame(null);
                setChitPullState(null);
                setChitPullGame(null);
                setMafiaState(null);
                setPartyQuestsState(null);
                setSurveySaysState(null);
                setGenericPromptState(null);
                setEditingPackId(undefined);
                setContentId('');
                setQuestionImages({});
                setState('SELECT_GAME');
            }
        };
        window.addEventListener('navigate-home', handler);
        return () => window.removeEventListener('navigate-home', handler);
    }, []);

    useEffect(() => {
        const handler = () => {
            if (stateRef.current === 'SELECT_GAME') return;
            const rules = rulesForGame(gameTypeRef.current, catalog);
            if (rules) setActiveRules(rules);
        };
        window.addEventListener('show-game-rules', handler);
        return () => window.removeEventListener('show-game-rules', handler);
    }, [catalog]);

    useEffect(() => {
        const publishRulesContext = () => {
            const rules = state === 'SELECT_GAME' ? null : rulesForGame(gameType, catalog);
            window.dispatchEvent(new CustomEvent('game-rules-context', {
                detail: { available: Boolean(rules), title: rules?.title },
            }));
        };
        publishRulesContext();
        window.addEventListener('request-game-rules-context', publishRulesContext);
        return () => {
            window.removeEventListener('request-game-rules-context', publishRulesContext);
            window.dispatchEvent(new CustomEvent('game-rules-context', { detail: { available: false } }));
        };
    }, [catalog, gameType, state]);

    // Proactive "Get Sparks" entry (e.g. tapping the spark badge) — open the purchase modal directly.
    useEffect(() => {
        const handler = () => {
            if (hostAppMode) return;
            if (remoteConfig.operations.kill_payments) {
                setErrorModal({ title: 'Payments Unavailable', message: 'Payments are temporarily disabled. Please try again later.' });
                return;
            }
            track('get_sparks_clicked', { source: 'spark_badge' });
            setShowPurchase(true);
        };
        window.addEventListener('open-spark-purchase', handler);
        return () => window.removeEventListener('open-spark-purchase', handler);
    }, [hostAppMode, remoteConfig.operations.kill_payments]);

    useEffect(() => {
        fetch(`${API_URL}/sd/status`)
            .then(res => res.ok ? res.json() : Promise.reject())
            .then(data => setSdAvailable(data?.available ?? false))
            .catch(() => setSdAvailable(false));

        fetch(`${API_URL}/providers`)
            .then(res => res.ok ? res.json() : Promise.reject())
            .then(data => {
                setProviders(data?.providers || []);
                const defaultProvider = data?.providers?.find((p: AIProvider) => p.available);
                if (defaultProvider) setProvider(defaultProvider.id);
            })
            .catch(() => {});

        // Resume pending checkout: if a previous checkout was interrupted, poll for token
        const pending = hostAppMode ? { pending: false } : getCheckoutPending();
        let poll: ReturnType<typeof setInterval> | null = null;
        if (pending.pending) {
            let attempts = 0;
            poll = setInterval(async () => {
                attempts++;
                if (attempts > 30) { clearInterval(poll!); poll = null; clearCheckoutPending(); return; }
                try {
                    const tokenRes = await fetch(apiUrl('/checkout/token'), { headers: apiHeaders() });
                    if (tokenRes.ok) {
                        const data = await tokenRes.json();
                        clearCheckoutPending();
                        clearInterval(poll!); poll = null;
                        track('tokens_purchased', { source: 'resume', tokens_added: data.tokens_added });
                        window.dispatchEvent(new CustomEvent('refresh-sparks'));
                        setErrorModal({ title: 'Sparks Added!', message: `+${data.tokens_added} sparks added to your balance. Enjoy!` });
                    }
                } catch { /* keep polling */ }
            }, 2000);
        }
        return () => { if (poll) clearInterval(poll); };
    }, [hostAppMode]);


    const handleWsMessage = useCallback((event: MessageEvent) => {
        let msg: Record<string, unknown>;
        try { msg = JSON.parse(event.data); } catch { return; }
        if (msg.type === 'ROOM_CREATED') {
            finishedRoomCanResetRef.current = false;
            setReviewPeekOpen(false);
            setRoomCode(msg.room_code as string || roomCodeRef.current);
            setPlayerCount((msg.player_count as number | undefined) || 0);
            setPlayers((msg.players as PlayerInfo[] | undefined) || []);
            setRoomLocked(false);
        }
        else if (msg.type === 'PLAYER_JOINED') {
            setPlayerCount(msg.player_count as number);
            setPlayers(msg.players as PlayerInfo[] || []);
            soundManager.play('playerJoin');
        }
        else if (msg.type === 'QUESTION') {
            finishedRoomCanResetRef.current = false;
            setReviewPeekOpen(false);
            // First question means game just started (sparks were charged)
            if (!hostAppMode && msg.question_number === 1) {
                window.dispatchEvent(new CustomEvent('refresh-sparks'));
            }
            setCurrentQuestion(msg.question_number as number);
            setTotalQuestions(msg.total_questions as number);
            setTimeRemaining(msg.time_limit as number);
            setAnsweredCount(0);
            setIsBonus(msg.is_bonus as boolean || false);
            setLiveQuestion((msg.question as Question | undefined) || null);
            if (msg.is_bonus) setShowBonusSplash(true);
            // For WMLT, store the statement text
            if (msg.statement) {
                setCurrentStatement((msg.statement as { text: string }).text);
            }
            if (msg.game_type === 'drawing') {
                setGameType('drawing');
                setDrawingActiveDrawer(msg.drawer as string || '');
                setDrawingClue(msg.drawing_clue as string || '');
                setDrawingNextRoundCountdown(null);
                setAnsweredCount(0);
            }
            setState('QUESTION');
        }
        else if (msg.type === 'TIMER') {
            setTimeRemaining(msg.remaining as number);
            if (typeof msg.drawing_clue === 'string') setDrawingClue(msg.drawing_clue);
            if (typeof msg.drawer === 'string') setDrawingActiveDrawer(msg.drawer);
        }
        else if (msg.type === 'DRAWING_NEXT_ROUND_PENDING') {
            setDrawingNextRoundCountdown(msg.remaining as number);
        }
        else if (msg.type === 'ANSWER_COUNT') setAnsweredCount(msg.answered as number);
        else if (msg.type === 'VOTE_COUNT') setAnsweredCount(msg.voted as number);
        else if (msg.type === 'QUESTION_OVER') {
            setLeaderboard(msg.leaderboard as LeaderboardEntry[]);
            if (msg.game_type === 'wmlt') {
                setWmltRoundResult({
                    winner: msg.winner as string,
                    winners: (msg.winners as string[]) || [msg.winner as string],
                    round_podium: (msg.round_podium as { nickname: string; avatar: string; vote_count: number; voters: string[] }[]) || [],
                    unanimous: msg.unanimous as boolean || false,
                    show_votes: msg.show_votes as boolean ?? true,
                    statement: msg.statement as string || '',
                });
                setDrawingRoundResult(null);
            } else if (msg.game_type === 'drawing') {
                setDrawingRoundResult({
                    prompt: msg.prompt as string || '',
                    drawer: msg.drawer as string || '',
                    correct_guessers: (msg.correct_guessers as string[]) || [],
                });
                setWmltRoundResult(null);
            } else {
                setWmltRoundResult(null);
                setDrawingRoundResult(null);
                setRevealedAnswer(typeof msg.answer === 'number' ? (msg.answer as number) : null);
            }
            // Quiz-runtime games reveal the correct answer before the leaderboard;
            // WMLT/Drawing have their own result screens and go straight to it.
            setState(msg.game_type === 'wmlt' || msg.game_type === 'drawing' ? 'LEADERBOARD' : 'ANSWER_REVEAL');
        }
        else if (msg.type === 'PODIUM') {
            finishedRoomCanResetRef.current = true;
            setLeaderboard(msg.leaderboard as LeaderboardEntry[]);
            setTeamLeaderboard(msg.team_leaderboard as TeamLeaderboardEntry[] || []);
            if (msg.housie_winners) setHousieWinners(msg.housie_winners as HousieWinner[]);
            if (msg.find_someone) setFindSomeoneState(msg.find_someone as FindSomeoneState);
            if (msg.photo_clue) setPhotoClueState(msg.photo_clue as PhotoClueState);
            if (msg.generic_prompt) setGenericPromptState(msg.generic_prompt as GenericPromptState);
            if (msg.would_you_rather || msg.never_have_i_ever || msg.word_association || msg.acronym) {
                setSimpleSocialState((msg.would_you_rather || msg.never_have_i_ever || msg.word_association || msg.acronym) as SimpleSocialState);
            }
            setSuperlatives((msg.superlatives as { title: string; icon: string; winner: string; avatar: string; detail: string }[]) || []);
            track('game_completed', { room_code: roomCodeRef.current, game_type: gameTypeRef.current, player_count: (msg.leaderboard as LeaderboardEntry[])?.length || 0, winner: (msg.leaderboard as LeaderboardEntry[])?.[0]?.nickname });
            setState('PODIUM');
            soundManager.play('fanfare');
        }
        else if (msg.type === 'BINGO_SYNC') {
            finishedRoomCanResetRef.current = false;
            const bingo = msg.bingo as { called_items?: Array<{ value: number | string; display: string; kind?: string; image_url?: string; alt_text?: string }>; latest_item?: { value: number | string; display: string; kind?: string; image_url?: string; alt_text?: string } | null; can_undo_last_call?: boolean; terminal_claim_pending?: boolean; patterns?: HousiePattern[]; winners?: HousieWinner[]; play_mode?: 'beginner' | 'pro'; caller_mode?: 'manual' | 'auto'; auto_status?: 'running' | 'paused' | 'stopped'; auto_interval_seconds?: number; auto_pause_on_claim?: boolean } | undefined;
            if (msg.game_type === 'bingo') setGameType('bingo');
            else setGameType('housie');
            setHousieCalled(bingo?.called_items || []);
            setHousieLatest(bingo?.latest_item || null);
            setHousieCanUndoLastCall(Boolean(bingo?.can_undo_last_call));
            setHousieTerminalClaimPending(Boolean(bingo?.terminal_claim_pending));
            setHousieWinners(bingo?.winners || []);
            if (bingo?.play_mode) setHousiePlayMode(bingo.play_mode);
            if (bingo?.caller_mode) setHousieCallerMode(bingo.caller_mode);
            if (bingo?.auto_status) setHousieAutoStatus(bingo.auto_status);
            if (bingo?.auto_interval_seconds) setHousieAutoInterval(bingo.auto_interval_seconds);
            if (typeof bingo?.auto_pause_on_claim === 'boolean') setHousieAutoPauseOnClaim(bingo.auto_pause_on_claim);
            setState('BINGO_CALLING');
        }
        else if (msg.type === 'BINGO_CALL') {
            if (msg.game_type === 'bingo') setGameType('bingo');
            else setGameType('housie');
            setHousieCalled(msg.called_items as Array<{ value: number | string; display: string }> || []);
            setHousieLatest(msg.item as { value: number | string; display: string });
            setHousieCanUndoLastCall(Boolean(msg.can_undo_last_call));
            setHousieTerminalClaimPending(false);
            const callItem = msg.item as { value?: number | string; display?: string; kind?: string; image_url?: string; alt_text?: string };
            setHousieCallFlash({ item: { ...callItem, display: String(callItem?.display || '') }, key: Date.now() });
            setState('BINGO_CALLING');
            soundManager.play('correct');
        }
        else if (msg.type === 'BINGO_AUTO_STATUS') {
            if (msg.caller_mode === 'manual' || msg.caller_mode === 'auto') setHousieCallerMode(msg.caller_mode);
            if (msg.auto_status === 'running' || msg.auto_status === 'paused' || msg.auto_status === 'stopped') setHousieAutoStatus(msg.auto_status);
            if (typeof msg.auto_interval_seconds === 'number') setHousieAutoInterval(msg.auto_interval_seconds);
        }
        else if (msg.type === 'BINGO_CLAIM_ACCEPTED') {
            setHousieWinners(msg.winners as HousieWinner[] || []);
            setLeaderboard(msg.leaderboard as LeaderboardEntry[] || []);
            setHousieCanUndoLastCall(Boolean(msg.can_undo_last_call));
            setHousieTerminalClaimPending(Boolean(msg.terminal_claim_pending));
            const winner = msg.winner as HousieWinner | undefined;
            if (winner) setHousieAnnouncement({ text: `${winner.nickname} won ${winner.label}${winner.winning_number ? ` on ${winner.winning_number}` : ''}`, key: Date.now() });
            soundManager.play('fanfare');
        }
        else if (msg.type === 'BINGO_COMPLETE') {
            setHousieWinners(msg.winners as HousieWinner[] || []);
            setLeaderboard(msg.leaderboard as LeaderboardEntry[] || []);
            setHousieTerminalClaimPending(false);
        }
        else if (msg.type === 'MC_SYNC' || msg.type === 'MC_ROUND_START' || msg.type === 'MC_MUSIC_STOP' || msg.type === 'MC_GRAB_COUNT' || msg.type === 'MC_ROUND_OVER') {
            finishedRoomCanResetRef.current = false;
            setGameType('musical_chairs');
            setMusicalChairsState(msg.musical_chairs as MusicalChairsState);
            setState('MUSICAL_CHAIRS');
        }
        else if (msg.type === 'MC_WINNER') {
            setGameType('musical_chairs');
        }
        else if (msg.type === 'BLUFF_SYNC') {
            finishedRoomCanResetRef.current = false;
            setGameType('bluff');
            setBluffState(msg.bluff as BluffState);
            setState('BLUFF');
        }
        else if (msg.type === 'TT_SYNC') {
            finishedRoomCanResetRef.current = false;
            setGameType('two_truths');
            setTwoTruthsState(msg.two_truths as TwoTruthsState);
            setLeaderboard(msg.leaderboard as LeaderboardEntry[] || []);
            setState('TWO_TRUTHS');
        }
        else if (msg.type === 'STORY_SYNC') {
            finishedRoomCanResetRef.current = false;
            setGameType('story_chain');
            setStoryChainState(msg.story_chain as StoryChainState);
            setLeaderboard(msg.leaderboard as LeaderboardEntry[] || []);
            setState('STORY_CHAIN');
        }
        else if (msg.type === 'COMMON_SYNC') {
            finishedRoomCanResetRef.current = false;
            setGameType('common_ground');
            setCommonGroundState(msg.common_ground as CommonGroundState);
            setLeaderboard(msg.leaderboard as LeaderboardEntry[] || []);
            setState('COMMON_GROUND');
        }
        else if (msg.type === 'FIND_SYNC') {
            finishedRoomCanResetRef.current = false;
            setGameType('find_someone');
            setFindSomeoneState(msg.find_someone as FindSomeoneState);
            setLeaderboard(msg.leaderboard as LeaderboardEntry[] || []);
            setState('FIND_SOMEONE');
        }
        else if (msg.type === 'WHOAMI_SYNC') {
            finishedRoomCanResetRef.current = false;
            setGameType('who_am_i');
            setWhoAmIState(msg.who_am_i as WhoAmIState);
            setLeaderboard(msg.leaderboard as LeaderboardEntry[] || []);
            setState('WHO_AM_I');
        }
        else if (msg.type === 'CHIT_SYNC') {
            finishedRoomCanResetRef.current = false;
            setGameType('chit_pull');
            setChitPullState(msg.chit_pull as ChitPullState);
            setLeaderboard(msg.leaderboard as LeaderboardEntry[] || []);
            setState('CHIT_PULL');
        }
        else if (msg.type === 'MAFIA_SYNC') {
            finishedRoomCanResetRef.current = false;
            setGameType('mafia');
            setMafiaState(msg.mafia as MafiaState);
            setLeaderboard(msg.leaderboard as LeaderboardEntry[] || []);
            setState('MAFIA');
        }
        else if (msg.type === 'QUESTS_SYNC') {
            finishedRoomCanResetRef.current = false;
            setGameType('party_quests');
            setPartyQuestsState(msg.party_quests as PartyQuestsState);
            setLeaderboard(msg.leaderboard as LeaderboardEntry[] || []);
            setState('PARTY_QUESTS');
        }
        else if (msg.type === 'SURVEY_SYNC') {
            finishedRoomCanResetRef.current = false;
            setGameType('survey_says');
            setSurveySaysState(msg.survey_says as SurveySaysState);
            setPlayers(msg.players as PlayerInfo[] || []);
            setPlayerCount(msg.player_count as number || 0);
            setLeaderboard(msg.leaderboard as LeaderboardEntry[] || []);
            setTeamLeaderboard(msg.team_leaderboard as TeamLeaderboardEntry[] || []);
            setState('SURVEY_SAYS');
        }
        else if (msg.type === 'GENERIC_PROMPT_SYNC') {
            finishedRoomCanResetRef.current = false;
            const incomingGameType = msg.game_type as GenericPromptGameType;
            setGameType(incomingGameType);
            setGenericPromptState(msg.generic_prompt as GenericPromptState);
            setPlayers(msg.players as PlayerInfo[] || []);
            setPlayerCount(msg.player_count as number || 0);
            setLeaderboard(msg.leaderboard as LeaderboardEntry[] || []);
            setState('GENERIC_PROMPT');
        }
        else if (msg.type === 'SIMPLE_SOCIAL_SYNC') {
            finishedRoomCanResetRef.current = false;
            const incomingGameType = msg.game_type as SimpleSocialGameType;
            const payload = (msg[incomingGameType] || null) as SimpleSocialState | null;
            setGameType(incomingGameType);
            setSimpleSocialState(payload);
            setPlayers(msg.players as PlayerInfo[] || []);
            setPlayerCount(msg.player_count as number || 0);
            setLeaderboard(msg.leaderboard as LeaderboardEntry[] || []);
            setState('SIMPLE_SOCIAL');
        }
        else if (msg.type === 'PHOTO_CLUE_SYNC') {
            finishedRoomCanResetRef.current = false;
            setGameType('photo_clue');
            setPhotoClueState(msg.photo_clue as PhotoClueState);
            setPlayers(msg.players as PlayerInfo[] || []);
            setPlayerCount(msg.player_count as number || 0);
            setLeaderboard(msg.leaderboard as LeaderboardEntry[] || []);
            setState('PHOTO_CLUE');
        }
        else if (msg.type === 'POKER_SYNC') {
            finishedRoomCanResetRef.current = false;
            setGameType('poker');
            setPokerState(msg.poker as PokerState);
            setPlayers(msg.players as PlayerInfo[] || []);
            setPlayerCount(msg.player_count as number || 0);
            setLeaderboard(msg.leaderboard as LeaderboardEntry[] || []);
            setState('POKER');
        }
        else if (msg.type === 'PLAYER_LEFT' || msg.type === 'PLAYER_DISCONNECTED' || msg.type === 'PLAYERS_REMOVED') {
            setPlayerCount(msg.player_count as number);
            setPlayers(msg.players as PlayerInfo[] || []);
        }
        else if (msg.type === 'PLAYER_RECONNECTED') {
            setPlayerCount(msg.player_count as number);
            setPlayers(msg.players as PlayerInfo[] || []);
        }
        else if (msg.type === 'ROOM_RESET') {
            finishedRoomCanResetRef.current = false;
            setReviewPeekOpen(false);
            if (msg.game_type) {
                setGameType(msg.game_type as GameType);
                persistOrganizerSession({ gameType: msg.game_type as string, contentId: '' });
            }
            setPlayerCount(msg.player_count as number);
            setPlayers(msg.players as PlayerInfo[] || []);
            setRoomLocked(false);
            setCurrentQuestion(0);
            setLeaderboard([]);
            setTeamLeaderboard([]);
            setHousieCalled([]);
            setHousieLatest(null);
            setHousieCanUndoLastCall(false);
            setHousieWinners([]);
            setTwoTruthsState(null);
            setStoryChainState(null);
            setCommonGroundState(null);
            setFindSomeoneState(null);
            setWhoAmIState(null);
            setChitPullState(null);
            setMafiaState(null);
            setPartyQuestsState(null);
            setSurveySaysState(null);
            setGenericPromptState(null);
            setAnsweredCount(0);
            setLiveQuestion(null);
            setCurrentStatement('');
            setState('ROOM');
        }
        else if (msg.type === 'ROOM_CLOSED') {
            if (reconnectTimerRef.current) {
                clearTimeout(reconnectTimerRef.current);
                reconnectTimerRef.current = null;
            }
            clearOrganizerSession();
            roomCodeRef.current = '';
            stateRef.current = 'SELECT_GAME';
            setRoomCode('');
            setPlayerCount(0);
            setPlayers([]);
            setState('SELECT_GAME');
            if (hostAppMode) {
                setErrorModal({
                    title: 'Game cancelled',
                    message: msg.message as string || 'This game session was cancelled.',
                    returnToHostApp: true,
                });
            }
        }
        else if (msg.type === 'INSUFFICIENT_SPARKS') {
            setErrorModal({
                title: hostAppMode ? 'Game Unavailable' : 'Not Enough Sparks',
                message: hostAppMode ? 'This Revelry-managed game could not be started. Please return to Revelry and try again.' : msg.message as string || 'You need more sparks to start a game.',
                upgradeAvailable: !hostAppMode,
            });
        }
        else if (msg.type === 'ROOM_LOCK_STATUS') {
            setRoomLocked(msg.locked as boolean);
        }
        else if (msg.type === 'ORGANIZER_RECONNECTED') {
            setRoomCode(msg.room_code as string);
            persistOrganizerSession({
                roomCode: msg.room_code as string,
                gameType: msg.game_type as string || gameTypeRef.current,
            });
            setPlayerCount(msg.player_count as number);
            setPlayers(msg.players as PlayerInfo[] || []);
            setTotalQuestions(msg.total_questions as number);
            setLeaderboard(msg.leaderboard as LeaderboardEntry[] || []);
            setTeamLeaderboard(msg.team_leaderboard as TeamLeaderboardEntry[] || []);
            setTimeLimit(msg.time_limit as number);
            setRoomLocked(msg.locked as boolean ?? false);
            if (msg.game_type) setGameType(msg.game_type as GameType);
            if (msg.musical_chairs) setMusicalChairsState(msg.musical_chairs as MusicalChairsState);
            if (msg.bluff) setBluffState(msg.bluff as BluffState);
            if (msg.poker) setPokerState(msg.poker as PokerState);
            if (msg.two_truths) setTwoTruthsState(msg.two_truths as TwoTruthsState);
            if (msg.story_chain) setStoryChainState(msg.story_chain as StoryChainState);
            if (msg.common_ground) setCommonGroundState(msg.common_ground as CommonGroundState);
            if (msg.find_someone) setFindSomeoneState(msg.find_someone as FindSomeoneState);
            if (msg.who_am_i) setWhoAmIState(msg.who_am_i as WhoAmIState);
            if (msg.chit_pull) setChitPullState(msg.chit_pull as ChitPullState);
            if (msg.mafia) setMafiaState(msg.mafia as MafiaState);
            if (msg.party_quests) setPartyQuestsState(msg.party_quests as PartyQuestsState);
            if (msg.survey_says) setSurveySaysState(msg.survey_says as SurveySaysState);
            if (msg.generic_prompt) setGenericPromptState(msg.generic_prompt as GenericPromptState);
            if (msg.photo_clue) setPhotoClueState(msg.photo_clue as PhotoClueState);
            if (msg.would_you_rather || msg.never_have_i_ever || msg.word_association || msg.acronym) {
                setSimpleSocialState((msg.would_you_rather || msg.never_have_i_ever || msg.word_association || msg.acronym) as SimpleSocialState);
            }
            if (msg.quiz) {
                const quizData = msg.quiz as Record<string, unknown>;
                if (quizData.questions) {
                    setQuiz(quizData as unknown as Quiz);
                    setTotalQuestions((quizData.questions as unknown[]).length);
                } else if (quizData.statements) {
                    setMltGame(quizData as unknown as MLTGame);
                    setTotalQuestions((quizData.statements as unknown[]).length);
                } else if (quizData.prompts) {
                    setDrawingGame(quizData as unknown as DrawingGame);
                    setTotalQuestions((quizData.prompts as unknown[]).length);
                }
            }
            if (msg.state === 'LOBBY' || msg.state === 'INTRO') {
                finishedRoomCanResetRef.current = false;
                setState('ROOM');
            } else if (msg.state === 'QUESTION') {
                finishedRoomCanResetRef.current = false;
                setCurrentQuestion(msg.question_number as number);
                setTimeRemaining((msg.time_remaining ?? msg.time_limit) as number);
                setAnsweredCount((msg.answered_count ?? msg.voted_count ?? 0) as number);
                setIsBonus(msg.is_bonus as boolean || false);
                setLiveQuestion((msg.question as Question | undefined) || null);
                if (msg.statement) {
                    setCurrentStatement((msg.statement as { text: string }).text);
                }
                setState('QUESTION');
            } else if (msg.state === 'LEADERBOARD') {
                finishedRoomCanResetRef.current = false;
                setCurrentQuestion(msg.question_number as number);
                setState('LEADERBOARD');
            } else if (msg.state === 'PODIUM') {
                finishedRoomCanResetRef.current = true;
                setState('PODIUM');
                soundManager.play('fanfare');
            } else if (String(msg.state || '').startsWith('MC_')) {
                finishedRoomCanResetRef.current = false;
                setState('MUSICAL_CHAIRS');
            } else if (String(msg.state || '').startsWith('BLUFF_')) {
                finishedRoomCanResetRef.current = false;
                setState('BLUFF');
            } else if (String(msg.state || '').startsWith('POKER_')) {
                finishedRoomCanResetRef.current = false;
                setState('POKER');
            } else if (String(msg.state || '').startsWith('TT_')) {
                finishedRoomCanResetRef.current = false;
                setState('TWO_TRUTHS');
            } else if (String(msg.state || '').startsWith('STORY_')) {
                finishedRoomCanResetRef.current = false;
                setState('STORY_CHAIN');
            } else if (String(msg.state || '').startsWith('COMMON_')) {
                finishedRoomCanResetRef.current = false;
                setState('COMMON_GROUND');
            } else if (String(msg.state || '').startsWith('FIND_')) {
                finishedRoomCanResetRef.current = false;
                setState('FIND_SOMEONE');
            } else if (String(msg.state || '').startsWith('CHIT_')) {
                finishedRoomCanResetRef.current = false;
                setState('CHIT_PULL');
            } else if (String(msg.state || '').startsWith('WHOAMI_')) {
                finishedRoomCanResetRef.current = false;
                setState('WHO_AM_I');
            } else if (String(msg.state || '').startsWith('MAFIA_')) {
                finishedRoomCanResetRef.current = false;
                setState('MAFIA');
            } else if (String(msg.state || '').startsWith('QUESTS_')) {
                finishedRoomCanResetRef.current = false;
                setState('PARTY_QUESTS');
            } else if (String(msg.state || '').startsWith('SURVEY_')) {
                finishedRoomCanResetRef.current = false;
                setState('SURVEY_SAYS');
            } else if (String(msg.state || '').startsWith('GENERIC_')) {
                finishedRoomCanResetRef.current = false;
                setState('GENERIC_PROMPT');
            } else if (String(msg.state || '').startsWith('PHOTO_')) {
                finishedRoomCanResetRef.current = false;
                setState('PHOTO_CLUE');
            } else if (
                String(msg.state || '').startsWith('WYR_') ||
                String(msg.state || '').startsWith('NHIE_') ||
                String(msg.state || '').startsWith('WORD_ASSOC_') ||
                String(msg.state || '').startsWith('ACRONYM_')
            ) {
                finishedRoomCanResetRef.current = false;
                setState('SIMPLE_SOCIAL');
            }
        }
        else if (msg.type === 'ERROR') {
            const message = msg.message as string || 'Unknown error';
            console.error('Organizer error:', message);
            // Non-fatal errors (e.g. min players) — show a dismissable modal and
            // stay in the current state. The lobby already disables Start below the
            // minimum, so this is a rare fallback (e.g. a player left mid-press).
            if (message.includes('players')) {
                setErrorModal({ title: 'Not enough players', message });
            } else {
                clearOrganizerSession();
                if (hostAppMode) {
                    setErrorModal({
                        title: 'Game Unavailable',
                        message: 'This Revelry-managed game is no longer available. Return to Revelry Games to start another one.',
                        returnToHostApp: true,
                    });
                } else {
                    clearOrganizerSession();
                    setRoomCode('');
                    setState('SELECT_GAME');
                }
            }
        }
    }, [hostAppMode, persistOrganizerSession]);

    const handleGameSelect = (type: GameType) => {
        window.dispatchEvent(new CustomEvent('close-settings'));
        setGameType(type);
        setTimeLimit(defaultTimeLimitForGame(type));
        if (type === 'wmlt') setDifficulty('party');
        else setDifficulty('medium');
        if (type === 'wmlt') setState('MLT_PROMPT');
        else if (type === 'drawing') setState('DRAWING_PROMPT');
        else if (type === 'housie') {
            setHousieTitle('Housie');
            setState('HOUSIE_SETUP');
        }
        else if (type === 'bingo') {
            setBingoTitle('Bingo');
            setBingoDeck(starterBingoDeck());
            setGeneratedBingoId('');
            setBingoFreeCenter(true);
            setBingoClaimRequiresLatest(false);
            setNumQuestions(30);
            setPrompt('');
            setDifficulty('medium');
            setState('BINGO_PROMPT');
        }
        else if (type === 'baby_bingo' || type === 'wedding_bingo' || type === 'holiday_bingo' || type === 'road_trip_bingo') {
            const occasion = OCCASION_BINGO[type];
            setBingoTitle(occasion.title);
            setBingoDeck(bingoDeckFrom(occasion.prefix, occasion.items));
            setGeneratedBingoId('');
            setBingoFreeCenter(true);
            setBingoClaimRequiresLatest(false);
            setNumQuestions(25);
            setPrompt(occasion.prompt);
            setDifficulty('easy');
            setState('BINGO_SETUP');
        }
        else if (type === 'musical_chairs') {
            setMusicalChairsConfig(defaultMusicalChairsConfig);
            setMusicalChairsState(null);
            setState('MUSICAL_CHAIRS_SETUP');
        }
        else if (type === 'bluff') {
            setBluffState(null);
            void createRoom(undefined, 'bluff', defaultTimeLimitForGame('bluff'));
        }
        else if (type === 'two_truths') {
            setTwoTruthsState(null);
            void createRoom(undefined, 'two_truths', defaultTimeLimitForGame('two_truths'));
        }
        else if (type === 'story_chain') {
            setStoryChainState(null);
            void createRoom(undefined, 'story_chain', defaultTimeLimitForGame('story_chain'));
        }
        else if (type === 'common_ground') {
            setCommonGroundState(null);
            void createRoom(undefined, 'common_ground', defaultTimeLimitForGame('common_ground'));
        }
        else if (type === 'find_someone') {
            setFindSomeoneState(null);
            void createRoom(undefined, 'find_someone', defaultTimeLimitForGame('find_someone'));
        }
        else if (type === 'who_am_i') {
            setWhoAmIState(null);
            setWhoAmIGame(null);
            setPrompt(randomQuizTopic(prompt));
            setNumQuestions(10);
            setState('WHO_AM_I_PROMPT');
        }
        else if (type === 'chit_pull') {
            setChitPullState(null);
            setChitPullGame(null);
            setChitPullSafeLevel('family');
            setPrompt('birthday party, silly but clean');
            setDifficulty('medium');
            setNumQuestions(20);
            setState('CHIT_PULL_PROMPT');
        }
        else if (type === 'mafia') {
            setMafiaState(null);
            void createRoom(undefined, 'mafia', defaultTimeLimitForGame('mafia'));
        }
        else if (type === 'poker') {
            setPokerState(null);
            void createRoom(undefined, 'poker', defaultTimeLimitForGame('poker'));
        }
        else if (type === 'party_quests') {
            const next = defaultPartyQuestsConfig();
            setPartyQuestsConfig(next);
            setPartyQuestsState(null);
            setState('PARTY_QUESTS_SETUP');
        }
        else if (type === 'survey_says') {
            setSurveySaysState(null);
            void createRoom(undefined, 'survey_says', defaultTimeLimitForGame('survey_says'));
        }
        else if (isGenericPromptGame(type)) {
            setGenericPromptState(null);
            void createRoom(undefined, type, defaultTimeLimitForGame(type));
        }
        else if (type === 'would_you_rather' || type === 'never_have_i_ever' || type === 'word_association' || type === 'acronym' || type === 'odd_question') {
            setSimpleSocialState(null);
            void createRoom(undefined, type, defaultTimeLimitForGame(type));
        }
        else if (type === 'photo_clue') {
            setPhotoClueState(null);
            void createRoom(undefined, 'photo_clue', defaultTimeLimitForGame('photo_clue'));
        }
        else if (type === 'quiz') {
            setPrompt(randomQuizTopic(prompt));
            setState('PROMPT');
        }
        else {
            setPrompt(randomQuizTopic(prompt));
            setState('QUIZ_VARIANT_PROMPT');
        }
    };

    const generateQuiz = async () => {
        if (remoteConfig.operations.kill_generate) {
            setErrorModal({ title: 'Temporarily Unavailable', message: 'Game generation is temporarily disabled. Please try again later.' });
            return;
        }
        setLoadingCopy({ title: 'Generating Quiz' });
        setState('LOADING');
        try {
            const res = await fetch(apiUrl('/quiz/generate'), {
                method: 'POST',
                headers: apiHeaders({ 'X-Idempotency-Key': generateIdempotencyKey() }),
                body: JSON.stringify({
                    prompt,
                    difficulty,
                    num_questions: numQuestions,
                    provider,
                    mode: getGameModeConfig(gameType).mode || 'classic',
                }),
            });
            if (res.status === 402) {
                track('paywall_hit', { source: 'quiz' });
                setErrorModal({ title: 'Not Enough Sparks', message: 'You need more sparks! Grab a spark pack to keep playing, or come back tomorrow for your daily bonus.', upgradeAvailable: !hostAppMode });
                setState(gameType === 'quiz' ? 'PROMPT' : 'QUIZ_VARIANT_PROMPT');
                return;
            }
            if (res.status === 503) {
                track('quota_error', { source: 'quiz' });
                setErrorModal({ title: 'Daily Limit Reached', message: 'Daily generation limit reached. Try again tomorrow or buy a spark pack!', upgradeAvailable: true });
                setState(gameType === 'quiz' ? 'PROMPT' : 'QUIZ_VARIANT_PROMPT');
                return;
            }
            if (res.status === 429) {
                const err = await res.json().catch(() => ({ detail: 'Too many requests. Please wait a minute.' }));
                setErrorModal({ title: 'Rate Limited', message: err.detail || 'Too many requests.' });
                setState(gameType === 'quiz' ? 'PROMPT' : 'QUIZ_VARIANT_PROMPT');
                return;
            }
            const data = await res.json();
            if (data.quiz) {
                setQuizOrigin('ai');
                let nextQuiz = data.quiz;
                setContentId(data.quiz_id);
                setTotalQuestions(data.quiz.questions.length);
                track('quiz_generated', { topic: prompt, difficulty, num_questions: numQuestions, provider, mode: getGameModeConfig(gameType).mode || 'classic' });
                window.dispatchEvent(new CustomEvent('refresh-sparks'));
                if (generateQuizImages && sdAvailable) {
                    setLoadingCopy({ title: 'Generating Images' });
                    nextQuiz = await generateImagesForQuiz(data.quiz_id, data.quiz);
                }
                setQuiz(nextQuiz);
                setState('REVIEW');
            } else {
                setErrorModal({ title: 'Generation Failed', message: 'Failed to generate quiz. Please try a different topic.' });
                setState(gameType === 'quiz' ? 'PROMPT' : 'QUIZ_VARIANT_PROMPT');
            }
        } catch {
            setErrorModal({ title: 'Connection Error', message: 'Could not reach the server. Check your internet connection.' });
            setState(gameType === 'quiz' ? 'PROMPT' : 'QUIZ_VARIANT_PROMPT');
        }
    };

    const importCustomQuiz = async (customQuiz: Quiz) => {
        setLoadingCopy({ title: 'Preparing Quiz', messages: PREPARING_MESSAGES });
        setState('LOADING');
        try {
            const res = await fetch(apiUrl('/quiz/import'), {
                method: 'POST',
                headers: apiHeaders(),
                body: JSON.stringify({ quiz: customQuiz }),
            });
            if (!res.ok) {
                const err = await res.json().catch(() => ({ detail: 'Could not prepare this quiz.' }));
                setErrorModal({ title: 'Quiz Error', message: err.detail || `Server error (${res.status})` });
                setState('CUSTOM_QUIZ');
                return;
            }
            const data = await res.json();
            setGameType('quiz');
            setQuizOrigin('custom');
            setQuiz(customQuiz);
            setContentId(data.quiz_id);
            setTotalQuestions(customQuiz.questions.length);
            setQuestionImages({});
            track('custom_quiz_imported', { num_questions: customQuiz.questions.length });
            setState('REVIEW');
        } catch {
            setErrorModal({ title: 'Connection Error', message: 'Could not reach the server. Check your internet connection.' });
            setState('CUSTOM_QUIZ');
        }
    };

    const saveCustomQuizPack = async (customQuiz: Quiz, packId?: string) => {
        const res = await fetch(apiUrl('/quiz-packs'), {
            method: 'POST',
            headers: apiHeaders(),
            body: JSON.stringify({ pack_id: packId, quiz: customQuiz }),
        });
        if (!res.ok) throw new Error('save_failed');
        const data = await res.json();
        setEditingPackId(data.pack.id);
        track('custom_quiz_saved', { num_questions: customQuiz.questions.length });
        return data.pack.id as string;
    };

    const loadQuizLibrary = async () => {
        setLibraryLoading(true);
        try {
            const res = await fetch(apiUrl('/quiz-packs'), { headers: apiHeaders() });
            if (!res.ok) throw new Error('load_failed');
            const data = await res.json();
            setLibraryPacks(data.packs || []);
        } catch {
            setErrorModal({ title: 'Quiz Library', message: 'Could not load your saved quizzes.' });
        } finally {
            setLibraryLoading(false);
        }
    };

    const openQuizLibrary = () => {
        setGameType('quiz');
        setState('QUIZ_LIBRARY');
        void loadQuizLibrary();
    };

    const editQuizPack = async (packId: string) => {
        setLibraryLoading(true);
        try {
            const res = await fetch(apiUrl(`/quiz-packs/${packId}`), { headers: apiHeaders() });
            if (!res.ok) throw new Error('load_failed');
            const data = await res.json();
            setEditingPackId(packId);
            setQuiz(data.quiz);
            setQuizOrigin('custom');
            setState('CUSTOM_QUIZ');
        } catch {
            setErrorModal({ title: 'Quiz Library', message: 'Could not open that quiz.' });
        } finally {
            setLibraryLoading(false);
        }
    };

    const startQuizPack = async (packId: string) => {
        const flowEpoch = ++flowEpochRef.current;
        setLoadingCopy({ title: 'Preparing Quiz', messages: PREPARING_MESSAGES });
        setState('LOADING');
        try {
            const res = await fetch(apiUrl(`/quiz-packs/${packId}/materialize`), {
                method: 'POST',
                headers: apiHeaders(),
            });
            if (!res.ok) throw new Error('start_failed');
            const data = await res.json();
            const fullRes = await fetch(apiUrl(`/quiz-packs/${packId}`), { headers: apiHeaders() });
            const fullData = fullRes.ok ? await fullRes.json() : null;
            const customQuiz = fullData?.quiz || data.quiz;
            if (flowEpoch !== flowEpochRef.current) return;
            setGameType('quiz');
            setQuizOrigin('custom');
            setQuiz(customQuiz);
            setContentId(data.quiz_id);
            setTotalQuestions(customQuiz.questions.length);
            setQuestionImages({});
            setEditingPackId(packId);
            setState('REVIEW');
        } catch {
            if (flowEpoch !== flowEpochRef.current) return;
            setErrorModal({ title: 'Quiz Library', message: 'Could not start that quiz.' });
            setState('QUIZ_LIBRARY');
        }
    };

    const deleteQuizPack = async (packId: string) => {
        try {
            const res = await fetch(apiUrl(`/quiz-packs/${packId}`), {
                method: 'DELETE',
                headers: apiHeaders(),
            });
            if (!res.ok) throw new Error('delete_failed');
            setLibraryPacks((packs) => packs.filter((pack) => pack.id !== packId));
        } catch {
            setErrorModal({ title: 'Quiz Library', message: 'Could not delete that quiz.' });
        }
    };

    const generateMLT = async () => {
        if (remoteConfig.operations.kill_generate) {
            setErrorModal({ title: 'Temporarily Unavailable', message: 'Game generation is temporarily disabled. Please try again later.' });
            return;
        }
        setLoadingCopy({ title: 'Generating Game' });
        setState('LOADING');
        try {
            const res = await fetch(apiUrl('/mlt/generate'), {
                method: 'POST',
                headers: apiHeaders({ 'X-Idempotency-Key': generateIdempotencyKey() }),
                body: JSON.stringify({ prompt, difficulty, num_rounds: numQuestions, provider }),
            });
            if (res.status === 402) {
                track('paywall_hit', { source: 'mlt' });
                setErrorModal({ title: 'Not Enough Sparks', message: 'You need more sparks! Grab a spark pack to keep playing, or come back tomorrow for your daily bonus.', upgradeAvailable: !hostAppMode });
                setState('MLT_PROMPT');
                return;
            }
            if (res.status === 503) {
                track('quota_error', { source: 'mlt' });
                setErrorModal({ title: 'Daily Limit Reached', message: 'Daily generation limit reached. Try again tomorrow or buy a spark pack!', upgradeAvailable: true });
                setState('MLT_PROMPT');
                return;
            }
            if (res.status === 429) {
                const err = await res.json().catch(() => ({ detail: 'Too many requests. Please wait a minute.' }));
                setErrorModal({ title: 'Rate Limited', message: err.detail || 'Too many requests.' });
                setState('MLT_PROMPT');
                return;
            }
            const data = await res.json();
            if (data.game) {
                setMltGame(data.game);
                setContentId(data.scenario_id);
                setTotalQuestions(data.game.statements.length);
                track('mlt_generated', { topic: prompt, difficulty, num_rounds: numQuestions, provider });
                window.dispatchEvent(new CustomEvent('refresh-sparks'));
                setState('MLT_REVIEW');
            } else {
                setErrorModal({ title: 'Generation Failed', message: 'Failed to generate statements. Please try a different topic.' });
                setState('MLT_PROMPT');
            }
        } catch {
            setErrorModal({ title: 'Connection Error', message: 'Could not reach the server. Check your internet connection.' });
            setState('MLT_PROMPT');
        }
    };

    const generateDrawing = async () => {
        if (remoteConfig.operations.kill_generate) {
            setErrorModal({ title: 'Temporarily Unavailable', message: 'Game generation is temporarily disabled. Please try again later.' });
            return;
        }
        setLoadingCopy({ title: 'Generating Prompts' });
        setState('LOADING');
        try {
            const res = await fetch(apiUrl('/drawing/generate'), {
                method: 'POST',
                headers: apiHeaders({ 'X-Idempotency-Key': generateIdempotencyKey() }),
                body: JSON.stringify({ prompt, difficulty, num_prompts: numQuestions, provider }),
            });
            if (res.status === 402) {
                track('paywall_hit', { source: 'drawing' });
                setErrorModal({ title: 'Not Enough Sparks', message: 'You need more sparks! Grab a spark pack to keep playing, or come back tomorrow for your daily bonus.', upgradeAvailable: !hostAppMode });
                setState('DRAWING_PROMPT');
                return;
            }
            if (res.status === 503) {
                track('quota_error', { source: 'drawing' });
                setErrorModal({ title: 'Daily Limit Reached', message: 'Daily generation limit reached. Try again tomorrow or buy a spark pack!', upgradeAvailable: true });
                setState('DRAWING_PROMPT');
                return;
            }
            if (res.status === 429) {
                const err = await res.json().catch(() => ({ detail: 'Too many requests. Please wait a minute.' }));
                setErrorModal({ title: 'Rate Limited', message: err.detail || 'Too many requests.' });
                setState('DRAWING_PROMPT');
                return;
            }
            const data = await res.json();
            if (data.game) {
                setDrawingGame(data.game);
                setContentId(data.drawing_id);
                setTotalQuestions(data.game.prompts.length);
                track('drawing_generated', { topic: prompt, difficulty, num_prompts: numQuestions, provider });
                window.dispatchEvent(new CustomEvent('refresh-sparks'));
                setState('DRAWING_REVIEW');
            } else {
                setErrorModal({ title: 'Generation Failed', message: 'Failed to generate drawing prompts. Please try a different topic.' });
                setState('DRAWING_PROMPT');
            }
        } catch {
            setErrorModal({ title: 'Connection Error', message: 'Could not reach the server. Check your internet connection.' });
            setState('DRAWING_PROMPT');
        }
    };

    const starterWhoAmIGame = (): WhoAmIGameContent => ({
        game_title: 'Who Am I?',
        clues_per_round: 5,
        round_count: 3,
        rounds: [
            { id: 'round_1', answer: 'Taylor Swift', aliases: ['Taylor'], category: 'Musician', difficulty: 'easy', clues: ['I started in country music.', 'My albums are known as eras.', 'My lucky number is 13.', 'Fans call themselves Swifties.', 'I released Midnights.'] },
            { id: 'round_2', answer: 'Spider-Man', aliases: ['Peter Parker', 'Spiderman'], category: 'Character', difficulty: 'easy', clues: ['I live in New York City.', 'I am known for quick jokes.', 'My uncle taught me about responsibility.', 'I climb walls.', 'I swing using webs.'] },
            { id: 'round_3', answer: 'The Eiffel Tower', aliases: ['Eiffel Tower'], category: 'Landmark', difficulty: 'easy', clues: ['I was built for a world fair.', 'I am made mostly of iron.', 'I stand near the Seine.', 'I am in Paris.', 'Visitors climb me for the view.'] },
        ],
    });

    const starterChitPullGame = (): ChitPullGameContent => ({
        game_title: 'Random Chit',
        rounds: 10,
        turn_time_seconds: 30,
        safe_level: chitPullSafeLevel,
        chits: [
            'Make the face you make when someone says there is cake.',
            'Tell the room your most useless talent.',
            'Do your best slow-motion celebration.',
            'Ask someone nearby for a two-word movie review.',
            'Say one food you could eat every week.',
            'Make your most dramatic villain face.',
            'Invent a silly award for someone in the room.',
            'Give the party a five-second news headline.',
            'Do a tiny victory dance from your chair.',
            'Name a fictional character you would invite here.',
        ].map((text, index) => ({ id: `chit_${index + 1}`, text, category: (index % 2 === 0 ? 'funny_face' : 'question') as ChitPullCategory, safe_level: chitPullSafeLevel })),
    });

    const generateWhoAmI = async () => {
        if (remoteConfig.operations.kill_generate) {
            setErrorModal({ title: 'Temporarily Unavailable', message: 'Game generation is temporarily disabled. Please try again later.' });
            return;
        }
        setLoadingCopy({ title: 'Generating Clues' });
        setState('LOADING');
        try {
            const res = await fetch(apiUrl('/who-am-i/generate'), {
                method: 'POST',
                headers: apiHeaders({ 'X-Idempotency-Key': generateIdempotencyKey() }),
                body: JSON.stringify({ prompt, difficulty, num_rounds: numQuestions, clues_per_round: 5, provider }),
            });
            if (!res.ok) {
                const err = await res.json().catch(() => ({ detail: 'Failed to generate clue rounds' }));
                setErrorModal({ title: res.status === 402 ? 'Not Enough Sparks' : 'Generation Failed', message: err.detail || 'Failed to generate clue rounds.', upgradeAvailable: !hostAppMode && res.status === 402 });
                setState('WHO_AM_I_PROMPT');
                return;
            }
            const data = await res.json();
            setWhoAmIGame(data.game);
            setContentId(data.who_am_i_id);
            setTotalQuestions(data.game?.rounds?.length || numQuestions);
            window.dispatchEvent(new CustomEvent('refresh-sparks'));
            setState('WHO_AM_I_REVIEW');
        } catch {
            setErrorModal({ title: 'Connection Error', message: 'Could not reach the server. Check your internet connection.' });
            setState('WHO_AM_I_PROMPT');
        }
    };

    const importWhoAmI = async (game: WhoAmIGameContent) => {
        const res = await fetch(apiUrl('/who-am-i/import'), { method: 'POST', headers: apiHeaders(), body: JSON.stringify(game) });
        if (!res.ok) throw new Error('who_am_i_import_failed');
        const data = await res.json();
        setContentId(data.who_am_i_id);
        setWhoAmIGame(data.game);
        setTotalQuestions(data.game?.rounds?.length || game.rounds.length);
        return data.who_am_i_id as string;
    };

    const updateWhoAmIGame = async (updated: WhoAmIGameContent) => {
        setWhoAmIGame(updated);
        setTotalQuestions(updated.rounds.length);
        if (!contentId) return;
        try {
            await fetch(apiUrl(`/who-am-i/${contentId}`), { method: 'PUT', headers: apiHeaders(), body: JSON.stringify(updated) });
        } catch { /* keep local edits */ }
    };

    const generateChitPull = async () => {
        if (remoteConfig.operations.kill_generate) {
            setErrorModal({ title: 'Temporarily Unavailable', message: 'Game generation is temporarily disabled. Please try again later.' });
            return;
        }
        setLoadingCopy({ title: 'Generating Chits' });
        setState('LOADING');
        try {
            const res = await fetch(apiUrl('/chit-pull/generate'), {
                method: 'POST',
                headers: apiHeaders({ 'X-Idempotency-Key': generateIdempotencyKey() }),
                body: JSON.stringify({ prompt, difficulty, num_chits: numQuestions, safe_level: chitPullSafeLevel, provider }),
            });
            if (!res.ok) {
                const err = await res.json().catch(() => ({ detail: 'Failed to generate chits' }));
                setErrorModal({ title: res.status === 402 ? 'Not Enough Sparks' : 'Generation Failed', message: err.detail || 'Failed to generate chits.', upgradeAvailable: !hostAppMode && res.status === 402 });
                setState('CHIT_PULL_PROMPT');
                return;
            }
            const data = await res.json();
            setChitPullGame(data.game);
            setContentId(data.chit_pull_id);
            setTotalQuestions(data.game?.rounds || numQuestions);
            window.dispatchEvent(new CustomEvent('refresh-sparks'));
            setState('CHIT_PULL_REVIEW');
        } catch {
            setErrorModal({ title: 'Connection Error', message: 'Could not reach the server. Check your internet connection.' });
            setState('CHIT_PULL_PROMPT');
        }
    };

    const importChitPull = async (game: ChitPullGameContent) => {
        const res = await fetch(apiUrl('/chit-pull/import'), { method: 'POST', headers: apiHeaders(), body: JSON.stringify(game) });
        if (!res.ok) throw new Error('chit_pull_import_failed');
        const data = await res.json();
        setContentId(data.chit_pull_id);
        setChitPullGame(data.game);
        setTotalQuestions(data.game?.rounds || game.rounds);
        return data.chit_pull_id as string;
    };

    const updateChitPullGame = async (updated: ChitPullGameContent) => {
        setChitPullGame(updated);
        setTotalQuestions(updated.rounds);
        if (!contentId) return;
        try {
            await fetch(apiUrl(`/chit-pull/${contentId}`), { method: 'PUT', headers: apiHeaders(), body: JSON.stringify(updated) });
        } catch { /* keep local edits */ }
    };

    const generateImagesForQuiz = async (quizId: string, sourceQuiz: Quiz): Promise<Quiz> => {
        const questions = [...sourceQuiz.questions];
        setImageProgress(0);
        try {
            const res = await fetch(`${API_URL}/quiz/generate-images`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', ...apiHeaders() },
                body: JSON.stringify({ quiz_id: quizId }),
            });
            if (!res.ok) throw new Error('image_generation_failed');
            const data = await res.json();
            const assets = Array.isArray(data.assets) ? data.assets : [];
            const assetsByQuestion = new Map<number, { id: string; url: string; alt_text?: string }>();
            assets.forEach((asset: { question_id?: number; id: string; url: string; alt_text?: string }) => {
                if (asset.question_id && asset.url) assetsByQuestion.set(asset.question_id, asset);
            });
            questions.forEach((question, index) => {
                const asset = assetsByQuestion.get(question.id);
                if (!asset) return;
                questions[index] = {
                    ...question,
                    image_asset_id: asset.id,
                    image_url: asset.url,
                    image_alt: asset.alt_text || question.text,
                };
                setQuestionImages(prev => ({
                    ...prev,
                    [question.id]: mediaUrl(asset.url),
                }));
            });
            setImageProgress(sourceQuiz.questions.length);
            const failures = sourceQuiz.questions.length - assetsByQuestion.size;
            if (failures > 0) {
                setErrorModal({ title: 'Image Generation', message: `${failures} image(s) failed to generate. You can still play without them.` });
            }
        } catch {
            setErrorModal({ title: 'Image Generation', message: 'Images could not be generated. You can still play this quiz without them.' });
        }
        return { ...sourceQuiz, questions };
    };

    const generateImages = async () => {
        if (!sdAvailable || !contentId) return;
        setState('GENERATING_IMAGES');
        setImageProgress(0);

        if (quiz) {
            const nextQuiz = await generateImagesForQuiz(contentId, quiz);
            setQuiz(nextQuiz);
        }
        setState('REVIEW');
    };

    const updateQuiz = async (updated: Quiz) => {
        setQuiz(updated);
        setTotalQuestions(updated.questions.length);
        try {
            const res = await fetch(apiUrl(`/quiz/${contentId}`), {
                method: 'PUT',
                headers: apiHeaders(),
                body: JSON.stringify(updated),
            });
            if (res.status === 403) {
                setErrorModal({ title: 'Permission Denied', message: "You don't have permission to modify this content." });
            } else if (!res.ok) {
                console.error('Failed to save quiz update:', res.status);
            }
        } catch (err) {
            console.error('Failed to save quiz update:', err);
        }
    };

    const updateMLTGame = async (updated: MLTGame) => {
        setMltGame(updated);
        setTotalQuestions(updated.statements.length);
        try {
            const res = await fetch(apiUrl(`/mlt/${contentId}`), {
                method: 'PUT',
                headers: apiHeaders(),
                body: JSON.stringify(updated),
            });
            if (res.status === 403) {
                setErrorModal({ title: 'Permission Denied', message: "You don't have permission to modify this content." });
            } else if (!res.ok) {
                console.error('Failed to save MLT update:', res.status);
            }
        } catch (err) {
            console.error('Failed to save MLT update:', err);
        }
    };

    const updateDrawingGame = async (updated: DrawingGame) => {
        setDrawingGame(updated);
        setTotalQuestions(updated.prompts.length);
        try {
            const res = await fetch(apiUrl(`/drawing/${contentId}`), {
                method: 'PUT',
                headers: apiHeaders(),
                body: JSON.stringify(updated),
            });
            if (res.status === 403) {
                setErrorModal({ title: 'Permission Denied', message: "You don't have permission to modify this content." });
            } else if (!res.ok) {
                console.error('Failed to save DrawingGame update:', res.status);
            }
        } catch (err) {
            console.error('Failed to save DrawingGame update:', err);
        }
    };

    const connectWs = useCallback((code: string) => {
        if (wsRef.current) {
            wsRef.current.onclose = null;
            wsRef.current.close();
        }
        const clientId = `organizer-${Date.now()}`;
        const ws = new WebSocket(`${WS_URL}/ws/${code}/${clientId}?organizer=true`);
        wsRef.current = ws;
        ws.onopen = () => {
            // First-frame auth: send token as first message instead of query string
            ws.send(JSON.stringify({ type: 'AUTH', token: organizerTokenRef.current }));
        };
        ws.onmessage = handleWsMessage;
        ws.onclose = () => {
            if (wsRef.current !== ws) return;
            wsRef.current = null;
            if (!mountedRef.current) return;
            const activeStates: OrganizerState[] = ['ROOM', 'QUESTION', 'BINGO_CALLING', 'MUSICAL_CHAIRS', 'BLUFF', 'POKER', 'TWO_TRUTHS', 'STORY_CHAIN', 'COMMON_GROUND', 'FIND_SOMEONE', 'WHO_AM_I', 'CHIT_PULL', 'MAFIA', 'PARTY_QUESTS', 'SURVEY_SAYS', 'GENERIC_PROMPT', 'SIMPLE_SOCIAL', 'PHOTO_CLUE', 'ANSWER_REVEAL', 'LEADERBOARD', 'PODIUM'];
            if (roomCodeRef.current && activeStates.includes(stateRef.current)) {
                if (reconnectTimerRef.current) clearTimeout(reconnectTimerRef.current);
                reconnectTimerRef.current = setTimeout(() => connectWsRef.current(roomCodeRef.current), 2000);
            }
        };
    }, [handleWsMessage]);
    useEffect(() => { connectWsRef.current = connectWs; }, [connectWs]);

    useEffect(() => {
        const params = new URLSearchParams(window.location.search);
        if (params.get('launch_token')) return;
        if (roomCodeRef.current || stateRef.current !== 'SELECT_GAME') return;
        const saved = getSavedOrganizerSession();
        if (!saved) return;
        organizerTokenRef.current = saved.organizerToken;
        setRoomCode(saved.roomCode);
        if (saved.gameType) setGameType(saved.gameType as GameType);
        if (saved.contentId) setContentId(saved.contentId);
        if (saved.hostAppJoinUrl) setHostAppJoinUrl(saved.hostAppJoinUrl);
        if (saved.hostAppJoinLabel) setHostAppJoinLabel(saved.hostAppJoinLabel);
        if (saved.hostAppReturnUrl) setHostAppReturnUrl(saved.hostAppReturnUrl);
        if (saved.hostAppPartyHubUrl) setHostAppPartyHubUrl(saved.hostAppPartyHubUrl);
        setState('ROOM');
        connectWsRef.current(saved.roomCode);
    }, []);

    useEffect(() => {
        const params = new URLSearchParams(window.location.search);
        const launchToken = params.get('launch_token');
        if (!launchToken) return;
        let cancelled = false;
        (async () => {
            try {
                const res = await fetch(apiUrl(`/integrations/revelry/launch-token/resolve?scope=organizer&launch_token=${encodeURIComponent(launchToken)}`));
                if (!res.ok) throw new Error('Launch token rejected');
                const data = await res.json();
                if (cancelled) return;
                const display = data.launch_context?.display || {};
                const launchedGameType = data.game_type as GameType | undefined;
                const launchedContentId = String(data.content_id || '');
                setRoomCode(data.room_code);
                if (launchedGameType) setGameType(launchedGameType);
                if (launchedContentId) setContentId(launchedContentId);
                setHostAppJoinUrl(display.guest_join_url || data.launch_context?.guest_join_url || '');
                setHostAppJoinLabel(display.guest_join_label || 'Scan to join from Revelry');
                setHostAppReturnUrl(data.launch_context?.return_url || data.return_url || '');
                setHostAppPartyHubUrl(data.launch_context?.party_hub_url || '');
                organizerTokenRef.current = data.organizer_token || '';
                persistOrganizerSession({
                    roomCode: data.room_code,
                    organizerToken: data.organizer_token || '',
                    gameType: launchedGameType || gameTypeRef.current,
                    contentId: launchedContentId,
                    hostAppJoinUrl: display.guest_join_url || data.launch_context?.guest_join_url || '',
                    hostAppJoinLabel: display.guest_join_label || 'Scan to join from Revelry',
                    hostAppReturnUrl: data.launch_context?.return_url || data.return_url || '',
                    hostAppPartyHubUrl: data.launch_context?.party_hub_url || '',
                });
                setState('ROOM');
                connectWsRef.current(data.room_code);
            } catch {
                if (!cancelled) {
                    setErrorModal({ title: 'Launch Expired', message: 'This game link expired. Return to Revelry and reopen the game.', returnToHostApp: true });
                }
            }
        })();
        return () => { cancelled = true; };
    }, []);

    useEffect(() => {
        return () => {
            mountedRef.current = false;
            if (reconnectTimerRef.current) clearTimeout(reconnectTimerRef.current);
            if (checkoutPollRef.current) { clearInterval(checkoutPollRef.current); checkoutPollRef.current = null; }
            wsRef.current?.close();
            wsRef.current = null;
        };
    }, []);

    const createRoom = async (
        contentOverride?: string,
        gameTypeOverride: GameType = gameType,
        timeLimitOverride: number = timeLimit,
        runtimeConfigOverride?: Record<string, unknown>,
    ) => {
        const selectedContentId = contentOverride ?? contentId;
        const effectiveGameType = gameTypeOverride;
        const effectiveTimeLimit = timeLimitOverride;
        const resetRuntimeConfig =
            effectiveGameType === 'musical_chairs' ? musicalChairsConfig :
            effectiveGameType === 'party_quests' ? (runtimeConfigOverride || partyQuestsConfig) :
            undefined;
        // Play Again / choose another path: reuse a finished room so connected
        // players on the final-results screen receive ROOM_RESET and move forward.
        if (
            finishedRoomCanResetRef.current &&
            roomCode &&
            wsRef.current?.readyState === WebSocket.OPEN &&
            canResetFinishedRoomWithGame(effectiveGameType, selectedContentId)
        ) {
            setReviewPeekOpen(false);
            wsRef.current.send(JSON.stringify({
                type: 'RESET_ROOM',
                content_id: selectedContentId,
                time_limit: effectiveTimeLimit,
                game_type: runtimeGameType(effectiveGameType),
                drawing_auto_advance: drawingAutoAdvance,
                drawing_inter_round_seconds: 5,
                ...(resetRuntimeConfig ? { runtime_config: resetRuntimeConfig } : {}),
            }));
            return;
        }

        // First-time room creation
        try {
            finishedRoomCanResetRef.current = false;
            setReviewPeekOpen(false);
            setPlayerCount(0);
            setPlayers([]);
            const body: Record<string, unknown> = {
                time_limit: effectiveTimeLimit,
                game_type: runtimeGameType(effectiveGameType),
            };
            if (effectiveGameType === 'wmlt') {
                body.mlt_id = selectedContentId;
            } else if (effectiveGameType === 'drawing') {
                body.drawing_id = selectedContentId;
                body.drawing_auto_advance = drawingAutoAdvance;
                body.drawing_inter_round_seconds = 5;
            } else if (effectiveGameType === 'housie') {
                body.housie_id = selectedContentId;
            } else if (effectiveGameType === 'bingo') {
                body.bingo_id = selectedContentId;
            } else if (effectiveGameType === 'musical_chairs') {
                body.musical_chairs_config = musicalChairsConfig;
            } else if (effectiveGameType === 'bluff') {
                body.bluff_config = { game_title: 'Bluff' };
            } else if (effectiveGameType === 'two_truths') {
                body.two_truths_config = { game_title: 'Two Truths and a Lie' };
            } else if (effectiveGameType === 'story_chain') {
                body.story_chain_config = {
                    game_title: 'Story Chain',
                    starter_prompt: 'The birthday cake started glowing at midnight.',
                    tone: 'funny',
                    visibility_mode: 'last_sentence_only',
                    turn_time_seconds: 45,
                    sentence_max_chars: 180,
                };
            } else if (effectiveGameType === 'common_ground') {
                body.common_ground_config = {
                    game_title: 'Common Ground',
                    team_size: 3,
                    rounds: 5,
                    discussion_time_seconds: 90,
                    vote_time_seconds: 30,
                    voting_enabled: true,
                    vote_category: 'most_surprising',
                };
            } else if (effectiveGameType === 'find_someone') {
                body.find_someone_config = {
                    game_title: 'Find Someone Who',
                    layout: 'bingo_5x5_free',
                    confirmation_mode: 'tap_confirm',
                    round_time_seconds: 1800,
                    claim_patterns: ['first_line', 'four_corners', 'blackout'],
                };
            } else if (effectiveGameType === 'who_am_i') {
                if (selectedContentId) body.who_am_i_id = selectedContentId;
                else body.who_am_i_config = { game_title: 'Who Am I?' };
            } else if (effectiveGameType === 'chit_pull') {
                if (selectedContentId) body.chit_pull_id = selectedContentId;
                else body.chit_pull_config = { game_title: 'Random Chit' };
            } else if (effectiveGameType === 'mafia') {
                body.mafia_config = { game_title: 'Mafia' };
            } else if (effectiveGameType === 'party_quests') {
                body.party_quests_config = runtimeConfigOverride || partyQuestsConfig;
            } else if (effectiveGameType === 'survey_says') {
                body.survey_says_config = { game_title: 'Survey Says' };
            } else if (isGenericPromptGame(effectiveGameType)) {
                body.generic_prompt_config = { game_title: getGameModeConfig(effectiveGameType).title };
            } else if (effectiveGameType === 'would_you_rather') {
                body.would_you_rather_config = { game_title: 'Would You Rather' };
            } else if (effectiveGameType === 'never_have_i_ever') {
                body.never_have_i_ever_config = { game_title: 'Never Have I Ever' };
            } else if (effectiveGameType === 'word_association') {
                body.word_association_config = { game_title: 'Word Association' };
            } else if (effectiveGameType === 'acronym') {
                body.acronym_config = { game_title: 'Acronym Game' };
            } else if (effectiveGameType === 'photo_clue') {
                body.photo_clue_config = { game_title: 'Photo Clue' };
            } else if (effectiveGameType === 'poker') {
                body.poker_config = { game_title: 'Party Poker' };
            } else if (isQuizRuntimeGame(effectiveGameType)) {
                body.quiz_id = selectedContentId;
            }

            const res = await fetch(apiUrl('/room/create'), {
                method: 'POST',
                headers: apiHeaders(),
                body: JSON.stringify(body),
            });
            if (!res.ok) {
                const err = await res.json().catch(() => ({ detail: 'Failed to create room' }));
                setErrorModal({ title: 'Room Error', message: err.detail || `Server error (${res.status})` });
                return;
            }
            const data = await res.json();
            setRoomCode(data.room_code);
            organizerTokenRef.current = data.organizer_token || '';
            persistOrganizerSession({
                roomCode: data.room_code,
                organizerToken: data.organizer_token || '',
                gameType: effectiveGameType,
                contentId: selectedContentId,
            });
            track('room_created', { room_code: data.room_code, game_type: effectiveGameType, time_limit: effectiveTimeLimit });
            setState('ROOM');
            connectWs(data.room_code);
        } catch {
            setErrorModal({ title: 'Connection Error', message: 'Could not reach the server. Check your internet connection.' });
        }
    };

    const createHousieAndRoom = async () => {
        try {
            const res = await fetch(apiUrl('/housie/create'), {
                method: 'POST',
                headers: apiHeaders(),
                body: JSON.stringify({
                    game_title: housieTitle.trim() || 'Housie',
                    pattern_ids: housiePatterns,
                    play_mode: housiePlayMode,
                    caller_mode: housieCallerMode,
                    auto_interval_seconds: housieAutoInterval,
                    auto_pause_on_claim: housieAutoPauseOnClaim,
                }),
            });
            if (!res.ok) {
                const err = await res.json().catch(() => ({ detail: 'Failed to create Housie setup' }));
                setErrorModal({ title: 'Housie Error', message: err.detail || 'Failed to create Housie setup.' });
                return;
            }
            const data = await res.json();
            const newContentId = data.housie_id as string;
            setContentId(newContentId);
            setGameType('housie');
            setTotalQuestions(90);
            await createRoom(newContentId, 'housie');
        } catch {
            setErrorModal({ title: 'Connection Error', message: 'Could not create the Housie setup.' });
        }
    };

    const generateBingo = async () => {
        if (remoteConfig.operations.kill_generate) {
            setErrorModal({ title: 'Temporarily Unavailable', message: 'Game generation is temporarily disabled. Please try again later.' });
            return;
        }
        setLoadingCopy({ title: 'Generating Bingo' });
        setState('LOADING');
        try {
            const res = await fetch(apiUrl('/bingo/generate'), {
                method: 'POST',
                headers: apiHeaders({ 'X-Idempotency-Key': generateIdempotencyKey() }),
                body: JSON.stringify({
                    prompt,
                    difficulty,
                    num_items: Math.max(24, Math.min(60, numQuestions)),
                    provider,
                }),
            });
            if (!res.ok) {
                const err = await res.json().catch(() => ({ detail: 'Failed to generate Bingo' }));
                if (res.status === 402) {
                    setErrorModal({ title: 'Not Enough Sparks', message: 'You need more sparks! Grab a spark pack to keep playing, or come back tomorrow for your daily bonus.', upgradeAvailable: !hostAppMode });
                } else {
                    setErrorModal({ title: 'Generation Failed', message: err.detail || 'Failed to generate Bingo. Please try a different theme.' });
                }
                setState('BINGO_PROMPT');
                return;
            }
            const data = await res.json();
            setGeneratedBingoId(data.bingo_id || '');
            setBingoTitle(data.game?.game_title || 'Bingo');
            setBingoDeck(data.game?.deck || starterBingoDeck());
            setBingoFreeCenter(data.game?.free_center ?? true);
            setBingoClaimRequiresLatest(data.game?.claim_requires_latest_call ?? false);
            setGameType('bingo');
            setState('BINGO_SETUP');
            track('bingo_generated', { topic: prompt, difficulty, num_items: numQuestions, provider });
        } catch {
            setErrorModal({ title: 'Connection Error', message: 'Could not reach the server. Check your internet connection.' });
            setState('BINGO_PROMPT');
        }
    };

    const createBingoAndRoom = async () => {
        try {
            const res = await fetch(apiUrl(generatedBingoId ? `/bingo/${generatedBingoId}` : '/bingo/create'), {
                method: generatedBingoId ? 'PUT' : 'POST',
                headers: apiHeaders(),
                body: JSON.stringify({
                    game_title: bingoTitle.trim() || 'Bingo',
                    deck: bingoDeck,
                    pattern_ids: ['first_line', 'four_corners', 'blackout'],
                    free_center: bingoFreeCenter,
                    free_center_label: 'FREE',
                    caller_mode: 'manual',
                    claim_requires_latest_call: bingoClaimRequiresLatest,
                }),
            });
            if (!res.ok) {
                const err = await res.json().catch(() => ({ detail: 'Failed to create Bingo setup' }));
                setErrorModal({ title: 'Bingo Error', message: err.detail || 'Failed to create Bingo setup.' });
                return;
            }
            const data = await res.json();
            const newContentId = (data.bingo_id || generatedBingoId) as string;
            setContentId(newContentId);
            setGameType('bingo');
            setTotalQuestions((data.game?.deck?.length as number) || bingoDeck.length);
            await createRoom(newContentId, 'bingo');
        } catch {
            setErrorModal({ title: 'Connection Error', message: 'Could not create the Bingo setup.' });
        }
    };

    const startGame = () => {
        soundManager.play('gameStart');
        track('game_started', { room_code: roomCode, game_type: gameType, player_count: playerCount, num_questions: totalQuestions });
        if (gameType === 'wmlt') {
            wsRef.current?.send(JSON.stringify({ type: 'SET_SHOW_VOTES', show_votes: showVotes }));
        }
        wsRef.current?.send(JSON.stringify({ type: 'START_GAME' }));
        if (gameType !== 'housie' && gameType !== 'bingo' && gameType !== 'drawing' && gameType !== 'musical_chairs' && gameType !== 'bluff' && gameType !== 'poker' && gameType !== 'two_truths' && gameType !== 'story_chain' && gameType !== 'common_ground' && gameType !== 'find_someone' && gameType !== 'who_am_i' && gameType !== 'chit_pull' && gameType !== 'mafia' && gameType !== 'party_quests' && gameType !== 'survey_says' && gameType !== 'would_you_rather' && gameType !== 'never_have_i_ever' && gameType !== 'word_association' && gameType !== 'acronym' && gameType !== 'photo_clue') {
            wsRef.current?.send(JSON.stringify({ type: 'NEXT_QUESTION' }));
        }
    };

    const nextQuestion = () => wsRef.current?.send(JSON.stringify({ type: 'NEXT_QUESTION' }));
    const callHousieNumber = () => wsRef.current?.send(JSON.stringify({ type: 'BINGO_CALL_NEXT' }));
    const undoHousieCall = () => wsRef.current?.send(JSON.stringify({ type: 'BINGO_UNDO_LAST_CALL' }));
    const setHousieCallerModeRuntime = (mode: 'manual' | 'auto') => {
        setHousieCallerMode(mode);
        wsRef.current?.send(JSON.stringify({ type: 'BINGO_SET_CALLER_MODE', caller_mode: mode, auto_interval_seconds: housieAutoInterval }));
    };
    const pauseHousieAuto = () => wsRef.current?.send(JSON.stringify({ type: 'BINGO_PAUSE' }));
    const resumeHousieAuto = () => wsRef.current?.send(JSON.stringify({ type: 'BINGO_RESUME' }));
    const endQuiz = () => wsRef.current?.send(JSON.stringify({ type: 'END_QUIZ' }));
    const cancelCurrentGame = () => {
        const guestCopy = playerCount > 0
            ? ` ${playerCount} connected guest${playerCount === 1 ? '' : 's'} will be returned to Revelry.`
            : '';
        if (!window.confirm(`Cancel this game?${guestCopy} No results will be recorded.`)) return;
        wsRef.current?.send(JSON.stringify({ type: 'CANCEL_GAME' }));
    };
    const startMusicalChairsRound = () => wsRef.current?.send(JSON.stringify({ type: 'MC_START_ROUND' }));
    const stopMusicalChairsMusic = () => wsRef.current?.send(JSON.stringify({ type: 'MC_STOP_MUSIC' }));
    const eliminateMusicalChairsPlayer = (nickname: string) => wsRef.current?.send(JSON.stringify({ type: 'MC_ELIMINATE_PLAYER', nickname }));
    const continueBluff = () => wsRef.current?.send(JSON.stringify({ type: 'BLUFF_CONTINUE' }));
    const startTwoTruthsReveal = () => wsRef.current?.send(JSON.stringify({ type: 'TT_START_REVEAL' }));
    const nextTwoTruthsStep = () => wsRef.current?.send(JSON.stringify({ type: 'TT_NEXT_AUTHOR' }));
    const skipStoryTurn = () => wsRef.current?.send(JSON.stringify({ type: 'STORY_SKIP_TURN' }));
    const nextStoryReveal = () => wsRef.current?.send(JSON.stringify({ type: 'STORY_NEXT_REVEAL_STEP' }));
    const startCommonReveal = () => wsRef.current?.send(JSON.stringify({ type: 'COMMON_START_REVEAL' }));
    const startCommonVoting = () => wsRef.current?.send(JSON.stringify({ type: 'COMMON_START_VOTING' }));
    const scoreCommonRound = () => wsRef.current?.send(JSON.stringify({ type: 'COMMON_SCORE_ROUND' }));
    const nextCommonRound = () => wsRef.current?.send(JSON.stringify({ type: 'COMMON_NEXT_ROUND' }));
    const nextWhoAmIClue = () => wsRef.current?.send(JSON.stringify({ type: 'WHOAMI_NEXT_CLUE' }));
    const revealWhoAmIAnswer = () => wsRef.current?.send(JSON.stringify({ type: 'WHOAMI_REVEAL_ANSWER' }));
    const nextWhoAmIRound = () => wsRef.current?.send(JSON.stringify({ type: 'WHOAMI_NEXT_ROUND' }));
    const pullNextChit = () => wsRef.current?.send(JSON.stringify({ type: 'CHIT_NEXT' }));
    const completeChit = (bonus = false) => wsRef.current?.send(JSON.stringify({ type: 'CHIT_COMPLETE', bonus }));
    const skipChit = () => wsRef.current?.send(JSON.stringify({ type: 'CHIT_SKIP' }));
    const redrawChitPlayer = () => wsRef.current?.send(JSON.stringify({ type: 'CHIT_REDRAW_PLAYER' }));
    const redrawChit = () => wsRef.current?.send(JSON.stringify({ type: 'CHIT_REDRAW_CHIT' }));
    const skipMafiaTimer = () => wsRef.current?.send(JSON.stringify({ type: 'MAFIA_SKIP_TIMER' }));
    const extendMafiaTimer = () => wsRef.current?.send(JSON.stringify({ type: 'MAFIA_EXTEND_TIMER' }));
    const partyQuestsFinalCall = () => wsRef.current?.send(JSON.stringify({ type: 'QUESTS_FINAL_CALL' }));
    const partyQuestsReveal = () => wsRef.current?.send(JSON.stringify({ type: 'QUESTS_REVEAL' }));
    const revealSurveyAnswer = (answerId: string) => wsRef.current?.send(JSON.stringify({ type: 'SURVEY_REVEAL_ANSWER', answer_id: answerId }));
    const strikeSurvey = () => wsRef.current?.send(JSON.stringify({ type: 'SURVEY_STRIKE' }));
    const revealSurveyAll = () => wsRef.current?.send(JSON.stringify({ type: 'SURVEY_REVEAL_ALL' }));
    const nextSurveyRound = () => wsRef.current?.send(JSON.stringify({ type: 'SURVEY_NEXT_ROUND' }));
    const startGenericPromptVoting = () => wsRef.current?.send(JSON.stringify({ type: 'GENERIC_START_VOTING' }));
    const revealGenericPromptRound = () => wsRef.current?.send(JSON.stringify({ type: 'GENERIC_REVEAL' }));
    const nextGenericPromptRound = () => wsRef.current?.send(JSON.stringify({ type: 'GENERIC_NEXT_ROUND' }));
    const revealSimpleSocialRound = () => {
        if (gameType === 'would_you_rather') wsRef.current?.send(JSON.stringify({ type: 'WYR_REVEAL' }));
        else if (gameType === 'never_have_i_ever') wsRef.current?.send(JSON.stringify({ type: 'NHIE_REVEAL' }));
        else if (gameType === 'word_association') wsRef.current?.send(JSON.stringify({ type: 'WORD_REVEAL' }));
        else if (gameType === 'acronym') wsRef.current?.send(JSON.stringify({ type: 'ACRO_REVEAL' }));
        else if (gameType === 'odd_question') wsRef.current?.send(JSON.stringify({ type: 'ODDQ_REVEAL' }));
    };
    const nextSimpleSocialRound = () => {
        if (gameType === 'would_you_rather') wsRef.current?.send(JSON.stringify({ type: 'WYR_NEXT_ROUND' }));
        else if (gameType === 'odd_question') wsRef.current?.send(JSON.stringify({ type: 'ODDQ_NEXT_ROUND' }));
        else if (gameType === 'never_have_i_ever') wsRef.current?.send(JSON.stringify({ type: 'NHIE_NEXT_ROUND' }));
        else if (gameType === 'word_association') wsRef.current?.send(JSON.stringify({ type: 'WORD_NEXT_ROUND' }));
        else if (gameType === 'acronym') wsRef.current?.send(JSON.stringify({ type: 'ACRO_NEXT_ROUND' }));
    };
    const startAcronymVoting = () => wsRef.current?.send(JSON.stringify({ type: 'ACRO_START_VOTING' }));
    // Acronym and Impostor are the two-step simple-social games (close input, then reveal).
    const startSimpleSocialVoting = () => {
        if (gameType === 'odd_question') wsRef.current?.send(JSON.stringify({ type: 'ODDQ_START_VOTING' }));
        else startAcronymVoting();
    };
    const revealPhotoClue = () => wsRef.current?.send(JSON.stringify({ type: 'PHOTO_CLUE_REVEAL' }));
    const nextPhotoClueRound = () => wsRef.current?.send(JSON.stringify({ type: 'PHOTO_CLUE_NEXT_ROUND' }));
    const revealPokerHand = () => wsRef.current?.send(JSON.stringify({ type: 'POKER_REVEAL' }));
    const nextPokerHand = () => wsRef.current?.send(JSON.stringify({ type: 'POKER_NEXT_HAND' }));
    const createPartyQuestsAndRoom = async (config: PartyQuestSetupConfig) => {
        setPartyQuestsConfig(config);
        setGameType('party_quests');
        await createRoom(undefined, 'party_quests', defaultTimeLimitForGame('party_quests'), config as unknown as Record<string, unknown>);
    };

    const generatePartyQuests = async (request: {
        prompt: string;
        theme: string;
        numQuests: number;
        questsPerPlayer: number;
        durationMinutes: number;
        confirmationMode: PartyQuestSetupConfig['confirmation_mode'];
        provider: string;
    }): Promise<PartyQuestSetupConfig | null> => {
        if (remoteConfig.operations.kill_generate) {
            setErrorModal({ title: 'Temporarily Unavailable', message: 'Game generation is temporarily disabled. Please try again later.' });
            return null;
        }
        try {
            const res = await fetch(apiUrl('/party-quests/generate'), {
                method: 'POST',
                headers: apiHeaders({ 'X-Idempotency-Key': generateIdempotencyKey() }),
                body: JSON.stringify({
                    prompt: request.prompt,
                    theme: request.theme,
                    num_quests: request.numQuests,
                    quests_per_player: request.questsPerPlayer,
                    duration_minutes: request.durationMinutes,
                    confirmation_mode: request.confirmationMode,
                    provider: request.provider,
                }),
            });
            if (!res.ok) {
                const err = await res.json().catch(() => ({ detail: 'Failed to generate quests' }));
                setErrorModal({
                    title: res.status === 402 ? 'Not Enough Sparks' : 'Generation Failed',
                    message: err.detail || 'Failed to generate Party Quests. Please try a different theme.',
                    upgradeAvailable: !hostAppMode && res.status === 402,
                });
                return null;
            }
            const data = await res.json();
            if (!data.game) {
                setErrorModal({ title: 'Generation Failed', message: 'Failed to generate Party Quests. Please try a different theme.' });
                return null;
            }
            window.dispatchEvent(new CustomEvent('refresh-sparks'));
            track('party_quests_generated', { theme: request.theme, num_quests: request.numQuests, provider: request.provider });
            return data.game as PartyQuestSetupConfig;
        } catch {
            setErrorModal({ title: 'Connection Error', message: 'Could not reach the server. Check your internet connection.' });
            return null;
        }
    };

    const createWhoAmIAndRoom = async () => {
        try {
            const game = whoAmIGame || starterWhoAmIGame();
            const nextContentId = contentId || await importWhoAmI(game);
            setGameType('who_am_i');
            await createRoom(nextContentId, 'who_am_i', defaultTimeLimitForGame('who_am_i'));
        } catch {
            setErrorModal({ title: 'Who Am I?', message: 'Could not prepare this clue pack.' });
        }
    };

    const createChitPullAndRoom = async () => {
        try {
            const game = chitPullGame || starterChitPullGame();
            const nextContentId = contentId || await importChitPull(game);
            setGameType('chit_pull');
            await createRoom(nextContentId, 'chit_pull', defaultTimeLimitForGame('chit_pull'));
        } catch {
            setErrorModal({ title: 'Random Chit', message: 'Could not prepare this chit deck.' });
        }
    };

    const playAgain = () => {
        setCurrentQuestion(0);
        setLeaderboard([]);
        setTeamLeaderboard([]);
        setTimeRemaining(timeLimit);
        setQuestionImages({});
        setAnsweredCount(0);
        setPrompt('');
        setCurrentStatement('');
        setHousieCalled([]);
        setHousieLatest(null);
        setHousieCanUndoLastCall(false);
        setHousieWinners([]);
        setCommonGroundState(null);
        setFindSomeoneState(null);
        setWhoAmIState(null);
        setChitPullState(null);
        setMafiaState(null);
        setPartyQuestsState(null);
        setSurveySaysState(null);
        if (contentId && roomCode && wsRef.current?.readyState === WebSocket.OPEN) {
            createRoom(contentId);
            return;
        }
        chooseAnotherGame();
    };

    const chooseAnotherGame = () => {
        clearOrganizerSession();
        setQuiz(null);
        setMltGame(null);
        setDrawingGame(null);
        setContentId('');
        setQuestionImages({});
        setPrompt('');
        setCurrentStatement('');
        setHousieCalled([]);
        setHousieLatest(null);
        setHousieCanUndoLastCall(false);
        setHousieWinners([]);
        setCommonGroundState(null);
        setFindSomeoneState(null);
        setWhoAmIState(null);
        setWhoAmIGame(null);
        setChitPullState(null);
        setChitPullGame(null);
        setMafiaState(null);
        setPartyQuestsState(null);
        setSurveySaysState(null);
        if (hostAppMode) {
            returnToHostApp();
        } else {
            setState('SELECT_GAME');
        }
    };

    const returnToHostApp = () => {
        if (hostAppPartyHubUrl) {
            window.location.assign(hostAppPartyHubUrl);
            return;
        }
        if (hostAppReturnUrl) {
            returnToHostAppParent(hostAppReturnUrl);
            return;
        }
        setErrorModal({
            title: 'Back to Revelry',
            message: 'Open this party from Revelry to start another game.',
        });
    };

    const closeCurrentLobbyRoom = (nextState?: OrganizerState) => {
        flowEpochRef.current += 1;
        finishedRoomCanResetRef.current = false;
        setReviewPeekOpen(false);
        clearOrganizerSession();
        if (reconnectTimerRef.current) {
            clearTimeout(reconnectTimerRef.current);
            reconnectTimerRef.current = null;
        }
        const ws = wsRef.current;
        wsRef.current = null;
        roomCodeRef.current = '';
        if (nextState) stateRef.current = nextState;
        ws?.close();
        setRoomCode('');
        setPlayerCount(0);
        setPlayers([]);
    };

    const getLobbyEditTarget = (): OrganizerState | null => {
        if (isQuizRuntimeGame(gameType) && quiz) return 'REVIEW';
        if (gameType === 'wmlt' && mltGame) return 'MLT_REVIEW';
        if (gameType === 'drawing' && drawingGame) return 'DRAWING_REVIEW';
        if (gameType === 'who_am_i' && whoAmIGame) return 'WHO_AM_I_REVIEW';
        if (gameType === 'chit_pull' && chitPullGame) return 'CHIT_PULL_REVIEW';
        if (gameType === 'housie') return 'HOUSIE_SETUP';
        if (gameType === 'bingo' || gameType === 'baby_bingo') return 'BINGO_SETUP';
        if (gameType === 'musical_chairs') return 'MUSICAL_CHAIRS_SETUP';
        if (gameType === 'party_quests') return 'PARTY_QUESTS_SETUP';
        return null;
    };

    const getLobbyEditLabel = (): string => {
        if (isQuizRuntimeGame(gameType)) return 'Edit questions';
        if (gameType === 'wmlt' || gameType === 'drawing') return 'Edit prompts';
        if (gameType === 'who_am_i') return 'Edit clues';
        if (gameType === 'chit_pull') return 'Edit chits';
        if (gameType === 'party_quests') return 'Edit quests';
        return 'Edit setup';
    };

    const editLobbySetup = () => {
        const target = getLobbyEditTarget();
        if (!target) return;
        const confirmed = window.confirm('Editing setup will close this lobby. Connected players will need to rejoin the new room after you save changes. Continue?');
        if (!confirmed) return;
        closeCurrentLobbyRoom(target);
        setState(target);
    };

    const leaveLobbyForGameList = () => {
        if (!hostAppMode) {
            window.dispatchEvent(new CustomEvent('navigate-home'));
            return;
        }
        const confirmed = window.confirm('Going home will leave this active room. Players may be interrupted if the game is in progress. Continue?');
        if (!confirmed) return;
        closeCurrentLobbyRoom();
        setQuiz(null);
        setMltGame(null);
        setDrawingGame(null);
        setHousieCalled([]);
        setHousieLatest(null);
        setHousieCanUndoLastCall(false);
        setHousieWinners([]);
        setTwoTruthsState(null);
        setStoryChainState(null);
        setCommonGroundState(null);
        setFindSomeoneState(null);
        setWhoAmIState(null);
        setWhoAmIGame(null);
        setChitPullState(null);
        setChitPullGame(null);
        setMafiaState(null);
        setPartyQuestsState(null);
        setSurveySaysState(null);
        setGenericPromptState(null);
        setEditingPackId(undefined);
        setContentId('');
        setQuestionImages({});
        returnToHostApp();
    };

    // In Capacitor, window.location.origin is capacitor://localhost — use the web URL instead
    const isCapacitor = window.location.protocol === 'capacitor:' || window.location.hostname === 'localhost' && !window.location.port;
    const baseUrl = isCapacitor
        ? (import.meta.env.VITE_WEB_URL || 'https://games.revelryapp.me/')
        : `${window.location.origin}${import.meta.env.BASE_URL}`;
    const joinUrl = `${baseUrl}join/${roomCode}`;
    const currentQ = liveQuestion || quiz?.questions[currentQuestion - 1];
    const currentImageUrl = currentQ?.image_url ? mediaUrl(currentQ.image_url) : (currentQ ? questionImages[currentQ.id] : undefined);

    return (
        <div className="app-container">
            <div className="content-wrapper">
                {state === 'SELECT_GAME' && (
                    hostAppMode ? (
                        <div className="min-h-dvh flex flex-col items-center justify-center container-responsive safe-bottom animate-in text-center">
                            <h1 className="hero-title mb-3">Open From Revelry</h1>
                            <p className="text-[--text-tertiary] mb-6">This organizer view needs an active Revelry game launch.</p>
                            {(hostAppPartyHubUrl || hostAppReturnUrl) && (
                                <button className="btn btn-primary w-full" onClick={returnToHostApp}>
                                    Back to Revelry Games
                                </button>
                            )}
                        </div>
                    ) : (
                        <GameSelectScreen onSelect={handleGameSelect} catalog={catalog} />
                    )
                )}

                {state === 'PROMPT' && (
                    <PromptScreen
                        prompt={prompt}
                        setPrompt={setPrompt}
                        difficulty={difficulty}
                        setDifficulty={setDifficulty}
                        numQuestions={numQuestions}
                        setNumQuestions={setNumQuestions}
                        provider={provider}
                        setProvider={setProvider}
                        providers={providers}
                        imageGenerationAvailable={sdAvailable}
                        generateImages={generateQuizImages}
                        setGenerateImages={setGenerateQuizImages}
                        onGenerate={generateQuiz}
                        onCreateCustom={() => {
                            setGameType('quiz');
                            setQuiz(null);
                            setEditingPackId(undefined);
                            setState('CUSTOM_QUIZ');
                        }}
                        onOpenLibrary={openQuizLibrary}
                        onBack={() => setState('SELECT_GAME')}
                    />
                )}

                {state === 'CUSTOM_QUIZ' && (
                    <CustomQuizEditor
                        onBack={() => setState('PROMPT')}
                        onReview={importCustomQuiz}
                        onSave={saveCustomQuizPack}
                        initialQuiz={quizOrigin === 'custom' ? quiz : null}
                        packId={editingPackId}
                    />
                )}

                {state === 'QUIZ_LIBRARY' && (
                    <div className="min-h-dvh flex flex-col container-responsive safe-top safe-bottom animate-in">
                        <div className="text-center py-5">
                            <div className="hero-icon mb-3">📚</div>
                            <h1 className="hero-title">My Quizzes</h1>
                            <p className="text-[--text-tertiary] mt-2">Saved custom quiz packs</p>
                        </div>
                        <div className="space-y-3 flex-1 overflow-y-auto no-scrollbar pb-4">
                            {libraryLoading && <div className="review-question-card"><div className="p-4 text-center text-[--text-tertiary]">Loading...</div></div>}
                            {!libraryLoading && libraryPacks.length === 0 && (
                                <div className="review-question-card">
                                    <div className="p-4 text-center">
                                        <p className="font-semibold mb-2">No saved quizzes yet</p>
                                        <button
                                            className="btn btn-primary quiz-library-empty-action"
                                            onClick={() => {
                                                setQuiz(null);
                                                setEditingPackId(undefined);
                                                setState('CUSTOM_QUIZ');
                                            }}
                                        >
                                            Create Quiz
                                        </button>
                                    </div>
                                </div>
                            )}
                            {libraryPacks.map((pack) => (
                                <div key={pack.id} className="quiz-library-card">
                                    <div className="quiz-library-card__content">
                                        <div className="quiz-library-card__meta">
                                            <p className="quiz-library-card__title">{pack.title}</p>
                                            <p className="quiz-library-card__subtitle">{pack.question_count} questions</p>
                                        </div>
                                        <div className="quiz-library-actions">
                                            <button className="btn btn-primary quiz-library-action" onClick={() => void startQuizPack(pack.id)}>
                                                Start
                                            </button>
                                            <button className="btn btn-secondary quiz-library-action" onClick={() => void editQuizPack(pack.id)}>
                                                Edit
                                            </button>
                                            <button className="btn btn-secondary quiz-library-action quiz-library-action--danger" onClick={() => void deleteQuizPack(pack.id)}>
                                                Delete
                                            </button>
                                        </div>
                                    </div>
                                </div>
                            ))}
                        </div>
                        <div className="quiz-library-footer pb-4">
                            <button onClick={() => setState('PROMPT')} className="btn btn-secondary" style={{ flexShrink: 0, paddingLeft: 16, paddingRight: 16 }}>
                                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                                    <polyline points="15 18 9 12 15 6" />
                                </svg>
                            </button>
                            <button
                                className="btn btn-primary"
                                style={{ flex: 1 }}
                                onClick={() => {
                                    setQuiz(null);
                                    setEditingPackId(undefined);
                                    setState('CUSTOM_QUIZ');
                                }}
                            >
                                New Quiz
                            </button>
                        </div>
                    </div>
                )}

                {state === 'QUIZ_VARIANT_PROMPT' && (
                    <QuizVariantPromptScreen
                        config={getGameModeConfig(gameType)}
                        prompt={prompt}
                        setPrompt={setPrompt}
                        difficulty={difficulty}
                        setDifficulty={setDifficulty}
                        numQuestions={numQuestions}
                        setNumQuestions={setNumQuestions}
                        provider={provider}
                        setProvider={setProvider}
                        providers={providers}
                        onGenerate={generateQuiz}
                        onBack={() => setState('SELECT_GAME')}
                    />
                )}

                {state === 'MLT_PROMPT' && (
                    <MLTPromptScreen
                        prompt={prompt}
                        setPrompt={setPrompt}
                        difficulty={difficulty}
                        setDifficulty={setDifficulty}
                        numRounds={numQuestions}
                        setNumRounds={setNumQuestions}
                        provider={provider}
                        setProvider={setProvider}
                        providers={providers}
                        onGenerate={generateMLT}
                        onBack={() => setState('SELECT_GAME')}
                    />
                )}

                {state === 'DRAWING_PROMPT' && (
                    <DrawingPromptScreen
                        prompt={prompt}
                        setPrompt={setPrompt}
                        difficulty={difficulty}
                        setDifficulty={setDifficulty}
                        numPrompts={numQuestions}
                        setNumPrompts={setNumQuestions}
                        provider={provider}
                        setProvider={setProvider}
                        providers={providers}
                        onGenerate={generateDrawing}
                        onBack={() => setState('SELECT_GAME')}
                    />
                )}

                {state === 'WHO_AM_I_PROMPT' && (
                    <WhoAmIPromptScreen
                        prompt={prompt}
                        setPrompt={setPrompt}
                        difficulty={difficulty}
                        setDifficulty={setDifficulty}
                        numRounds={numQuestions}
                        setNumRounds={setNumQuestions}
                        provider={provider}
                        setProvider={setProvider}
                        providers={providers}
                        onGenerate={generateWhoAmI}
                        onCreateCustom={() => {
                            setContentId('');
                            setWhoAmIGame(starterWhoAmIGame());
                            setState('WHO_AM_I_REVIEW');
                        }}
                        onQuickStart={() => {
                            setContentId('');
                            void createRoom(undefined, 'who_am_i', defaultTimeLimitForGame('who_am_i'));
                        }}
                        onBack={() => setState('SELECT_GAME')}
                    />
                )}

                {state === 'WHO_AM_I_REVIEW' && whoAmIGame && (
                    <WhoAmIReviewScreen
                        game={whoAmIGame}
                        onUpdateGame={updateWhoAmIGame}
                        onCreateRoom={createWhoAmIAndRoom}
                        onBack={() => setState('WHO_AM_I_PROMPT')}
                    />
                )}

                {state === 'CHIT_PULL_PROMPT' && (
                    <ChitPullPromptScreen
                        prompt={prompt}
                        setPrompt={setPrompt}
                        difficulty={difficulty}
                        setDifficulty={setDifficulty}
                        numChits={numQuestions}
                        setNumChits={setNumQuestions}
                        safeLevel={chitPullSafeLevel}
                        setSafeLevel={setChitPullSafeLevel}
                        provider={provider}
                        setProvider={setProvider}
                        providers={providers}
                        onGenerate={generateChitPull}
                        onCreateCustom={() => {
                            setContentId('');
                            setChitPullGame(starterChitPullGame());
                            setState('CHIT_PULL_REVIEW');
                        }}
                        onQuickStart={() => {
                            setContentId('');
                            void createRoom(undefined, 'chit_pull', defaultTimeLimitForGame('chit_pull'));
                        }}
                        onBack={() => setState('SELECT_GAME')}
                    />
                )}

                {state === 'CHIT_PULL_REVIEW' && chitPullGame && (
                    <ChitPullReviewScreen
                        game={chitPullGame}
                        onUpdateGame={updateChitPullGame}
                        onCreateRoom={createChitPullAndRoom}
                        onBack={() => setState('CHIT_PULL_PROMPT')}
                    />
                )}

                {state === 'HOUSIE_SETUP' && (
                    <HousieSetupScreen
                        title={housieTitle}
                        setTitle={setHousieTitle}
                        playMode={housiePlayMode}
                        setPlayMode={setHousiePlayMode}
                        selectedPatterns={housiePatterns}
                        setSelectedPatterns={setHousiePatterns}
                        callerMode={housieCallerMode}
                        setCallerMode={setHousieCallerMode}
                        autoIntervalSeconds={housieAutoInterval}
                        setAutoIntervalSeconds={setHousieAutoInterval}
                        autoPauseOnClaim={housieAutoPauseOnClaim}
                        setAutoPauseOnClaim={setHousieAutoPauseOnClaim}
                        onCreateRoom={createHousieAndRoom}
                        onBack={() => setState('SELECT_GAME')}
                    />
                )}

                {state === 'BINGO_PROMPT' && (
                    <BingoPromptScreen
                        prompt={prompt}
                        setPrompt={setPrompt}
                        difficulty={difficulty}
                        setDifficulty={setDifficulty}
                        numItems={numQuestions}
                        setNumItems={setNumQuestions}
                        provider={provider}
                        setProvider={setProvider}
                        providers={providers}
                        onGenerate={generateBingo}
                        onCreateCustom={() => {
                            setGeneratedBingoId('');
                            setBingoTitle('Bingo');
                            setBingoDeck(starterBingoDeck());
                            setBingoFreeCenter(true);
                            setBingoClaimRequiresLatest(false);
                            setState('BINGO_SETUP');
                        }}
                        onBack={() => setState('SELECT_GAME')}
                    />
                )}

                {state === 'BINGO_SETUP' && (
                    <BingoSetupScreen
                        title={bingoTitle}
                        setTitle={setBingoTitle}
                        deck={bingoDeck}
                        setDeck={setBingoDeck}
                        freeCenter={bingoFreeCenter}
                        setFreeCenter={setBingoFreeCenter}
                        claimRequiresLatest={bingoClaimRequiresLatest}
                        setClaimRequiresLatest={setBingoClaimRequiresLatest}
                        onCreateRoom={createBingoAndRoom}
                        onBack={() => setState(generatedBingoId ? 'BINGO_PROMPT' : 'SELECT_GAME')}
                    />
                )}

                {state === 'MUSICAL_CHAIRS_SETUP' && (
                    <MusicalChairsSetupScreen
                        config={musicalChairsConfig}
                        setConfig={setMusicalChairsConfig}
                        onCreateRoom={() => {
                            setGameType('musical_chairs');
                            void createRoom(undefined, 'musical_chairs', defaultTimeLimitForGame('musical_chairs'));
                        }}
                        onBack={() => setState('SELECT_GAME')}
                    />
                )}

                {state === 'PARTY_QUESTS_SETUP' && (
                    <PartyQuestsSetupScreen
                        initialConfig={partyQuestsConfig}
                        provider={provider}
                        setProvider={setProvider}
                        providers={providers}
                        onGenerateQuests={generatePartyQuests}
                        onCreate={(config) => void createPartyQuestsAndRoom(config)}
                        onBack={() => setState('SELECT_GAME')}
                    />
                )}

                {state === 'LOADING' && <LoadingScreen title={loadingCopy.title} messages={loadingCopy.messages} />}

                {state === 'REVIEW' && quiz && (
                    <ReviewScreen
                        quiz={quiz}
                        timeLimit={timeLimit}
                        setTimeLimit={setTimeLimit}
                        sdAvailable={sdAvailable}
                        questionImages={questionImages}
                        onGenerateImages={generateImages}
                        onCreateRoom={createRoom}
                        onUpdateQuiz={updateQuiz}
                        onBack={() => setState(quizOrigin === 'custom' ? 'CUSTOM_QUIZ' : gameType === 'quiz' ? 'PROMPT' : 'QUIZ_VARIANT_PROMPT')}
                    />
                )}

                {state === 'MLT_REVIEW' && mltGame && (
                    <MLTReviewScreen
                        game={mltGame}
                        timeLimit={timeLimit}
                        setTimeLimit={setTimeLimit}
                        showVotes={showVotes}
                        setShowVotes={setShowVotes}
                        onCreateRoom={createRoom}
                        onUpdateGame={updateMLTGame}
                        onBack={() => setState('MLT_PROMPT')}
                    />
                )}

                {state === 'DRAWING_REVIEW' && drawingGame && (
                    <DrawingReviewScreen
                        game={drawingGame}
                        timeLimit={timeLimit}
                        setTimeLimit={setTimeLimit}
                        autoAdvance={drawingAutoAdvance}
                        setAutoAdvance={setDrawingAutoAdvance}
                        onCreateRoom={createRoom}
                        onUpdateGame={updateDrawingGame}
                        onBack={() => setState('DRAWING_PROMPT')}
                    />
                )}

                {state === 'GENERATING_IMAGES' && quiz && (
                    <ImageGenerationScreen quiz={quiz} imageProgress={imageProgress} />
                )}

                {state === 'ROOM' && (
                    <LobbyScreen
                        roomCode={roomCode}
                        joinUrl={joinUrl}
                        gameTitle={getGameModeConfig(gameType).title}
                        playerCount={playerCount}
                        players={players}
                        minPlayers={getMinPlayers(gameType)}
                        locked={roomLocked}
                        hostAppMode={hostAppMode}
                        hostAppJoinUrl={hostAppJoinUrl}
                        hostAppJoinLabel={hostAppJoinLabel}
                        onStartGame={startGame}
                        onToggleLock={() => wsRef.current?.send(JSON.stringify({ type: 'TOGGLE_LOCK' }))}
                        onRemoveOfflinePlayers={() => wsRef.current?.send(JSON.stringify({ type: 'REMOVE_OFFLINE_PLAYERS' }))}
                        onCancelGame={hostAppMode ? cancelCurrentGame : undefined}
                        onBackToGames={leaveLobbyForGameList}
                        onReviewContent={isQuizRuntimeGame(gameType) && quiz ? () => setReviewPeekOpen(true) : undefined}
                        onEditSetup={!hostAppMode && getLobbyEditTarget() && !(isQuizRuntimeGame(gameType) && quiz) ? editLobbySetup : undefined}
                        editSetupLabel={getLobbyEditLabel()}
                        onShowRules={() => setActiveRules(rulesForGame(gameType, catalog))}
                    />
                )}
                {state === 'ROOM' && reviewPeekOpen && quiz && (
                    <div className="review-peek-backdrop" onClick={() => setReviewPeekOpen(false)}>
                        <div className="review-peek" onClick={(e) => e.stopPropagation()}>
                            <div className="review-peek-header">
                                <h2>{quiz.quiz_title || 'Questions'}</h2>
                                <button type="button" className="btn btn-secondary" onClick={() => setReviewPeekOpen(false)}>Close</button>
                            </div>
                            <p className="review-peek-sub">{quiz.questions.length} question{quiz.questions.length === 1 ? '' : 's'} · read-only preview</p>
                            <div className="review-peek-list no-scrollbar">
                                {quiz.questions.map((q, i) => (
                                    <div key={q.id ?? i} className="review-peek-q">
                                        <p className="review-peek-q-text"><strong>{i + 1}.</strong> {q.text}</p>
                                        <ul>
                                            {q.options.map((opt, oi) => (
                                                <li key={oi} className={oi === q.answer_index ? 'review-peek-correct' : ''}>
                                                    {String.fromCharCode(65 + oi)}. {opt}{oi === q.answer_index ? ' ✓' : ''}
                                                </li>
                                            ))}
                                        </ul>
                                    </div>
                                ))}
                            </div>
                            {!hostAppMode && getLobbyEditTarget() && (
                                <button type="button" className="btn btn-secondary review-peek-edit" onClick={() => { setReviewPeekOpen(false); editLobbySetup(); }}>
                                    Edit questions (restarts the room)
                                </button>
                            )}
                        </div>
                    </div>
                )}

                {state === 'MUSICAL_CHAIRS' && (
                    <MusicalChairsGameScreen
                        state={musicalChairsState}
                        onStartRound={startMusicalChairsRound}
                        onStopMusic={stopMusicalChairsMusic}
                        onEliminatePlayer={eliminateMusicalChairsPlayer}
                        onEndGame={endQuiz}
                    />
                )}

                {state === 'BLUFF' && (
                    <BluffTable
                        state={bluffState}
                        controls="host"
                        onContinue={continueBluff}
                        onEndGame={endQuiz}
                    />
                )}

                {state === 'POKER' && (
                    <PokerGame
                        state={pokerState}
                        role="host"
                        leaderboard={leaderboard}
                        onReveal={revealPokerHand}
                        onNextHand={nextPokerHand}
                        onEndGame={endQuiz}
                    />
                )}

                {state === 'TWO_TRUTHS' && (
                    <TwoTruthsGame
                        state={twoTruthsState}
                        controls="host"
                        onStartReveal={startTwoTruthsReveal}
                        onNext={nextTwoTruthsStep}
                        onEndGame={endQuiz}
                    />
                )}

                {state === 'STORY_CHAIN' && (
                    <StoryChainGame
                        state={storyChainState}
                        controls="host"
                        onSkipTurn={skipStoryTurn}
                        onNextReveal={nextStoryReveal}
                        onEndGame={endQuiz}
                    />
                )}

                {state === 'COMMON_GROUND' && (
                    <CommonGroundGame
                        state={commonGroundState}
                        controls="host"
                        onStartReveal={startCommonReveal}
                        onStartVoting={startCommonVoting}
                        onScoreRound={scoreCommonRound}
                        onNextRound={nextCommonRound}
                        onEndGame={endQuiz}
                    />
                )}

                {state === 'FIND_SOMEONE' && (
                    <FindSomeoneGame
                        state={findSomeoneState}
                        controls="host"
                        onEndGame={endQuiz}
                    />
                )}

                {state === 'WHO_AM_I' && (
                    <WhoAmIGame
                        state={whoAmIState}
                        controls="host"
                        onNextClue={nextWhoAmIClue}
                        onRevealAnswer={revealWhoAmIAnswer}
                        onNextRound={nextWhoAmIRound}
                        onEndGame={endQuiz}
                    />
                )}

                {state === 'CHIT_PULL' && (
                    <ChitPullGame
                        state={chitPullState}
                        controls="host"
                        onNext={pullNextChit}
                        onComplete={completeChit}
                        onSkip={skipChit}
                        onRedrawPlayer={redrawChitPlayer}
                        onRedrawChit={redrawChit}
                        onEndGame={endQuiz}
                    />
                )}

                {state === 'MAFIA' && (
                    <MafiaGame
                        state={mafiaState}
                        controls="host"
                        onSkipTimer={skipMafiaTimer}
                        onExtendTimer={extendMafiaTimer}
                        onEndGame={endQuiz}
                    />
                )}

                {state === 'PARTY_QUESTS' && (
                    <PartyQuestsGame
                        state={partyQuestsState}
                        controls="host"
                        onFinalCall={partyQuestsFinalCall}
                        onReveal={partyQuestsReveal}
                        onEndGame={endQuiz}
                        onCancelGame={hostAppMode ? cancelCurrentGame : undefined}
                    />
                )}

                {state === 'SURVEY_SAYS' && (
                    <SurveySaysGame
                        state={surveySaysState}
                        controls="host"
                        onRevealAnswer={revealSurveyAnswer}
                        onStrike={strikeSurvey}
                        onRevealAll={revealSurveyAll}
                        onNextRound={nextSurveyRound}
                        onEndGame={endQuiz}
                    />
                )}

                {state === 'GENERIC_PROMPT' && (
                    <GenericPromptGame
                        gameType={gameType as GenericPromptGameType}
                        state={genericPromptState}
                        players={players}
                        controls="host"
                        onStartVoting={startGenericPromptVoting}
                        onReveal={revealGenericPromptRound}
                        onNextRound={nextGenericPromptRound}
                        onEndGame={endQuiz}
                    />
                )}

                {state === 'SIMPLE_SOCIAL' && (
                    <SimpleSocialGame
                        gameType={gameType as SimpleSocialGameType}
                        state={simpleSocialState}
                        players={players}
                        controls="host"
                        onReveal={revealSimpleSocialRound}
                        onStartVoting={startSimpleSocialVoting}
                        onNextRound={nextSimpleSocialRound}
                        onEndGame={endQuiz}
                    />
                )}

                {state === 'PHOTO_CLUE' && (
                    <PhotoClueGame
                        state={photoClueState || { phase: 'PHOTO_WAITING_FOR_PHOTO', current_round_index: 0, round_count: 1 }}
                        role="organizer"
                        leaderboard={leaderboard}
                        onReveal={revealPhotoClue}
                        onNextRound={nextPhotoClueRound}
                    />
                )}

                {state === 'QUESTION' && (
                    showBonusSplash ? (
                        <BonusSplash onComplete={() => setShowBonusSplash(false)} />
                    ) : gameType === 'wmlt' ? (
                        <GameQuestionScreen
                            questionNumber={currentQuestion}
                            totalQuestions={totalQuestions}
                            timeRemaining={timeRemaining}
                            timeLimit={timeLimit}
                            answeredCount={answeredCount}
                            playerCount={playerCount}
                            isBonus={isBonus}
                            onNextQuestion={nextQuestion}
                            onEndQuiz={endQuiz}
                            gameType="wmlt"
                            statementText={currentStatement}
                        />
                    ) : gameType === 'drawing' ? (
                        <GameQuestionScreen
                            questionNumber={currentQuestion}
                            totalQuestions={totalQuestions}
                            timeRemaining={timeRemaining}
                            timeLimit={timeLimit}
                            answeredCount={answeredCount}
                            playerCount={Math.max(0, playerCount - 1)}
                            isBonus={false}
                            onNextQuestion={nextQuestion}
                            onEndQuiz={endQuiz}
                            gameType="drawing"
                            statementText={[
                                drawingActiveDrawer ? `Drawer: ${drawingActiveDrawer}` : 'Drawing round in progress',
                                drawingClue ? `Clue: ${drawingClue}` : '',
                            ].filter(Boolean).join('\n')}
                        />
                    ) : currentQ ? (
                        <GameQuestionScreen
                            question={currentQ}
                            questionNumber={currentQuestion}
                            totalQuestions={totalQuestions}
                            timeRemaining={timeRemaining}
                            timeLimit={timeLimit}
                            imageUrl={currentImageUrl}
                            answeredCount={answeredCount}
                            playerCount={playerCount}
                            isBonus={isBonus}
                            onNextQuestion={nextQuestion}
                            onEndQuiz={endQuiz}
                        />
                    ) : null
                )}

                {state === 'BINGO_CALLING' && (
                    <div className="housie-caller-screen container-responsive safe-top safe-bottom animate-in">
                        {housieCallFlash && (gameType === 'bingo'
                            ? <BingoCallOverlay key={housieCallFlash.key} item={housieCallFlash.item} />
                            : <div key={housieCallFlash.key} className="housie-call-overlay">{housieCallFlash.item.display}</div>)}
                        {housieAnnouncement && (
                            <div key={housieAnnouncement.key} className="housie-win-overlay">
                                <div className="housie-confetti" aria-hidden="true">{Array.from({ length: 18 }, (_, index) => <i key={index} />)}</div>
                                <p>{housieAnnouncement.text}</p>
                            </div>
                        )}
                        <div className="housie-runtime-header">
                            <p>{gameType === 'bingo' ? 'Bingo caller' : 'Housie caller'}</p>
                            <h1 className="hero-title">{housieLatest ? housieLatest.display : 'Ready to call'}</h1>
                            <span>
                                {gameType === 'bingo'
                                    ? `${housieCalled.length} items called · Custom board · Manual`
                                    : housieTerminalClaimPending
                                        ? `${housieCalled.length} of 90 numbers called · Final claims open`
                                        : `${housieCalled.length} of 90 numbers called · ${housiePlayMode === 'pro' ? 'Pro' : 'Beginner'} · ${housieCallerMode === 'auto' ? `Auto ${housieAutoStatus}` : 'Manual'}`}
                            </span>
                        </div>
                        <div className="housie-runtime-panel housie-call-controls">
                            <div>
                                <p className="housie-muted-copy">Caller controls</p>
                                <h2>{housieTerminalClaimPending ? 'Final claims open' : housieCallerMode === 'auto' ? `Auto every ${housieAutoInterval}s` : 'Manual calling'}</h2>
                            </div>
                            <div className="housie-caller-actions">
                                <button type="button" onClick={undoHousieCall} disabled={!housieCanUndoLastCall} className="btn btn-secondary">Undo</button>
                                <button type="button" onClick={callHousieNumber} disabled={housieTerminalClaimPending} className="btn btn-primary btn-glow">Call Next</button>
                                {housieCallerMode === 'auto' && housieAutoStatus === 'running' ? (
                                    <button type="button" onClick={pauseHousieAuto} className="btn btn-secondary">Pause Auto</button>
                                ) : (
                                    <button type="button" onClick={() => setHousieCallerModeRuntime('auto')} disabled={housieTerminalClaimPending} className="btn btn-secondary">Start Auto</button>
                                )}
                                {housieCallerMode === 'auto' && housieAutoStatus === 'paused' && (
                                    <button type="button" onClick={resumeHousieAuto} className="btn btn-secondary">Resume</button>
                                )}
                                {housieCallerMode === 'auto' && (
                                    <button type="button" onClick={() => setHousieCallerModeRuntime('manual')} className="btn btn-secondary">Manual</button>
                                )}
                            </div>
                        </div>
                        <div className="housie-runtime-panel">
                            {gameType === 'bingo' ? (
                                <BingoCalledList items={housieCalled} />
                            ) : (
                                <HousieCalledBoard
                                    calledValues={new Set(housieCalled.map((item) => String(item.value)))}
                                    latestValue={housieLatest?.value}
                                />
                            )}
                        </div>
                        <div className="housie-runtime-panel">
                            <h2>Prizes</h2>
                            <HousieWinners winners={housieWinners} />
                        </div>
                        <div className="housie-caller-actions">
                            <button type="button" onClick={endQuiz} className="btn btn-secondary">End Game</button>
                        </div>
                    </div>
                )}

                {state === 'ANSWER_REVEAL' && currentQ && (
                    <GameQuestionScreen
                        question={currentQ}
                        questionNumber={currentQuestion}
                        totalQuestions={totalQuestions}
                        timeRemaining={0}
                        timeLimit={timeLimit}
                        imageUrl={currentImageUrl}
                        isBonus={isBonus}
                        revealAnswerIndex={revealedAnswer}
                        onContinue={() => setState('LEADERBOARD')}
                        onEndQuiz={endQuiz}
                    />
                )}

                {state === 'LEADERBOARD' && (
                    gameType === 'drawing' && drawingRoundResult ? (
                        <div className="min-h-dvh flex flex-col container-responsive safe-top safe-bottom animate-in">
                            <div className="flex-1 flex flex-col justify-center text-center">
                                <div className="hero-icon mb-4">🎨</div>
                                <p className="text-[--text-tertiary] text-sm mb-2">Round {currentQuestion} of {totalQuestions}</p>
                                <h2 className="hero-title mb-4">{drawingRoundResult.prompt}</h2>
                                <p className="text-[--text-secondary] mb-2">Drawer: <strong>{drawingRoundResult.drawer}</strong></p>
                                <p className="text-[--text-secondary]">
                                    {drawingRoundResult.correct_guessers.length
                                        ? `${drawingRoundResult.correct_guessers.join(', ')} guessed it`
                                        : 'No correct guesses this round'}
                                </p>
                                {drawingNextRoundCountdown !== null && (
                                    <p className="text-[--accent-primary] font-bold mt-4">
                                        {currentQuestion >= totalQuestions ? 'Final results' : 'Next round'} in {drawingNextRoundCountdown}s
                                    </p>
                                )}
                            </div>
                            <div className="pb-4 space-y-2">
                                <button onClick={nextQuestion} className="btn btn-primary btn-glow w-full">
                                    {currentQuestion >= totalQuestions ? 'Show Results' : 'Next Round'}
                                </button>
                                <button onClick={endQuiz} className="btn btn-secondary w-full">
                                    End Game
                                </button>
                            </div>
                        </div>
                    ) : gameType === 'wmlt' && wmltRoundResult ? (
                        <div className="min-h-dvh flex flex-col container-responsive safe-top safe-bottom animate-in">
                            <div className="flex-1 flex flex-col py-6">
                                <div className="text-center mb-4">
                                    <p className="text-[--text-tertiary] text-sm mb-2">Round {currentQuestion} of {totalQuestions}</p>
                                    <div style={{ fontSize: '2.5rem', marginBottom: 4 }}>👑</div>
                                    {wmltRoundResult.winners.length > 1 ? (
                                        <>
                                            <h2 className="text-2xl font-extrabold">{wmltRoundResult.winners.join(' & ')}</h2>
                                            <p className="text-[--text-secondary] text-sm mt-1">Tied with {wmltRoundResult.round_podium[0]?.vote_count || 0} votes each!</p>
                                        </>
                                    ) : (
                                        <>
                                            <h2 className="text-2xl font-extrabold">{wmltRoundResult.winner}</h2>
                                            {wmltRoundResult.unanimous && <p className="text-[--accent-success] font-semibold mt-1">Unanimous!</p>}
                                        </>
                                    )}
                                    <p className="text-xs text-[--text-tertiary] mt-2 italic">"{wmltRoundResult.statement}"</p>
                                </div>

                                <div className="flex-1">
                                    <LeaderboardBarChart
                                        leaderboard={wmltRoundResult.round_podium.map(p => ({
                                            nickname: p.nickname,
                                            score: p.vote_count,
                                            avatar: p.avatar,
                                        }))}
                                        maxEntries={8}
                                        size="compact"
                                    />
                                </div>
                            </div>

                            <div className="pb-4 space-y-2">
                                <button onClick={nextQuestion} className="btn btn-primary btn-glow w-full">
                                    {currentQuestion >= totalQuestions ? 'Show Results' : 'Next Question'}
                                </button>
                                <button onClick={endQuiz} className="btn btn-secondary w-full">
                                    End Game
                                </button>
                            </div>
                        </div>
                    ) : (
                        <LeaderboardScreen
                            leaderboard={leaderboard}
                            questionNumber={currentQuestion}
                            totalQuestions={totalQuestions}
                            onNextQuestion={nextQuestion}
                            onEndQuiz={endQuiz}
                        />
                    )
                )}

                {state === 'PODIUM' && (
                    <PodiumScreen
                        leaderboard={leaderboard}
                        teamLeaderboard={teamLeaderboard}
                        superlatives={superlatives}
                        onPlayAgain={playAgain}
                        onChooseAnotherGame={chooseAnotherGame}
                        onShareResults={hostAppMode ? undefined : () => shareGameResult(gameTypeRef.current, leaderboard)}
                        playAgainLabel="Play Again"
                        chooseAnotherLabel={hostAppMode ? 'Back to Revelry Games' : 'Choose Another Game'}
                    />
                )}
            </div>

            <GameRulesModal rules={activeRules} onClose={() => setActiveRules(null)} />

            {errorModal && (
                <ErrorModal
                    title={errorModal.title}
                    message={errorModal.message}
                    upgradeAvailable={!hostAppMode && errorModal.upgradeAvailable}
                    onDismiss={() => {
                        const shouldReturn = errorModal.returnToHostApp;
                        setErrorModal(null);
                        if (hostAppMode && shouldReturn) returnToHostApp();
                    }}
                    onUpgrade={() => {
                        if (hostAppMode) return;
                        track('upgrade_clicked', { source: 'error_modal' });
                        setErrorModal(null);
                        if (remoteConfig.operations.kill_payments) {
                            setErrorModal({ title: 'Payments Unavailable', message: 'Payments are temporarily disabled. Please try again later.' });
                            return;
                        }
                        setShowPurchase(true);
                    }}
                />
            )}
            {showPurchase && (
                <SparkPurchaseModal
                    onClose={() => setShowPurchase(false)}
                    onSuccess={(added) => {
                        setShowPurchase(false);
                        window.dispatchEvent(new CustomEvent('refresh-sparks'));
                        setErrorModal(added != null
                            ? { title: 'Sparks Added!', message: `+${added} sparks added to your balance. Enjoy!` }
                            : { title: 'Purchase Complete', message: 'Your sparks will appear in your balance shortly.' });
                    }}
                />
            )}
        </div>
    );
}
