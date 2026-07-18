import { expect, test } from '@playwright/test';

/**
 * Legal/support pages required by the app stores.
 *
 * Apple requires a working Support URL and Privacy Policy URL; Play requires a privacy policy
 * and a data-deletion contact. These are static files in `frontend/public/`, served on IONOS
 * (Apache MultiViews resolves the extensionless path), on the backend-served SPA, and bundled
 * into both native apps — so one file covers every surface.
 *
 * Why this test exists: `/support` previously "worked" — it returned **200** — but the SPA
 * catch-all was serving index.html, so the page rendered 11 characters of app chrome and no
 * support content. A status-code check cannot catch that; only asserting on rendered text can.
 * A store submission against a URL that renders empty gets rejected late and expensively.
 */

const PAGES = [
    {
        path: '/privacy',
        heading: /Privacy Policy/i,
        // Claims the store declarations depend on (see marketing/store-privacy-declarations.md).
        // If the app's data collection changes, these must change together.
        mustContain: [
            /Sign in with Google or Sign in with Apple/i,
            /never receive or store your card number/i,
            /Stripe/,
            /RevenueCat/,
            /Supabase/,
            /do not sell your personal information/i,
            /privacy@revelryapp\.me/,
        ],
        // The pre-2026-07 policy claimed no accounts and no purchases. Both are now false.
        mustNotContain: [/No Account Required/i, /does not require account registration/i],
    },
    {
        path: '/support',
        heading: /Support/i,
        mustContain: [
            /support@revelryapp\.me/,
            /Sparks/,
            /[Rr]efund/,
            /reportaproblem\.apple\.com/,
            /Restore purchases/i,
        ],
        mustNotContain: [],
    },
] as const;

test.describe('Store-required legal pages', () => {
    for (const page of PAGES) {
        test(`${page.path} serves real content, not the SPA fallback`, async ({ page: browserPage }) => {
            const response = await browserPage.goto(page.path);
            expect(response?.status(), `${page.path} HTTP status`).toBe(200);

            const body = (await browserPage.innerText('body')).replace(/\s+/g, ' ').trim();

            // The SPA fallback renders ~11 chars of chrome ("S 30 sparks"). Real pages are long.
            expect(
                body.length,
                `${page.path} rendered only ${body.length} chars — this is the SPA fallback, not the page`,
            ).toBeGreaterThan(1000);

            await expect(browserPage.locator('h1')).toHaveText(page.heading);

            for (const pattern of page.mustContain) {
                expect(body, `${page.path} must mention ${pattern}`).toMatch(pattern);
            }
            for (const pattern of page.mustNotContain) {
                expect(body, `${page.path} must NOT still claim ${pattern}`).not.toMatch(pattern);
            }
        });
    }

    test('the two pages link to each other', async ({ page }) => {
        await page.goto('/privacy');
        await expect(page.locator('a[href="support.html"]')).toHaveCount(1);

        await page.goto('/support');
        await expect(page.locator('a[href="privacy.html"]').first()).toBeVisible();
    });

    test('the app root still renders (static pages did not break SPA routing)', async ({ page }) => {
        // Guards the inverse of the above: adding static .html files to public/ must not
        // shadow or break normal app routing.
        await page.goto('/');
        await expect(page.getByRole('heading', { name: 'Choose a Game' })).toBeVisible({ timeout: 30_000 });
    });

    test('an unknown path is served by the SPA, not a server 404', async ({ page }) => {
        // Documents actual behaviour: unknown paths return 200 and the SPA shell. The router
        // has no catch-all route, so the shell renders with no page content — cosmetically
        // poor, but it means /privacy and /support MUST be real files (they are, in public/),
        // because an unmatched path would otherwise look "fine" while showing nothing.
        const response = await page.goto('/definitely-not-a-real-page-xyz');
        expect(response?.status()).toBe(200);
        const body = (await page.innerText('body')).replace(/\s+/g, ' ').trim();
        expect(body.length).toBeLessThan(200); // the empty shell — the exact trap this suite guards
    });
});
