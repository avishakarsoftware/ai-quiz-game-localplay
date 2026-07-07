# Store Asset Sizes — Revelry Quiz/Games

Reference for App Store + Google Play screenshot/asset dimensions, and the exact Playwright
`viewport × deviceScaleFactor` recipe to hit each pixel size (image px = viewport × dsf).

> Capture rule: screenshots must be **opaque** (no transparency/alpha) for both stores. Our screens
> are full-bleed on the Velvet background, so they're already opaque. Capture as PNG.

---

## Apple App Store (iOS)

Apple requires at least the largest iPhone set; if the app supports iPad, the largest iPad set too.
Smaller device sizes are auto-scaled from these. 3–10 screenshots per set; PNG/JPEG, no alpha.

| Device tier | Portrait px | Playwright viewport @ dsf | Required? |
|---|---|---|---|
| iPhone 6.9" (16 Pro Max) | **1320 × 2868** | 440 × 956 @ 3 | Provide this **or** 6.7" |
| iPhone 6.7" (15 Pro Max / 14 Plus) | **1290 × 2796** | 430 × 932 @ 3 | Widely accepted as the iPhone set |
| iPhone 6.5" (legacy) | 1242 × 2688 | 414 × 896 @ 3 | Optional |
| iPhone 5.5" (legacy) | 1242 × 2208 | 414 × 736 @ 3 | Optional/deprecated |
| iPad 13" (M4 iPad Pro) | **2064 × 2752** | 1032 × 1376 @ 2 | Provide this **or** 12.9" (if iPad supported) |
| iPad 12.9" (iPad Pro) | **2048 × 2732** | 1024 × 1366 @ 2 | iPad set |

**Practical minimum to ship:** iPhone **1290 × 2796** + iPad **2048 × 2732**.

---

## Google Play (Android)

2–8 phone screenshots required; tablet optional but recommended. PNG/JPEG, no alpha, each side
**320–3840 px**, aspect ratio **max 2:1** (so Apple's 2.17:1 iPhone shots are **too tall** — capture
Google phone separately at ≤2:1).

| Asset | Recommended px | Playwright viewport @ dsf | Notes |
|---|---|---|---|
| Phone | **1080 × 2160** (2:1) or 1080 × 1920 | 360 × 720 @ 3  (or 360 × 640 @ 3) | min 2, max 8 |
| 7" tablet | 1200 × 1920 | 600 × 960 @ 2 | up to 8 |
| 10" tablet | 1600 × 2560 | 800 × 1280 @ 2 | up to 8 |
| **Feature graphic** (required) | **1024 × 500** | n/a (design asset) | no alpha |
| App icon | 512 × 512 | n/a | 32-bit PNG w/ alpha |

> Google tablet can reuse the Apple iPad captures (2048 × 2732 is 0.75:1, within range) if you don't
> want a separate tablet pass.

---

## Capture matrix (what we render per target)

Same flows, different viewport/dsf. Folders: `marketing/play-store/` (Android), `marketing/app-store/` (iOS).

| Target | viewport | dsf | image px |
|---|---|---|---|
| iOS iPhone 6.7" | 430 × 932 | 3 | 1290 × 2796 |
| iOS iPad 12.9" | 1024 × 1366 | 2 | 2048 × 2732 |
| Android phone | 360 × 720 | 3 | 1080 × 2160 |
| Android 10" tablet | 800 × 1280 | 2 | 1600 × 2560 |

Capture against **prod** (`PLAYWRIGHT_BASE_URL=https://games.revelryapp.me`) so visible join URLs are
the real public domain. The Capacitor native apps render this same web bundle, so browser captures
represent the native apps.

## Captured "games in action" set (`marketing/gameplay/`, 1600×900 landscape "TV"/spectator)
- `01-question.png` — live quiz question with A/B/C/D options
- `02-answer-reveal.png` — correct answer highlighted (instant feedback)
- `03-leaderboard.png` — multiplayer standings with scores (Maya 973 / Leo 973 / Ada 0)
- `04-podium.png` — "Final Results" / champion podium with crown + confetti
- Captured by driving a real quiz over WebSockets against gamma (host-agnostic — no URL shown). The
  SpectatorPage correctly waits for PODIUM on the final question (no app bug); the podium capture just
  needed the driver's `waitFor` to consume matched messages so Q2's waits weren't matching stale Q1 events.

## Screens to capture (the "games in action" set)
1. Catalog — "Choose a Game" (variety)
2. AI Quiz setup — topic / difficulty / length
3. Lobby — QR + room code ("everyone joins from their phone")
4. Gameplay — a live quiz question (player view) + spectator/TV view
5. Podium — winner celebration
6. Variety — Who's Most Likely To and Drawing in action
7. Get Sparks — purchase modal (also the IAP review screenshot)

## Design assets (not screenshots)
- [x] Google Play **feature graphic** 1024 × 500 → `marketing/play-store/feature-graphic.png`
      (source: `/tmp/fg/feature.html`; rendered 2x then downscaled). Apple has no feature-graphic equivalent.
- [x] App icon 512 × 512 / 1024 → `frontend/public/icons/icon-512.png`, `icon-1024.png` (existing)
