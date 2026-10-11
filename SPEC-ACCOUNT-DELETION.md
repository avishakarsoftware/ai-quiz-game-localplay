# SPEC-ACCOUNT-DELETION — In-app account deletion

Status: **Implemented, with owned-content cleanup expanded in the 2026-10-10 source review.** The new Supabase RPC migration is saved locally and has not been applied to gamma or production. Earlier deployment evidence is in `DEPLOY.md`; it does not qualify this change.

Related: `SPEC-IAP.md`, `SPEC-CUSTOM-QUIZ-AUTHORING.md`, `SPEC-SUPABASE-MIGRATION.md`, `frontend/public/privacy.html`.

## 1. Identity and revocation

`tokens.get_wallet_id` uses the signed-in `users.id` as the wallet id, and the device id for guests. Sign-in merges the device wallet into the user wallet. Provider subject identifies the account; email is display information.

Session JWTs have a default 30-day lifetime. `auth.get_session_from_request` verifies the JWT and checks `deleted_accounts`. A denylisted user is treated as signed out, so the old session cannot recreate the deleted user's wallet. Wallet operations also guard deleted accounts. There is no automatic denylist pruning job; removing entries merely because the JWT lifetime elapsed would need a separate review of late payment fulfillment.

## 2. Transactional deletion

`db.delete_account(user_id)` and the prefixed Supabase `delete_account` RPC perform these changes in one transaction:

| Data | Behavior |
|---|---|
| `users` | Delete the provider identity and email row. |
| `wallets` | Delete the wallet keyed by user id, including unspent Sparks. |
| `generated_content` | Delete rows owned by that wallet. |
| SQLite `custom_quiz_packs` / `custom_quiz_questions`; Supabase `{prefix}quiz_packs` / `{prefix}quiz_questions` | Delete all owned packs and their questions, including previously soft-deleted packs. |
| `media_assets` | Delete owned LocalPlay asset metadata. |
| `entitlements`, `device_usage` | Delete rows linked by user id. |
| `deleted_accounts` | Insert the opaque user id and deletion timestamp. |
| `token_transactions` | Retain the purchase/spend ledger and stable reference ids for payment deduplication. |

Another wallet's content must remain untouched. Revelry content owned by `revelry:party:{party_id}` belongs to the party and is not erased by deleting an individual's standalone account. Existing rooms, process-local histories, statistics, other aggregate records, and analytics already sent to PostHog are not covered by this transaction.

**Storage limitation:** metadata deletion does not delete IONOS/CDN bytes or revoke a public image URL. A separate authenticated storage deletion/retention path remains required before claiming uploaded files are physically erased. Images may also remain in active in-memory rooms until those rooms expire.

## 3. API

```http
DELETE /account
X-Session-Token: <session JWT>
Content-Type: application/json

{"confirm":"DELETE"}
```

- The endpoint uses the existing per-IP rate limiter; excess requests return `429`.
- Missing/invalid/denylisted session returns `401`. A retry using the deleted user's old token normally follows this path.
- A well-formed body with missing or incorrect confirmation returns `400`; malformed/missing request bodies may return FastAPI validation `422`.
- Successful deletion returns `200 {"deleted":true}`.
- If the account becomes denylisted after the session check, the transaction returns false and the endpoint returns `410`.
- Failure rolls back the transaction; no partial content, identity, wallet, or denylist deletion is allowed.

`account_deleted` is captured before the database call, without email or provider tokens. That best-effort analytics event is not proof the deletion transaction committed.

## 4. Client

`SettingsDrawer` shows **Delete account** only while signed in. `DeleteAccountDialog` requires exact typed `DELETE`, disables duplicate submissions, and warns that the account, email, unspent Sparks, and owned content are lost. Purchases cannot restore the old wallet after signing in again.

The dialog fetches `/tokens/balance` on open. Positive balances receive a numeric warning with correct singular/plural wording; zero omits it. A failed balance fetch uses “Any unspent Sparks will be permanently destroyed” and does not block deletion. This is a fresh read, not a guarantee that another concurrent purchase/spend cannot change the balance before confirmation.

On `200` or `410`, the caller signs out and refreshes guest balance. The device id remains so deletion does not create a new device signup bonus. `401` requests reauthentication. Auth revalidation rejects `401`, `403`, and `410`, clears the cached session, and resets analytics to the guest identity; network/timeouts/server errors preserve a potentially valid cached login.

## 5. Later requests and payments

- Signing in with the same provider subject creates a new user id. The deleted user's wallet and purchase access do not return.
- Guest behavior uses the existing device id; it must not grant a fresh device signup bonus.
- A late `credit_purchase` to a denylisted wallet is ignored without recreating that wallet or adding a new credit. The webhook is acknowledged and its event id processed; previously credited session/transaction references remain deduplicated by the retained ledger.
- Repeated deletion must not return `500` or partially mutate another wallet's content.

## 6. Verification and rollout

SQLite regression coverage is in `backend/tests/test_account_deletion.py`: identity/wallet/content removal, denylist and stale-token behavior, re-sign-in, retained ledger, other-owner isolation, and forced transactional rollback. Real PostgREST coverage is in `backend/tests/test_supabase_economy_features.py`, including saved content/media ownership and rollback under an injected deletion failure. Frontend coverage is in `DeleteAccountDialog.test.tsx`, `SettingsDrawer.test.tsx`, `AuthContext.test.tsx`, and `utils/__tests__/auth.test.ts`.

The review updates `sql/templates/games-schema.template.sql` and both rendered schemas. Existing installations need the **targeted** migrations:

- `sql/migrations/20261010T000000_account_content_deletion_gamma.sql`
- `sql/migrations/20261010T000000_account_content_deletion.sql`

These replace only the corresponding deletion RPC and preserve its service-role-only execution boundary. Do not apply a full bootstrap schema to the shared database. Qualify both prefixes against a fresh disposable local PostgreSQL/PostgREST stack, then use the release plan's backup, targeted migration, gamma verification, and promotion gates. Local SQL validation is not evidence that either hosted function has been updated.

Deletion has no recovery window. Data export, remote byte cleanup, and removal of previously transmitted analytics remain separate work.
