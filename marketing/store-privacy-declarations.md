# Store Privacy Declarations — Revelry Games

Fill-in reference for Apple's **App Privacy** questionnaire and Google Play's **Data safety** form.

**Why this file exists:** the two store forms and the published privacy policy must agree. They are
filled in months apart, in different consoles, from memory — which is how they drift. Everything
below is derived from the same source of truth as
[`frontend/public/privacy.html`](../frontend/public/privacy.html): the actual schema in
`backend/db.py` and the actual third-party integrations. **If you change what the app collects,
update the policy and this file in the same commit.**

Verified against: `users` (`id`, `provider`, `provider_subject_id`, `email`, `created_at`),
`wallets`, `token_transactions` (`wallet_id`, `amount`, `reason`, `reference_id`, `balance_after`,
`metadata`, `created_at`) — 2026-07-17.

---

## The short version

- Guest play collects **no** account data. Sign-in is optional.
- We collect **email only** via optional Google/Apple sign-in. No name, phone, contacts, photos, or
  precise location.
- We store **purchase records**, never payment details — Stripe/Apple/Google handle those.
- **No advertising identifiers, no third-party ad SDKs, no cross-app tracking.** (`SPEC-ADS.md` is
  not built. If AdMob ever ships, both forms and the policy must be revised.)
- We do **not** sell data.

---

## Apple — App Privacy (App Store Connect → App Privacy)

| Data type | Collected? | Linked to identity? | Used for tracking? | Purpose |
|---|---|---|---|---|
| **Contact Info → Email Address** | Yes — *only* if the user signs in | Yes | No | App Functionality (cross-device account) |
| **Purchases → Purchase History** | Yes | Yes, when signed in | No | App Functionality (deliver Sparks, prevent duplicate credits, refunds) |
| **Identifiers → User ID** | Yes | Yes | No | App Functionality (device id keeps the Spark balance attached) |
| **User Content → Other User Content** | Yes — nicknames, topics/prompts, drawings, answers | No | No | App Functionality; Analytics |
| **Usage Data → Product Interaction** | Yes | No | No | Analytics; App Functionality |
| **Diagnostics → Performance / Crash Data** | Yes | No | No | Analytics; App Functionality |

**Not collected** (answer *No* to all): Name, Phone Number, Physical Address, Health & Fitness,
Financial Info (payment method — Apple/Stripe handle it, we never receive it), Precise or Coarse
Location, Contacts, Photos or Videos, Audio Data, Search History, Browsing History, Advertising Data,
Device ID (**advertising** identifier — note this is distinct from *User ID* above, which we do use),
Sensitive Info.

**Tracking:** answer **No** to "Do you or your third-party partners use data for tracking?" —
we do not link user data with third-party data for advertising, and there is no ad SDK.

> Apple's "Financial Info" trips people up: we sell things but never see card data, so the honest
> answer is **Purchase History = yes, Payment Info = no**.

### The Facebook SDK in the iOS binary — why "tracking = No" is still correct

**The app binary contains Meta's Facebook SDK (`FacebookCore`, `FacebookLogin`, `FBAEMKit`), and
the app has no Facebook feature.** This looks alarming in a privacy review, so the reasoning is
recorded here rather than re-derived under time pressure.

**How it gets there:** `@capgo/capacitor-social-login` — the plugin used for *Google and Apple*
sign-in — declares `facebook-ios-sdk` unconditionally in its `Package.swift`
(`node_modules/@capgo/capacitor-social-login/Package.swift:15`), pulling in the `FacebookCore` and
`FacebookLogin` products. It is a transitive dependency, not a choice we made, and there is no
build flag to opt out.

**Why it is inert** — verified 2026-07-18, all three independently true:

| Check | Result |
|---|---|
| App source references Facebook | **None.** `frontend/src/` has zero matches; `socialAuth.ts` initializes only `google` (+ `apple` on iOS). |
| `FacebookAppID` / FB URL scheme in `Info.plist` | **Absent.** The SDK has no app identity to authenticate against. |
| Plugin's `FacebookProvider.initialize()` | **Empty function body** — literally `// No initialization required`. Every entry point guards on `AccessToken.current`, which is permanently nil. |

An SDK that is never initialized and has no App ID configured cannot collect, transmit, or link any
data. Apple defines *tracking* as linking user data with third-party data for targeted advertising
or sharing with a data broker — none of which can occur here. **"No" is the truthful answer.**

**If App Review asks**, the reply is: *"The Facebook SDK is a transitive dependency of the
Capacitor social-login plugin we use for Sign in with Google and Sign in with Apple. It is never
initialized, no Facebook App ID is configured, and the app exposes no Facebook functionality."*

**Deliberately not removed.** Excluding it means patching `Package.swift` inside `node_modules`
(silently lost on every `npm install` unless `patch-package` is adopted). A subtly wrong patch
breaks Google/Apple sign-in — a far worse outcome than a reviewer question. Revisit only if Apple
actually objects, or if the plugin is replaced for other reasons.

**This changes if Facebook login is ever enabled**, or if the SDK is initialized for any reason —
at that point it becomes a real data path and both store forms plus
[`privacy.html`](../frontend/public/privacy.html) must be revised.

---

## Google Play — Data safety

**Overview answers**
- Does your app collect or share required user data? **Yes**
- Is all user data encrypted in transit? **Yes** (HTTPS/WSS everywhere)
- Do you provide a way to request data deletion? **Yes** — `support@revelryapp.me`, documented in
  the policy §5 and on the support page. Provide that URL in the deletion-request field.

| Data type | Collected | Shared | Optional? | Purpose |
|---|---|---|---|---|
| **Personal info → Email address** | Yes | No | **Optional** (sign-in only) | App functionality; Account management |
| **Personal info → User IDs** | Yes | No | Required | App functionality (device id / account id) |
| **Financial info → Purchase history** | Yes | No | Required (if purchasing) | App functionality |
| **App activity → App interactions** | Yes | No | Required | Analytics; App functionality |
| **App activity → Other user-generated content** | Yes | No | Required | App functionality; Analytics |
| **App info & performance → Crash logs** | Yes | No | Required | Analytics; App functionality |
| **App info & performance → Diagnostics** | Yes | No | Required | Analytics; App functionality |

**Not collected:** Name, Address, Phone number, Race/ethnicity, Political or religious beliefs,
Sexual orientation, Other personal info, Payment info (card details), Credit score, Location
(approximate or precise), Web browsing history, Contacts, Calendar, Photos/Videos, Audio, Files,
Health & fitness, SMS/Call logs, Installed apps, Device or other IDs (**advertising ID** — none).

> "Shared" = transferred to a third party for *their own* use. Our providers (Supabase, Stripe,
> RevenueCat, PostHog, Gemini) are processors acting on our behalf, so **No** is correct — but keep
> them listed in the policy's third-party table either way.

---

## Related Play Console tasks

- **Ads** — declare **No ads**. Revisit if `SPEC-ADS.md` (AdMob rewarded video) is ever built.
- **App access** — sign-in is **optional**; all content is reachable without credentials. Say so, so
  review isn't blocked waiting for a test account. Provide one only if asked.
- **Target audience** — **13+**. Do *not* select an under-13 age group: that triggers Play's Families
  policy, which brings extra requirements the app is not built for. Consistent with policy §11.
- **Content rating (IARC)** — party/trivia. Disclose that **content is AI-generated** and that users
  submit free-text/drawings, i.e. user-generated content is present.

## Apple — related fields

- **Support URL** (required): `https://games.revelryapp.me/support`
- **Privacy Policy URL** (required): `https://games.revelryapp.me/privacy`
- **Marketing URL** (optional): `https://revelryapp.me`
- **Age rating**: 12+ or 13+ is the safe read given AI-generated + user-generated content.
- **Sign in with Apple**: offered. Apple requires it wherever a third-party sign-in (Google) is
  offered — both are implemented.
