import { expect, test, type Page } from '@playwright/test';
import { stubCoreBackend, expectNoHorizontalOverflow } from './helpers';

/**
 * Payment UX: drives the REAL standalone web app (local dev server + stubbed backend)
 * from the spark badge → the Get Sparks purchase modal, and verifies buyers see every
 * piece of information they need before paying, plus the web Stripe flow and failure paths.
 * Network is fully stubbed so this is deterministic and needs no live Stripe keys.
 */

async function stubBalance(page: Page, balance = 12) {
    await page.route('**/tokens/balance', (route) =>
        route.fulfill({ json: { balance, daily_bonus_available: false, bonus_streak: 0 } }),
    );
}

// Capture window.open (the Stripe redirect) instead of spawning a real popup.
async function captureWindowOpen(page: Page) {
    await page.addInitScript(() => {
        (window as unknown as { __opened: string[] }).__opened = [];
        window.open = ((url?: string | URL) => {
            (window as unknown as { __opened: string[] }).__opened.push(String(url));
            return null;
        }) as typeof window.open;
    });
}

async function openPurchaseModal(page: Page) {
    await page.goto('/');
    await expect(page.getByRole('heading', { name: 'Choose a Game' })).toBeVisible();
    await page.locator('[aria-label="Get Sparks"]').first().click();
    return page.getByTestId('spark-purchase-modal');
}

test.describe('Spark purchase (payment) UX', () => {
    test.beforeEach(async ({ page }) => {
        await stubCoreBackend(page);
        await stubBalance(page);
        await captureWindowOpen(page);
    });

    test('shows all the information a buyer needs before paying', async ({ page }) => {
        const modal = await openPurchaseModal(page);
        await expect(modal.getByRole('heading', { name: 'Get Sparks' })).toBeVisible();

        // What sparks are + what they cost to use (pack sizes are meaningless without this).
        await expect(modal.getByText(/Sparks are used to generate quizzes and host games/)).toBeVisible();
        await expect(modal.getByTestId('spark-cost-context')).toContainText('Host a game: 10');
        await expect(modal.getByTestId('spark-cost-context')).toContainText('Each AI quiz: 1');

        // Three tiers with amounts, prices and value badges.
        for (const [amount, price] of [['50', '$1.99'], ['200', '$4.99'], ['500', '$9.99']] as const) {
            await expect(modal.getByText(amount, { exact: true })).toBeVisible();
            await expect(modal.getByText(price, { exact: true })).toBeVisible();
        }
        await expect(modal.getByText('Popular')).toBeVisible();
        await expect(modal.getByText('Best value')).toBeVisible();

        // Purchase terms + a no-cost way out.
        await expect(modal.getByTestId('spark-purchase-terms')).toContainText(/one-time purchase/i);
        await expect(modal.getByTestId('spark-purchase-terms')).toContainText(/no subscription/i);
        await expect(modal.getByRole('button', { name: 'Maybe Later' })).toBeVisible();

        await expectNoHorizontalOverflow(page);
    });

    test('captures the payment screen for visual review', async ({ page }, testInfo) => {
        const modal = await openPurchaseModal(page);
        await expect(modal).toBeVisible();
        const shot = await modal.screenshot();
        await testInfo.attach('spark-purchase-modal', { body: shot, contentType: 'image/png' });
        if (process.env.PAYMENT_UX_SHOT) {
            const fs = await import('node:fs/promises');
            await fs.writeFile(`${process.env.PAYMENT_UX_SHOT}-${testInfo.project.name}.png`, shot);
        }
    });

    test('completes the web Stripe checkout happy path', async ({ page }) => {
        await page.route('**/checkout/create', (route) =>
            route.fulfill({ json: { checkout_url: 'https://pay.stripe.test/session', session_id: 'cs_test_1' } }),
        );
        await page.route('**/checkout/token', (route) => route.fulfill({ json: { tokens_added: 200 } }));

        const modal = await openPurchaseModal(page);
        await modal.getByText('$4.99', { exact: true }).click();

        // Immediate feedback + Stripe opened with the returned checkout URL.
        await expect(page.getByText(/Waiting for payment/)).toBeVisible();
        const opened = await page.evaluate(() => (window as unknown as { __opened: string[] }).__opened);
        expect(opened).toContain('https://pay.stripe.test/session');

        // Poll credits → purchase modal closes and a confirmation appears.
        await expect(page.getByRole('heading', { name: 'Sparks Added!' })).toBeVisible({ timeout: 8000 });
        await expect(page.getByText(/\+200 sparks added/)).toBeVisible();
    });

    test('handles payments-unavailable gracefully and stays dismissable', async ({ page }) => {
        await page.route('**/checkout/create', (route) => route.fulfill({ status: 500, json: {} }));

        const modal = await openPurchaseModal(page);
        await modal.getByText('$1.99', { exact: true }).click();

        await expect(modal.getByText(/Payments are not available right now/)).toBeVisible();
        // The user is not stuck — packs still there, and they can back out.
        await expect(modal.getByRole('button', { name: 'Maybe Later' })).toBeVisible();
    });

    test('can be dismissed without buying', async ({ page }) => {
        const modal = await openPurchaseModal(page);
        await modal.getByRole('button', { name: 'Maybe Later' }).click();
        await expect(page.getByTestId('spark-purchase-modal')).not.toBeVisible();
    });
});
