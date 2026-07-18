# SPEC-ACCOUNT-DELETION — In-app account deletion

Status: **Draft — not implemented** (2026-07-18)
Owner: Avi
Related: `SPEC-IAP.md` (wallets, purchases), `LAUNCH-CHECKLIST.md` (submission blocker),
`frontend/public/privacy.html` (§5 rights), `marketing/store-privacy-declarations.md`

---

## 0. Why this exists

**This is a store-submission blocker.** App Store Review Guideline **5.1.1(v)**: an app that
supports account creation must let the user **initiate account deletion from within the app**.
Revelry Games creates accounts — `find_or_create_user` does `INSERT INTO users` on Google/Apple
sign-in — and today offers sign-in, sign-out, and Restore purchases, but **no deletion path** in
the UI or the backend. Pointing users at an email address does **not** satisfy the guideline.

Google Play's equivalent (Data safety → data deletion) can be satisfied by a URL, so Android is
already covered by the policy contact. **iOS is the blocker.**

---

## 1. The data model (verified 2026-07-18, `backend/db.py`)

Understanding this is non-optional, because the identity model is unusual.

**`wallet_id` is polymorphic.** From `tokens.get_wallet_id`:

> *"Resolve wallet ID: user_id if signed in, else device_id."*

There is **no foreign key**. `wallets.id` holds a `users.id` for signed-in users and a raw device
id for guests. Consequently a user's Sparks live in a wallet row whose primary key **is** their
user id, and `token_transactions.wallet_id` / `generated_content.wallet_id` point at that same
value.

Tables carrying user-linked data:

| Table | Link column | Contains |
|---|---|---|
| `users` | `id` (PK) | provider, provider_subject_id, **email** — the only PII |
| `wallets` | `id` == user_id | balance, lifetime_purchased, bonus/streak state |
| `token_transactions` | `wallet_id` | purchase + spend ledger, `reference_id` |
| `generated_content` | `wallet_id` | saved quizzes/prompts the user authored |
| `entitlements` | `user_id`, `device_id` | legacy entitlement rows |
| `device_usage` | `user_id`, `device_id` | free-usage counters |

On sign-in, `merge_device_to_user` and `merge_wallet(device_id, user_id)` fold the guest wallet
into the user wallet — so by deletion time, Sparks earned as a guest are already in the user wallet.

---

## 2. ⚠️ The trap: sessions are unrevocable JWTs

`create_session_token` issues a **stateless JWT** (`SESSION_JWT_EXPIRY_DAYS = 30`), and
`get_session_from_request` **only verifies the signature — it never checks that the user still
exists.**

A naive "delete the users row" implementation is therefore actively harmful:

1. Delete `users` row. The client still holds a valid JWT for up to **30 days**.
2. Next request → `get_wallet_id()` returns the deleted `user_id` from the token.
3. `get_or_create_wallet(user_id, signup_bonus=True)` **recreates the wallet — with a fresh signup
   bonus.**

Net effect: the account silently resurrects, deletion appears not to work, and it becomes a
**Spark-farming loop** (delete → keep using the same token → repeat). Any implementation must close
this, and it is the single most important requirement in this spec.

**Decision: maintain a `deleted_users` denylist**, checked during session verification.
Rejected alternatives:
- *Look up `users` on every request* — adds a DB read to the hot path, and cannot distinguish
  "deleted" from "never existed", which matters for the error we return.
- *Shorten JWT expiry* — narrows but does not close the window, and hurts normal users.

Rows may be pruned once older than `SESSION_JWT_EXPIRY_DAYS` (no live token can reference them).

---

## 3. What is deleted, kept, and why

**Deleted immediately (hard delete):**
- `users` row — **all PII** (email, provider subject id)
- `wallets` row keyed on the user id — **including any unspent Spark balance**
- `generated_content` authored by that wallet
- `entitlements` / `device_usage` rows for that `user_id`

**Retained — `token_transactions`:** the purchase/spend ledger stays. This is a deliberate,
disclosed exception, on two grounds:
1. **Legal.** Purchase records are financial records with tax/accounting retention obligations, and
   GDPR Art. 17(3)(b) permits retention for legal compliance. Apple accepts retention where law
   requires it, provided it is disclosed.
2. **Operational.** `credit_purchase` is idempotent on `reference_id`; the ledger is what prevents
   double-crediting a replayed or late webhook.

The ledger is **pseudonymized by construction after deletion**: its only identifier is
`wallet_id` — the deleted user's random UUID. With `users` gone, nothing links it to an email,
provider, or person. **No additional scrubbing is required, and none should be invented** — mutating
`wallet_id` would break the idempotency guarantee above.

> Open question for Avi: confirm this retention stance is what you want. The alternative (deleting
> transactions too) is cleaner privacy-wise but sacrifices refund/chargeback defensibility and
> double-credit protection.

**Not deleted:** live in-memory game sessions (they expire on their own), and analytics events
already sent to PostHog (documented in the policy as separately retained).

---

## 4. Behaviour

### 4.1 Endpoint

```
DELETE /account
Headers: X-Session-Token (required)
Body:    { "confirm": "DELETE" }
```

- **401** if no/invalid session; **410 Gone** if the user is already deleted (denylisted).
- **400** if `confirm` is absent — a deliberate second gate so a stray call cannot destroy data.
- **200** `{ "deleted": true }` on success.
- **Rate limited** (reuse the existing limiter) — this is a destructive, unauthenticated-adjacent
  endpoint.
- **Idempotent**: deleting twice returns 410, never 500.
- Wrapped in a **single transaction** so a partial failure cannot leave a half-deleted account
  (e.g. wallet gone, PII retained — the worst possible outcome).

### 4.2 Client

Settings drawer, in the account section, below Sign out:
- **"Delete account"** in a destructive style, shown **only when signed in**.
- Confirmation dialog stating plainly:
  - the account and **email** are permanently deleted
  - **unspent Sparks are forfeited** — see §4.2.1, this is the headline warning
  - purchases **cannot be restored** to a new account
  - saved custom content is deleted
  - the action **cannot be undone**
- Requires an explicit confirm (typed `DELETE`, matching the API contract).
- On success: clear the local session/device state, sign out, return to the catalog as a guest,
  and show a confirmation toast.

#### 4.2.1 Unspent Sparks warning (required)

Losing paid-for currency is the most consequential and least obvious effect of deletion, and the
one a user is most likely to regret. The dialog must therefore surface it **conditionally and
concretely** — never as boilerplate:

- **Balance > 0 →** show a prominent, visually distinct warning with the **exact live balance**,
  fetched at dialog-open time (not a stale cached value):

  > ⚡ **You still have 240 Sparks.**
  > They will be permanently destroyed and cannot be recovered, refunded, or moved to another
  > account — including if you sign in again with the same Google or Apple account.

  Singular/plural must agree ("1 Spark"). If the balance is large, this is exactly the case where a
  user should be given pause, so the warning ranks **above** the other consequences in the dialog.

- **Balance == 0 →** omit the Sparks warning entirely. Warning someone about losing nothing is
  noise that trains people to skip the dialog, which is precisely when they miss a real warning.

- **Balance unavailable** (request fails) → do **not** silently show nothing, and do not block
  deletion. Fall back to the non-numeric form: *"Any unspent Sparks will be permanently destroyed."*

The number shown must come from the same `/tokens/balance` source the header badge uses, so the
dialog can never contradict the balance the user is looking at.

### 4.3 After deletion

- **Signing in again with the same Google/Apple account creates a brand-new account** — new
  `users.id`, new empty wallet. Prior Sparks and purchase history do **not** return. The
  confirmation copy must make this unambiguous.
- **Guest wallet:** the device id persists, so the user falls back to their guest wallet. Deletion
  must **not** grant a fresh signup bonus to that device — verify `get_or_create_wallet` is called
  with the existing device id (already-existing wallet ⇒ no bonus).
- **Late webhooks** (a refund or a delayed purchase arriving after deletion) must **not** resurrect
  an account. `credit_purchase` for a denylisted wallet id should be recorded and acked (HTTP 200,
  so the provider stops retrying) but must not recreate `users`. **Test this explicitly** — it is
  the second-most-likely way for this feature to silently regress.

---

## 5. Testing

**Backend**
- deletes users/wallet/content/entitlements/device_usage; retains `token_transactions`
- **a session token for a deleted user is rejected** (the §2 trap) — and specifically does *not*
  recreate a wallet with a signup bonus
- second delete → 410, not 500
- missing/incorrect `confirm` → 400; no session → 401
- a late `credit_purchase` for a deleted wallet does not resurrect the user
- re-sign-in with the same provider subject creates a *different* `users.id`
- transaction integrity: a forced mid-delete failure leaves **no** partial state

**Frontend**
- the button is hidden when signed out, visible when signed in
- confirmation is required; cancelling changes nothing
- success clears session and returns to guest state
- **Sparks warning (§4.2.1):**
  - balance 240 → warning shown containing "240"
  - balance 1 → singular wording ("1 Spark", not "1 Sparks")
  - balance 0 → Sparks warning **not** rendered
  - balance request fails → non-numeric fallback shown, deletion still possible
  - the figure matches `/tokens/balance`, i.e. the dialog cannot contradict the header badge

**E2E**: extend `legal-pages.spec.ts` or add an account spec asserting the deletion path is
reachable in-app — that is precisely what Apple review checks.

---

## 6. Out of scope

- Grace period / soft-delete with recovery window. Immediate deletion is simpler, more
  privacy-forward, and sufficient. Revisit only if support burden demands it.
- Data **export** (GDPR portability). Currently handled by emailing support; revisit if requested
  volume grows.
- Deleting analytics already transmitted to PostHog.
- Web-only account management UI beyond the shared Settings drawer (the same component serves all
  surfaces).

---

## 7. Rollout

1. Implement backend + tests; full backend suite must stay green.
2. Implement client + tests.
3. Deploy gamma → verify by deleting a real gamma account, then confirm the old token is rejected
   and no wallet reappears.
4. Deploy prod + IONOS.
5. `npm run cap:sync:prod` — **before** the iOS archive, since the native apps bundle the web build.
6. Update `privacy.html` §5 to state deletion is available **in the app** (currently email-only),
   and note the transaction-ledger retention from §3.
7. Update `LAUNCH-CHECKLIST.md` / `DEPLOY.md` ledger.
