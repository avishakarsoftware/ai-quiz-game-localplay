# LocalPlay Image Game Platform Spec

## Purpose

Build image support as a reusable LocalPlay platform capability, then use it to unlock multiple image-centric game modes.

This is not one game. It is the shared media layer for games that need generated images, uploaded photos, visual prompts, image questions, caption rounds, or TV-first visual clues.

The first product goal is simple: make images reliable enough that hosts can confidently run visual rounds on phones and TV without broken assets, oversized payloads, or one-off per-game hacks.

## Current State

LocalPlay already has partial image support:

- Quiz questions can include `image_prompt` and `image_url`.
- The organizer can call `/quiz/generate-images`.
- `image_engine.py` can talk to a local Stable Diffusion server and returns base64 PNG data.
- Stable Diffusion is a local/development capability only; gamma and production should not assume it is available.
- Generated quiz images are stored in process memory as `quiz_images`.
- `/quiz/{quiz_id}/image/{question_id}` serves generated image bytes.
- `/media/status` and `/media/{asset_id}` now exist as the Phase 0 shared media namespace.
- Quiz image generation now also creates in-memory media assets and attaches `/media/{asset_id}` URLs when rooms start.
- Host upload signing exists at `POST /media/upload-url`, with finalize at `POST /media/{asset_id}/finalize`.
- `ionos/media/upload.php` is checked into the repo for deployment to the LocalPlay media host.
- Uploaded custom quiz image files are stored on IONOS; metadata is stored through the LocalPlay DB layer.
- Host, player, and spectator question cards display image content through the reusable `GameImage` component.
- Remote config has an `enable_image_generation` feature flag.

Current limitations:

- Image generation depends on a local Stable Diffusion endpoint and is not reliable on the current VM unless that service is running.
- Generated images are not yet persisted in Supabase/IONOS and still use in-memory image storage.
- Phase 0 images are still stored as base64 strings in backend memory.
- No provider abstraction exists for Gemini image generation, Gemini vision analysis, or future storage backends.
- Upload safety currently validates MIME, size, HMAC, expiry, and path shape; decoded dimension checks, EXIF stripping, normalization, moderation, delete, and cleanup remain backlog.
- Gamma and production custom quiz images should use host upload plus persisted media storage, not local Stable Diffusion.

## Goals

- Provide a reusable image asset model for quizzes, drawing-adjacent games, caption games, and future visual modes.
- Support both AI-generated images and host-uploaded images.
- Keep game content and image assets owned by a wallet/session.
- Avoid exposing Supabase service-role keys or IONOS upload secrets to the browser.
- Work in same-origin backend-served SPA mode and IONOS-hosted frontend mode.
- Keep the initial VM deployment safe and simple.
- Make future Cloud Run migration easier by removing in-memory image dependencies.
- Reuse image infrastructure across many games instead of building one-off endpoints.

## Non-Goals For V1

- No public image gallery.
- No social sharing of uploaded/generated images.
- No player photo submissions except if a specific game mode explicitly requires it in a later phase.
- No permanent storage guarantee for user uploads without a retention policy.
- No AI moderation of live drawings.
- No high-volume or unlimited image generation.
- No direct browser writes to Supabase or arbitrary public storage.
- No separate Firebase dependency.

## Product Principle

Image games should remain party-friendly:

- Visuals should be legible on a living-room TV.
- Phones should show enough context to answer without pinching.
- Host setup should feel like choosing a vibe, not configuring a media pipeline.
- If image generation fails, the game should degrade gracefully or clearly block before the room starts.
- Uploaded photos should be treated as private party content by default.

## Recommended Phasing

### Phase 0: Stabilize Existing Quiz Images

Purpose: make the already-built quiz image feature less fragile without introducing new game modes.

Scope:

- Introduce a shared `ImageAsset` model.
- Add a reusable frontend `GameImage` component.
- Keep existing `/quiz/generate-images` behavior but internally route through the new asset layer.
- Keep in-memory fallback during development.
- Add stronger image serving headers, size checks, and ownership checks.

Phase 0 can be done before object storage, but it should shape the code as if object storage is coming.

### Phase 1: Persistent Image Assets

Purpose: make image assets survive process restarts and support Cloud Run later.

Scope:

- Store image files on the IONOS media CDN, matching the Revelry media-upload pattern.
- Store image metadata in `games_generated_content` or a new `games_media_assets` table in Supabase.
- Use prefix isolation:
  - Production tables: `games_*`.
  - Gamma tables: `games_gamma_*`.
  - Production/gamma media paths must include an environment segment so assets cannot collide.
- Backend signs upload paths so the browser can upload directly to IONOS without giving it any server secret.
- Backend can proxy, redirect, or return CDN URLs for reads, while `/media/{asset_id}` remains the stable app-facing asset URL.
- Add cleanup jobs or manual retention scripts.

### Phase 2: Host Uploads

Purpose: unlock Photo Round and party-photo games.

Scope:

- Add host-only upload endpoint.
- Validate MIME type, dimensions, and file size.
- Strip EXIF metadata.
- Store original or normalized image.
- Generate thumbnails if needed.
- Attach uploads to generated game content and wallet ownership.

### Phase 3: First Image-Native Game Mode

Recommended first mode: **Image Quiz** or **Photo Round**.

Reason:

- They reuse quiz mechanics.
- They need the image platform but do not require new answer/voting state machines.
- They give immediate product value while exercising the asset layer.

### Phase 4: Creative And Vision-Based Modes

Build once the asset layer is trustworthy:

- Meme Caption.
- AI Art Guessing.
- Rebus / Emoji Puzzles.
- What's Wrong With This Picture?
- Spot the Difference.
- Eye Spy / room-photo games.

## Image Asset Model

Use a common asset shape across game content:

```ts
export interface ImageAsset {
  id: string;
  owner_wallet_id: string;
  source: 'generated' | 'upload' | 'template' | 'external';
  provider?: 'stable_diffusion' | 'gemini' | 'host_upload' | 'template';
  status: 'pending' | 'ready' | 'failed' | 'deleted';
  mime_type: 'image/png' | 'image/jpeg' | 'image/webp';
  width: number;
  height: number;
  bytes: number;
  url: string;
  thumbnail_url?: string;
  prompt?: string;
  alt_text?: string;
  safety_status?: 'unchecked' | 'passed' | 'blocked';
  created_at: number;
  expires_at?: number;
}
```

Rules:

- `url` must be an app-controlled URL, such as `/media/{asset_id}` or a generated IONOS CDN URL.
- `prompt` may be omitted for uploaded photos.
- `alt_text` should be generated or provided for accessibility where possible.
- `status='failed'` should include an internal error log, but not expose provider internals to players.
- Uploaded images should not store EXIF metadata.

## Storage Design

### Tables

Prefer a dedicated media table rather than overloading every game table:

```sql
CREATE TABLE games_media_assets (
  id TEXT PRIMARY KEY,
  owner_wallet_id TEXT NOT NULL,
  source TEXT NOT NULL CHECK (source IN ('generated', 'upload', 'template', 'external')),
  provider TEXT,
  status TEXT NOT NULL CHECK (status IN ('pending', 'ready', 'failed', 'deleted')),
  mime_type TEXT NOT NULL,
  width INTEGER NOT NULL,
  height INTEGER NOT NULL,
  bytes INTEGER NOT NULL,
  storage_backend TEXT,
  storage_path TEXT,
  public_url TEXT,
  prompt TEXT,
  alt_text TEXT,
  safety_status TEXT NOT NULL DEFAULT 'unchecked',
  metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at BIGINT NOT NULL,
  expires_at BIGINT
);

CREATE INDEX idx_games_media_assets_owner
  ON games_media_assets(owner_wallet_id, created_at DESC);

CREATE INDEX idx_games_media_assets_status
  ON games_media_assets(status, created_at DESC);
```

Gamma equivalent:

```sql
CREATE TABLE games_gamma_media_assets (...same columns...);
```

This can also be represented as `games_generated_content` rows with `content_type='media_asset'`, but a dedicated table is cleaner once uploads exist.

### IONOS Media Storage

Image files should be stored on IONOS, not Supabase Storage.

Use the same high-level pattern as Revelry:

1. Frontend asks the LocalPlay backend for a signed upload target.
2. Backend validates wallet/content ownership and creates an HMAC-signed relative path with a short expiry using `MEDIA_UPLOAD_SECRET`.
3. Frontend posts the file directly to an IONOS PHP handler.
4. The PHP handler validates CORS, HMAC, expiry, path prefix, extension, MIME type, and upload status, then writes the file to disk.
5. Backend stores/updates metadata in `games_media_assets` and returns a stable `ImageAsset`.

Recommended IONOS layout:

```text
Public base URL: https://media.revelryapp.me/apps/localplay/

IONOS server root:
~/revelryapp/media/apps/localplay/

prod/
  uploads/{wallet_prefix}/YYYY/MM/DD/{asset_id}.webp
  generated/{asset_id}.webp
  thumbs/{asset_id}.webp

gamma/
  uploads/{wallet_prefix}/YYYY/MM/DD/{asset_id}.webp
  generated/{asset_id}.webp
  thumbs/{asset_id}.webp
```

The IONOS PHP handler should live in this repo before deployment, e.g. `ionos/media/upload.php`, and be deployed to:

```text
~/revelryapp/media/apps/localplay/upload.php
~/revelryapp/media/apps/localplay/delete.php
~/revelryapp/media/apps/localplay/.htaccess
~/revelryapp/media/apps/localplay/.upload_secret
```

Storage access:

- Uploads require signed paths generated by the backend.
- IONOS file reads are CDN-style public URLs with unguessable UUID paths.
- Treat paths as bearer URLs: do not expose directory listings, do not use sequential names, and do not store sensitive images that require revocable per-view authorization.
- Backend should store `storage_path` and `public_url` in metadata.
- Backend may serve `/media/{asset_id}` by redirecting to the IONOS URL, proxying it, or returning the URL in API payloads.
- The `.htaccess` for reads should set CORS headers that let the IONOS frontend, backend-served gamma/prod, and native webviews display/fetch images.
- Delete should be best-effort through a signed IONOS delete handler plus a metadata soft-delete.

## API Surface

### Status

Implemented in Phase 0. This is the lightweight capability endpoint for feature
checks and smoke tests.

```http
GET /media/status
```

Response:

```json
{
  "upload_available": false,
  "generation_available": true,
  "providers": [
    {"id": "stable_diffusion", "name": "Stable Diffusion", "available": true}
  ],
  "max_upload_bytes": 5242880,
  "allowed_mime_types": ["image/png", "image/jpeg", "image/webp"],
  "storage_backend": "memory"
}
```

### Generate Image Asset

Future Phase 1/2 endpoint. Phase 0 does not expose standalone generation here;
existing quiz image generation still enters through `/quiz/generate-images` and
now stores the result as an in-memory media asset.

```http
POST /media/generate
```

Request:

```json
{
  "prompt": "A whimsical birthday cake shaped like a rocket",
  "style": "party illustration",
  "aspect_ratio": "16:9",
  "provider": "gemini_image",
  "purpose": "image_quiz"
}
```

Response:

```json
{
  "asset": {
    "id": "img_abc123",
    "status": "ready",
    "url": "/media/img_abc123",
    "thumbnail_url": "/media/img_abc123?variant=thumb",
    "width": 1280,
    "height": 720,
    "mime_type": "image/webp"
  }
}
```

### Upload Image Asset

Implemented for custom quiz question images. The API follows the Revelry signed IONOS upload pattern.

```http
POST /media/upload-url
```

Request:

```json
{
  "filename": "cake.jpg",
  "mime_type": "image/jpeg",
  "bytes": 123456,
  "purpose": "custom_quiz_question"
}
```

Response:

```json
{
  "asset": {
    "id": "img_abc123",
    "owner_wallet_id": "wallet...",
    "storage_backend": "ionos",
    "storage_path": "gamma/uploads/wallet.../2026/05/20/img_abc123.jpg",
    "public_url": "https://media.revelryapp.me/apps/localplay/gamma/uploads/wallet.../2026/05/20/img_abc123.jpg",
    "status": "pending",
    "mime_type": "image/jpeg"
  },
  "upload": {
    "url": "https://media.revelryapp.me/apps/localplay/upload.php",
    "fields": {
      "path": "gamma/uploads/wallet.../2026/05/20/img_abc123.jpg",
      "expires": "1779290300",
      "mime_type": "image/jpeg",
      "bytes": "123456",
      "token": "hmac"
    }
  }
}
```

The frontend then uploads `multipart/form-data` directly to IONOS:

```http
POST https://media.revelryapp.me/apps/localplay/upload.php
Content-Type: multipart/form-data
```

Fields:

- `file`: required.
- `path`: backend-generated relative path.
- `expires`: backend-generated expiry.
- `mime_type`: backend-validated MIME type.
- `bytes`: backend-validated size.
- `token`: backend-generated HMAC.

After upload succeeds, the frontend calls a backend finalize endpoint so metadata can move from `pending` to `ready`:

```http
POST /media/{asset_id}/finalize
```

The backend may also finalize lazily by checking the expected IONOS URL on first attach/materialize.

Legacy/direct backend multipart upload can exist for local development, but the production/gamma path should be signed browser-to-IONOS upload.

```http
POST /media/upload
Content-Type: multipart/form-data
```

Fields:

- `file`: required.
- `purpose`: optional, e.g. `photo_round`.
- `alt_text`: optional.

Backend behavior:

- Authenticate wallet.
- Enforce size limit.
- Validate content sniffing, not just extension.
- Decode image to verify dimensions.
- Strip EXIF.
- Normalize to WebP or JPEG.
- Store original only if product need is clear.
- Save image bytes to IONOS media storage, not Supabase Storage.
- Insert asset metadata.
- Return `ImageAsset`.

### Fetch Image Asset

Implemented in Phase 0 for generated quiz images stored by the in-memory media
store. Thumbnail variants are future work.

```http
GET /media/{asset_id}
GET /media/{asset_id}?variant=thumb
```

Rules:

- For generated game content currently attached to an active room, players/spectators may view it.
- For owner-only assets not attached to an active room, require wallet ownership.
- Return `404` for deleted/missing assets.
- If the asset is stored on IONOS, `/media/{asset_id}` may redirect to the CDN URL.
- Set appropriate cache headers:
  - Immutable generated assets: `Cache-Control: public, max-age=31536000, immutable` if URL is content-addressed.
  - Owner/private assets: `private, max-age=300`.

### Delete Image Asset

Future Phase 1/2 endpoint. Phase 0 assets are removed with in-memory quiz/room
eviction.

```http
DELETE /media/{asset_id}
```

Owner only. Marks metadata deleted and removes storage object if not attached to retained game history.
For IONOS-backed files, deletion should call a signed `delete.php` handler and tolerate missing files.

## Provider Architecture

Add `backend/media_engine.py`:

```py
class MediaProvider(Protocol):
    id: str
    async def is_available(self) -> bool: ...
    async def generate_image(self, prompt: str, *, aspect_ratio: str, style: str) -> GeneratedImage: ...
    async def analyze_image(self, image_bytes: bytes, *, instruction: str) -> dict: ...
```

Initial providers:

- `StableDiffusionProvider`: wraps existing `image_engine.py`.
- `GeminiImageProvider`: future image generation provider.
- `GeminiVisionProvider`: future image analysis for Photo Round / Eye Spy.
- `UploadProvider`: validates and stores host uploads.

Configuration:

```env
ENABLE_IMAGE_GENERATION=true
MEDIA_PUBLIC_BASE_URL=https://media.revelryapp.me/apps/localplay
MEDIA_UPLOAD_URL=https://media.revelryapp.me/apps/localplay/upload.php
MEDIA_UPLOAD_SECRET=<shared with IONOS .upload_secret>
MEDIA_PATH_PREFIX=prod
MEDIA_ALLOWED_MIME_TYPES=image/png,image/jpeg,image/webp
MEDIA_UPLOAD_TOKEN_TTL_SECONDS=900
MAX_IMAGE_SIZE_BYTES=2097152
MEDIA_MAX_GENERATED_BYTES=5242880
MEDIA_DEFAULT_PROVIDER=gemini_image
MEDIA_RETENTION_DAYS=30
```

Gamma:

```env
MEDIA_PATH_PREFIX=gamma
```

Do not use Gemma for image work. Gemini multimodal/image providers should be the default direction when using Google-hosted capabilities.

## Frontend Components

### `<GameImage>`

Reusable image display component.

Props:

```ts
interface GameImageProps {
  src: string;
  alt: string;
  aspect?: '16:9' | '4:3' | '1:1' | 'contain';
  mode?: 'question' | 'hero' | 'thumbnail' | 'tv';
  reveal?: boolean;
}
```

Responsibilities:

- Loading skeleton.
- Error state with clear retry/skip affordance for host screens.
- Object-fit rules appropriate for phone and TV.
- No text overlap on top of busy images unless a scrim is intentionally applied.
- Accessible alt text.
- Prevent layout shift with stable aspect ratio.
- Tap-to-fullscreen on phone where appropriate.

### Host Image Picker

Use in game generation/review screens:

- Generate image from prompt.
- Upload image.
- Pick from recent assets.
- Remove/replace image.
- Show provider availability.
- Show upload limits.

V1 can expose this only for Photo Round/Image Quiz.

### TV/Spectator Display

TV views should:

- Favor large 16:9 media with no crop surprises.
- Show answers/prompts below or beside the image, not over it unless designed for a specific game.
- Provide a safe fallback if image fails.
- Preload next-round image when possible.

## Game Content Schema Extensions

Keep image references generic:

```ts
interface VisualPrompt {
  image_asset_id?: string;
  image_url?: string;
  image_alt?: string;
  image_prompt?: string;
}
```

Quiz question extension:

```ts
interface QuizQuestion {
  id: number;
  text: string;
  options: string[];
  answer_index: number;
  image_prompt?: string;
  image_asset_id?: string;
  image_url?: string;
  image_alt?: string;
}
```

Caption/voting extension:

```ts
interface CaptionRound {
  id: number;
  image_asset_id: string;
  image_url: string;
  prompt: string;
  captions: CaptionSubmission[];
}
```

## Game Modes Enabled

### 1. Image Quiz

Core loop:

- Host enters topic/vibe.
- AI generates quiz questions plus image prompts.
- Host generates or uploads images for selected questions.
- Players answer multiple choice questions with the image visible.

Implementation fit:

- Reuses current quiz room lifecycle.
- Reuses `image_url`.
- Best first mode because it is mostly an extension of current Quiz.

V1 scope:

- Add "Image Quiz" toggle or template in Quiz prompt screen.
- Require at least one image before starting if host chose Image Quiz.
- Let host skip failed images and convert to text-only question.

### 2. Photo Round

Core loop:

- Host uploads 1-10 photos.
- AI generates questions about the photos, or host writes questions manually.
- Players answer quiz-style.

Implementation fit:

- Requires upload endpoint.
- Uses quiz mechanics.
- Needs optional Gemini vision analysis.

V1 scope:

- Host upload photos.
- Host writes text questions manually or uses simple prompt guidance.
- AI vision generation can be Phase 2.5.

### 3. Meme Caption

Core loop:

- Show an image.
- Players submit captions.
- Captions are revealed anonymously.
- Players vote for funniest/best.

Implementation fit:

- Reuses future "submit -> anonymous reveal -> vote" pattern from Caption This/Acronym Game.
- Uses image asset display.

V1 scope:

- Host selects/generated/uploaded image per round.
- Text submission.
- Vote on captions.
- Score by votes received.

### 4. AI Art Guessing

Core loop:

- AI generates an image from a hidden prompt.
- Players guess the original prompt/phrase.
- Closest exact or alias match scores.

Implementation fit:

- Reuses DrawingGame guess matching.
- No drawing canvas needed.

V1 scope:

- AI generates prompt/image pairs.
- Players type guesses.
- Use normalized answer + aliases.

Risk:

- Generated image may be too ambiguous. Host review should allow editing aliases or deleting bad rounds.

### 5. Rebus / Emoji Puzzles

Core loop:

- Show emoji or small visual components.
- Players guess the phrase.
- Fast rounds, time-based scoring.

Implementation fit:

- Can start emoji-only without image generation.
- Later can use image assets for richer rebus cards.

V1 scope:

- Emoji-only or text-symbol visual puzzles.
- Use `<GameImage>` only if a generated image is attached.

### 6. What's Wrong With This Picture?

Core loop:

- Show a scene with deliberate oddities.
- Players identify one or more oddities.
- Score by correct matches.

Implementation fit:

- Needs generated image plus known oddity list.
- Uses text input or multiple choice.

V1 recommendation:

- Do not build first. It depends on controllable image generation and reliable oddity metadata.

### 7. Spot the Difference

Core loop:

- Show two similar images.
- Players tap/click or type differences.
- Score by found differences.

Implementation fit:

- Needs paired image display and optionally coordinate-based answers.
- Harder than it looks because image-generation consistency is difficult.

V1 recommendation:

- Backlog until media storage, image pair display, and touch-coordinate answer support exist.

### 8. Eye Spy / Room Photo

Core loop:

- Host uploads/takes a room photo.
- AI vision generates questions.
- Players answer what they observe.

Implementation fit:

- Requires upload + vision provider.
- Strong "wow" factor but higher privacy/safety burden.

V1 recommendation:

- Build after Photo Round proves uploads and image display.

## Scoring Patterns

Image games should reuse existing scoring patterns:

- Quiz-style multiple choice: existing quiz scoring.
- Typed guess: DrawingGame normalized matching + time/speed scoring.
- Caption/voting: WMLT-like vote tally, but vote targets are submissions rather than players.
- Multi-answer oddity list: score per accepted item, cap repeated guesses.
- Coordinate tap: future mechanic for Spot the Difference.

Avoid introducing a new scoring engine per game. Add reusable scoring helpers when the second image mode needs the same pattern.

## Token / Spark Economy

Separate costs:

- Text-only game generation: current generation cost.
- Image generation: additional per-image cost.
- Host upload: no generation cost, but may have storage/vision analysis cost.
- Game start: existing room cost.

Recommended config:

```env
COST_IMAGE_GENERATE=3
COST_IMAGE_ANALYZE=2
MAX_IMAGES_PER_GAME_FREE=0
MAX_IMAGES_PER_GAME=20
```

Billing behavior:

- Charge image generation only after an image provider succeeds.
- Do not charge for failed image generation.
- If batch generation partially succeeds, charge only for successful assets.
- Use idempotency keys for image generation requests.
- Do not increment `lifetime_purchased` for admin grants or image refunds.

## Safety, Privacy, And Moderation

Uploaded photos:

- Strip EXIF metadata.
- Limit file size and dimensions.
- Restrict MIME types.
- Keep private by default in product UX and metadata.
- Provide delete controls for owner.
- Do not use uploaded photos for model training.
- IONOS-hosted file URLs are public CDN-style bearer URLs; use unguessable UUID paths and do not create directory listings.
- Do not place sensitive images in predictable paths.

Generated images:

- Apply provider safety filters.
- Block sexual, graphic, hateful, or targeted harassment prompts.
- Block prompts asking for real private people or sensitive personal data.
- Avoid photorealistic images of private individuals unless explicitly uploaded by host for private game use.

Kids/family mode:

- Add remote config or prompt mode for family-safe generation.
- Default Image Quiz/Photo Round to family-safe.

Audit:

- Log asset metadata, provider, size, and status.
- Do not log raw image bytes.
- Avoid logging uploaded photo filenames if they may contain personal names.

## Retention

Recommended defaults:

- Generated images: 30 days.
- Uploaded photos: 7 days unless attached to saved game history.
- Thumbnails: same retention as originals.
- Deleted assets: metadata soft-delete immediately, storage delete best-effort.

Future user-facing controls:

- "Delete my uploaded photos".
- "Clear recent media".
- "Save this game pack" if content persistence becomes a premium feature.

## Implementation Status

Phase 0 is implemented:

1. `backend/media_store.py` provides an in-memory `ImageAsset` store.
2. `/media/status` reports upload/generation capability and storage backend.
3. `/media/{asset_id}` serves generated quiz images with explicit image bytes and cache headers.
4. `/media` is protected in `API_PREFIXES` so backend-served SPA fallback cannot intercept asset requests.
5. `/quiz/generate-images` still preserves the legacy response shape while also creating `image_asset_id`, `image_url`, and `image_alt`.
6. `create_room()` converts generated quiz images into media URLs for room payloads.
7. Legacy `/quiz/{quiz_id}/image/{question_id}` still works and falls back to old in-memory image storage.
8. `scripts/smoke-remote.py` checks `/media/status`.

Implemented beyond Phase 0:

1. IONOS media upload signing plus `games_` / `games_gamma_` media metadata SQL.
2. Host upload URL endpoint at `/media/upload-url`.
3. Finalize endpoint at `/media/{asset_id}/finalize`.
4. Repo-owned `ionos/media/upload.php` handler source.
5. Custom quiz editor integration for uploaded question images.

Remaining backend work:

1. Add `backend/media_models.py` if the asset schema needs shared Pydantic validation beyond the current dataclass.
2. Add `backend/media_engine.py` with provider abstraction.
3. Add standalone `/media/generate`.
4. Add IONOS-backed `DELETE /media/{asset_id}`.
5. Add cleanup script for expired persisted metadata and IONOS files.
6. Add admin stats for ready/failed/deleted media assets.
7. Add decoded dimension validation, EXIF stripping, and optional image normalization.

## Frontend Implementation Status

Phase 0 is implemented:

1. `frontend/src/components/media/GameImage.tsx` handles loading, ready, and error states.
2. `frontend/src/utils/media.ts` resolves media URLs for same-origin and IONOS-hosted frontends.
3. Organizer, player, and spectator question screens use `GameImage` for attached images.
4. CSS defines stable image aspect ratios, skeleton loading, and error presentation.
5. Vitest component coverage verifies loading, loaded, and error behavior.

Implemented beyond Phase 0:

1. Custom quiz image upload control.
2. Thumbnail preview via `GameImage`.
3. Alt text editing.
4. Saved pack persistence and materialize/start preservation for uploaded image URLs.

Remaining frontend work:

1. Add richer host image status and picker components.
2. Add remove/replace cleanup for attached assets.
3. Add Image Quiz mode toggle in Quiz prompt/review flow.
4. Add Photo Round once upload endpoint is stable.
5. Add Playwright coverage for:
   - image question on organizer/player/spectator
   - image load failure
   - mobile no-overflow
   - TV 16:9 display

## API Prefixes And SPA Fallback

Backend-served SPA fallback must protect:

- `/media` — **must stay listed in `API_PREFIXES` in `main.py`** (`/sd` and `/quiz` are also listed)

If `/media` is removed from `API_PREFIXES`, `/media/...` asset requests will return `index.html` instead of image bytes. Keep this covered by tests.

## Deployment Notes

Gamma:

- Use `games_gamma_` metadata rows.
- Use `gamma/` IONOS media path prefix.
- Test image upload/generation with non-sensitive sample images.
- Do not point gamma to production-only paid image provider quota unless expected.

Production:

- Use `games_` metadata rows.
- Use `prod/` IONOS media path prefix.
- Verify same-origin backend-served SPA and IONOS frontend can both display `/media/{asset_id}` URLs.

IONOS:

- The IONOS-hosted frontend should call backend API URLs through the existing API config.
- Media URLs returned to the frontend must be absolute or API-relative in a way that works from IONOS.
- Uploaded files live under `https://media.revelryapp.me/apps/localplay/`.
- Deploy PHP handlers from repo source to `~/revelryapp/media/apps/localplay/`.
- `MEDIA_UPLOAD_SECRET` in backend env must match `~/revelryapp/media/apps/localplay/.upload_secret`.
- Upload handler CORS must include `https://games.revelryapp.me`, `https://gamesapi.revelryapp.me`, `https://gamesapi-gamma.revelryapp.me`, local dev origins, and Capacitor origins as needed.
- Read `.htaccess` should allow image fetches from web/PWA/native surfaces.
- Prefer returning full URLs when frontend is not same-origin:
  - `https://gamesapi.revelryapp.me/media/{asset_id}`
  - `https://gamesapi-gamma.revelryapp.me/media/{asset_id}`
  - or direct CDN URLs such as `https://media.revelryapp.me/apps/localplay/prod/...`

## Testing Plan

Backend tests:

- `/media/status` returns capability metadata.
- `/media/{asset_id}` returns image bytes and cache headers.
- `/media` is protected from SPA fallback.
- Quiz image generation creates media assets while preserving legacy behavior.
- Upload rejects unsupported MIME types. Implemented.
- Upload rejects oversized files. Implemented.
- Upload strips/normalizes metadata. Backlog.
- Upload URL generation creates a pending media asset with a signed IONOS path. Implemented.
- Finalize marks uploaded IONOS media as ready after successful upload. Implemented.
- Generated image success inserts persisted metadata and stores the image on IONOS. Future Phase 1.
- Generated image failure does not charge sparks.
- Media fetch requires authorization for unattached owner-only assets.
- Media fetch works for assets attached to active rooms.
- Expired/deleted assets return 404.

Frontend tests:

- `GameImage` loading, ready, and error states. Implemented.
- Image Quiz review shows image thumbnails and missing-image warnings.
- Player/spectator image questions render without text overlap.
- Playwright visual checks for phone and TV layouts.

Remote smoke:

- `/media/status`.
- Generate one gamma test image if provider is enabled.
- Upload one tiny test image if uploads are enabled.
- Create an Image Quiz room and verify image URL loads.

## Acceptance Criteria

Phase 0:

- Existing quiz image generation still works when provider is available.
- Quiz image URLs use shared media rendering semantics.
- Image UI has stable dimensions and graceful failure.
- `/media/status` and `/media/{asset_id}` exist.
- `/media` is listed in `API_PREFIXES`.
- `/sd/status` remains backward-compatible until replaced by `/media/status`.

Phase 1:

- Generated images survive backend container restart.
- Image metadata is isolated by `games_` vs `games_gamma_`.
- Upload signing secret is never exposed to the frontend.
- Image bytes are stored on IONOS, not Supabase Storage.
- Assets can be deleted or expired.

Phase 2:

- Host can upload an image and attach it to game content.
- Uploaded image has metadata stripped and size/type validation.
- IONOS production frontend can display uploaded media through backend `/media/{asset_id}` or direct `media.revelryapp.me` URLs.

First image game:

- Host can create and run Image Quiz or Photo Round.
- Phone, organizer, and spectator layouts are readable with image content.
- Remote smoke confirms image asset fetch works in gamma.

## Backlog

- Gemini image generation provider.
- Gemini vision provider for Photo Round / Eye Spy.
- Image prompt moderation.
- Image asset cleanup scheduler.
- Thumbnail generation.
- Recent media picker.
- Saved media packs.
- Caption/voting game state machine.
- Coordinate-tap input for Spot the Difference.
- Public sharing/export only after explicit privacy review.
