# SPEC-SHARE-CARD — Shareable result cards

Status: **Implemented** — v1 OG text + static image live; snapshots persisted to DB (2026-07-21)
Owner: Avi
Related: `SPEC-ANALYTICS.md`, `SPEC-REFERRAL.md` (share plumbing), `backend/main.py` (SPA serving, `PUBLIC_BASE_URL`)

---

## 0. Goal

After a game, let the host share a result — "I scored N in Revelry Games!" — as a link that unfurls with
rich Open Graph preview (title/description/image) in iMessage, WhatsApp, Slack, etc. Drives installs and
pairs with the referral loop. **v1 = dynamic OG text + a static branded image** (fully device-free);
dynamic per-result image generation is deferred.

## 1. Scope decision (why static image)

| Option | Unfurl quality | Effort / risk | Verdict |
|---|---|---|---|
| Dynamic OG **text** + static branded image | Title/desc are per-result (score, winner); image is the brand card | Trivial, no image pipeline, works offline of any renderer | **v1** |
| Dynamic per-result **image** (render score onto a card) | Fully personalized image | Needs an SVG→PNG/headless render path on the server; heavier, a device/runtime dep | **Deferred** (logged) |

The unfurl still shows the winner + score in the **title/description**, which is what humans read; the image
is the recognizable brand card. Good enough to ship and measure.

## 2. Backend

### Result snapshot store (DB-persisted + in-memory cache + TTL)
On game completion, the host can mint a share token. A minimal snapshot is stored keyed by a short opaque
token: `{game_type, winner, top_score, player_count, created_at}`. TTL = `SHARE_TTL_SECONDS` (7 days).
**Durable:** snapshots are written to the `share_snapshots` table (`db.save/get_share_snapshot`, mirrored in
`supabase_db`, migration `20260721T030000_share_snapshots{,_gamma}.sql`) so a link resolves after a process
restart / on any instance — with an in-memory write-through cache for the hot path. DB access is best-effort:
if it fails (e.g. Supabase before the migration is applied), `share.py` degrades to memory-only and never
500s a share. In-memory max-count eviction still bounds the cache; the DB store is TTL-pruned on write.
No PII beyond a chosen nickname.

### `POST /share/game` `{leaderboard-ish minimal payload}` → `{token, share_url}`
Host-authenticated enough to prevent spam: rate-limited (reuse `_check_rate_limit`), sanitize nickname via
the existing HTML/control-char stripping. `share_url = f"{PUBLIC_BASE_URL}/share/game/{token}"`.

### `GET /share/game/{token}` → HTML
- Unknown/expired token → a generic branded page (200, no result), so stale links still look fine.
- Returns a small self-contained HTML doc with OG + Twitter meta:
  - `og:title` = `"{winner} won with {top_score} in Revelry Games!"` (or generic if no snapshot)
  - `og:description` = `"{player_count} players • {pretty game_type}. Start your own AI game night."`
  - `og:image` = a **static** asset (existing `marketing/play-store/feature-graphic.png` copied to a served
    static path, or `frontend/public/icons/` — must be a stable absolute URL under `PUBLIC_BASE_URL`).
  - `og:url` = the canonical share URL; a `<meta http-equiv=refresh>` / JS redirect + a visible CTA button to
    the app (`PUBLIC_BASE_URL`) so a human who clicks lands in the app.
- All interpolated values HTML-escaped (defense-in-depth even though sanitized on store).

## 3. Frontend

- **Podium** (`SpectatorPage` PODIUM and/or `OrganizerPage` results): a **Share results** button. On tap:
  `POST /share/game` with the final leaderboard summary → get `share_url` → `@capacitor/share` /
  `navigator.share` (reuse LobbyScreen pattern), clipboard fallback. Fire `share_result_clicked{game_type}`.
- Hidden in `hostAppMode` (Revelry-managed) to match existing share-link gating.

## 4. Config
| Var | Default | Notes |
|---|---|---|
| `SHARE_TTL_SECONDS` | 604800 (7d) | snapshot lifetime |
| `MAX_SHARE_SNAPSHOTS` | 500 | eviction cap |
| `PUBLIC_BASE_URL` | (existing) | absolute base for share + og:image URLs; if unset, feature degrades to clipboard-only relative link |

## 5. Testing (`backend/tests/test_share_card.py`)
- create snapshot → `GET` returns HTML containing escaped title/description with the score; unknown token →
  generic page (200); XSS attempt in nickname is escaped in output; TTL/eviction prunes; rate limit on create.

## 6. Deferred / future
- Dynamic per-result OG image (SVG→PNG). (Persisting snapshots to DB for durable links — **done** 2026-07-21.)

## 7. Files touched
- `backend/config.py` (share consts), `backend/share.py` (new: snapshot store + HTML render) **or** inline in
  `main.py`, `backend/main.py` (2 routes + static og image path), `backend/tests/test_share_card.py`.
- Frontend: podium Share button in `SpectatorPage`/`OrganizerPage`, reuse share util.
- Copy a static branded image into a served static location for `og:image`.
