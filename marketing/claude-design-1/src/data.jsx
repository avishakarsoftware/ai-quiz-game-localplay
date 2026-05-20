// LocalPlay Redesign — Game data, player roster, simulation state machine.
// Globals exposed at the bottom of the file.

// Full avatar palette mirrors src/types.ts AVATAR_EMOJIS in the real codebase.
const AVATAR_EMOJIS = [
  '🐶','🐱','🐸','🦊','🐻','🐼','🐨','🦁',
  '🐯','🐮','🐷','🐵','🐰','🐔','🦋','🐙',
  '🦈','🐢','🦜','🐝','🦩','🐺','🦉','🐧',
  '🍕','🌮','🍩','🍦','🍔','🧁','🍿','🥑',
  '🎸','🚀','⚡','🔥','🌈','🎯','💎','🎲',
  '🦄','👾','🤖','🎃','👻','🧠','🦖','🐉',
  '🏀','⚽','🎱','🛹','🎭','🎨','🧊','💫',
];

// Players use their picked emoji from AVATAR_EMOJIS as the avatar (no monograms).
const PLAYERS = [
  { name: 'Mira',  avatar: '🦊', hue: 12  },
  { name: 'Theo',  avatar: '🐙', hue: 188 },
  { name: 'Jules', avatar: '🦄', hue: 320 },
  { name: 'Asha',  avatar: '🥑', hue: 70  },
  { name: 'Otto',  avatar: '👾', hue: 250 },
  { name: 'Cleo',  avatar: '🍩', hue: 32  },
  { name: 'Wren',  avatar: '🌈', hue: 150 },
  { name: 'Sage',  avatar: '🧠', hue: 280 },
];

const GAMES = [
  {
    id: 'quiz',
    name: 'Trivia',
    tagline: 'Bring-your-own-topic AI quiz',
    rounds: '10 questions',
    pace: '6–8 min',
    players: '2–30',
    chapter: 'I',
    glyph: 'q',
  },
  {
    id: 'wmlt',
    name: 'Most Likely To',
    tagline: 'Vote on each other, no wrong answers',
    rounds: '8 rounds',
    pace: '4–6 min',
    players: '3–12',
    chapter: 'II',
    glyph: 'm',
  },
  {
    id: 'pictionary',
    name: 'Pictionary',
    tagline: 'Draw on your phone, group guesses',
    rounds: '6 rounds',
    pace: '8–12 min',
    players: '3–12',
    chapter: 'III',
    glyph: 'p',
    badge: 'New',
  },
  {
    id: 'taboo',
    name: 'Taboo',
    tagline: 'Get your team to say the word — without saying it',
    rounds: '5 min sprint',
    pace: '5 min',
    players: '4–10',
    chapter: 'IV',
    glyph: 't',
    badge: 'New',
  },
  {
    id: 'whispers',
    name: 'Whispers',
    tagline: 'Pass a phrase down the chain. Watch it mutate.',
    rounds: '4 phrases',
    pace: '6 min',
    players: '4–12',
    chapter: 'V',
    glyph: 'w',
    badge: 'New',
  },
  {
    id: 'fibbage',
    name: 'Bluff',
    tagline: 'Write a fake answer. Fool everyone.',
    rounds: '8 rounds',
    pace: '10 min',
    players: '3–12',
    chapter: 'VI',
    glyph: 'b',
    badge: 'Soon',
  },
];

// Sample question used by Quiz simulation
const QUIZ_QUESTION = {
  number: 3,
  total: 10,
  topic: 'Renaissance Italy',
  text: 'Which Florentine artist sculpted the marble David that stands in the Galleria dell\u2019Accademia?',
  options: [
    { glyph: 'A', text: 'Donatello' },
    { glyph: 'B', text: 'Michelangelo' },
    { glyph: 'C', text: 'Bernini' },
    { glyph: 'D', text: 'Verrocchio' },
  ],
  correct: 1,
};

const WMLT_STATEMENT = {
  number: 2,
  total: 8,
  text: 'Most likely to bring a homemade dessert to a dinner party.',
};

const PICTIONARY_WORD = {
  number: 2,
  total: 6,
  drawer: 'Jules',
  prompt: 'Lighthouse',
};

const TABOO_CARD = {
  number: 4,
  total: 12,
  word: 'TELESCOPE',
  forbidden: ['stars', 'lens', 'see', 'far', 'astronomy'],
};

const WHISPERS_PHRASE = {
  number: 2,
  total: 4,
  origin: 'Mira',
  chain: [
    { player: 'Mira',  text: 'A small penguin in a velvet tuxedo orders espresso every Tuesday.' },
    { player: 'Theo',  text: 'A tiny penguin wearing velvet drinks espresso on Tuesdays.' },
    { player: 'Asha',  text: 'Small penguin, velvet jacket. Tuesday espresso ritual.' },
    { player: 'Otto',  text: 'Penguin in jacket likes coffee on Tuesdays.' },
    { player: 'Cleo',  text: 'A bird in a jacket drinks coffee.' },
  ],
};

// Final-podium scoreboard. Same numbers regardless of game (for demo).
const FINAL_SCORES = [
  { name: 'Asha',  score: 8420, delta: '+1' },
  { name: 'Mira',  score: 7910, delta: '0' },
  { name: 'Theo',  score: 7180, delta: '+2' },
  { name: 'Otto',  score: 6510, delta: '-1' },
  { name: 'Jules', score: 5900, delta: '-2' },
  { name: 'Cleo',  score: 5240, delta: '0' },
  { name: 'Wren',  score: 4820, delta: '+1' },
  { name: 'Sage',  score: 3950, delta: '-1' },
];

// Mid-round leaderboard (after Q3)
const LIVE_SCORES = [
  { name: 'Asha',  score: 2840, delta: '+2', last: 920 },
  { name: 'Mira',  score: 2510, delta: '-1', last: 720 },
  { name: 'Otto',  score: 2340, delta: '+1', last: 880 },
  { name: 'Theo',  score: 2120, delta: '0',  last: 600 },
  { name: 'Cleo',  score: 1880, delta: '+1', last: 540 },
  { name: 'Jules', score: 1640, delta: '-2', last: 0 },
  { name: 'Wren',  score: 1450, delta: '0',  last: 480 },
  { name: 'Sage',  score: 1220, delta: '-1', last: 320 },
];

// Awards revealed on podium
const AWARDS = [
  { title: 'Fastest Finger',  detail: 'Avg 2.4s to answer', winner: 'Otto' },
  { title: 'Comeback Kid',    detail: 'Climbed 4 places',  winner: 'Theo' },
  { title: 'Longest Streak',  detail: '5 in a row',         winner: 'Asha' },
  { title: 'Just for Fun',    detail: 'Voted MVP by peers', winner: 'Mira' },
];

// ─────────────────────────────────────────────────────────────
// Simulation loop — drives the synced TV + phone prototype.
// ─────────────────────────────────────────────────────────────
// Phases:
//   'lobby'        → waiting for game, players streaming in
//   'intro'        → countdown 3-2-1
//   'asking'       → question shown, players answering
//   'revealing'    → answer revealed, points animating
//   'leaderboard'  → mid-game standings
//   'podium'       → final results
const PHASES = ['lobby', 'intro', 'asking', 'revealing', 'leaderboard', 'podium'];

const PHASE_DURATIONS = {
  lobby: 6000,
  intro: 2400,
  asking: 9000,
  revealing: 3500,
  leaderboard: 5000,
  podium: 12000,
};

function useGameSim({ paused, speed = 1, jumpTo = null, gameType = 'quiz' }) {
  const [phase, setPhase] = React.useState('lobby');
  const [elapsed, setElapsed] = React.useState(0);
  const [playersJoined, setPlayersJoined] = React.useState(3);
  // Per-player answer state during 'asking' phase
  const [answers, setAnswers] = React.useState({});
  const startRef = React.useRef(performance.now());

  // Jump-to override
  React.useEffect(() => {
    if (jumpTo && PHASES.includes(jumpTo)) {
      setPhase(jumpTo);
      setElapsed(0);
      startRef.current = performance.now();
      if (jumpTo === 'lobby') setPlayersJoined(3);
      else setPlayersJoined(PLAYERS.length);
      setAnswers({});
    }
  }, [jumpTo]);

  // RAF tick
  React.useEffect(() => {
    if (paused) return;
    let raf = 0;
    let last = performance.now();
    const tick = (t) => {
      const dt = (t - last) * speed;
      last = t;
      setElapsed((prev) => {
        const next = prev + dt;
        const dur = PHASE_DURATIONS[phase] || 4000;

        // Lobby: stream players in
        if (phase === 'lobby') {
          const targetCount = Math.min(PLAYERS.length, 3 + Math.floor(next / 700));
          setPlayersJoined((p) => Math.max(p, targetCount));
        }
        // Asking: players answer at varied times
        if (phase === 'asking') {
          setAnswers((prev) => {
            const updated = { ...prev };
            PLAYERS.forEach((p, i) => {
              if (updated[p.name]) return;
              // Each player picks at a deterministic time between 1.5s and 8s
              const pickAt = 1500 + ((i * 977) % 6500);
              if (next >= pickAt) {
                // Most pick option B (correct) for quiz; some wrong for variety
                const choice = (i % 5 === 0) ? 0 : (i % 7 === 0) ? 2 : (i % 11 === 0) ? 3 : 1;
                updated[p.name] = { choice, time: pickAt };
              }
            });
            return updated;
          });
        }

        if (next >= dur) {
          const idx = PHASES.indexOf(phase);
          const nextPhase = PHASES[(idx + 1) % PHASES.length];
          setPhase(nextPhase);
          startRef.current = performance.now();
          if (nextPhase === 'lobby') setPlayersJoined(3);
          if (nextPhase === 'asking' || nextPhase === 'intro') setAnswers({});
          return 0;
        }
        return next;
      });
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [phase, paused, speed]);

  const duration = PHASE_DURATIONS[phase] || 4000;
  const progress = Math.min(1, elapsed / duration);

  return {
    phase,
    elapsed,
    progress,
    duration,
    playersJoined,
    answers,
    answeredCount: Object.keys(answers).length,
    setPhase: (p) => { setPhase(p); setElapsed(0); setAnswers({}); },
  };
}

Object.assign(window, {
  LP_PLAYERS: PLAYERS,
  LP_GAMES: GAMES,
  LP_QUIZ: QUIZ_QUESTION,
  LP_WMLT: WMLT_STATEMENT,
  LP_PICT: PICTIONARY_WORD,
  LP_TABOO: TABOO_CARD,
  LP_WHISPERS: WHISPERS_PHRASE,
  LP_FINAL_SCORES: FINAL_SCORES,
  LP_LIVE_SCORES: LIVE_SCORES,
  LP_AWARDS: AWARDS,
  LP_PHASES: PHASES,
  useGameSim,
});
