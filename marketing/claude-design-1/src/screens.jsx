// LocalPlay Redesign — TV + phone screens, parameterized by theme via CSS variables.
//
// All screens take theme tokens from the wrapping `.theme-salon` / `.theme-velvet`
// / `.theme-playground` ancestor. Each component renders the same data three ways.

const { LP_PLAYERS, LP_GAMES, LP_QUIZ, LP_WMLT, LP_PICT, LP_TABOO, LP_WHISPERS,
        LP_FINAL_SCORES, LP_LIVE_SCORES, LP_AWARDS } = window;

// ─────────────────────────────────────────────────────────────
// Avatar — themed via .av primitive in styles.css
// ─────────────────────────────────────────────────────────────
function Avatar({ player, size = 32, you = false }) {
  if (!player) return null;
  // Playground uses player-specific hues as the avatar tile background
  const playgroundBg = `oklch(72% 0.18 ${player.hue})`;
  return (
    <span
      className="av"
      data-you={you}
      style={{
        width: size,
        height: size,
        // Emoji glyph fills most of the disc; clamp so tiny chips remain legible
        fontSize: Math.max(14, Math.round(size * 0.62)),
        '--av-pg-bg': playgroundBg,
      }}
    >
      <span className="av-emoji" aria-hidden="true">{player.avatar}</span>
      <span className="visually-hidden">{player.name}</span>
    </span>
  );
}

// ─────────────────────────────────────────────────────────────
// Faux QR — looks the part without external libs
// ─────────────────────────────────────────────────────────────
function FauxQR({ size = 180, code = 'PLAY42' }) {
  // Deterministic pattern from code
  const seed = [...code].reduce((s, c, i) => s + c.charCodeAt(0) * (i + 1), 0);
  const N = 21;
  const cells = [];
  for (let r = 0; r < N; r++) {
    for (let c = 0; c < N; c++) {
      const v = ((r * 31 + c * 17 + seed) * 2654435761) >>> 0;
      cells.push({ r, c, on: (v % 100) < 48 });
    }
  }
  // Force the 3 finder squares
  const forceOff = (r, c) => {
    const finder = (a, b) =>
      (r >= a && r < a + 7 && c >= b && c < b + 7);
    return finder(0, 0) || finder(0, N - 7) || finder(N - 7, 0);
  };
  const finder = (x, y) => (
    <>
      <rect x={x} y={y} width={7} height={7} fill="currentColor" />
      <rect x={x + 1} y={y + 1} width={5} height={5} fill="var(--qr-bg, white)" />
      <rect x={x + 2} y={y + 2} width={3} height={3} fill="currentColor" />
    </>
  );
  return (
    <svg width={size} height={size} viewBox={`0 0 ${N} ${N}`} shapeRendering="crispEdges" style={{ display: 'block' }}>
      <rect x={0} y={0} width={N} height={N} fill="var(--qr-bg, white)" />
      {cells.map(({ r, c, on }, i) =>
        on && !forceOff(r, c) ? <rect key={i} x={c} y={r} width={1} height={1} fill="currentColor" /> : null
      )}
      {finder(0, 0)}
      {finder(0, N - 7)}
      {finder(N - 7, 0)}
    </svg>
  );
}

// ─────────────────────────────────────────────────────────────
// Header bar (TV) — small upper-band with room code etc.
// ─────────────────────────────────────────────────────────────
function TVHeader({ game = 'TRIVIA', round, total, code = 'PLAY42', kind = 'standard' }) {
  return (
    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', padding: '32px 56px 0' }}>
      <div className="eyebrow" style={{ display: 'flex', gap: 24 }}>
        <span>LocalPlay</span>
        <span>·</span>
        <span>{game}</span>
        {round && (
          <>
            <span>·</span>
            <span>{kind === 'wmlt' ? 'ROUND' : 'QUESTION'} {String(round).padStart(2, '0')} / {String(total).padStart(2, '0')}</span>
          </>
        )}
      </div>
      <div className="eyebrow">ROOM <strong style={{ color: 'var(--ink)', letterSpacing: '0.2em' }}>{code}</strong></div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────
// Timer ring (animated)
// ─────────────────────────────────────────────────────────────
function TimerRing({ progress = 0, size = 96, stroke = 5, label }) {
  const r = (size - stroke) / 2;
  const C = 2 * Math.PI * r;
  const remaining = Math.ceil((1 - progress) * 15);
  return (
    <div style={{ position: 'relative', width: size, height: size }}>
      <svg width={size} height={size} style={{ transform: 'rotate(-90deg)' }}>
        <circle cx={size/2} cy={size/2} r={r} stroke="var(--rule)" strokeWidth={stroke} fill="none" />
        <circle
          cx={size/2} cy={size/2} r={r}
          stroke="var(--accent)"
          strokeWidth={stroke}
          fill="none"
          strokeDasharray={C}
          strokeDashoffset={C * progress}
          strokeLinecap="round"
        />
      </svg>
      <div style={{
        position: 'absolute', inset: 0, display: 'flex',
        alignItems: 'center', justifyContent: 'center',
        fontFamily: 'var(--font-display)', fontSize: size * 0.42,
        fontWeight: 500, color: 'var(--ink)', fontVariantNumeric: 'tabular-nums',
        letterSpacing: '-0.04em',
      }}>
        {label ?? remaining}
      </div>
    </div>
  );
}

// ═════════════════════════════════════════════════════════════
//  TV · LOBBY
// ═════════════════════════════════════════════════════════════
function TVLobby({ code = 'PLAY42', joined = 3, game = 'TRIVIA' }) {
  const players = LP_PLAYERS.slice(0, joined);
  return (
    <div className="tv-content" style={{ position: 'relative', zIndex: 1, height: '100%', display: 'flex', flexDirection: 'column' }}>
      <TVHeader game={game} code={code} />
      <div style={{ flex: 1, display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 48, padding: '40px 56px' }}>
        {/* LEFT: instructions + room code */}
        <div style={{ display: 'flex', flexDirection: 'column', justifyContent: 'center' }}>
          <div className="eyebrow" style={{ marginBottom: 16 }}>· Round one starts when host is ready</div>
          <h1 className="display" style={{ fontSize: 84, lineHeight: 0.96, marginBottom: 32 }}>
            <span style={{ fontStyle: 'italic', color: 'var(--accent)' }}>Join</span> the game.
          </h1>
          <div style={{ display: 'flex', gap: 48, alignItems: 'flex-start' }}>
            <div>
              <div className="eyebrow" style={{ marginBottom: 8 }}>Step 01</div>
              <p style={{ fontSize: 17, color: 'var(--ink-2)', maxWidth: 280, lineHeight: 1.4 }}>
                Open the camera on your phone and scan the code.
              </p>
            </div>
            <div>
              <div className="eyebrow" style={{ marginBottom: 8 }}>Step 02</div>
              <p style={{ fontSize: 17, color: 'var(--ink-2)', maxWidth: 280, lineHeight: 1.4 }}>
                Or enter <strong style={{ fontFamily: 'var(--font-mono)' }}>localplay.fm</strong> and the code.
              </p>
            </div>
          </div>
          <div className="hr-ink" style={{ marginTop: 48, marginBottom: 32 }} />
          <div style={{ display: 'flex', gap: 64, alignItems: 'baseline', flexWrap: 'wrap' }}>
            <div>
              <div className="eyebrow" style={{ marginBottom: 6 }}>Room code</div>
              <div style={{ fontFamily: 'var(--font-display)', fontSize: 88, lineHeight: 1, letterSpacing: '0.04em', color: 'var(--ink)' }}>
                {code}
              </div>
            </div>
            <div>
              <div className="eyebrow" style={{ marginBottom: 6 }}>Players</div>
              <div style={{ fontFamily: 'var(--font-display)', fontSize: 88, lineHeight: 1, color: 'var(--accent)' }} className="num">
                {String(joined).padStart(2, '0')}
              </div>
            </div>
          </div>
        </div>

        {/* RIGHT: QR + player roster */}
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 28 }}>
          <div style={{
            background: 'var(--paper)',
            padding: 24,
            border: '1px solid var(--ink)',
            color: 'var(--ink)',
            ['--qr-bg']: 'var(--paper)',
            borderRadius: 'var(--qr-radius, 0)',
            boxShadow: 'var(--shadow)',
          }}>
            <FauxQR size={220} code={code} />
          </div>
          {/* Player roster — appearing */}
          <div style={{ width: '100%', display: 'flex', flexDirection: 'column', gap: 10 }}>
            <div className="eyebrow" style={{ display: 'flex', justifyContent: 'space-between' }}>
              <span>Roster</span>
              <span>{joined} of 30 seats</span>
            </div>
            <div className="hr" />
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginTop: 8 }}>
              {players.map((p, i) => (
                <PlayerChip key={p.name} player={p} className="lp-fade-in" delay={i * 60} />
              ))}
              {Array.from({ length: Math.max(0, 8 - joined) }).map((_, i) => (
                <span key={'e' + i} style={{
                  padding: '8px 14px',
                  border: '1px dashed var(--rule)',
                  color: 'var(--ink-mute)',
                  borderRadius: 100,
                  fontFamily: 'var(--font-mono)',
                  fontSize: 11,
                  letterSpacing: '0.08em',
                }}>—</span>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function PlayerChip({ player, you = false, delay = 0, className = '' }) {
  return (
    <span
      className={className}
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 8,
        padding: '6px 14px 6px 6px',
        border: '1px solid var(--rule-2)',
        borderRadius: 100,
        background: you ? 'var(--accent)' : 'transparent',
        color: you ? 'var(--accent-ink)' : 'var(--ink)',
        animationDelay: `${delay}ms`,
        fontWeight: 500,
        fontSize: 14,
      }}
    >
      <Avatar player={player} size={26} you={you} />
      {player.name}{you ? ' ★' : ''}
    </span>
  );
}

// ═════════════════════════════════════════════════════════════
//  TV · INTRO (3-2-1)
// ═════════════════════════════════════════════════════════════
function TVIntro({ game = 'TRIVIA', round, total, code, progress }) {
  // Progress 0..1 over 2.4s → step 3, 2, 1, GO
  const step = Math.min(3, Math.floor(progress * 4));
  const labels = ['Three', 'Two', 'One', 'Begin.'];
  return (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column', position: 'relative', zIndex: 1 }}>
      <TVHeader game={game} code={code} round={round} total={total} />
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 24 }}>
        <div className="eyebrow">Question {String(round).padStart(2, '0')} of {String(total).padStart(2, '0')}</div>
        <div className="display" style={{ fontSize: 280, lineHeight: 0.85, fontStyle: step < 3 ? 'normal' : 'italic', color: 'var(--ink)' }}>
          {labels[step]}
        </div>
        <div className="eyebrow">{LP_QUIZ.topic} · 4 options · 15 seconds</div>
      </div>
    </div>
  );
}

// ═════════════════════════════════════════════════════════════
//  TV · QUIZ — asking or revealing
// ═════════════════════════════════════════════════════════════
function TVQuiz({ phase, progress, answeredCount, code }) {
  const q = LP_QUIZ;
  const revealing = phase === 'revealing';
  const remaining = Math.ceil((1 - progress) * 15);

  return (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column', position: 'relative', zIndex: 1 }}>
      <TVHeader game="TRIVIA" round={q.number} total={q.total} code={code} />

      {/* Topic strip + timer */}
      <div style={{ padding: '32px 56px 0', display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end' }}>
        <div>
          <div className="eyebrow" style={{ marginBottom: 8 }}>· Topic · {q.topic}</div>
          <h2 className="display" style={{ fontSize: 56, lineHeight: 1.05, maxWidth: 900, letterSpacing: '-0.02em' }}>
            {q.text}
          </h2>
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 12 }}>
          <TimerRing progress={progress} size={120} stroke={5} label={revealing ? '·' : remaining} />
          <div className="eyebrow" style={{ textAlign: 'right' }}>
            <div>{answeredCount} of {LP_PLAYERS.length} answered</div>
          </div>
        </div>
      </div>

      {/* Progress bar */}
      <div style={{ padding: '24px 56px 0' }}>
        <div className="progress">
          <div className="progress-fill" style={{ width: `${(1 - progress) * 100}%`, transition: 'width 0.1s linear' }} />
        </div>
      </div>

      {/* Answer grid 2x2 */}
      <div style={{
        flex: 1,
        padding: '32px 56px 48px',
        display: 'grid',
        gridTemplateColumns: '1fr 1fr',
        gridTemplateRows: '1fr 1fr',
        gap: 16,
      }}>
        {q.options.map((opt, i) => {
          const isCorrect = i === q.correct;
          const showState = revealing;
          return (
            <div
              key={i}
              className={`answer ${showState && isCorrect ? 'correct' : ''} ${showState && !isCorrect ? 'wrong' : ''}`}
              style={{ fontSize: 26, padding: '24px 32px' }}
            >
              <span className="answer-glyph" style={{ width: 44, height: 44, fontSize: 20 }}>{opt.glyph}</span>
              <span style={{ flex: 1 }}>{opt.text}</span>
              {showState && isCorrect && (
                <span className="eyebrow" style={{ color: 'inherit', opacity: 0.8 }}>+ 920 pts to leaders</span>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ═════════════════════════════════════════════════════════════
//  TV · WMLT
// ═════════════════════════════════════════════════════════════
function TVWmlt({ phase, progress, answeredCount, code }) {
  const s = LP_WMLT;
  const remaining = Math.ceil((1 - progress) * 15);
  return (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column', position: 'relative', zIndex: 1 }}>
      <TVHeader game="MOST LIKELY TO" round={s.number} total={s.total} code={code} kind="wmlt" />
      <div style={{ flex: 1, padding: '40px 56px', display: 'flex', flexDirection: 'column', justifyContent: 'space-between' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 48 }}>
          <div style={{ flex: 1 }}>
            <div className="eyebrow" style={{ marginBottom: 16 }}>· Statement</div>
            <h2 className="display" style={{ fontSize: 72, lineHeight: 1.0, letterSpacing: '-0.03em' }}>
              {s.text}
            </h2>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 8 }}>
            <TimerRing progress={progress} size={120} label={remaining} />
            <div className="eyebrow" style={{ textAlign: 'right' }}>{answeredCount} / {LP_PLAYERS.length} voted</div>
          </div>
        </div>

        <div>
          <div className="eyebrow" style={{ marginBottom: 16 }}>· Pick one from the room</div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(8, 1fr)', gap: 12 }}>
            {LP_PLAYERS.map((p, i) => (
              <div key={p.name} style={{
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'center',
                gap: 8,
                padding: '16px 8px',
                border: '1px solid var(--rule-2)',
                borderRadius: 12,
                background: 'var(--paper)',
              }}>
                <Avatar player={p} size={48} />
                <div style={{ fontWeight: 500, fontSize: 15 }}>{p.name}</div>
                <div className="eyebrow" style={{ fontSize: 10 }}>+ vote</div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

// ═════════════════════════════════════════════════════════════
//  TV · PICTIONARY
// ═════════════════════════════════════════════════════════════
function TVPictionary({ phase, progress, code }) {
  const p = LP_PICT;
  const remaining = Math.ceil((1 - progress) * 60);
  // Faux drawing — animate strokes appearing as time progresses
  const drawProg = Math.min(1, progress * 1.4);
  return (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column', position: 'relative', zIndex: 1 }}>
      <TVHeader game="PICTIONARY" round={p.number} total={p.total} code={code} />
      <div style={{ flex: 1, padding: '32px 56px 48px', display: 'grid', gridTemplateColumns: '1fr 360px', gap: 32 }}>
        {/* Drawing surface */}
        <div style={{
          background: 'var(--paper)',
          border: '1px solid var(--rule-2)',
          borderRadius: 6,
          position: 'relative',
          overflow: 'hidden',
        }}>
          <div className="eyebrow" style={{ position: 'absolute', top: 16, left: 20 }}>· Drawing — {p.drawer}</div>
          <FauxLighthouse progress={drawProg} />
        </div>

        {/* Right rail */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 28 }}>
          <div>
            <div className="eyebrow" style={{ marginBottom: 8 }}>· Time left</div>
            <TimerRing progress={progress} size={140} label={remaining} stroke={6} />
          </div>
          <div>
            <div className="eyebrow" style={{ marginBottom: 12 }}>· Guesses</div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              {[
                { p: LP_PLAYERS[0], g: 'tower' },
                { p: LP_PLAYERS[2], g: 'chess piece?' },
                { p: LP_PLAYERS[3], g: 'rocket' },
                { p: LP_PLAYERS[5], g: 'lighthouse', hit: true },
              ].map((row, i) => (
                <div key={i} style={{
                  display: 'flex', alignItems: 'center', gap: 10,
                  padding: '10px 14px',
                  background: row.hit ? 'var(--olive)' : 'var(--paper)',
                  color: row.hit ? '#FFFCF6' : 'var(--ink)',
                  border: '1px solid ' + (row.hit ? 'var(--olive)' : 'var(--rule)'),
                  borderRadius: 8,
                }}>
                  <Avatar player={row.p} size={24} />
                  <span style={{ fontSize: 14, fontWeight: 500 }}>{row.p.name}</span>
                  <span style={{ marginLeft: 'auto', fontStyle: 'italic', opacity: 0.85 }}>"{row.g}"</span>
                </div>
              ))}
            </div>
          </div>
          <div style={{ marginTop: 'auto' }}>
            <div className="eyebrow" style={{ marginBottom: 6 }}>· Word</div>
            <div className="display" style={{ fontSize: 36, letterSpacing: '0.08em' }}>
              <span style={{ color: 'var(--ink-mute)' }}>L</span>
              <span style={{ color: 'var(--ink)' }}>_ _ _ _ _ _ _ _ _</span>
              <div className="eyebrow" style={{ marginTop: 8 }}>9 letters · only the drawer sees the word</div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

// Hand-rendered placeholder: faux lighthouse strokes that fill in over time
function FauxLighthouse({ progress = 1 }) {
  return (
    <svg viewBox="0 0 400 400" style={{ width: '100%', height: '100%' }}>
      <defs>
        <linearGradient id="stroke-fade" x1="0" y1="0" x2="1" y2="0">
          <stop offset={`${progress * 100}%`} stopColor="var(--ink)" />
          <stop offset={`${progress * 100}%`} stopColor="transparent" />
        </linearGradient>
      </defs>
      <g fill="none" stroke="url(#stroke-fade)" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round">
        {/* Base */}
        <path d="M 100 350 L 300 350" />
        <path d="M 120 350 L 130 380 L 270 380 L 280 350" />
        {/* Body */}
        <path d="M 160 350 L 145 240 L 255 240 L 240 350" />
        {/* Horizontal stripes */}
        <path d="M 152 290 L 248 290" opacity="0.5" />
        <path d="M 156 320 L 244 320" opacity="0.5" />
        {/* Top room */}
        <path d="M 145 240 L 135 230 L 265 230 L 255 240" />
        <path d="M 150 230 L 150 200 L 250 200 L 250 230" />
        <rect x="170" y="206" width="60" height="18" />
        {/* Roof */}
        <path d="M 135 200 L 200 160 L 265 200" />
        {/* Spike */}
        <path d="M 200 160 L 200 130" />
        <circle cx="200" cy="125" r="4" />
        {/* Light beams */}
        <path d="M 200 215 L 60 180" opacity="0.6" />
        <path d="M 200 215 L 60 250" opacity="0.6" />
        {/* Waves */}
        <path d="M 60 360 Q 80 354 100 360 T 140 360" />
        <path d="M 280 360 Q 300 354 320 360 T 360 360" />
      </g>
    </svg>
  );
}

// ═════════════════════════════════════════════════════════════
//  TV · TABOO
// ═════════════════════════════════════════════════════════════
function TVTaboo({ phase, progress, code }) {
  const t = LP_TABOO;
  const remaining = Math.ceil((1 - progress) * 60);
  return (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column', position: 'relative', zIndex: 1 }}>
      <TVHeader game="TABOO" round={t.number} total={t.total} code={code} />
      <div style={{ flex: 1, padding: '32px 56px', display: 'grid', gridTemplateColumns: '1fr 320px', gap: 32 }}>
        {/* The card */}
        <div style={{
          background: 'var(--paper)',
          border: '2px solid var(--ink)',
          borderRadius: 8,
          padding: '48px',
          display: 'flex',
          flexDirection: 'column',
          justifyContent: 'space-between',
          boxShadow: 'var(--shadow)',
          position: 'relative',
        }}>
          <div className="eyebrow">· Get your team to say</div>
          <div style={{ textAlign: 'center', flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <div className="display" style={{ fontSize: 140, letterSpacing: '-0.03em', fontStyle: 'italic' }}>
              {t.word}
            </div>
          </div>
          <div>
            <div className="hr-ink" style={{ marginBottom: 16 }} />
            <div className="eyebrow" style={{ marginBottom: 12 }}>· Cannot say</div>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 12 }}>
              {t.forbidden.map(w => (
                <span key={w} style={{
                  padding: '8px 18px',
                  border: '1px solid var(--accent)',
                  color: 'var(--accent)',
                  borderRadius: 100,
                  fontSize: 16,
                  fontWeight: 500,
                  textTransform: 'lowercase',
                }}>{w}</span>
              ))}
            </div>
          </div>
        </div>

        {/* Right rail: team + timer */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>
          <TimerRing progress={progress} size={140} label={remaining} stroke={6} />
          <div>
            <div className="eyebrow" style={{ marginBottom: 12 }}>· On the clock</div>
            <div style={{ display: 'flex', gap: 8, marginBottom: 16 }}>
              <Avatar player={LP_PLAYERS[2]} size={36} />
              <div>
                <div style={{ fontWeight: 600 }}>Jules</div>
                <div className="eyebrow" style={{ fontSize: 10 }}>describing for Team Coral</div>
              </div>
            </div>
            <div className="hr" />
          </div>
          <div>
            <div className="eyebrow" style={{ marginBottom: 8 }}>· Score</div>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: 6 }}>
              <span style={{ fontSize: 16 }}>Team Coral</span>
              <span className="display num" style={{ fontSize: 32 }}>04</span>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
              <span style={{ fontSize: 16 }}>Team Mint</span>
              <span className="display num" style={{ fontSize: 32, color: 'var(--ink-mute)' }}>03</span>
            </div>
          </div>
          <div style={{ marginTop: 'auto', display: 'flex', flexDirection: 'column', gap: 10 }}>
            <button className="btn btn-primary">Got it ✓</button>
            <button className="btn btn-ghost">Skip (-1)</button>
          </div>
        </div>
      </div>
    </div>
  );
}

// ═════════════════════════════════════════════════════════════
//  TV · WHISPERS
// ═════════════════════════════════════════════════════════════
function TVWhispers({ phase, progress, code }) {
  const w = LP_WHISPERS;
  const revealed = Math.max(1, Math.floor(progress * 5) + 1);
  return (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column', position: 'relative', zIndex: 1 }}>
      <TVHeader game="WHISPERS" round={w.number} total={w.total} code={code} />
      <div style={{ flex: 1, padding: '32px 56px 48px', display: 'flex', flexDirection: 'column', gap: 24 }}>
        <div>
          <div className="eyebrow" style={{ marginBottom: 8 }}>· Original phrase from {w.origin}</div>
          <div className="display" style={{ fontSize: 36, fontStyle: 'italic', color: 'var(--accent)' }}>
            "{w.chain[0].text}"
          </div>
        </div>
        <div className="hr-ink" />
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 14 }}>
          <div className="eyebrow">· The chain</div>
          {w.chain.map((step, i) => {
            const visible = i < revealed;
            return (
              <div key={i} style={{
                display: 'flex', alignItems: 'flex-start', gap: 16,
                opacity: visible ? 1 : 0.18,
                transition: 'opacity 0.4s ease',
              }}>
                <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 4, paddingTop: 4 }}>
                  <Avatar player={LP_PLAYERS.find(p => p.name === step.player) || LP_PLAYERS[0]} size={36} />
                  <span className="eyebrow" style={{ fontSize: 10 }}>{step.player}</span>
                </div>
                <div style={{ flex: 1, paddingTop: 6 }}>
                  <div className="display" style={{ fontSize: 24, fontStyle: i === w.chain.length - 1 ? 'italic' : 'normal', color: i === w.chain.length - 1 ? 'var(--accent)' : 'var(--ink)' }}>
                    "{step.text}"
                  </div>
                </div>
                <div className="eyebrow num" style={{ paddingTop: 12 }}>0{i + 1}</div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}

// ═════════════════════════════════════════════════════════════
//  TV · LEADERBOARD (mid-game bar chart)
// ═════════════════════════════════════════════════════════════
function TVLeaderboard({ progress, code }) {
  const max = LP_LIVE_SCORES[0].score;
  return (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column', position: 'relative', zIndex: 1 }}>
      <TVHeader game="TRIVIA" round={LP_QUIZ.number} total={LP_QUIZ.total} code={code} />
      <div style={{ flex: 1, padding: '32px 56px 56px', display: 'flex', flexDirection: 'column' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end', marginBottom: 32 }}>
          <div>
            <div className="eyebrow" style={{ marginBottom: 8 }}>· After question 03</div>
            <h2 className="display" style={{ fontSize: 64, lineHeight: 1 }}>
              Standings.
            </h2>
          </div>
          <div className="eyebrow" style={{ textAlign: 'right' }}>
            <div>Top of the table</div>
            <div className="display" style={{ fontSize: 22, color: 'var(--ink)', fontStyle: 'italic', marginTop: 4 }}>Asha</div>
          </div>
        </div>
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 12 }}>
          {LP_LIVE_SCORES.map((s, i) => {
            const player = LP_PLAYERS.find(p => p.name === s.name);
            const width = (s.score / max) * 100;
            return (
              <div key={s.name} style={{ display: 'flex', alignItems: 'center', gap: 18 }}>
                <span className="eyebrow num" style={{ width: 36 }}>{String(i + 1).padStart(2, '0')}</span>
                <Avatar player={player} size={36} />
                <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 4 }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
                    <span style={{ fontSize: 18, fontWeight: 500 }}>{s.name}</span>
                    <div style={{ display: 'flex', gap: 16, alignItems: 'baseline' }}>
                      <span className="eyebrow" style={{ color: s.last > 0 ? 'var(--olive)' : 'var(--ink-mute)' }}>
                        {s.last > 0 ? `+${s.last}` : '+0'}
                      </span>
                      <span className="display num" style={{ fontSize: 28, minWidth: 80, textAlign: 'right' }}>
                        {s.score.toLocaleString()}
                      </span>
                    </div>
                  </div>
                  <div style={{ height: 6, background: 'var(--rule)', borderRadius: 3, overflow: 'hidden' }}>
                    <div style={{
                      width: `${width}%`, height: '100%',
                      background: i === 0 ? 'var(--accent)' : 'var(--ink)',
                      transition: 'width 0.6s ease',
                    }} />
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}

// ═════════════════════════════════════════════════════════════
//  TV · PODIUM
// ═════════════════════════════════════════════════════════════
function TVPodium({ progress, code }) {
  const heights = [320, 220, 160];
  const top3 = LP_FINAL_SCORES.slice(0, 3);
  return (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column', position: 'relative', zIndex: 1 }}>
      <TVHeader game="TRIVIA" code={code} />
      <div style={{ flex: 1, padding: '24px 56px 32px', display: 'flex', flexDirection: 'column' }}>
        <div style={{ textAlign: 'center', marginBottom: 16 }}>
          <div className="eyebrow" style={{ marginBottom: 8 }}>· Final standings · 10 of 10 complete</div>
          <h2 className="display" style={{ fontSize: 64, lineHeight: 1, letterSpacing: '-0.03em' }}>
            <span style={{ fontStyle: 'italic', color: 'var(--accent)' }}>{top3[0].name}</span> takes the crown.
          </h2>
        </div>

        <div style={{ flex: 1, display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 24, alignItems: 'end', maxWidth: 900, margin: '0 auto', width: '100%' }}>
          {[1, 0, 2].map((idx) => {
            const s = top3[idx];
            if (!s) return null;
            const player = LP_PLAYERS.find(p => p.name === s.name);
            const h = heights[idx];
            return (
              <div key={s.name} style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 12 }}>
                <Avatar player={player} size={idx === 0 ? 88 : 64} />
                <div className="display" style={{ fontSize: 28 }}>{s.name}</div>
                <div className="display num" style={{ fontSize: idx === 0 ? 48 : 36, color: 'var(--accent)' }}>
                  {s.score.toLocaleString()}
                </div>
                <div style={{
                  width: '100%',
                  height: h,
                  background: idx === 0 ? 'var(--accent)' : idx === 1 ? 'var(--ink)' : 'var(--ink-2)',
                  color: idx === 0 ? 'var(--accent-ink)' : 'var(--bg)',
                  display: 'flex',
                  alignItems: 'flex-start',
                  justifyContent: 'center',
                  paddingTop: 16,
                  fontFamily: 'var(--font-display)',
                  fontSize: 32,
                  borderRadius: 'var(--podium-radius, 2px)',
                }}>
                  {idx === 0 ? 'I' : idx === 1 ? 'II' : 'III'}
                </div>
              </div>
            );
          })}
        </div>

        {/* Awards strip */}
        <div style={{ marginTop: 16, display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 12, paddingTop: 16, borderTop: '1px solid var(--rule)' }}>
          {LP_AWARDS.map((a) => {
            const player = LP_PLAYERS.find(p => p.name === a.winner) || LP_PLAYERS[0];
            return (
              <div key={a.title}>
                <div className="eyebrow" style={{ marginBottom: 6 }}>· {a.title}</div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                  <Avatar player={player} size={28} />
                  <div>
                    <div style={{ fontSize: 15, fontWeight: 500 }}>{a.winner}</div>
                    <div className="eyebrow" style={{ fontSize: 9 }}>{a.detail}</div>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}

// ═════════════════════════════════════════════════════════════
//  PHONE SCREENS
// ═════════════════════════════════════════════════════════════
function PhoneHeader({ left, right }) {
  return (
    <div style={{
      display: 'flex', justifyContent: 'space-between', alignItems: 'baseline',
      padding: '20px 24px 8px',
    }}>
      <div className="eyebrow" style={{ display: 'flex', gap: 8 }}>{left}</div>
      <div className="eyebrow">{right}</div>
    </div>
  );
}

function PhoneLobby({ joined, code, me = LP_PLAYERS[3] }) {
  return (
    <div className="phone-content" style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
      <PhoneHeader left="LocalPlay" right={`ROOM ${code}`} />
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', justifyContent: 'center', padding: '0 24px', textAlign: 'center', gap: 24 }}>
        <div>
          <Avatar player={me} size={80} you />
        </div>
        <div>
          <div className="eyebrow" style={{ marginBottom: 6 }}>You're in</div>
          <h1 className="display" style={{ fontSize: 42, lineHeight: 1 }}>
            Hi, <em style={{ fontStyle: 'italic', color: 'var(--accent)' }}>{me.name}</em>
          </h1>
          <p style={{ marginTop: 12, fontSize: 15, color: 'var(--ink-mute)', maxWidth: 280, margin: '12px auto 0' }}>
            Waiting for the room to fill up. Look at the TV when the host starts.
          </p>
        </div>
        <div className="hr" />
        <div>
          <div className="eyebrow" style={{ marginBottom: 12 }}>· {joined} player{joined !== 1 ? 's' : ''} in the room</div>
          <div style={{ display: 'flex', flexWrap: 'wrap', justifyContent: 'center', gap: 6 }}>
            {LP_PLAYERS.slice(0, joined).map((p, i) => (
              <PlayerChip key={p.name} player={p} you={p.name === me.name} delay={i * 60} className="lp-fade-in" />
            ))}
          </div>
        </div>
      </div>
      <div style={{ padding: '0 24px 32px', display: 'flex', justifyContent: 'center' }}>
        <div className="eyebrow lp-pulse">· · · waiting for host</div>
      </div>
    </div>
  );
}

function PhoneIntro({ progress, code }) {
  const step = Math.min(3, Math.floor(progress * 4));
  const labels = ['3', '2', '1', 'Go.'];
  return (
    <div className="phone-content" style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
      <PhoneHeader left="LocalPlay · TRIVIA" right={`ROOM ${code}`} />
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center' }}>
        <div className="eyebrow" style={{ marginBottom: 12 }}>Get ready · Q3 of 10</div>
        <div className="display" style={{ fontSize: 200, lineHeight: 1, fontStyle: step === 3 ? 'italic' : 'normal' }}>
          {labels[step]}
        </div>
      </div>
    </div>
  );
}

function PhoneQuiz({ phase, progress, me = LP_PLAYERS[3], answers }) {
  const q = LP_QUIZ;
  const revealing = phase === 'revealing';
  const myAns = answers && answers[me.name] ? answers[me.name].choice : null;
  const remaining = Math.ceil((1 - progress) * 15);
  return (
    <div className="phone-content" style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
      <PhoneHeader left={[<span key="t">TRIVIA · Q{q.number}/{q.total}</span>]} right={<span className="num">{remaining}s</span>} />
      <div style={{ padding: '0 24px 16px' }}>
        <div className="progress">
          <div className="progress-fill" style={{ width: `${(1 - progress) * 100}%` }} />
        </div>
      </div>
      <div style={{ padding: '8px 24px 16px' }}>
        <div className="eyebrow" style={{ marginBottom: 8 }}>· {q.topic}</div>
        <p className="display" style={{ fontSize: 22, lineHeight: 1.2 }}>{q.text}</p>
      </div>
      <div style={{ flex: 1, padding: '8px 24px 16px', display: 'flex', flexDirection: 'column', gap: 10 }}>
        {q.options.map((opt, i) => {
          const isMine = myAns === i;
          const isCorrect = i === q.correct;
          return (
            <div
              key={i}
              className={`answer ${revealing && isCorrect ? 'correct' : ''} ${revealing && !isCorrect ? 'wrong' : ''}`}
              style={{
                fontSize: 16,
                padding: '14px 16px',
                outline: isMine && !revealing ? '2px solid var(--accent)' : 'none',
                outlineOffset: '-2px',
              }}
            >
              <span className="answer-glyph">{opt.glyph}</span>
              <span style={{ flex: 1 }}>{opt.text}</span>
              {isMine && <span className="eyebrow" style={{ color: 'inherit' }}>· your pick</span>}
            </div>
          );
        })}
      </div>
      {/* Power-ups strip */}
      {!revealing && (
        <div style={{ padding: '0 24px 20px', display: 'flex', gap: 8 }}>
          <button className="btn btn-ghost" style={{ flex: 1, fontSize: 13, padding: '10px 12px' }}>2× points</button>
          <button className="btn btn-ghost" style={{ flex: 1, fontSize: 13, padding: '10px 12px' }}>50 / 50</button>
        </div>
      )}
      {revealing && (
        <div style={{ padding: '0 24px 20px', textAlign: 'center' }}>
          <div className="eyebrow" style={{ marginBottom: 4 }}>{myAns === q.correct ? '· Correct ·' : '· Wrong ·'}</div>
          <div className="display num" style={{ fontSize: 36, color: myAns === q.correct ? 'var(--olive)' : 'var(--ink-mute)' }}>
            {myAns === q.correct ? '+ 920' : '+ 0'}
          </div>
        </div>
      )}
    </div>
  );
}

function PhoneWmlt({ phase, progress, me = LP_PLAYERS[3] }) {
  const s = LP_WMLT;
  const remaining = Math.ceil((1 - progress) * 15);
  const myVote = LP_PLAYERS[5]; // Cleo (faux)
  return (
    <div className="phone-content" style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
      <PhoneHeader left={`MOST LIKELY · ${s.number}/${s.total}`} right={<span className="num">{remaining}s</span>} />
      <div style={{ padding: '0 24px 12px' }}>
        <div className="progress"><div className="progress-fill" style={{ width: `${(1 - progress) * 100}%` }} /></div>
      </div>
      <div style={{ padding: '12px 24px 16px' }}>
        <div className="eyebrow" style={{ marginBottom: 8 }}>· Statement</div>
        <p className="display" style={{ fontSize: 22, lineHeight: 1.2 }}>{s.text}</p>
      </div>
      <div style={{ flex: 1, padding: '0 24px 16px', display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10, alignContent: 'start' }}>
        {LP_PLAYERS.map((p, i) => {
          const isMe = p.name === me.name;
          const isMyVote = p.name === myVote.name;
          return (
            <div key={p.name} style={{
              display: 'flex', alignItems: 'center', gap: 10,
              padding: 10,
              background: 'var(--paper)',
              border: '1px solid ' + (isMyVote ? 'var(--accent)' : 'var(--rule)'),
              outline: isMyVote ? '1px solid var(--accent)' : 'none',
              borderRadius: 10,
              opacity: isMe ? 0.4 : 1,
            }}>
              <Avatar player={p} size={32} />
              <span style={{ fontSize: 14, fontWeight: 500 }}>{p.name}</span>
            </div>
          );
        })}
      </div>
      <div style={{ padding: '0 24px 20px' }}>
        <button className="btn btn-primary" style={{ width: '100%' }}>Cast vote</button>
      </div>
    </div>
  );
}

function PhonePictionary({ progress, me = LP_PLAYERS[3] }) {
  return (
    <div className="phone-content" style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
      <PhoneHeader left="PICTIONARY · GUESSING" right={<span className="num">{Math.ceil((1-progress)*60)}s</span>} />
      <div style={{ padding: '0 24px 12px' }}>
        <div className="progress"><div className="progress-fill" style={{ width: `${(1 - progress) * 100}%` }} /></div>
      </div>
      <div style={{ padding: '16px 24px 0' }}>
        <div className="eyebrow" style={{ marginBottom: 6 }}>· Jules is drawing</div>
        <div style={{
          aspectRatio: '1', background: 'var(--paper)', border: '1px solid var(--rule-2)',
          borderRadius: 6, overflow: 'hidden',
        }}>
          <FauxLighthouse progress={Math.min(1, progress * 1.4)} />
        </div>
      </div>
      <div style={{ flex: 1, padding: '16px 24px 0', display: 'flex', flexDirection: 'column', gap: 8 }}>
        <div className="eyebrow">· Recent guesses</div>
        {[
          { p: LP_PLAYERS[0], g: 'tower' },
          { p: LP_PLAYERS[2], g: 'rocket' },
          { p: LP_PLAYERS[5], g: 'lighthouse!', hit: true },
        ].map((row, i) => (
          <div key={i} style={{
            display: 'flex', gap: 10, alignItems: 'center',
            padding: '8px 12px', borderRadius: 8,
            background: row.hit ? 'var(--olive)' : 'transparent',
            color: row.hit ? '#FFFCF6' : 'var(--ink)',
            border: '1px solid ' + (row.hit ? 'var(--olive)' : 'var(--rule)'),
          }}>
            <Avatar player={row.p} size={22} />
            <span style={{ fontSize: 14 }}>{row.p.name}</span>
            <span style={{ marginLeft: 'auto', fontStyle: 'italic' }}>"{row.g}"</span>
          </div>
        ))}
      </div>
      <div style={{ padding: '12px 24px 20px' }}>
        <div style={{
          display: 'flex', alignItems: 'center', gap: 10,
          padding: '14px 16px', border: '1px solid var(--rule-2)', borderRadius: 12,
          background: 'var(--paper)',
        }}>
          <input
            placeholder="Type your guess…"
            style={{
              flex: 1, border: 'none', background: 'transparent', outline: 'none',
              fontFamily: 'inherit', fontSize: 16, color: 'var(--ink)',
            }}
          />
          <button className="btn btn-primary" style={{ padding: '8px 14px', fontSize: 13 }}>Guess</button>
        </div>
      </div>
    </div>
  );
}

function PhoneTaboo({ progress, me = LP_PLAYERS[2] }) {
  const t = LP_TABOO;
  return (
    <div className="phone-content" style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
      <PhoneHeader left="TABOO · YOUR TURN" right={<span className="num">{Math.ceil((1-progress)*60)}s</span>} />
      <div style={{ padding: '0 24px 12px' }}>
        <div className="progress"><div className="progress-fill" style={{ width: `${(1 - progress) * 100}%` }} /></div>
      </div>
      <div style={{
        margin: '0 24px',
        flex: 1,
        background: 'var(--paper)',
        border: '2px solid var(--ink)',
        borderRadius: 8,
        padding: 24,
        display: 'flex',
        flexDirection: 'column',
        boxShadow: 'var(--shadow)',
      }}>
        <div className="eyebrow" style={{ marginBottom: 12 }}>· Get your team to say</div>
        <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          <div className="display" style={{ fontSize: 56, fontStyle: 'italic', textAlign: 'center', lineHeight: 1 }}>
            {t.word}
          </div>
        </div>
        <div className="hr-ink" style={{ margin: '16px 0' }} />
        <div className="eyebrow" style={{ marginBottom: 8 }}>· Cannot say</div>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
          {t.forbidden.map(w => (
            <span key={w} style={{
              padding: '6px 12px',
              border: '1px solid var(--accent)',
              color: 'var(--accent)',
              borderRadius: 100, fontSize: 13,
            }}>{w}</span>
          ))}
        </div>
      </div>
      <div style={{ padding: '16px 24px 20px', display: 'flex', gap: 10 }}>
        <button className="btn btn-ghost" style={{ flex: 1 }}>Skip</button>
        <button className="btn btn-primary" style={{ flex: 2 }}>Got it ✓</button>
      </div>
    </div>
  );
}

function PhoneWhispers({ progress, me = LP_PLAYERS[2] }) {
  const w = LP_WHISPERS;
  return (
    <div className="phone-content" style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
      <PhoneHeader left="WHISPERS · YOUR TURN" right={<span className="num">{Math.ceil((1-progress)*30)}s</span>} />
      <div style={{ padding: '0 24px 12px' }}>
        <div className="progress"><div className="progress-fill" style={{ width: `${(1 - progress) * 100}%` }} /></div>
      </div>
      <div style={{ flex: 1, padding: '16px 24px', display: 'flex', flexDirection: 'column' }}>
        <div className="eyebrow" style={{ marginBottom: 8 }}>· Asha whispered to you</div>
        <div className="display" style={{ fontSize: 22, lineHeight: 1.25, fontStyle: 'italic', marginBottom: 24 }}>
          "{w.chain[2].text}"
        </div>
        <div className="hr-ink" style={{ marginBottom: 16 }} />
        <div className="eyebrow" style={{ marginBottom: 8 }}>· Now whisper to Cleo</div>
        <div style={{
          flex: 1,
          background: 'var(--paper)',
          border: '1px solid var(--rule-2)',
          borderRadius: 6,
          padding: 14,
        }}>
          <div style={{
            fontSize: 16,
            color: 'var(--ink-mute)',
            fontStyle: 'italic',
          }}>Penguin in jacket likes coffee on Tuesdays.</div>
        </div>
      </div>
      <div style={{ padding: '0 24px 20px' }}>
        <button className="btn btn-primary" style={{ width: '100%' }}>Pass it on →</button>
      </div>
    </div>
  );
}

function PhoneLeaderboard({ me = LP_PLAYERS[3] }) {
  return (
    <div className="phone-content" style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
      <PhoneHeader left="STANDINGS" right="Q3 / 10" />
      <div style={{ padding: '16px 24px 0', textAlign: 'center' }}>
        <div className="eyebrow">Your position</div>
        <div className="display" style={{ fontSize: 96, lineHeight: 1, color: 'var(--accent)' }}>
          #03
        </div>
        <div className="display num" style={{ fontSize: 28, color: 'var(--ink)' }}>2,340</div>
        <div className="eyebrow" style={{ marginTop: 4 }}>+ 880 this round · climbed 1 spot</div>
      </div>
      <div style={{ flex: 1, padding: '24px 24px 16px', display: 'flex', flexDirection: 'column', gap: 8 }}>
        <div className="eyebrow">· Top of the table</div>
        {LP_LIVE_SCORES.slice(0, 5).map((s, i) => {
          const player = LP_PLAYERS.find(p => p.name === s.name);
          const isMe = s.name === me.name;
          return (
            <div key={s.name} style={{
              display: 'flex', alignItems: 'center', gap: 10,
              padding: '10px 12px',
              background: isMe ? 'var(--accent)' : 'var(--paper)',
              color: isMe ? 'var(--accent-ink)' : 'var(--ink)',
              border: '1px solid ' + (isMe ? 'var(--accent)' : 'var(--rule)'),
              borderRadius: 10,
            }}>
              <span className="eyebrow num" style={{ width: 24, color: 'inherit', opacity: 0.7 }}>{String(i + 1).padStart(2, '0')}</span>
              <Avatar player={player} size={28} />
              <span style={{ fontSize: 15, fontWeight: 500 }}>{s.name}</span>
              <span className="display num" style={{ marginLeft: 'auto', fontSize: 18 }}>{s.score.toLocaleString()}</span>
            </div>
          );
        })}
      </div>
      <div style={{ padding: '0 24px 20px' }}>
        <div className="eyebrow lp-pulse" style={{ textAlign: 'center' }}>· · · next question loading</div>
      </div>
    </div>
  );
}

function PhonePodium({ me = LP_PLAYERS[3] }) {
  const myRank = LP_FINAL_SCORES.findIndex(s => s.name === me.name) + 1 || 4;
  const myScore = LP_FINAL_SCORES.find(s => s.name === me.name)?.score || 6510;
  return (
    <div className="phone-content" style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
      <PhoneHeader left="FINAL · TRIVIA" right="GAME OVER" />
      <div style={{ padding: '16px 24px 8px', textAlign: 'center' }}>
        <div className="eyebrow">You finished</div>
        <div className="display" style={{ fontSize: 110, lineHeight: 0.95, color: 'var(--accent)' }}>
          #{String(myRank).padStart(2, '0')}
        </div>
        <div className="display num" style={{ fontSize: 30 }}>{myScore.toLocaleString()}</div>
      </div>
      <div style={{ flex: 1, padding: '24px 24px 12px', display: 'flex', flexDirection: 'column', gap: 16 }}>
        <div>
          <div className="eyebrow" style={{ marginBottom: 8 }}>· Podium</div>
          <div style={{ display: 'flex', gap: 8 }}>
            {LP_FINAL_SCORES.slice(0, 3).map((s, i) => {
              const player = LP_PLAYERS.find(p => p.name === s.name);
              return (
                <div key={s.name} style={{
                  flex: 1, textAlign: 'center', padding: 12,
                  border: '1px solid ' + (i === 0 ? 'var(--accent)' : 'var(--rule)'),
                  background: i === 0 ? 'var(--accent)' : 'var(--paper)',
                  color: i === 0 ? 'var(--accent-ink)' : 'var(--ink)',
                  borderRadius: 10,
                }}>
                  <Avatar player={player} size={36} />
                  <div className="display num" style={{ fontSize: 22, marginTop: 4 }}>{i === 0 ? 'I' : i === 1 ? 'II' : 'III'}</div>
                  <div style={{ fontSize: 13, fontWeight: 600, marginTop: 2 }}>{s.name}</div>
                </div>
              );
            })}
          </div>
        </div>
        <div>
          <div className="eyebrow" style={{ marginBottom: 8 }}>· You picked up</div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            <div style={{ display: 'flex', gap: 10, alignItems: 'center', padding: '8px 12px', border: '1px solid var(--rule)', borderRadius: 8 }}>
              <span className="eyebrow">Award</span>
              <span style={{ fontSize: 14, fontWeight: 500 }}>Fastest Finger</span>
              <span className="display num" style={{ marginLeft: 'auto', color: 'var(--accent)' }}>+ 150</span>
            </div>
            <div style={{ display: 'flex', gap: 10, alignItems: 'center', padding: '8px 12px', border: '1px solid var(--rule)', borderRadius: 8 }}>
              <span className="eyebrow">Streak</span>
              <span style={{ fontSize: 14, fontWeight: 500 }}>3 in a row · Q4-6</span>
              <span className="display num" style={{ marginLeft: 'auto', color: 'var(--accent)' }}>+ 300</span>
            </div>
          </div>
        </div>
      </div>
      <div style={{ padding: '0 24px 20px', display: 'flex', gap: 8 }}>
        <button className="btn btn-ghost" style={{ flex: 1, fontSize: 13 }}>Recap</button>
        <button className="btn btn-primary" style={{ flex: 2 }}>Play again</button>
      </div>
    </div>
  );
}

// Game library — TV "home" screen (used in the canvas)
function TVLibrary() {
  return (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column', position: 'relative', zIndex: 1 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', padding: '32px 56px 0' }}>
        <div className="eyebrow" style={{ display: 'flex', gap: 24 }}>
          <span>LocalPlay</span>
          <span>·</span>
          <span>EVENING SESSION · 8 PEOPLE · ROOM PLAY42</span>
        </div>
        <div className="eyebrow" style={{ display: 'flex', gap: 12 }}>
          <span>HOST · MIRA</span>
          <span>·</span>
          <span>240 SPARKS</span>
        </div>
      </div>
      <div style={{ padding: '24px 56px 16px' }}>
        <h1 className="display" style={{ fontSize: 80, lineHeight: 0.95, letterSpacing: '-0.03em' }}>
          Pick a <span style={{ fontStyle: 'italic', color: 'var(--accent)' }}>game</span>.
        </h1>
        <div className="eyebrow" style={{ marginTop: 12 }}>· Six rooms, all played locally. Phones become controllers. No accounts required.</div>
      </div>
      <div style={{ flex: 1, padding: '24px 56px 48px', display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 16 }}>
        {LP_GAMES.map((g, i) => (
          <div key={g.id} style={{
            border: '1px solid var(--rule-2)',
            background: 'var(--paper)',
            padding: 20,
            display: 'flex',
            flexDirection: 'column',
            gap: 12,
            position: 'relative',
            borderRadius: 'var(--card-radius, 4px)',
            cursor: 'pointer',
            transition: 'transform 0.15s ease',
          }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
              <span className="eyebrow num">{g.chapter}</span>
              {g.badge && <span className="chip chip-accent">{g.badge}</span>}
            </div>
            <div className="display" style={{ fontSize: 36, lineHeight: 1, fontStyle: i === 0 ? 'italic' : 'normal' }}>
              {g.name}
            </div>
            <p style={{ fontSize: 14, color: 'var(--ink-2)', lineHeight: 1.35, minHeight: 38 }}>{g.tagline}</p>
            <div className="hr" style={{ marginTop: 'auto' }} />
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
              <div className="eyebrow" style={{ display: 'flex', gap: 8 }}>
                <span>{g.players}</span>
                <span>·</span>
                <span>{g.pace}</span>
              </div>
              <div style={{ fontFamily: 'var(--font-display)', fontSize: 20, fontStyle: 'italic', color: 'var(--accent)' }}>→</div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────
// Theme-specific Playground avatar swap (player-hued)
// ─────────────────────────────────────────────────────────────
// "You" highlight — a ring/glow rather than a fill swap, so the player's
// chosen emoji always reads clearly on top.
const _styleAdd = document.createElement('style');
_styleAdd.textContent = `
  .theme-salon .av[data-you="true"] {
    box-shadow: 0 0 0 2px var(--bg), 0 0 0 3.5px var(--accent);
  }
  .theme-velvet .av[data-you="true"] {
    box-shadow: 0 0 0 2px var(--accent), 0 0 24px rgba(255,46,122,0.65);
  }
  .theme-playground .av[data-you="true"] {
    box-shadow: 0 0 0 2px var(--bg), 0 0 0 4.5px var(--accent);
  }
  .theme-arcade .av[data-you="true"] {
    box-shadow: 0 0 0 2px var(--bg), 0 0 0 3.5px var(--accent), 0 0 24px rgba(56,255,107,0.55);
  }
  .theme-garden .av[data-you="true"] {
    box-shadow: 0 0 0 2px var(--bg), 0 0 0 3.5px var(--accent);
  }
`;
document.head.appendChild(_styleAdd);

Object.assign(window, {
  Avatar, FauxQR, PlayerChip,
  TVHeader, TVLobby, TVIntro, TVQuiz, TVWmlt, TVPictionary, TVTaboo, TVWhispers,
  TVLeaderboard, TVPodium, TVLibrary,
  PhoneLobby, PhoneIntro, PhoneQuiz, PhoneWmlt, PhonePictionary, PhoneTaboo, PhoneWhispers,
  PhoneLeaderboard, PhonePodium,
});
