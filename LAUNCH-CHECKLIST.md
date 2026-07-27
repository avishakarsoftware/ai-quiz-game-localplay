# LAUNCH-CHECKLIST — IAP / native app go-live

Ordered, ready-to-run runbook to take Revelry Games (`me.revelryapp.quiz`) IAP + native apps live.
Engineering is done and verified (real iOS purchase + Google auth on device, 2026-07-07). Prod backend
RevenueCat webhook auth is configured and deployed (verified 2026-07-14). What remains is
**RevenueCat console hookup, store submissions, Play listing, and optional live Stripe keys** — no code work. Cross-refs: `SPEC-IAP.md §0`,
`DEPLOY.md §3c/§3d`, secrets in `backupenv/quiz/local/iap-setup.md`.

Status snapshot (re-verified against the live endpoints 2026-07-16):
- `POST /webhook/revenuecat` unauthenticated → **401** (secret set, rejecting unauthenticated traffic);
  prod console webhook Active, test event returned 200 on both sides.
- `POST /webhook/stripe` unsigned → **400** (live keys configured; was 503 when unset).
- Prod `ALLOWED_ORIGINS` includes the capacitor/localhost origins.
- Native **v3.1.1 / build 6** on both platforms; iOS uploaded to App Store Connect, Android AAB signed.
- **Not yet proven:** any real store purchase (see Phase 6 gates) — and the uploaded iOS build carries
  the paywall bug described in "Sequencing decision" below.

---

## CURRENT STATE — 2026-07-26

**iOS: v3.1.3 (9) archived + distributed to App Store Connect by Avi.** Remaining is metadata +
submission only, in the ASC web UI:

1. Upload the refreshed screenshots (13 per target in `marketing/app-store/…`; pick 10).
   **Recommended order** (breadth-first, see `marketing/store-listing.md`):
   `01 → 03 → 04 → 09 → 12 → 10 → 11 → 13 → 05 → 07`.
2. Attach the 3 IAPs, confirm the privacy answers, Submit for Review.

**No new build is needed for the screenshots.** They are metadata and attach to the already-
distributed 3.1.3 (9); rebuilding only burns a build number.

**Before uploading:** delete `marketing/app-store/iphone-6.9/`. It holds 2 of 10 native-simulator
shots from an abandoned capture path; a half-populated size slot must not ship. (Apple's 6.9" slot
accepts the 1290×2796 set in `iphone-6.7/`, and the 13" iPad slot accepts 2048×2732 from
`ipad-12.9/` — so the existing folders already satisfy current requirements. The folder names are
legacy, not a size problem.)

**Claude cannot drive this step:** every Apple domain (`appstoreconnect.apple.com`,
`apps.apple.com`) returns "Navigation to this domain is not allowed" under the browser policy, and
there is no App Store Connect API key or fastlane in this repo. Play Console *is* reachable.

**Android: v3.1.3 (9) in Play review since 2026-07-20**, managed publishing OFF → auto-publishes on
approval. Deliberately not re-uploaded on 07-26 (gifting/achievements ship dormant, so re-uploading
would restart the review clock for no user-visible gain).

---

## Sequencing decision — ✅ RESOLVED 2026-07-17: option A (rebuild)

**Chosen: A — rebuild.** The web fix is **deployed and verified live** on gamma, prod, and IONOS
(the rail already taking real money). Native is bumped to **v3.1.2 / build 7** with the fix baked
and verified in both bundles; iOS is open in Xcode for Archive → Distribute.

**Do not submit the previously-uploaded v3.1.1 (6)** — it still carries the bug. Submit v3.1.2 (7).

Remaining for this decision:
- [ ] iOS: Archive → Distribute → App Store Connect from the open Xcode window (v3.1.2/7).
      **Verify before archiving that the synced bundle is `index-Cp1gjoTq.js`** — it contains the
      account-deletion UI; the earlier `index-CIs1AnyA.js` sync predates it.
- [x] Android AAB **rebuilt 2026-07-19** at v3.1.2 / versionCode 7, signed, contents verified
      (deletion UI ×2, prod API, zero stale-paywall template):
      `frontend/android/app/build/outputs/bundle/release/app-release.aab`.
      Keystore password is at `~/Desktop/dev/antigravity/backupenv/quiz/local/keystore.properties`
      (the **dev-root** backupenv — NOT the repo-local `backupenv/`, which is a different dir).

Original analysis retained below for context.

---

## Original analysis — the uploaded iOS build has a paywall bug (2026-07-16)

**The uploaded `v3.1.1 (6)` misquotes the price at the moment of purchase.** When a host runs out
of sparks, the CTA renders `Get 110 Sparks — $0.99` from the retired single-pack remote config. That
pack does not exist: tapping it opens the modal offering **50/$1.99, 200/$4.99, 500/$9.99**. The
hardcoded fallback carries the same values, so every user on that path sees it, and on native
RevenueCat returns store-localized prices, so a hardcoded USD figure is wrong in every non-USD
storefront regardless.

Fixed on master 2026-07-16 (`frontend/src/components/ErrorModal.tsx` — CTA now reads "Get Sparks";
regression test asserts the modal never renders a pack size or a price). **The fix is not in the
uploaded binary.**

Options considered:

| Option | What it means |
|---|---|
| **A — rebuild (chosen)** | Bump to v3.1.2 / build 7, `npm run cap:sync:prod`, re-archive, upload, submit that. Costs one build cycle; ships an accurate paywall. |
| **B — ship (6) as-is** | Submit the uploaded build and fix next release. The bug is a wrong price shown *before* checkout — the actual charge is always correct and comes from the store. Risk is user trust and a possible App Store metadata/IAP-accuracy rejection. |

---

## Phase 1 — Prod IAP backend (server-side; ~15 min + one deploy) ✅ COMPLETE 2026-07-14

**Status: DONE + verified on both sides.** RevenueCat prod webhook "Revelry Games Prod" is Active; test event `E1662E2D-…` (env=SANDBOX, product=`test_product`) shows **Response 200 in the RevenueCat dashboard** and the same event id landed **authenticated + 200 in prod logs** (bearer auth passed; webhook_events dedup + `games_mark_webhook_processed` ran). Prod native IAP fulfillment is wired end-to-end. Steps below retained for rotation/reference.

1. **Create a prod RevenueCat webhook** (distinct secret from gamma; backend secret already exists on prod as of 2026-07-14):
   - Generate a secret (e.g. `python3 -c "import secrets;print('rcwh_rvly_prod_'+secrets.token_urlsafe(24))"`).
   - RevenueCat → Integrations → Webhooks → add `https://gamesapi.revelryapp.me/webhook/revenuecat`,
     Authorization header `Bearer <secret>`, HMAC off, environment **Production + Sandbox**, no event filter.
2. **Set `REVENUECAT_WEBHOOK_SECRET` on prod** `.env` (the token, no `Bearer`) — done 2026-07-14; command kept for rotation:
   ```bash
   gcloud compute ssh revelry-backend --zone us-central1-a --command '
     ENV=/home/revelry-games/app/.env
     sudo grep -q "^REVENUECAT_WEBHOOK_SECRET=" "$ENV" \
       && sudo sed -i "s#^REVENUECAT_WEBHOOK_SECRET=.*#REVENUECAT_WEBHOOK_SECRET=<secret>#" "$ENV" \
       || echo "REVENUECAT_WEBHOOK_SECRET=<secret>" | sudo tee -a "$ENV"'
   ```
3. **Deploy prod** (also picks up latest master; `docker restart` does NOT re-read env, so a real deploy is required) — done 2026-07-14:
   ```bash
   ./scripts/deploy-gcp.sh --with-frontend
   ```
4. **Verify**: `curl -s -o /dev/null -w "%{http_code}\n" -X POST https://gamesapi.revelryapp.me/webhook/revenuecat -d '{}'`
   → should be **401** (verified 2026-07-14). After the RevenueCat console webhook is created with the same secret,
   a bearer-authed synthetic `INITIAL_PURCHASE` should credit (mirror the gamma smoke test).

---

## Phase 2 — Native app builds (point at prod) ✅ BUILT 2026-07-16 (v3.1.1 / build 6)

```bash
cd frontend
npm run cap:sync:prod      # bakes VITE_API_URL=https://gamesapi.revelryapp.me + RC/OAuth keys
```
Both builds verified prod-baked (`gamesapi.revelryapp.me`) with the payment UX (cost context + terms) and
display name **Revelry Games**; bundle id stays `me.revelryapp.quiz`.

- **iOS** — ✅ **v3.1.1 (6) archived + sent to App Store Connect 2026-07-16.** `npx cap open ios` → Archive →
  Distribute → App Store Connect.
  **Intricacy (do not attempt headless):** `xcodebuild -exportArchive` **cannot** produce an App Store build
  here — it fails with `No signing certificate "iOS Distribution" found` + `No Accounts` (CLI has no signed-in
  Apple ID to mint a distribution cert), and the auto-generated store profile came back missing
  `com.apple.developer.applesignin` (*"Provisioning profile doesn't include the Sign In with Apple
  capability"*). Xcode Organizer resolves both (creates the distribution cert via the signed-in Apple ID and
  regenerates the profile). If Distribute ever errors on Sign In with Apple: developer.apple.com →
  Identifiers → `me.revelryapp.quiz` → enable **Sign In with Apple**, then re-Distribute.
- **Android** — ✅ **AAB built**: `frontend/android/app/build/outputs/bundle/release/app-release.aab`
  (v3.1.1, versionCode **6**, signed with the v2 upload keystore). `cd android && KEYSTORE_PASSWORD=…
  KEY_PASSWORD=… ./gradlew bundleRelease` (bump `versionCode` each upload). **Not yet uploaded** — goes to the
  Production track after the Phase 4 listing is complete.

**Dev-install path (no TestFlight needed):** paired devices install directly —
`xcodebuild -scheme App -configuration Debug -sdk iphoneos -destination 'id=<udid>' -allowProvisioningUpdates build`
then `xcrun devicectl device install app --device <udid> <App.app>`. Used 2026-07-16 to put v3.1.1 on Ruchi's
iPhone (device is registered/paired; TestFlight tester list is empty — installs were never via TestFlight).
Dev-signed builds expire ~7 days.

---

## Phase 3 — Store submissions

### App Store (iOS)
- ⚠️ **v3.1.1 (6) is uploaded but SUPERSEDED — do not submit it** (carries the paywall bug).
- [ ] **Archive + upload v3.1.2 (7)** from Xcode (already open, prod-baked and verified).
- [ ] **Submit for review with the 3 IAPs attached** — the consumables are "Ready to Submit". Attaching
      them to the *first* submission matters: IAPs reviewed separately can lag the binary.
- [ ] **Confirm the Paid Apps agreement is Active** (Business → Agreements) — if it is not, purchases
      fail in production even with everything else correct.
- [ ] **Verify Sign in with Apple** on the distribution profile. Xcode Organizer regenerated this during
      the 07-16 archive; if Distribute ever errors, enable the capability at developer.apple.com →
      Identifiers → `me.revelryapp.quiz`, then re-Distribute.
- [ ] **Optional but smart: add internal TestFlight testers first.** The tester list is currently empty
      (0 testers) — past installs on Ruchi's device were direct devicectl dev-installs, never TestFlight.
      TestFlight is also the cheapest way to run the iOS purchase smoke on a real build.
- Once approved, RevenueCat's App Store "Could not check" clears (cosmetic pre-approval).

**Upload new listing assets with the submission** — screenshots and copy were refreshed 2026-07-16:
`marketing/app-store/iphone-6.7/` + `ipad-12.9/` (7 screens each, exact required px) and
`marketing/store-listing.md` (name **Revelry Games**, all 33 games, v3.1.1 release notes).

### Google Play — ✅ SUBMITTED FOR REVIEW 2026-07-20

**All 12 changes sent to Google 2026-07-20 (~4:45 AM PT); status "Changes in review".** Managed
publishing OFF → on approval the app goes LIVE in production automatically (176 countries; Korea
excluded pending GRAC). Submitted: production release **8 (3.1.2)** (AD_ID-free bundle), all
content declarations, IARC rating (ESRB Teen / PEGI 18 / AU R18+), Data safety, listing +
screenshots + feature graphic, Games→Trivia, contacts. Internal testing also serves 8 (3.1.2)
(superseded v5, which was blocking the ad-ID check). Reviews typically complete within 7 days.
**After approval: run the license-tester purchase smoke immediately** (Play Billing is live then).

#### Original checklist (completed)
- [ ] **Rebuild the AAB at versionCode 7** — the existing artifact is v3.1.1/6 and carries the paywall
      bug. Needs the release keystore password (not found in `backupenv/quiz/local/`, the keychain, or
      the env): `cd frontend/android && KEYSTORE_PASSWORD=… KEY_PASSWORD=… ./gradlew bundleRelease`
      → `app/build/outputs/bundle/release/app-release.aab` (keystore `~/keystores/revelry-quiz-upload-v2.keystore`).
- [ ] **Upload the signed release AAB.** Bump `versionCode` for any re-upload.
- [ ] Complete the listing tasks (Phase 4).
- [ ] **Promote to a closed/open testing track first**, run the license-tester purchase gate
      (Phase 6), then promote to Production. Products are already Active + mapped in RevenueCat.

---

## Phase 4 — Play store listing gaps ("Set up your app": was 1/11)

Assets we already have (in `marketing/`): app icon (512/1024), **feature graphic** 1024×500
(`play-store/feature-graphic.png`), **gameplay** shots (`gameplay/`), and — refreshed 2026-07-16 —
**phone** (`play-store/phone/`) and **tablet** (`play-store/tablet-10/`) screenshots (7 screens each,
captured from prod at exact required px) plus rewritten copy in `store-listing.md` (name **Revelry
Games**, all 33 games, short + full description, v3.1.1 release notes). To regenerate any of the
screenshots see `marketing/STORE_ASSETS.md`.

Play Console → this app → complete each dashboard task:
- [ ] **App access** — declare whether login is required (sign-in is optional; guest play works) + any test creds.
- [ ] **Ads** — declare whether the app contains ads (currently no; update if AdMob is added).
- [ ] **Content rating** — IARC questionnaire; disclose AI-generated content + user-generated content.
- [ ] **Target audience & content** — set age groups (13+; not designed for children — avoids Families policy).
- [ ] **Data safety** — use the matrix in `marketing/store-privacy-declarations.md` (email = optional/sign-in only, purchase history, user IDs, app interactions, crash logs; no ads ID, no location, no payment details).
      purchases. No data sold; encrypted in transit.
- [ ] **Government apps / Financial features / Health** — declare "no" as applicable.
- [ ] **Main store listing** — app name **Revelry Games**, short + full description (from `store-listing.md`),
      **feature graphic**, **phone screenshots** (≥2; use `marketing/play-store/phone/` + `marketing/gameplay/`),
      tablet screenshots, app icon, category = **Games / Trivia**, contact email, privacy policy URL.
- [x] **Privacy policy URL** — ✅ `https://games.revelryapp.me/privacy` (rewritten 2026-07-18 to cover
      accounts + purchases; must stay consistent with the Data safety form).
- [x] **Support URL** — ✅ `https://games.revelryapp.me/support` (new 2026-07-18; required by Apple).
- [ ] **Fill both consoles from `marketing/store-privacy-declarations.md`** — ready-made App Privacy
      and Data safety matrices derived from the real schema, so the forms and the policy agree.
- [ ] **Store settings** — category, tags, contact details.

When all tasks are ✅, the "promote to Production" action unblocks.

---

## Phase 5 — Web Stripe go-live ✅ CONFIGURED 2026-07-15 (real-card test pending)

**Status: live keys set + verified; one real-card test remaining.** On 2026-07-15 the prod `.env`
was set with a live `sk_live_` `STRIPE_SECRET_KEY`, a `whsec_` `STRIPE_WEBHOOK_SECRET` (endpoint
`https://gamesapi.revelryapp.me/webhook/stripe`, events `checkout.session.completed` /
`charge.refunded` / `charge.dispute.created`), and `CHECKOUT_RETURN_URL=https://games.revelryapp.me/`;
the container was recreated to load them. Verified live: `/webhook/stripe` → 400 (configured, was
503), `/checkout/create` → a real `cs_live_` Checkout Session on `checkout.stripe.com`. Inline
`price_data` (no Stripe Product objects). Live secrets backed up in
`backupenv/quiz/local/localplay-prod-payment.env`.

**Remaining:** one real-card purchase on `games.revelryapp.me` (small pack) → confirm
`checkout.session.completed` credits sparks in prod logs → optionally refund to confirm clawback.
(Note: the improved payment-modal frontend — cost context + terms — ships with the next web/IONOS
deploy; the checkout *flow* already works with the currently-deployed frontend.)

---

## Phase 6 — Release gates (must pass before broad rollout)

Submission can proceed in parallel, but **do not promote to full production release until the
purchase smokes below pass.** Everything up to this point is verified server-side with synthetic
events; no *real* store purchase has ever been proven on prod. Tail the backend while testing:

```bash
gcloud compute ssh revelry-backend --zone us-central1-a \
  --command 'docker logs games-backend -f' | grep -iE 'IAP credit|revenuecat|checkout.session'
```

**Payments**
- [ ] **iOS** — real or sandbox purchase on the submitted build → sparks credit via `/webhook/revenuecat`.
- [ ] **Android** — license-tester install + buy → sparks credit. *The one entirely unproven path:
      no real Play purchase has ever completed.*
- [ ] **Web** — one small real-card purchase on `games.revelryapp.me` → `checkout.session.completed`
      credits sparks. Then optionally refund → confirm the clawback debit.

**Auth**
- [ ] **Google sign-in** on the installed iOS and Android builds.
- [ ] **Apple sign-in on an adult Apple ID** — the flow is wired and launches correctly; the earlier
      failure was a child/Family-Sharing account, not a code defect.

**Rollout advice:** for Play, use a closed/open testing track or a staged percentage rollout first —
it makes the Android purchase gate cheap to run against the real production billing path without
exposing everyone.
