// LocalPlay Redesign — top-level App
//
// Composes:
//   • Page intro (designer's hand-off note)
//   • The interactive prototype (TV + phone, synced, simulated loop)
//   • A design canvas with frozen variations across all 3 directions
//   • The Tweaks panel

const TWEAK_DEFAULTS = /*EDITMODE-BEGIN*/{
  "direction": "salon",
  "gameType": "quiz",
  "phase": "auto",
  "speed": 1,
  "paused": false,
  "showCanvas": true
}/*EDITMODE-END*/;

const DIRECTIONS = {
  salon: {
    label: 'A · Salon',
    blurb: 'Editorial premium — warm cream paper, terracotta, Newsreader display.',
  },
  velvet: {
    label: 'B · Velvet',
    blurb: 'Late-night lounge — midnight + neon, soft vignette, magenta + mint.',
  },
  playground: {
    label: 'C · Playground',
    blurb: 'Confident pop — paper white, chunky ink borders, coral + electric blue.',
  },
  arcade: {
    label: 'D · Arcade',
    blurb: 'CRT cabinet — near-black, neon green, scanlines, mono terminal type.',
  },
  garden: {
    label: 'E · Garden',
    blurb: 'Botanical zine — sage paper, dusty rose, deep-forest ink, soft serif.',
  },
};

const GAME_TYPES = {
  quiz:       { label: 'Trivia',          screenTV: 'TVQuiz',       screenPhone: 'PhoneQuiz' },
  wmlt:       { label: 'Most Likely To',  screenTV: 'TVWmlt',       screenPhone: 'PhoneWmlt' },
  pictionary: { label: 'Pictionary',      screenTV: 'TVPictionary', screenPhone: 'PhonePictionary' },
  taboo:      { label: 'Taboo',           screenTV: 'TVTaboo',      screenPhone: 'PhoneTaboo' },
  whispers:   { label: 'Whispers',        screenTV: 'TVWhispers',   screenPhone: 'PhoneWhispers' },
};

// ═════════════════════════════════════════════════════════════
// Intro panel — top of page
// ═════════════════════════════════════════════════════════════
function Intro() {
  return (
    <>
      <div className="lp-intro">
        <div className="lp-intro-eyebrow">
          LOCALPLAY · REDESIGN · <span>VERSION 01</span>
        </div>
        <h1>
          A premium <em>party-games</em> living room.
        </h1>
        <p>
          Three aesthetic directions for LocalPlay's full surface area — TV host, mobile player, and a library that now welcomes Pictionary, Taboo, and Whispers alongside the existing trivia and Most-Likely formats. The visual system is built to flex across game types without losing identity.
        </p>
        <p>
          The prototype below runs a simulated game loop. Open <strong style={{ color: '#E0A87E' }}>Tweaks</strong> in the toolbar to switch direction, game type, or jump to a specific phase. The design canvas underneath shows frozen versions of every key screen in all three directions.
        </p>
      </div>
      <div className="lp-rule" />
    </>
  );
}

// ═════════════════════════════════════════════════════════════
// Phase router — picks which screen to show for the given (gameType, phase)
// ═════════════════════════════════════════════════════════════
function PhaseScreen({ surface, gameType, phase, sim, code }) {
  // Surface = 'tv' or 'phone'
  const { TVLobby, TVIntro, TVQuiz, TVWmlt, TVPictionary, TVTaboo, TVWhispers,
          TVLeaderboard, TVPodium,
          PhoneLobby, PhoneIntro, PhoneQuiz, PhoneWmlt, PhonePictionary,
          PhoneTaboo, PhoneWhispers, PhoneLeaderboard, PhonePodium } = window;

  const baseProps = {
    phase,
    progress: sim.progress,
    code,
    answeredCount: sim.answeredCount,
    answers: sim.answers,
  };

  if (surface === 'tv') {
    if (phase === 'lobby')   return <TVLobby code={code} joined={sim.playersJoined} game={GAME_TYPES[gameType].label.toUpperCase()} />;
    if (phase === 'intro')   return <TVIntro code={code} game={GAME_TYPES[gameType].label.toUpperCase()} round={3} total={10} progress={sim.progress} />;
    if (phase === 'leaderboard') return <TVLeaderboard {...baseProps} />;
    if (phase === 'podium')      return <TVPodium {...baseProps} />;
    // asking / revealing → route by game type
    const Comp = window[GAME_TYPES[gameType].screenTV];
    return <Comp {...baseProps} />;
  }
  if (phase === 'lobby')   return <PhoneLobby joined={sim.playersJoined} code={code} />;
  if (phase === 'intro')   return <PhoneIntro code={code} progress={sim.progress} />;
  if (phase === 'leaderboard') return <PhoneLeaderboard />;
  if (phase === 'podium')      return <PhonePodium />;
  const Comp = window[GAME_TYPES[gameType].screenPhone];
  return <Comp {...baseProps} />;
}

// ═════════════════════════════════════════════════════════════
// Stage — TV + phone, theme-applied
// ═════════════════════════════════════════════════════════════
function PrototypeStage({ direction, gameType, phase, speed, paused }) {
  const sim = window.useGameSim({
    paused,
    speed,
    jumpTo: phase === 'auto' ? null : phase,
    gameType,
  });
  const effectivePhase = phase === 'auto' ? sim.phase : phase;
  const themeClass = `theme-${direction}`;
  const code = 'PLAY42';

  return (
    <div className="lp-stage">
      <div className="lp-stage-header">
        <div>
          <strong>{DIRECTIONS[direction].label}</strong> · <span>{DIRECTIONS[direction].blurb}</span>
        </div>
        <div>
          PHASE · <strong>{effectivePhase.toUpperCase()}</strong> · {GAME_TYPES[gameType].label.toUpperCase()}
        </div>
      </div>

      <div className="lp-stage-grid">
        {/* TV — Browser window */}
        <div>
          <div className="lp-stage-label">
            <span>TV · 1280 × 720 · Chromecast / browser fullscreen</span>
            <span>localplay.fm/tv/{code.toLowerCase()}</span>
          </div>
          <window.ChromeWindow
            tabs={[{ title: 'LocalPlay · TV', active: true }]}
            url={`localplay.fm/tv/${code.toLowerCase()}`}
            width={1280}
            height={720}
          >
            <div className={`${themeClass} tv lp-tv-wrap`}>
              <PhaseScreen
                surface="tv"
                gameType={gameType}
                phase={effectivePhase}
                sim={sim}
                code={code}
              />
            </div>
          </window.ChromeWindow>
        </div>

        {/* Phone — iOS device */}
        <div>
          <div className="lp-stage-label">
            <span>PHONE · iPhone 15 · player view</span>
            <span>·</span>
          </div>
          <window.IOSDevice width={402} height={874} title="LocalPlay">
            <div className={`${themeClass} phone`} style={{ width: '100%', height: '100%' }}>
              <PhaseScreen
                surface="phone"
                gameType={gameType}
                phase={effectivePhase}
                sim={sim}
                code={code}
              />
            </div>
          </window.IOSDevice>
        </div>
      </div>

      <div className="lp-stage-header" style={{ marginTop: 8 }}>
        <div>
          PROGRESS · <strong className="num">{Math.round(sim.progress * 100)}%</strong> of phase ·
          <span style={{ marginLeft: 8 }}>{sim.answeredCount} of 8 answered</span>
        </div>
        <div>
          {paused ? 'PAUSED' : `PLAYING · ${speed}×`}
        </div>
      </div>
    </div>
  );
}

// ═════════════════════════════════════════════════════════════
// Frozen artboards for the design canvas
// ═════════════════════════════════════════════════════════════
function FrozenTV({ direction, screen, ...props }) {
  const themeClass = `theme-${direction}`;
  const code = 'PLAY42';
  // Build a synthetic "sim" object
  const sim = {
    progress: props.progress ?? 0.45,
    answeredCount: props.answeredCount ?? 5,
    answers: { Mira: { choice: 1, time: 1500 }, Theo: { choice: 1, time: 2300 }, Asha: { choice: 1, time: 1800 }, Otto: { choice: 0, time: 4200 }, Cleo: { choice: 1, time: 3100 } },
    playersJoined: props.joined ?? 7,
  };
  return (
    <div className={`${themeClass} tv`} style={{ width: 1280, height: 720, transform: 'none' }}>
      <PhaseScreen surface="tv" gameType={props.gameType || 'quiz'} phase={screen} sim={sim} code={code} />
    </div>
  );
}
function FrozenPhone({ direction, screen, ...props }) {
  const themeClass = `theme-${direction}`;
  const code = 'PLAY42';
  const sim = {
    progress: props.progress ?? 0.45,
    answeredCount: 4,
    answers: { Mira: { choice: 1, time: 1500 }, Theo: { choice: 1, time: 2300 }, Otto: { choice: 0, time: 4200 } },
    playersJoined: 7,
  };
  return (
    <div className={`${themeClass} phone`} style={{ width: 402, height: 740 }}>
      <PhaseScreen surface="phone" gameType={props.gameType || 'quiz'} phase={screen} sim={sim} code={code} />
    </div>
  );
}

// Library card — TV "home"
function FrozenLibrary({ direction }) {
  return (
    <div className={`theme-${direction} tv`} style={{ width: 1280, height: 720 }}>
      <window.TVLibrary />
    </div>
  );
}

// ═════════════════════════════════════════════════════════════
// Design canvas — frozen comparisons across the three directions
// ═════════════════════════════════════════════════════════════
function CanvasSection() {
  const { DesignCanvas, DCSection, DCArtboard } = window;
  const dirs = ['salon', 'velvet', 'playground'];
  return (
    <div style={{ position: 'relative', height: '100vh', borderTop: '1px solid rgba(244,238,228,0.15)' }}>
      <DesignCanvas>
        <DCSection
          id="overview"
          title="01 · The system, three ways"
          subtitle="Library · Lobby · In-game · Leaderboard · Podium — across Salon, Velvet, and Playground."
        >
          {dirs.map(d => (
            <DCArtboard key={`lib-${d}`} id={`lib-${d}`} label={`${DIRECTIONS[d].label} · Library`} width={1280} height={720}>
              <FrozenLibrary direction={d} />
            </DCArtboard>
          ))}
        </DCSection>

        <DCSection id="lobby" title="02 · Lobby (TV)" subtitle="Same room code, same QR, three different lounges.">
          {dirs.map(d => (
            <DCArtboard key={`lobby-${d}`} id={`lobby-${d}`} label={DIRECTIONS[d].label} width={1280} height={720}>
              <FrozenTV direction={d} screen="lobby" joined={7} />
            </DCArtboard>
          ))}
        </DCSection>

        <DCSection id="quiz" title="03 · Trivia question (TV)" subtitle="Mid-question — 5 of 8 answered, timer at 60%.">
          {dirs.map(d => (
            <DCArtboard key={`q-${d}`} id={`q-${d}`} label={DIRECTIONS[d].label} width={1280} height={720}>
              <FrozenTV direction={d} screen="asking" gameType="quiz" progress={0.6} answeredCount={5} />
            </DCArtboard>
          ))}
        </DCSection>

        <DCSection id="quiz-reveal" title="04 · Trivia answer reveal" subtitle="Correct option lights up, points push to the leaders.">
          {dirs.map(d => (
            <DCArtboard key={`qr-${d}`} id={`qr-${d}`} label={DIRECTIONS[d].label} width={1280} height={720}>
              <FrozenTV direction={d} screen="revealing" gameType="quiz" progress={0.5} answeredCount={8} />
            </DCArtboard>
          ))}
        </DCSection>

        <DCSection id="wmlt" title="05 · Most Likely To (TV)" subtitle="One statement, vote on a player from the room.">
          {dirs.map(d => (
            <DCArtboard key={`w-${d}`} id={`w-${d}`} label={DIRECTIONS[d].label} width={1280} height={720}>
              <FrozenTV direction={d} screen="asking" gameType="wmlt" progress={0.4} answeredCount={4} />
            </DCArtboard>
          ))}
        </DCSection>

        <DCSection id="pict" title="06 · Pictionary (TV)" subtitle="Drawer sees the word; everyone else guesses live.">
          {dirs.map(d => (
            <DCArtboard key={`p-${d}`} id={`p-${d}`} label={DIRECTIONS[d].label} width={1280} height={720}>
              <FrozenTV direction={d} screen="asking" gameType="pictionary" progress={0.6} />
            </DCArtboard>
          ))}
        </DCSection>

        <DCSection id="taboo" title="07 · Taboo (TV)" subtitle="One big word, five forbidden ones. Sprint format.">
          {dirs.map(d => (
            <DCArtboard key={`t-${d}`} id={`t-${d}`} label={DIRECTIONS[d].label} width={1280} height={720}>
              <FrozenTV direction={d} screen="asking" gameType="taboo" progress={0.35} />
            </DCArtboard>
          ))}
        </DCSection>

        <DCSection id="whispers" title="08 · Whispers (TV)" subtitle="The chain reveals, message by message.">
          {dirs.map(d => (
            <DCArtboard key={`wh-${d}`} id={`wh-${d}`} label={DIRECTIONS[d].label} width={1280} height={720}>
              <FrozenTV direction={d} screen="asking" gameType="whispers" progress={0.7} />
            </DCArtboard>
          ))}
        </DCSection>

        <DCSection id="lead" title="09 · Mid-game standings" subtitle="Bar chart, points delta, top-of-table callout.">
          {dirs.map(d => (
            <DCArtboard key={`l-${d}`} id={`l-${d}`} label={DIRECTIONS[d].label} width={1280} height={720}>
              <FrozenTV direction={d} screen="leaderboard" />
            </DCArtboard>
          ))}
        </DCSection>

        <DCSection id="podium" title="10 · Podium + awards" subtitle="1-2-3, then four superlatives.">
          {dirs.map(d => (
            <DCArtboard key={`pod-${d}`} id={`pod-${d}`} label={DIRECTIONS[d].label} width={1280} height={720}>
              <FrozenTV direction={d} screen="podium" />
            </DCArtboard>
          ))}
        </DCSection>

        <DCSection id="phone-quiz" title="11 · Phone — trivia answer" subtitle="The player's hand. Power-ups visible until they pick.">
          {dirs.map(d => (
            <DCArtboard key={`pq-${d}`} id={`pq-${d}`} label={DIRECTIONS[d].label} width={402} height={740}>
              <FrozenPhone direction={d} screen="asking" gameType="quiz" progress={0.5} />
            </DCArtboard>
          ))}
        </DCSection>

        <DCSection id="phone-lobby" title="12 · Phone — lobby" subtitle="Joined; waiting for the host to start.">
          {dirs.map(d => (
            <DCArtboard key={`pl-${d}`} id={`pl-${d}`} label={DIRECTIONS[d].label} width={402} height={740}>
              <FrozenPhone direction={d} screen="lobby" />
            </DCArtboard>
          ))}
        </DCSection>

        <DCSection id="phone-pict" title="13 · Phone — Pictionary guesser" subtitle="See the drawing as it lands, type a guess.">
          {dirs.map(d => (
            <DCArtboard key={`pp-${d}`} id={`pp-${d}`} label={DIRECTIONS[d].label} width={402} height={740}>
              <FrozenPhone direction={d} screen="asking" gameType="pictionary" progress={0.55} />
            </DCArtboard>
          ))}
        </DCSection>

        <DCSection id="phone-taboo" title="14 · Phone — Taboo describer" subtitle="Big word, forbidden tags, hit / skip buttons.">
          {dirs.map(d => (
            <DCArtboard key={`pt-${d}`} id={`pt-${d}`} label={DIRECTIONS[d].label} width={402} height={740}>
              <FrozenPhone direction={d} screen="asking" gameType="taboo" progress={0.4} />
            </DCArtboard>
          ))}
        </DCSection>

        <DCSection id="phone-podium" title="15 · Phone — final result" subtitle="Your rank, your earned awards, play-again CTA.">
          {dirs.map(d => (
            <DCArtboard key={`pp2-${d}`} id={`pp2-${d}`} label={DIRECTIONS[d].label} width={402} height={740}>
              <FrozenPhone direction={d} screen="podium" />
            </DCArtboard>
          ))}
        </DCSection>
      </DesignCanvas>
    </div>
  );
}

// ═════════════════════════════════════════════════════════════
// Tweaks Panel
// ═════════════════════════════════════════════════════════════
function Tweaks({ t, setTweak }) {
  const { TweaksPanel, TweakSection, TweakRow, TweakRadio, TweakSelect, TweakToggle, TweakSlider, TweakButton } = window;
  return (
    <TweaksPanel title="LocalPlay Tweaks">
      <TweakSection label="Direction">
        <TweakSelect
          label="Aesthetic"
          value={t.direction}
          onChange={(v) => setTweak('direction', v)}
          options={Object.entries(DIRECTIONS).map(([k, v]) => ({ value: k, label: v.label }))}
        />
      </TweakSection>

      <TweakSection label="Game">
        <TweakSelect
          label="Game type"
          value={t.gameType}
          onChange={(v) => setTweak('gameType', v)}
          options={Object.entries(GAME_TYPES).map(([k, v]) => ({ value: k, label: v.label }))}
        />
      </TweakSection>

      <TweakSection label="Playback">
        <TweakSelect
          label="Phase"
          value={t.phase}
          onChange={(v) => setTweak('phase', v)}
          options={[
            { value: 'auto',        label: 'Auto · loop' },
            { value: 'lobby',       label: 'Lobby' },
            { value: 'intro',       label: 'Intro · 3-2-1' },
            { value: 'asking',      label: 'Asking' },
            { value: 'revealing',   label: 'Revealing' },
            { value: 'leaderboard', label: 'Leaderboard' },
            { value: 'podium',      label: 'Podium' },
          ]}
        />
        <TweakToggle label="Paused" value={t.paused} onChange={(v) => setTweak('paused', v)} />
        <TweakRadio
          label="Speed"
          value={String(t.speed)}
          onChange={(v) => setTweak('speed', Number(v))}
          options={[
            { value: '0.5', label: '0.5×' },
            { value: '1',   label: '1×' },
            { value: '2',   label: '2×' },
          ]}
        />
      </TweakSection>
    </TweaksPanel>
  );
}

// ═════════════════════════════════════════════════════════════
// App
// ═════════════════════════════════════════════════════════════
function App() {
  const [t, setTweak] = window.useTweaks(TWEAK_DEFAULTS);
  return (
    <>
      <Intro />
      <PrototypeStage
        direction={t.direction}
        gameType={t.gameType}
        phase={t.phase}
        speed={t.speed}
        paused={t.paused}
      />
      <CanvasSection />
      <Tweaks t={t} setTweak={setTweak} />
    </>
  );
}

ReactDOM.createRoot(document.getElementById('app')).render(<App />);
