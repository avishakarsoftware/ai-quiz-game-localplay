# SPEC-ADS — Ad-Supported Sparks (rewarded video → free Sparks)

Status: **Not built** (rewarded-AdMob SSV design below is unimplemented — no ad SDK). **Farm hole closed and DEPLOYED 2026-07-26:** the legacy trust-the-client `/tokens/ad-reward` stub is gated behind `ADS_ENABLED` (default false → 403) and is live on gamma AND prod, verified. Note the gap: the gate was written 2026-07-21 but not deployed until 07-26, so prod served the farmable endpoint for those five days. See DEPLOY.md's env-status ledger.
Owner: Avi
Related: `SPEC-IAP.md` (paid Sparks / RevenueCat), `SPEC.md` (spark economy), `DEPLOY.md` (build contexts, env per environment), VibePix (no ads — this is net-new for the platform)

---

## 0. Status (as-built)

- **Backend endpoint exists but is a trust-the-client stub — now LOCKED:** `POST /tokens/ad-reward` was a stub that granted `AD_REWARD_TOKENS` sparks to any caller with a `X-Device-Id` (bounded only by an IP rate limit + a per-wallet daily cap, `db.check_and_grant_ad_reward`). No ad, no SDK, no proof an ad was watched → farmable free sparks. **As of 2026-07-21 (commit `672b7fb0`) it is gated behind `config.ADS_ENABLED` (default false) and returns 403** until server-side verification replaces the stub, closing the farm hole. The reward-logic path underneath is unchanged and only reachable when `ADS_ENABLED` is explicitly set.
- **No frontend:** there is no "watch ad" button (nothing calls the endpoint). The misleading *"watch an ad to earn free sparks"* copy was removed from the four Not-Enough-Sparks modals on 2026-07-06 (commit `ce612fb8`).
- **DB:** `wallets.ads_watched_today` / `ads_watched_date` columns exist and reset per UTC day. `check_and_grant_ad_reward` writes an `ad_reward` transaction with `reference_id = NULL` (no idempotency key yet).
- **Config:** `AD_REWARD_TOKENS = 5`, `MAX_ADS_PER_DAY = 5`, and `ADS_ENABLED = false` (the kill switch above; `backend/config.py`). No AdMob ids anywhere.
- **Supabase parity:** `supabase_db.check_and_grant_ad_reward` → `grant_ad_reward` RPC ([supabase_db.py:482](backend/supabase_db.py:482)); same NULL-reference shape.

**Net:** the economy plumbing (cap, counter, transaction ledger) is in place; the **ad itself and the fraud-proof fulfillment are missing.** This spec adds a real rewarded-ad integration and flips fulfillment from client-triggered to **server-verified**.

---

## 1. Goal & scope

Let players earn a small number of Sparks by watching a **rewarded video ad**, as a free alternative to buying a Spark pack — without opening a farm-free-currency hole and without violating store policy.

**In scope (v1):**
- **Native only** — rewarded video on iOS + Android via Google **AdMob** (Capacitor plugin).
- **Server-Side Verification (SSV):** the reward is granted by an AdMob-signed callback to our backend, not by the client. This is the whole point — it makes the reward unforgeable.
- Rewarded-ad button in `SparkPurchaseModal` (and optionally re-added to the Not-Enough-Sparks error modals) on native builds only.
- Daily cap (reuse `MAX_ADS_PER_DAY`), idempotency, consent/ATT, store declarations, testing, rollout.

**Out of scope (explicit non-goals for v1):**
- **Web rewarded ads.** No good rewarded-video path on the web SPA; web keeps Stripe + the daily bonus. The button is hidden on `platform === 'web'` (mirror the IAP native-only gate in `iap.ts`).
- Banner / interstitial / native ads anywhere. Rewarded video only — it's opt-in, so it doesn't degrade the party UX.
- Mediation / multiple ad networks. AdMob only in v1.
- Rewarding non-paying vs paying users differently (see §9 open question).

---

## 2. Key decision — AdMob rewarded video with Server-Side Verification

### 2.1 Why AdMob
Google AdMob is the default rewarded-video network for Capacitor apps, has first-class **SSV**, a maintained Capacitor plugin, and shares the existing Google/Play account footprint. No mediation needed for v1.

### 2.2 Fulfillment: SSV, not client-trust (the load-bearing decision)

| Approach | How the grant happens | Forgeable? | Verdict |
|---|---|---|---|
| **A. Client-trusted (current stub)** | App finishes the ad, calls our `POST /tokens/ad-reward`. | **Yes** — the HTTP call is trivially replayable/fakeable; no proof an ad played. | **Reject.** This is the hole we're closing. |
| **B. AdMob Server-Side Verification (SSV)** — *chosen* | AdMob's servers call **our** SSV URL with signed query params (`ad_network`, `ad_unit`, `custom_data`, `transaction_id`, `reward_amount`, `signature`, `key_id`) after a verified impression. We verify the signature against Google's public keys, then grant. | **No** — signature is over Google's private key; `transaction_id` gives replay-proof idempotency. | **Adopt.** |

**Decision: Approach B.** The client's role shrinks to (1) show the ad, (2) pass `custom_data = wallet_id`, (3) poll `/tokens/balance` for the credit. The client never asserts "give me sparks."

**Consequence:** the existing `POST /tokens/ad-reward` (client-trusted) is **retired** — either deleted or locked behind a config flag defaulting off. The new fulfillment path is a **GET** SSV callback endpoint (§4.1). Do **not** ship the button wired to the old endpoint.

---

## 3. Architecture / flow

```
 App (native)                 AdMob SDK / Google           Our backend
 ─────────────                ──────────────────           ───────────
 tap "Watch ad" ──load rewarded──►
                 ◄──── ad ready ───
 show ad, set SSV custom_data=wallet_id
                 ── impression verified ──►
                                    ── GET /ads/ssv?custom_data=<wallet>&
                                       transaction_id=<txn>&signature=…&key_id=… ──►
                                                            verify signature (Google keys)
                                                            + daily cap + idempotent(txn)
                                                            → credit_purchase-style grant
                                    ◄──────────── 200 OK ───
 onRewarded fires (client)
 poll GET /tokens/balance ───────────────────────────────► returns new balance
 UI shows "+5 Sparks"
```

Key properties:
- **Grant authority = SSV callback only.** `onRewarded` on the client is a *UI hint* to start polling, never the grant trigger.
- **Idempotency:** `reference_id = f"ad:{ad_network}:{transaction_id}"`; the AdMob `transaction_id` is unique per rewarded impression. Replay → no double-grant (same guarantee as IAP's `iap:{store}:{txn}`).
- **Daily cap** still enforced server-side inside the grant (reuse `ads_watched_today`).
- **Wallet routing:** `custom_data = wallet_id` (signed-in `user_id` else `device_id`) — identical to `walletAppUserId()` in `iap.ts`, so ad sparks land in the same wallet as purchases.

---

## 4. Backend changes

### 4.1 New SSV callback endpoint — `GET /ads/ssv`
AdMob calls this with query params (SSV is always a GET; there is no bearer/shared secret — trust comes from the signature). Steps:
1. Extract `key_id`, `signature`, and the **rest of the query string in original order** (the signed payload is everything up to `&signature=`).
2. Fetch AdMob's public keys from the **rewarded-ads verifier keyserver** (`https://gstatic.com/admob/reward/verifier-keys.json`), cache by `key_id` (keys rotate; refetch on unknown `key_id`). Verify the ECDSA signature over the payload.
3. On bad/absent signature → `403` and grant nothing. (Never grant on unverified input — this is the entire security model.)
4. Parse `custom_data` (wallet_id), `transaction_id`, `ad_network`, `reward_amount`/`reward_item` (ignore client-suggested amount; **server decides** `AD_REWARD_TOKENS`).
5. Grant via a new idempotent path: `db.grant_ad_reward(wallet_id, reference_id="ad:{ad_network}:{transaction_id}")` — dedup on `reference_id`, enforce `MAX_ADS_PER_DAY`, cap at `MAX_TOKEN_BALANCE`, write an `ad_reward` token_transaction. Return `200` even when the daily cap is hit or it's a replay (AdMob only needs a 200 to stop retrying); just don't double-credit.
6. Return `200 OK`.

### 4.2 Modify `check_and_grant_ad_reward` → take a `reference_id`
Add a `reference_id` parameter and dedup on it (currently writes `NULL`). Both `db.py` (SQLite) and `supabase_db.py` (`grant_ad_reward` RPC) must change in lockstep, plus the Supabase migration for the RPC signature. Keep the daily-cap + `MAX_TOKEN_BALANCE` logic intact.

### 4.3 Retire the client-trusted `POST /tokens/ad-reward`
Delete it, or gate behind `ADS_TRUST_CLIENT` (default `false`) returning `403` when off. Update `tests/` accordingly. Nothing in the shipped app should call it.

### 4.4 `/tokens/balance` already returns `ads_remaining_today`
No change needed — the client uses it to show "3 ads left today" and to hide the button at 0.

---

## 5. Config / env (per environment: local, gamma, prod)

New `config.py` values (env-overridable, mirroring the existing pattern):

| Var | Purpose | Notes |
|---|---|---|
| `ADMOB_APP_ID_IOS` / `ADMOB_APP_ID_ANDROID` | AdMob app ids | baked into native builds, not the API |
| `ADMOB_REWARDED_UNIT_IOS` / `ADMOB_REWARDED_UNIT_ANDROID` | rewarded ad unit ids | ditto; use Google **test unit ids** in local/gamma |
| `ADMOB_SSV_KEYSERVER_URL` | verifier keys | default `https://gstatic.com/admob/reward/verifier-keys.json` |
| `ADS_ENABLED` | master kill-switch | default `false` until stores approve |
| `ADS_TRUST_CLIENT` | legacy escape hatch | default `false` (see §4.3) |
| existing `AD_REWARD_TOKENS=5`, `MAX_ADS_PER_DAY=5` | economy knobs | keep; tune per §8 |

Publishable AdMob ids get baked by `frontend/scripts/cap-build.mjs` alongside the RC/OAuth ids (they're not secret). The SSV endpoint URL per env: `https://gamesapi.revelryapp.me/ads/ssv` (prod), gamma `:8004` equivalent — registered in the AdMob ad-unit's **SSV settings**.

---

## 6. Frontend changes

### 6.1 Plugin
`@capacitor-community/admob` (Capacitor 8 compatible). iOS via SPM/Package.swift, Android via Gradle — **no CocoaPods**, same constraint as RevenueCat.

### 6.2 `utils/ads.ts` (new — mirror `utils/iap.ts` structure)
Dynamic-import, code-split so the web bundle never loads it. Exports:
- `isAdsConfigured()` → `getPlatform() !== 'web' && !!rewarded unit id && ADS_ENABLED`.
- `initAds()` — initialize AdMob once at app start; request consent (§7).
- `loadRewarded()` / `showRewarded()` — load then show; on show, set SSV options `{ customData: walletAppUserId() }` (reuse the helper from `iap.ts` or `platform.ts`).
- Returns a result union `{ status: 'rewarded' | 'dismissed' | 'error' | 'unavailable' }`. `'rewarded'` = *start polling balance*, not *grant*.

### 6.3 `SparkPurchaseModal.tsx`
Add a **"Watch a short ad — +5 Sparks"** row, visible only when `isAdsConfigured() && adsRemaining > 0`. On tap: `showRewarded()` → on `'rewarded'`, poll `GET /tokens/balance` (same poll loop the native IAP path already uses) until balance increases or timeout → toast "+5 Sparks". Disable/hide at `ads_remaining_today === 0` ("Come back tomorrow").

### 6.4 Error modals (optional, gated)
Only after the flow is proven live may the *"…or watch a quick ad"* copy return to the Not-Enough-Sparks modals ([OrganizerPage.tsx](frontend/src/pages/OrganizerPage.tsx)), and only rendered when `isAdsConfigured()`. Do not reintroduce the promise on web builds.

### 6.5 Native config
- **iOS `Info.plist`:** `GADApplicationIdentifier` = `ADMOB_APP_ID_IOS`; `SKAdNetworkItems` (AdMob's SKAdNetwork ids); `NSUserTrackingUsageDescription` for the ATT prompt.
- **Android `AndroidManifest.xml`:** `<meta-data com.google.android.gms.ads.APPLICATION_ID>` = `ADMOB_APP_ID_ANDROID`.

---

## 7. Consent, privacy & policy

- **UMP / consent:** use Google's User Messaging Platform for GDPR/UK consent; on iOS trigger **ATT** (App Tracking Transparency) before the first ad request. If the user declines tracking, serve non-personalized ads (still valid rewarded impressions).
- **Google Play declarations:** flip **"Contains ads"** to *yes* on the Play listing (currently *no* per `LAUNCH-CHECKLIST.md §4`), and update **Data safety** to disclose the ad SDK's data collection (device/advertising id). Update `LAUNCH-CHECKLIST.md` when this ships.
- **Apple:** the app already declares IAP; add the ad networks to the privacy nutrition label ("Third-Party Advertising" / "Identifiers") and answer the IDFA question in App Store Connect.
- **Families policy:** target audience is 13+ (already set) — keep it out of the Designed-for-Families / Kids track, which restricts ads.

---

## 8. Economy tuning (defaults, revisit before launch)

- `AD_REWARD_TOKENS = 5`, `MAX_ADS_PER_DAY = 5` → max **25 free sparks/day** from ads, on top of the `DAILY_BONUS_TOKENS = 10`. A room costs `COST_ROOM = 10`.
- 25 + 10 = 35/day ≈ 3.5 free rooms/day for a determined viewer. That's the intended "free but grindy" tier; the 50-spark pack ($1.99) stays clearly more convenient.
- Levers if it's too generous: drop `AD_REWARD_TOKENS` to 3, or `MAX_ADS_PER_DAY` to 3, or make ad rewards scale down for wallets that have never purchased. Tune via env, no redeploy of code.

---

## 9. Open questions / decisions needed

1. **AdMob account** — create ad units under the existing Google account (same as Play)? Needs a one-time AdMob signup + linking to the Play app. **(Blocker for any real testing.)**
2. **Reward size** — confirm 5 sparks/ad and 5 ads/day against the pack pricing (§8).
3. **Paying-user treatment** — hide ads entirely for users who've purchased (`db.has_ever_purchased`), or always offer them? (Leaning: always offer; ads are opt-in and harmless.)
4. **Web** — confirmed out of scope for v1 (§1). Revisit only if web monetization matters.

---

## 10. Testing

- **Google test ad unit ids** in local/gamma (always fill, always "rewarded") — never hit production fill in dev.
- **SSV signature verification unit test** — golden request from Google's SSV docs sample; assert bad signature → 403, good → grant, replay (`transaction_id`) → single grant, daily cap → 200 + no extra credit. Add to `backend/tests/` next to `test_iap_webhook.py`.
- **Daily-cap + idempotency** reuse the IAP test patterns.
- **Device test (blocker):** real device, watch a test ad, confirm the SSV callback lands and `/tokens/balance` reflects +5. Android needs the internal-testing build; iOS a real device (test ads work in sandbox).

---

## 11. Rollout

1. Backend: SSV endpoint + `grant_ad_reward(reference_id)` + retire client-trust endpoint + tests → master.
2. AdMob account + ad units + register per-env SSV URLs.
3. Frontend `utils/ads.ts` + modal button (native-gated) + native manifest/plist config → `cap:sync:gamma`.
4. Verify end-to-end on gamma with a test device (test ad units).
5. Store declarations (Play "contains ads", Data safety; Apple privacy label).
6. Prod: set `ADS_ENABLED=true` + AdMob ids per env, deploy, ship native builds. Flip Play "contains ads".
7. Post-launch: watch `docker logs games-backend -f | grep -iE 'ad_reward|/ads/ssv'`; confirm SSV grants and no over-credit; monitor eCPM/fill in AdMob.

---

## 12. Files touched (implementation checklist)

- `backend/main.py` — new `GET /ads/ssv`; retire/gate `POST /tokens/ad-reward`.
- `backend/config.py` — AdMob ids, `ADS_ENABLED`, `ADS_TRUST_CLIENT`, keyserver URL.
- `backend/db.py` + `backend/supabase_db.py` (+ Supabase RPC migration) — `grant_ad_reward` takes `reference_id`, dedups.
- `backend/ads.py` (new, optional) — SSV signature verification + key caching.
- `backend/tests/test_ads_ssv.py` (new).
- `frontend/src/utils/ads.ts` (new); `SparkPurchaseModal.tsx`; optionally `OrganizerPage.tsx` (gated copy).
- `frontend/scripts/cap-build.mjs` — bake publishable AdMob ids.
- iOS `Info.plist`, Android `AndroidManifest.xml` — AdMob app id + SKAdNetwork/ATT.
- `LAUNCH-CHECKLIST.md` — flip "Ads" declaration; `SPEC-IAP.md` cross-ref.
