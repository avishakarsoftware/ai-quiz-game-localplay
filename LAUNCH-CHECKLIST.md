# LAUNCH-CHECKLIST — IAP / native app go-live

Ordered, ready-to-run runbook to take Revelry Games (`me.revelryapp.quiz`) IAP + native apps live.
Engineering is done and verified (real iOS purchase + Google auth on device, 2026-07-07). Prod backend
RevenueCat webhook auth is configured and deployed (verified 2026-07-14). What remains is
**RevenueCat console hookup, store submissions, Play listing, and optional live Stripe keys** — no code work. Cross-refs: `SPEC-IAP.md §0`,
`DEPLOY.md §3c/§3d`, secrets in `backupenv/quiz/local/iap-setup.md`.

Status snapshot (verified 2026-07-14):
- Prod backend has the IAP code and `REVENUECAT_WEBHOOK_SECRET`; unauthenticated
  `POST /webhook/revenuecat` returns **401** (configured + rejecting unauthenticated traffic).
- Prod `ALLOWED_ORIGINS` includes the capacitor/localhost origins.
- Pending on prod: create the matching RevenueCat console webhook using the stored prod secret; `STRIPE_SECRET_KEY`
  and `STRIPE_WEBHOOK_SECRET` remain unset for web checkout.

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

## Phase 2 — Native app builds (point at prod)

```bash
cd frontend
npm run cap:sync:prod      # bakes VITE_API_URL=https://gamesapi.revelryapp.me + RC/OAuth keys
```
- **iOS**: `npx cap open ios` → bump build if needed → **Archive** → upload to App Store Connect.
- **Android**: `cd android && KEYSTORE_PASSWORD=… KEY_PASSWORD=… ./gradlew bundleRelease` (v2 keystore; bump
  `versionCode`) → upload the AAB to the **Production** track (after the listing below is complete).

---

## Phase 3 — Store submissions

### App Store (iOS)
- Submit the app build **with the 3 IAPs attached** for review (the consumables are "Ready to Submit").
- Once approved, RevenueCat's App Store "Could not check" clears (it's cosmetic pre-approval).
- Confirm the Paid Apps agreement is Active (Business → Agreements).

### Google Play
- Complete the store listing (Phase 4), then **promote** the internal-testing build → Production (or a
  closed/open testing track first). Products are already Active + mapped in RevenueCat.

---

## Phase 4 — Play store listing gaps ("Set up your app": was 1/11)

Assets we already have (in `marketing/`): app icon (512/1024), **feature graphic** 1024×500
(`play-store/feature-graphic.png`), **phone screenshots** (`play-store/phone/`), **tablet**
(`play-store/tablet-10/`), **gameplay** shots (`gameplay/`), and listing copy (`store-listing.md`).

Play Console → this app → complete each dashboard task:
- [ ] **App access** — declare whether login is required (sign-in is optional; guest play works) + any test creds.
- [ ] **Ads** — declare whether the app contains ads (currently no; update if AdMob is added).
- [ ] **Content rating** — fill the IARC questionnaire (quiz/social; no objectionable content).
- [ ] **Target audience & content** — set age groups (13+; not designed for children — avoids Families policy).
- [ ] **Data safety** — declare data collected: account (email on sign-in), device/analytics (PostHog if on),
      purchases. No data sold; encrypted in transit.
- [ ] **Government apps / Financial features / Health** — declare "no" as applicable.
- [ ] **Main store listing** — app name **Revelry Games**, short + full description (from `store-listing.md`),
      **feature graphic**, **phone screenshots** (≥2; use `marketing/play-store/phone/` + `marketing/gameplay/`),
      tablet screenshots, app icon, category = **Games / Trivia**, contact email, privacy policy URL.
- [ ] **Privacy policy URL** — host a privacy policy (e.g. `https://games.revelryapp.me/privacy`) and link it.
- [ ] **Store settings** — category, tags, contact details.

When all tasks are ✅, the "promote to Production" action unblocks.

---

## Phase 5 — Web Stripe go-live (optional; only to sell on web)

Web currently can't sell in prod (`STRIPE_SECRET_KEY`/`STRIPE_WEBHOOK_SECRET` unset). To enable:
- Activate the Stripe account (business/bank/tax) → live mode.
- Set prod `STRIPE_SECRET_KEY` (`sk_live_…`) + a live `/webhook/stripe` endpoint → `STRIPE_WEBHOOK_SECRET`.
- Redeploy prod. Inline `price_data` needs no Stripe Product objects.
- Test with a real card on `games.revelryapp.me`.

---

## Phase 6 — Post-launch verification
- Real purchase on each store (or sandbox/license-tester) → confirm sparks credited via `/webhook/revenuecat`.
- Watch `docker logs games-backend -f | grep -iE 'IAP credit|revenuecat'`.
- Sanity: refund a sandbox purchase → confirm the clawback debit.

## Remaining device-dependent tests (not blockers for the above)
- **Android device purchase** (license-tester install + buy) — the one unproven path.
- **Apple sign-in on an adult Apple ID** (the flow works; test phone's child account blocked it).
