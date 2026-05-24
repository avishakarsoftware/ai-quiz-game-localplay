# LocalPlay Custom Quiz Authoring Spec

## Purpose

Let hosts create, edit, save, and run their own quiz packs inside LocalPlay without needing JSON import/export or an AI generation prompt.

This is the friendlier path for party/event games such as:

- "How well do you know the couple?"
- Baby shower trivia.
- Team onboarding quizzes.
- Family trivia.
- Classroom review games.
- Manually curated pub-quiz rounds.

The goal is not to replace AI generation. The goal is to make host-authored quizzes feel first-class, fast, visual, and durable, while still reusing the existing quiz room lifecycle, scoring, player screens, spectator screens, and image media layer.

For Revelry and future host-app integrations, custom quiz authoring should remain LocalPlay-hosted. Host apps launch the LocalPlay authoring surface with signed context and an allowlisted return URL, then store only pointer metadata such as `content_id`, title, thumbnail, question count, and status.

When authoring is launched from a host app, the editor should use host-app chrome: show the party/container name and return action, hide LocalPlay sparks/wallet/paywalls/account/library navigation, and expose only games/actions allowed by the host-app catalog and actor capabilities. Standalone LocalPlay authoring keeps the normal LocalPlay chrome and economy surfaces.

## Current State

LocalPlay already has most of the quiz runtime pieces:

- AI-generated quizzes are stored in memory under `quizzes`.
- Imported quizzes are accepted through `/quiz/import`.
- Existing quizzes can be edited through `PUT /quiz/{quiz_id}`.
- Individual questions can be deleted through `DELETE /quiz/{quiz_id}/question/{question_id}`.
- Quizzes can be exported through `/quiz/{quiz_id}/export`.
- Room creation accepts `quiz_id` and runs the normal quiz flow.
- The review screen already supports inline question editing after AI generation.
- The image media layer can display attached question images through `image_url` and `GameImage`.

Current gaps:

- The "Start from blank quiz" flow is implemented through **Create Your Own**.
- Hosts can manually author content before any AI generation/import step.
- Imported/generated quiz content is process-memory backed.
- Durable custom quiz library support is implemented through `/quiz-packs` and **My Quizzes**.
- Browser-local draft autosave is implemented; server-side debounce autosave is still backlog.
- The question-builder UX supports add, duplicate, delete, reorder, multiple choice, true/false, and correct-answer selection.
- Host upload flow for attaching images is implemented through signed IONOS uploads.
- Current Stable Diffusion image generation is local/dev-only and should not be treated as available in gamma or production.
- There is no friendly CSV/paste import.
- There is no saved-pack duplicate UI yet.

## Product Goals

- A host can create a playable custom quiz in under two minutes.
- A host can save a quiz pack and reuse it later when signed in.
- A guest host can create and run a quiz without signing in, with clear copy that saving across devices requires sign-in.
- The authoring UI should be touch-friendly on tablet/laptop and usable on mobile in a pinch.
- The quiz runtime should remain unchanged: once a custom quiz is launched, players should not care whether it was AI-generated, imported, or manually authored.
- Custom quizzes should support optional per-question images through host upload in gamma and production.
- Uploaded question images should be durable enough for saved quiz packs and reliable enough for organizer, player, and spectator display.
- AI image generation is an optional enhancement and must not block custom quiz images; local Stable Diffusion is only a development/local capability unless a production-safe cloud image provider is configured.
- Existing import/export should remain compatible.

## Non-Goals For V1

- No public marketplace of quiz packs.
- No collaborative real-time editing.
- No paid authoring gate for creating a basic manual quiz.
- No implementation of paid long-term retention/save plans in V1.
- No comments or moderation queue.
- No branching/version history beyond simple duplicate/restore.
- No question types beyond multiple-choice and true/false.
- No complex scoring modes such as closest numeric answer or free-text grading.
- No mandatory persistence for anonymous users beyond local browser drafts.
- No dependence on Stable Diffusion for gamma or production custom quiz images.
- No host app storing full quiz questions, answers, options, prompt text, or raw media internals.

## User Experience

### Entry Points

Add custom quiz authoring from the organizer flow:

1. Game Select -> Trivia.
2. Trivia setup shows three creation modes:
   - **Generate with AI**
   - **Create Your Own**
   - **Import**
3. The default can remain AI generation, but "Create Your Own" should be visually equal, not hidden in advanced settings.

Also add a library entry point:

- Menu -> My Quizzes.
- Organizer empty state -> "Create your own quiz".
- Review screen after AI generation -> "Save as custom quiz" for signed-in hosts.

For host-app launches such as Revelry:

- Host app opens a LocalPlay-hosted authoring route with signed party/user context, `draft_id`, and `return_url`.
- LocalPlay handles authoring, image upload, validation, local draft recovery, and saved content.
- LocalPlay redirects back to the host app with canonical `localplay_content_id` and safe metadata hints.
- Host app verifies the returned content server-side before storing a prepared game setup pointer or creating a session.
- Universal/app links and explicitly allowlisted custom schemes should work for native return flows.

Prepared game setup decisions:

- Multiple prepared quizzes may exist for one party.
- Prepared quizzes are party-scoped for MVP and cannot silently launch in another party.
- Prepared quizzes are visible to host/cohost only until started.
- Creating or editing a prepared quiz does not close an active game; replacement warning happens when the host taps Start.
- Once a `content_id` is used to start a session, it becomes immutable. Later edits create a new version/content id.
- Draft autosave survives 7 days since last edit.
- Free saved party content survives until 30 days after party end, or party start plus 48 hours plus 30 days when no end time exists.
- Authoring tokens are edit-only credentials and last 60 minutes. Expiry does not delete saved content or interrupt gameplay; server-side refresh/autosave recovery is backlog hardening.

### Create Flow

The minimum happy path:

1. Host selects **Create Your Own**.
2. Host enters quiz title.
3. App opens the question builder with one blank question.
4. Host fills question text, answer options, and marks the correct answer.
5. Host taps **Add Question** until the quiz is ready.
6. Host taps **Review & Start**.
7. App validates the quiz and moves into the existing review/start room flow.

The UI should autosave locally while editing. If the host is signed in, autosave should also persist to Supabase after debounce.

### Question Builder Layout

Desktop/tablet:

- Left column: question list with numbers, validation badges, drag handles.
- Main panel: selected question editor.
- Sticky footer: Save status, Preview, Review & Start.

Mobile:

- Single-column editor.
- Collapsible question list.
- Prev/Next question controls.
- Sticky bottom action bar.

Question editor fields:

- Question text.
- Question type segmented control:
  - Multiple choice.
  - True/False.
- Options:
  - Multiple choice: 2-4 options in V1, default 4.
  - True/False: locked options `True`, `False`.
- Correct answer selector.
- Optional explanation/host note.
- Optional time limit override.
- Optional image attachment:
  - Upload image from device.
  - Replace image.
  - Remove image.
  - Edit alt text.
  - Show upload progress and validation errors.
  - Hide AI image generation unless a provider is available for the current environment.

Controls:

- Add question.
- Duplicate question.
- Delete question.
- Move/reorder question.
- Preview as player.
- Validate quiz.

Validation should be inline and forgiving:

- Empty draft questions are allowed while editing.
- **Review & Start** is disabled until the quiz has at least one valid question.
- Invalid questions show a small badge in the list and the exact field-level issue in the editor.

### Quiz Library

Signed-in hosts get **My Quizzes**:

- List private custom quiz packs.
- Search by title.
- Sort by recently updated.
- Show question count and last edited date.
- Actions:
  - Edit.
  - Duplicate.
  - Export JSON.
  - Delete.
  - Start.

Anonymous hosts:

- See local drafts stored in browser storage.
- See a prompt: "Sign in to keep these across devices."
- Starting a local draft should still work.

### AI Assist Inside Custom Authoring

AI should be optional helper tooling, not the main flow.

Useful V1/V2 assists:

- "Suggest 3 more wrong answers" for a question.
- "Make this question easier/harder".
- "Generate 5 questions from this topic and add them to my quiz".
- "Rewrite for clarity".

These helpers should use the same provider/model configuration as normal quiz generation and should charge sparks only when they call an external model. Manual editing should be free.

## Data Model

Custom quiz packs are product content, not wallet/token infrastructure. They should live in the shared Supabase project with environment prefixes.

Production tables:

- `games_quiz_packs`
- `games_quiz_questions`

Gamma tables:

- `games_gamma_quiz_packs`
- `games_gamma_quiz_questions`

### `games_quiz_packs`

```sql
CREATE TABLE IF NOT EXISTS games_quiz_packs (
  id TEXT PRIMARY KEY,
  owner_wallet_id TEXT NOT NULL,
  title TEXT NOT NULL,
  description TEXT,
  source TEXT NOT NULL DEFAULT 'manual'
    CHECK (source IN ('manual', 'import', 'ai_saved')),
  status TEXT NOT NULL DEFAULT 'draft'
    CHECK (status IN ('draft', 'ready', 'archived', 'deleted')),
  visibility TEXT NOT NULL DEFAULT 'private'
    CHECK (visibility IN ('private', 'unlisted')),
  question_count INTEGER NOT NULL DEFAULT 0 CHECK (question_count >= 0),
  last_played_at BIGINT,
  created_at BIGINT NOT NULL,
  updated_at BIGINT NOT NULL,
  deleted_at BIGINT,
  metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_games_quiz_packs_owner_updated
  ON games_quiz_packs(owner_wallet_id, updated_at DESC);

CREATE INDEX IF NOT EXISTS idx_games_quiz_packs_status
  ON games_quiz_packs(status, updated_at DESC);
```

### `games_quiz_questions`

```sql
CREATE TABLE IF NOT EXISTS games_quiz_questions (
  id TEXT PRIMARY KEY,
  pack_id TEXT NOT NULL REFERENCES games_quiz_packs(id) ON DELETE CASCADE,
  position INTEGER NOT NULL CHECK (position >= 0),
  question_type TEXT NOT NULL DEFAULT 'multiple_choice'
    CHECK (question_type IN ('multiple_choice', 'true_false')),
  text TEXT NOT NULL,
  options JSONB NOT NULL,
  answer_index INTEGER NOT NULL CHECK (answer_index >= 0),
  explanation TEXT,
  image_asset_id TEXT,
  image_url TEXT,
  image_alt TEXT,
  time_limit_seconds INTEGER,
  points INTEGER,
  created_at BIGINT NOT NULL,
  updated_at BIGINT NOT NULL,
  metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
  UNIQUE(pack_id, position)
);

CREATE INDEX IF NOT EXISTS idx_games_quiz_questions_pack_position
  ON games_quiz_questions(pack_id, position);
```

Rules:

- `options` must contain exactly 2 options for true/false and 2-4 options for multiple choice.
- `answer_index` must be within the `options` array.
- `question_count` should be maintained server-side when questions change.
- `deleted` packs should be soft-deleted by default.
- Free saved packs may become `expired` or `deleted` after a LocalPlay-defined retention window.
- Hard delete can be a future account-data deletion operation after any grace/recovery period.

### Retention Model

Manual custom quiz creation should be free, but free saved quizzes do not need to live forever.

Recommended product model:

- Free hosts can create, edit, launch, import, export, duplicate, and upload host-provided question images during the free retention window.
- Free saved quizzes are retained for 30 days by default.
- After 30 days, quizzes enter a 7-day recoverable grace period.
- During the grace period, hosts can export, recover, or upgrade retention.
- After the grace period, quizzes should be soft-deleted from the library and associated media becomes eligible for cleanup according to the media retention policy.
- Hosts can pay LocalPlay to keep quizzes longer, recover recently expired quizzes, expand their saved library, or unlock premium creator features.
- Export should remain available where practical so hosts are not trapped by retention limits.
- Revelry may link hosts into LocalPlay to create or manage saved quizzes, but retention and payment are LocalPlay-owned.

Implementation notes:

- Add `expires_at`, `retention_tier`, and/or `retention_status` before enforcing automatic deletion.
- Media assets attached to expired/deleted packs should follow the media retention policy in `SPEC-IMAGE-GAMES.md`.
- Runtime games already launched from a quiz pack should not break if the source pack later expires; they should rely on materialized session content or a result snapshot.

### Relation To `games_generated_content`

Do not store manually authored quiz packs in `games_generated_content` long term.

Reason:

- Custom quiz packs are durable user-authored content.
- Generated content may remain temporary or TTL-based.
- Custom packs need edit history, library search, duplication, and ownership semantics.

However, launching a custom quiz can still materialize a runtime quiz object in the same shape as generated/imported quizzes, so the room engine stays unchanged.

## API Surface

All endpoints must use existing LocalPlay session/wallet ownership. The current implementation allows durable writes for the resolved wallet ID, whether that wallet comes from a signed-in user session or an anonymous device UUID. Product can later tighten this to signed-in users only if cross-device library behavior becomes the default expectation.

Implemented endpoints:

- `GET /quiz-packs`
- `POST /quiz-packs`
- `GET /quiz-packs/{pack_id}`
- `DELETE /quiz-packs/{pack_id}`
- `POST /quiz-packs/{pack_id}/materialize`

Planned endpoints below remain backlog unless marked implemented.

### List Quiz Packs

```http
GET /quiz-packs
```

Returns only packs owned by the current wallet/user.

```json
{
  "packs": [
    {
      "id": "qp_123",
      "title": "Avi Birthday Trivia",
      "status": "ready",
      "question_count": 12,
      "updated_at": 1779290000,
      "last_played_at": null
    }
  ]
}
```

### Save Pack

```http
POST /quiz-packs
```

```json
{
  "pack_id": "optional_existing_pack_id",
  "quiz": {
    "quiz_title": "Avi Birthday Trivia",
    "questions": []
  }
}
```

Creates or replaces a pack from the existing runtime quiz JSON shape.

### Get Pack

```http
GET /quiz-packs/{pack_id}
```

Returns pack metadata and questions in runtime quiz-compatible order.

### Update Pack Metadata

Backlog.

```http
PATCH /quiz-packs/{pack_id}
```

Allowed fields:

- `title`
- `description`
- `status`
- `metadata`

### Add Question

Backlog. The current implementation saves the whole quiz pack through `POST /quiz-packs`.

```http
POST /quiz-packs/{pack_id}/questions
```

```json
{
  "question_type": "multiple_choice",
  "text": "What city did we meet in?",
  "options": ["Mumbai", "Seattle", "Austin", "London"],
  "answer_index": 0,
  "explanation": "This was during the 2012 trip."
}
```

### Update Question

Backlog.

```http
PATCH /quiz-packs/{pack_id}/questions/{question_id}
```

Partial update. Server validates the full resulting question.

### Delete Question

Backlog as an endpoint; the current editor deletes locally and saves the whole pack.

```http
DELETE /quiz-packs/{pack_id}/questions/{question_id}
```

Deletes the question and compacts positions.

### Reorder Questions

Backlog as an endpoint; the current editor reorders locally and saves the whole pack.

```http
POST /quiz-packs/{pack_id}/questions/reorder
```

```json
{
  "question_ids": ["q_1", "q_3", "q_2"]
}
```

Server should perform the reorder atomically.

### Duplicate Pack

Backlog.

```http
POST /quiz-packs/{pack_id}/duplicate
```

Creates a new private draft copy owned by the current host.

### Import Existing JSON Into Pack

Backlog as a separate endpoint. The implemented `POST /quiz-packs` accepts existing quiz JSON in the `quiz` field.

```http
POST /quiz-packs/import
```

Accepts the existing exported quiz JSON shape:

```json
{
  "quiz": {
    "quiz_title": "Custom Trivia",
    "questions": [
      {
        "id": 1,
        "text": "Question?",
        "options": ["A", "B", "C", "D"],
        "answer_index": 0
      }
    ]
  }
}
```

### Export Pack

Backlog.

```http
GET /quiz-packs/{pack_id}/export
```

Returns the existing quiz export shape so current import/export stays compatible.

### Launch Pack

Option A, preferred for minimum room-engine churn:

```http
POST /quiz-packs/{pack_id}/materialize
```

Returns a transient `quiz_id` backed by the existing `quizzes` dictionary:

```json
{
  "quiz_id": "runtime_uuid",
  "quiz": {
    "quiz_title": "Avi Birthday Trivia",
    "questions": []
  }
}
```

Then existing room creation continues:

```http
POST /room/create
{
  "game_type": "quiz",
  "quiz_id": "runtime_uuid"
}
```

Option B, later cleanup:

```http
POST /room/create
{
  "game_type": "quiz",
  "quiz_pack_id": "qp_123"
}
```

The backend materializes internally.

Recommendation: implement Option A first because it isolates authoring from room creation and keeps `RoomCreateRequest` simpler.

## Frontend Components

Add organizer components:

```text
frontend/src/components/organizer/customQuiz/
  CustomQuizModeSelect.tsx
  CustomQuizEditor.tsx
  CustomQuizQuestionList.tsx
  CustomQuizQuestionEditor.tsx
  CustomQuizLibrary.tsx
  CustomQuizImportDialog.tsx
  CustomQuizValidationSummary.tsx
```

Recommended state shape:

```ts
export interface CustomQuizPack {
  id?: string;
  title: string;
  description?: string;
  status: 'draft' | 'ready' | 'archived' | 'deleted';
  questions: CustomQuizQuestion[];
  updated_at?: number;
}

export interface CustomQuizQuestion {
  id: string;
  question_type: 'multiple_choice' | 'true_false';
  text: string;
  options: string[];
  answer_index: number;
  explanation?: string;
  image_asset_id?: string;
  image_url?: string;
  image_alt?: string;
  time_limit_seconds?: number;
}
```

The editor should convert to the existing runtime `Quiz` type before review/start.

## Validation Rules

Pack:

- Title: 1-80 visible characters.
- At least 1 valid question before launch.
- Recommended warning below 5 questions, but do not block.
- Max questions should follow backend config (`MAX_QUESTIONS`) unless product decides custom packs can be larger.

Question:

- Text: 1-500 visible characters.
- Multiple choice: 2-4 non-empty options.
- True/False: exactly `True`, `False`.
- Option text: 1-200 visible characters.
- `answer_index` must point to a non-empty option.
- No duplicate empty-equivalent options after trimming.

Image:

- Optional.
- Host upload is the primary production/gamma path for custom quiz images.
- `image_asset_id` is the durable reference for saved packs.
- `image_url` is a backend-served `/media/{asset_id}` URL or an IONOS CDN URL derived from the asset; durable saved packs should not rely on arbitrary external URLs.
- `image_alt` should default to the question text but remain editable for accessibility.
- If `image_asset_id` is present, server must verify ownership or active attachment rights.
- If `image_url` is external, reject for durable saved packs unless explicitly allowed.
- Uploads must use the media safety rules from `SPEC-IMAGE-GAMES.md`: signed IONOS upload paths, size/type validation, content sniffing, ownership metadata, and retention controls. Metadata stripping and normalized dimensions/format are desired follow-up hardening.

## Persistence Strategy

### V1 Local/Runtime Behavior

Implemented behavior:

- Let anonymous users draft locally in `localStorage`.
- When they tap **Review & Start**, call existing `/quiz/import` with the assembled quiz JSON.
- Use returned `quiz_id` with existing `/room/create`.
- This gives a working custom quiz creator even without saving to the library.

Runtime content is still materialized into the existing in-memory quiz store when a quiz starts. Durable reuse comes from saved quiz packs.

### V2 Durable Library

Implemented:

- Signed-in hosts save packs to `games_quiz_packs`.
- Gamma uses `games_gamma_quiz_packs`.
- `GET /quiz-packs`, `POST /quiz-packs`, `GET /quiz-packs/{pack_id}`, `DELETE /quiz-packs/{pack_id}`, and `POST /quiz-packs/{pack_id}/materialize` are implemented.
- SQLite tables mirror the Supabase schema for local/dev.

Backlog:

- Autosave signed-in packs after 500-1000ms debounce.
- Show clear save state:
  - Saving...
  - Saved
  - Offline/local only
  - Save failed, retry

### Image Persistence

Custom quiz question image uploads are implemented using IONOS for files and backend/Supabase metadata.

Implemented behavior:

- Request a signed upload target from the backend before uploading.
- Upload image files to IONOS media storage through the signed PHP handler described in `SPEC-IMAGE-GAMES.md` and `DEPLOY.md`.
- Keep storage implementation details out of the authoring UI. Hosts upload, preview, replace, or remove images; they should not see or edit IONOS paths, CDN URLs, `/media` paths, asset ids, or storage backend names in normal quiz creation.
- Store media metadata in the shared media asset model from `SPEC-IMAGE-GAMES.md`.
- Save `image_url`, `image_alt`, and media metadata; `image_asset_id` is supported by the runtime shape and remains the preferred durable reference.
- Resolve `image_url` when reading/materializing packs so the quiz runtime receives the same shape as generated quizzes.
- Keep uploaded images private in product UX and metadata; the underlying IONOS file URLs are public CDN-style bearer URLs with unguessable UUID paths.
- Expose images through `/media/{asset_id}` or direct `https://media.revelryapp.me/apps/localplay/...` URLs only after ownership/attachment checks.

Backlog:

- Strip EXIF and normalize uploaded images to a canonical web-safe format before storage.
- Add remove/replace metadata cleanup and signed delete.
- If a media asset is missing, deleted, or expired, the editor should show a repair state and the runtime should degrade to a text-only question instead of crashing.

Stable Diffusion note:

- Existing Stable Diffusion integration is local-only and may be useful for development/demo image generation.
- Gamma and production should report image generation unavailable unless a cloud image provider is explicitly configured.
- Host upload must work independently of image generation availability.

### Offline/PWA Behavior

Custom authoring should be PWA-friendly:

- Keep current draft in localStorage/IndexedDB immediately.
- If network save fails, keep editing locally.
- On reconnect, sync the latest draft if ownership still matches.
- Avoid silent overwrites by comparing `updated_at`.

Conflict policy for V1:

- Last-write-wins with warning if server `updated_at` is newer.

## Security And Privacy

- Packs are private by default.
- All pack/question endpoints require wallet ownership checks.
- Do not expose other users' pack IDs through list/search.
- Treat quiz text as user content:
  - HTML-escape on render.
  - Store plain text, not markup.
  - Enforce length limits server-side.
- Treat uploaded images as private party content by default.
- Reuse the image media safety rules from `SPEC-IMAGE-GAMES.md`.
- Admin logs should include pack ID and owner wallet prefix, not full question text unless debugging explicitly requires it.

## Monetization And Spark Economy

Manual custom quiz authoring should remain free because comparable products commonly include it. The LocalPlay monetization opportunity is durability and premium creator features, not the basic ability to create a quiz.

Free saved custom quizzes are retained for 30 days by default, followed by a 7-day recoverable grace period. In standalone LocalPlay, hosts can pay LocalPlay to keep quizzes longer, expand their saved library, or unlock premium creator features. In Revelry-launched party mode, Revelry owns customer-facing party pass/payment decisions and LocalPlay should receive normalized party capabilities such as `saved_custom_games`, `premium_ai`, and `expires_at`.

Charge sparks only for optional AI assist actions:

- Generate questions into a custom quiz.
- Rewrite question.
- Suggest wrong answers.
- Generate image for a question, only when a production-safe image provider is configured.

Recommended behavior:

- Show spark cost on the AI assist button.
- Never charge for typing, editing, deleting, reordering, importing, exporting, duplicating, or launching a manual quiz while it is inside the free retention window.
- Never charge for uploading a host-provided image unless a separate storage/quota product decision is made.
- Keep save/retention entitlement separate from gameplay launch entitlement so guests never see payment prompts while joining or playing.

Open payment questions:

- Should paid save/retention use LocalPlay sparks, one-time purchases, a LocalPlay creator subscription, or another LocalPlay-owned model?
- Should free expired quizzes soft-delete first with a grace recovery window?
- Should premium features include larger libraries, larger media quotas, premium templates, AI assist bundles, advanced branding, analytics, or cross-event reuse?
- For host-app mode, which Revelry party-pass capabilities should map to longer quiz retention, premium AI assist, image quotas, and cross-party reuse?

## Import And Paste Helpers

Keep JSON import/export, but add easier inputs:

### CSV Import

Columns:

```text
question,option_a,option_b,option_c,option_d,correct,explanation
```

Rules:

- `correct` can be `A`, `B`, `C`, `D`, `1`, `2`, `3`, `4`, or exact option text.
- `option_c` and `option_d` may be blank for 2-option questions.

### Paste Import

Support a simple text parser later:

```text
Q: What city did we meet in?
A: Mumbai *
B: Seattle
C: Austin
D: London
Explanation: This was during the 2012 trip.
```

V1 can defer paste parsing and provide JSON/CSV only.

## Implementation Plan

### Phase 0: Frontend-Only Draft To Existing Import

Purpose: ship the easy create-your-own flow without new persistence tables.

Status: implemented in commit `c3bd58e`.

Backend:

1. Reuse `/quiz/import`, `/quiz/{quiz_id}`, `PUT /quiz/{quiz_id}`, `/quiz/{quiz_id}/export`, and `/room/create`.
2. Add tests that `/quiz/import` accepts editor-produced quiz JSON.
3. Add validation tests for 2-option and 4-option custom questions.

Frontend:

1. Add **Create Your Own** mode to Trivia setup.
2. Build `CustomQuizEditor`.
3. Store anonymous drafts locally.
4. Convert editor state to existing quiz JSON.
5. On **Review & Start**, call `/quiz/import`.
6. Reuse existing `ReviewScreen`.
7. Start room with returned `quiz_id`.

Acceptance:

- Host can create a 5-question quiz manually and start a room.
- Players can join and answer normally.
- Spectator view works normally.
- Refresh during editing restores local draft.
- No model call or spark charge occurs for manual authoring.

### Phase 1: Durable Signed-In Quiz Library

Status: partially implemented in commit `a22970a`.

Backend:

1. Add Supabase tables for `games_quiz_packs` and `games_quiz_questions`. Implemented.
2. Add prefixed gamma equivalents. Implemented.
3. Add `/quiz-packs` CRUD endpoints. Save/list/get/delete implemented; fine-grained question PATCH/reorder is backlog.
4. Add ownership checks. Implemented through wallet resolution.
5. Add pack export/import endpoints. Backlog.
6. Add `materialize` endpoint to produce runtime `quiz_id`. Implemented.

Frontend:

1. Add **My Quizzes** library. Implemented.
2. Autosave signed-in packs. Backlog; explicit Save is implemented.
3. Add duplicate/delete/export. Delete is implemented; duplicate/export are backlog.
4. Add "Save as custom quiz" from AI-generated review screen. Backlog.

Acceptance:

- Signed-in host can save, leave, return, edit, and start a quiz.
- Gamma and production data are isolated by table prefix.
- Anonymous drafts remain local and do not leak into another user account.

### Phase 2: Question Image Upload And Attachment

Status: partially implemented in commit `a22970a`.

Backend:

1. Add persisted media asset storage from `SPEC-IMAGE-GAMES.md`. Implemented for metadata.
2. Add host upload signing endpoint, e.g. `POST /media/upload-url`, plus finalize endpoint. Implemented.
3. Validate uploaded type, decoded dimensions, and file size. MIME and size are implemented; decoded dimension validation is backlog.
4. Strip EXIF and normalize to a web-safe image format. Backlog.
5. Store image bytes on IONOS and media metadata with wallet ownership in Supabase. Implemented.
6. Allow quiz pack questions to attach/detach owned media assets. Attach via editor/upload is implemented; detach cleanup is backlog.
7. Materialize `image_asset_id`, `image_url`, and `image_alt` into runtime quiz questions. Implemented for stored image fields.
8. Ensure `/media/{asset_id}` and/or direct IONOS CDN URLs work for IONOS frontend, backend-served gamma, active rooms, and owner-only editor preview. Direct IONOS URLs are implemented.
9. Sanitize host-app owner ids before creating signed IONOS upload paths. Implemented for synthetic Revelry party wallets such as `revelry:party:{party_id}`.

Frontend:

1. Add image attachment controls to `CustomQuizQuestionEditor`. Implemented.
2. Show upload progress, thumbnail preview, remove/replace actions, and alt text editing. Upload progress/preview/alt are implemented; remove/replace polish is backlog.
3. Persist image attachments in saved packs. Implemented.
4. Preserve image attachments through duplicate, export/import where possible, and materialize/start flow. Materialize/start is implemented; export/import preservation is backlog.
5. Show missing-image repair states in the editor. Backlog.

Acceptance:

- Host can create a custom quiz with at least one uploaded question image in gamma and production.
- Uploaded image questions render for organizer, player, and spectator views, including Revelry-launched organizer sessions where the browser receives the live question over WebSocket rather than from locally generated quiz state.
- Starting a room does not require Stable Diffusion or any local image generator.
- Missing or failed image assets degrade gracefully to text-only questions.
- Uploaded images survive backend container restart.
- Uploaded image files are stored on IONOS, not Supabase Storage or the GCP VM filesystem.

### Phase 3: Quality Helpers

- CSV import.
- Paste import.
- AI assist buttons.
- Pack thumbnails.
- Last played and play count.
- Better mobile bulk editing.

## Testing Plan

Backend tests:

- Pack ownership enforced.
- Question validation rejects empty text/options and invalid answer index.
- Question image attachment verifies media ownership.
- Durable saved packs reject arbitrary external image URLs.
- Reorder is atomic and compacts positions.
- Duplicate creates independent question rows.
- Export matches existing quiz JSON shape.
- Materialize creates runtime quiz compatible with `/room/create`.
- Materialize includes `image_asset_id`, `image_url`, and `image_alt` for attached images.
- Missing image assets degrade without breaking `/room/create`.
- Gamma table prefix does not touch production tables.

Frontend tests:

- Create custom quiz from blank.
- Add/edit/delete/duplicate/reorder questions.
- Upload/remove/replace a question image.
- Question image preview uses `GameImage` loading and error states.
- Inline validation disables start until valid.
- Manual creation does not call generation endpoints.
- Local draft survives refresh.
- Signed-in library shows saved pack.
- Mobile editor has no horizontal overflow.

Playwright smoke:

- Desktop: create 3-question quiz, review, start room.
- Mobile: edit a question and validate controls do not overlap fixed menu/sparks.
- IONOS base path: custom authoring routes work under `/quiz/`.

Remote smoke:

- Gamma custom quiz create/start flow.
- Signed-in save/load flow.
- Gamma custom quiz upload-image/start flow.
- `/media/status` reports upload availability accurately and does not imply Stable Diffusion is available in gamma/prod.

## Deployment Notes

- Phase 0 custom authoring is implemented.
- Revelry party-scoped quiz authoring is implemented with `/integrations/revelry/content/authoring-link`, `/revelry/author`, `/integrations/revelry/content`, and authoring-token media uploads. It reuses quiz-pack storage under `revelry:party:{party_id}`.
- Durable library UI requires deploying the rendered Supabase schema updates before enabling against Supabase environments.
- Uploaded images require IONOS `upload.php`, `.upload_secret`, and matching backend media env vars.
- Stable Diffusion should remain disabled/unavailable in gamma and production unless explicitly replaced by a production-safe cloud provider. Host-uploaded images are the required prod/gamma path.
- Suggested feature flags:

```text
custom_quiz_authoring_enabled=true
custom_quiz_library_enabled=true
custom_quiz_image_upload_enabled=true
custom_quiz_ai_assist_enabled=false
```

- Enable in gamma first.
- Production can expose **Create Your Own** and **My Quizzes** once database schema and IONOS media env are deployed.

## Interaction With Other Specs

- `SPEC-PLATFORM.md`: custom quiz authoring is the first friendlier event-pack creation workflow.
- `SPEC-SUPABASE-MIGRATION.md`: durable quiz packs are separate from temporary generated content.
- `SPEC-IMAGE-GAMES.md`: image attachments should reuse `ImageAsset`, `/media/{asset_id}`, and upload rules.
- `SPEC-THEME-VELVET.md`: authoring UI should follow Velvet tokens and avoid card-inside-card layouts.

## Backlog

- Generic host-app content table migration. The current implementation intentionally reuses existing custom quiz tables for both standalone and Revelry quiz authoring: standalone quizzes use the user's wallet id, and Revelry party quizzes use owner wallet id `revelry:party:<party_id>`. This avoids blocking the Revelry quiz flow on a schema migration while keeping non-Revelry custom quiz behavior on the same proven storage path. When LocalPlay adds editable non-quiz content types such as Bingo, Housie, Baby Bingo, Rebus, or other host-app-authored games, add a generic host-app content table/schema that carries `host_app`, `external_container_id`, `game_type`, ownership, retention, media, versioning, and payload metadata explicitly.
- CSV import.
- Paste import.
- AI assist for wrong answers and rewrites.
- Save AI-generated quiz as custom pack.
- Pack duplication.
- Pack archive/restore.
- Pack search.
- Shareable read-only pack links.
- Event templates for birthday, baby shower, wedding, holiday, team building.
- Bingo/Housie content templates that can reuse custom pack authoring concepts: number boards, phrase banks, baby bingo gift/activity lists, and saved caller decks. Runtime rules belong in `SPEC-PLATFORM.md` because Bingo/Housie needs board and claim validation instead of quiz scoring.
