# Token Economy Rollback Plan

> **HISTORICAL — this plan is no longer executable as written. Kept for the reasoning, not the steps.**
>
> It was written in March 2026, when the spark economy was an undeployed branch and the entitlement
> system was still live on master. Both premises are now false:
>
> - The spark economy shipped on 2026-03-22 and has been the only economy in production for months,
>   taking **real money** through Stripe and native IAP. Reverting to entitlements would orphan every
>   spark balance and every purchase recorded in `token_transactions`, so "roll back the code" is no
>   longer a safe operation — it is a data migration nobody has written.
> - The code this plan restores was **deleted from master on 2026-08-04** as dead weight:
>   `backend/premium.py`, the 9 entitlement/free-usage functions in `db.py` + `supabase_db.py`, and the
>   frontend `useEntitlement` hook + `QuotaBadge`. Nothing had imported them since March.
>
> Everything is recoverable — the pre-economy tree is tagged `pre-token-economy` (`0b1a8ec`), and the
> deletion commit has the full diff. If you ever genuinely need this, start from the tag, and budget
> for the balance-migration problem above rather than following Step 1 below.
>
> Still true and still worth reading: the failure modes under "When to Rollback", and the
> `/entitlements/current` compat note — that endpoint deliberately survives for pre-March-2026 app
> builds still installed on devices.

---

## When to Rollback

- Token balance bugs causing incorrect charges or lost tokens
- Stripe webhook not crediting tokens properly
- Migration corrupted existing users' entitlements
- Blocking App Store review issue tied to token economy

---

## Quick Rollback (Code Only)

If the economy branch has **not been deployed to production**:

```bash
git checkout master
```

Done. No data changes needed — production is still running the entitlement system.

---

## Full Rollback (After Production Deploy)

### Step 1: Deploy master branch

```bash
git checkout master
```

Build and deploy the frontend and backend from master. This restores:
- `backend/premium.py` as the active business logic
- All `/entitlements/current`, `/checkout/token` (JWT), `/room/create` (entitlement check) endpoints
- Frontend `useEntitlement` hook, `QuotaBadge`, premium JWT in `Authorization` header
- `getPremiumToken()` / `setPremiumToken()` in storage

### Step 2: Handle migrated entitlements

The economy branch migration marks active entitlements as `status = 'migrated_to_tokens'`. The old code only looks for `status = 'active'`, so migrated users would appear to have no entitlement.

Run this SQL on the production database to restore them:

```sql
UPDATE entitlements
SET status = 'active'
WHERE status = 'migrated_to_tokens';
```

### Step 3: Stripe webhook

The master branch webhook expects to:
1. Find a pending entitlement via `device_id` in Stripe metadata
2. Activate it and create a premium JWT

The economy branch stores `wallet_id` in Stripe metadata and credits tokens instead. **Any Stripe sessions created during the token economy period** will have `wallet_id` in metadata and no pending entitlement.

To handle in-flight purchases:
1. Check for any `checkout.session.completed` events in Stripe dashboard that arrived after the rollback
2. Manually activate entitlements for those device IDs via the admin endpoint:
   ```
   POST /admin/grant?device_id=<id>
   ```

### Step 4: Frontend storage cleanup

The economy branch removed `getPremiumToken()` / `setPremiumToken()`. Users who purchased during the token economy period won't have a premium JWT in localStorage.

These users will need to use **Restore Purchases** in the Settings drawer, which re-issues the JWT on master.

### Step 5: Verify

1. `/entitlements/current` returns correct free tier / premium status
2. New purchases flow through Stripe → webhook → entitlement activation → JWT
3. Existing users with active entitlements see correct games remaining
4. Free tier users see "X of 3 free games used"

---

## Database Tables

| Table | Action on Rollback |
|-------|-------------------|
| `entitlements` | **Restore** — set `migrated_to_tokens` back to `active` |
| `free_usage` | **No change** — still used by master |
| `wallets` | **Leave in place** — unused by master, no harm |
| `token_transactions` | **Leave in place** — unused by master, no harm |
| `users` | **No change** — unchanged between branches |
| `pending_tokens` | **No change** — unchanged between branches |

---

## Files Changed on Economy Branch

### New files (not on master — will be gone after checkout):
- `backend/tokens.py`
- `backend/tests/test_tokens.py`
- `backend/tests/conftest.py`
- `frontend/src/hooks/useTokenBalance.ts`
- `frontend/src/components/TokenBadge.tsx`

### Modified files (restored by checking out master):
| File | What changes back |
|------|-------------------|
| `backend/config.py` | `FREE_TIER_LIMIT` and `PREMIUM_DURATION_HOURS` restored; token constants removed |
| `backend/db.py` | Wallet tables still created (harmless) but wallet functions unused; migration function won't run |
| `backend/main.py` | `import premium` restored; entitlement-based `/room/create`, JWT-based webhook, `/entitlements/current` endpoint |
| `backend/auth.py` | `db.merge_wallet()` call removed from signin |
| `frontend/src/utils/storage.ts` | `getPremiumToken`, `setPremiumToken`, `clearPremiumToken` restored |
| `frontend/src/utils/api.ts` | `Authorization: Bearer <JWT>` header restored |
| `frontend/src/pages/OrganizerPage.tsx` | "Free Games Used Up" / "Party Pass" messaging restored |
| `frontend/src/components/ErrorModal.tsx` | "10 Games for 30 Days" button text restored |
| `frontend/src/components/SettingsDrawer.tsx` | "Party Pass" language restored |
| `frontend/src/components/SignInNudge.tsx` | "Party Pass" language restored |
| `frontend/src/components/organizer/PromptScreen.tsx` | `useEntitlement` + `QuotaBadge` imports restored |
| `frontend/src/components/organizer/MLTPromptScreen.tsx` | Same as PromptScreen |
| `frontend/src/types/remoteConfig.ts` | `pass_price` / `pass_duration_label` pricing fields restored |

---

## Risk Assessment

| Risk | Severity | Mitigation |
|------|----------|------------|
| Users who purchased tokens lose them | Medium | Tokens were bought with real money — issue refunds via Stripe for any token-only purchases |
| Migrated entitlements not restored | High | Run the SQL UPDATE above immediately after deploy |
| In-flight Stripe sessions fail | Low | Small window; manually grant via admin endpoint |
| Users confused by UI change | Low | Only affects users who saw the token UI during the economy period |
| Daily bonus tokens disappear | None | Bonus tokens were free — no refund needed |

---

## Checklist

- [ ] `git checkout master`
- [ ] `UPDATE entitlements SET status = 'active' WHERE status = 'migrated_to_tokens'`
- [ ] Build and deploy backend
- [ ] Build and deploy frontend
- [ ] Verify `/entitlements/current` works
- [ ] Verify new Stripe purchase → entitlement activation → JWT flow
- [ ] Check Stripe dashboard for any in-flight sessions to reconcile
- [ ] Notify affected users if any token-only purchases need refunds
