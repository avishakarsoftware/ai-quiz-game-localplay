---
name: Monetization Plan
description: $0.99/12h party pass via device ID tracking + signed JWT, no database needed
type: project
---

## Monetization: $0.99 / 12-Hour Party Pass

**Model:** 3 free game generations per 24h, then paywall. Payment unlocks unlimited generations for 12 hours + better AI model (Gemini 2.5 Flash).

### Architecture (No Database Required)

**1. Device ID Generation (Frontend)**
- Generate UUID on first visit, store in `localStorage` as `revelry_device_id`
- Send as header (e.g., `X-Device-ID`) with every `/quiz/generate` and `/mlt/generate` request

**2. Backend Usage Tracking (In-Memory)**
- `device_usage: Dict[str, { count: int, window_start: float }]` — per device ID
- On generate request: check count in current 24h window
- If count >= 3 and no valid premium token → return HTTP 402 with `{ "error": "limit_reached", "pricing": { ... } }`
- Resets naturally on server restart (generous, not strict — acceptable for casual game)
- Can layer IP as secondary signal: same IP + new device ID within 24h = suspicious

**3. Premium Token: Signed JWT (No Storage Needed)**
- User pays → Stripe webhook confirms → backend generates JWT:
  ```json
  { "device_id": "uuid", "exp": "<now + 12h>", "tier": "party_pass" }
  ```
- Signed with `JWT_SECRET` env var (set on GCP backend)
- Client stores JWT in `localStorage` as `revelry_premium_token`
- Sent as `Authorization: Bearer <token>` with generate requests
- Backend verifies signature + expiry — no DB lookup, no file, survives restarts
- Token bound to `device_id` — backend checks it matches the request's device ID

**4. Paywall UI (Frontend)**
- When backend returns 402, show upgrade prompt
- Pricing info pulled from `config.json` remote config (already has `pricing.pass_price`, `pricing.duration_hours`, `pricing.label`)
- `feature_flags.show_upgrade_button` controls visibility in UI

**5. Payment Flow**
- **Web:** Stripe Checkout (hosted page) → Stripe webhook → backend issues JWT → redirect back with token
- **iOS:** Apple IAP → receipt sent to backend → validate with Apple → issue JWT
- **Android:** Google Play Billing → purchase token sent to backend → validate with Google → issue JWT

**6. Model Upgrade for Paid Users**
- Free: `gemma-3-27b-it` (current default via Gemini API)
- Paid: `gemini-2.5-flash` — noticeably better quality, cheap (~$0.15/1M input tokens)
- Backend checks JWT presence → selects model accordingly

### Implementation Order
1. Device ID generation in frontend (trivial — UUID + localStorage)
2. Backend usage tracking dict + 402 response on limit
3. JWT signing utility + `JWT_SECRET` env var
4. Stripe Checkout endpoint + webhook handler
5. Paywall UI component (triggered by 402)
6. Model selection based on premium status
7. Apple IAP receipt validation (for iOS app)
8. Google Play Billing validation (for Android app)

### Edge Cases
- **Refund fraud:** Not worth handling at $0.99/12h — negligible risk
- **Token sharing:** Bound to device_id, backend checks match
- **localStorage cleared:** Token gone, must re-buy — fair for 12h window
- **Server restart:** In-memory usage counts reset (generous), JWTs still validate (self-contained)
- **Failed generations:** Should NOT count toward the 3 free limit — only decrement on success
