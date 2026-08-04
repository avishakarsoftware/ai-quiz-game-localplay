import { expect, test, type Browser, type BrowserContext, type Locator, type Page } from '@playwright/test';
import path from 'node:path';
import {
    createRoomViaApi,
    deterministicQuiz,
    liveBaseURL,
    liveDeviceId,
    openOrganizerFromRoom,
    postJson,
    startLobbyGame,
} from './liveGameHarness';

/**
 * L6 VISUAL REGRESSION (SPEC-TESTING §1, §7)
 * ==========================================
 *
 * Screenshot diffing over the app's load-bearing surfaces, so a theme token change, a broken
 * flex row, or a font/spacing regression fails a test instead of shipping.
 *
 * Run it (never against prod, never against gamma — see "Determinism" below):
 *
 *     npm run test:e2e:visual              # compare against committed baselines
 *     npm run test:e2e:visual:update       # accept new baselines (review the diff first!)
 *
 * Both go through scripts/visual-regression.sh, which brings up a throwaway backend (its own
 * temp SQLite dir) plus a vite dev server on dedicated ports, so a run cannot touch your normal
 * dev database or collide with `make dev`.
 *
 * DETERMINISM — why local, and why these games
 * -------------------------------------------
 * Gamma/prod generate quiz text with an LLM, so the same screen renders different words every
 * run: unusable as a baseline. This suite runs local with curated/imported content only
 * (`deterministicQuiz` from the shared harness), never a generation call.
 *
 * MASKING — the whole ballgame
 * ---------------------------
 * The failure mode of visual testing is a suite that diffs on every run until everyone ignores
 * it. Every volatile region below is either pinned to a fixed value or masked, and each one is
 * justified, because a mask is also a hole in coverage:
 *
 *   PINNED (made deterministic, so it stays asserted):
 *   - player roster: three players joined *sequentially* with fixed nicknames, so lobby pill
 *     order is stable (Promise.all joins race and reorder the roster).
 *   - avatars: PlayerPage picks one at random on mount, so each player context gets a seeded
 *     Math.random. Deterministic *and* still different per player.
 *   - podium ranking: Maya answers 2 correct, Leo 1, Ada 0. Scores are speed-weighted so their
 *     values are unpredictable, but the ORDER is a function of correctness alone — so
 *     "Maya is the Champion!" is asserted rather than masked.
 *   - motion: `reducedMotion: 'reduce'` (the app's own fireworks/burst code checks that media
 *     query and skips the canvas), `animations: 'disabled'`, `caret: 'hide'`.
 *   - fonts: every capture waits for document.fonts.ready AND asserts Outfit is really loaded;
 *     capturing mid-swap reflows every line of text.
 *
 *   MASKED (genuinely unpredictable):
 *   - room code — random per room, 6 chars.
 *   - the join URL line under it — contains the room code.
 *   - the join QR — encodes the room code, so every module changes.
 *   - countdown timers — wall-clock; also the reason the room uses time_limit 60, which keeps
 *     the timer in its one colour band (>10s) for the whole capture window.
 *   - spark balance badge — moves with daily bonus, room spend, and pricing config.
 *   - podium scores — speed-weighted, so not reproducible even with identical answers.
 *   - the Google sign-in button in the settings drawer — drawn by Google's own remote script, so
 *     its pixels are neither ours nor versioned here (its script is also blocked, so a run needs
 *     no third-party network at all).
 *
 * Masked boxes whose text width varies would just move the diff to the edge of the pink
 * rectangle, so e2e/visual-stabilize.css pins those widths at capture time. Read the comment at
 * the top of that file before adding a mask.
 *
 * Player counts are NOT masked (unlike the note in SPEC-TESTING §4): the suite controls how many
 * players join, so "3 connected players" is a real assertion worth keeping.
 */

const STYLE_PATH = path.resolve(process.cwd(), 'e2e/visual-stabilize.css');

/**
 * Deliberately tiny. With the pinning above, the measured run-to-run difference on the same
 * machine is exactly ZERO pixels on every surface (verified by running the suite with
 * VISUAL_MAX_DIFF_PIXELS=0). 250px is small enough that no real layout or theme change can hide
 * under it — for scale, the podium fireworks flake this suite eliminated was ~1,500px — while
 * still tolerating a little text-rasterisation drift between machines.
 *
 * Raising this is almost always the wrong fix: if a surface diffs every run, find the volatile
 * region and pin or mask it instead. Use the env override to measure, not to paper over.
 */
const MAX_DIFF_PIXELS = Number(process.env.VISUAL_MAX_DIFF_PIXELS ?? 250);

/**
 * Per-pixel colour sensitivity (0 = identical required, 1 = anything goes).
 *
 * Playwright's default of 0.2 is far too loose for a theme-regression suite: with it, nudging the
 * Velvet accent from #FF2E7A to #FF3E6A changed nothing that any of these 18 baselines noticed —
 * the suite passed while the brand colour was wrong. At 0.02 that same edit fails on every
 * surface that paints the accent, which is the entire point of owning L6.
 */
const PIXEL_THRESHOLD = Number(process.env.VISUAL_PIXEL_THRESHOLD ?? 0.02);

interface Player {
    context: BrowserContext;
    page: Page;
    nickname: string;
}

/** Chrome that sits over every non-TV surface. The spark balance is the volatile part. */
function chromeMasks(page: Page): Locator[] {
    return [page.locator('.settings-spark-badge')];
}

/** Room identity: the code, the join URL that embeds it, and the QR that encodes it. */
function roomMasks(page: Page): Locator[] {
    return [
        page.locator('.qr-container'),
        page.getByTestId('organizer-room-code'),
        // The join-URL hint is the room code's sibling <p> ("127.0.0.1:5199/join/AB12CD").
        page.locator('[data-testid="organizer-room-code"] + p'),
    ];
}

/** Countdown number + its progress bar, on both the organizer and the player question screens. */
function timerMasks(page: Page): Locator[] {
    return [page.locator('.question-timer-bar'), page.locator('span.tabular-nums')];
}

/**
 * Turn off the effects Playwright's `animations: 'disabled'` cannot see: the podium fireworks and
 * the celebration bursts are canvas/rAF, and they check `prefers-reduced-motion` themselves.
 *
 * This is a per-page call on purpose. `test.use({ reducedMotion: 'reduce' })` does NOT reach the
 * `page` fixture's context on Playwright 1.60 (verified: matchMedia still reported
 * no-preference), which is exactly how the fireworks canvas kept sprinkling ~1.5k random pixels
 * over the podium baseline. `page.emulateMedia()` and `browser.newContext({ reducedMotion })`
 * both work, so the suite uses those two and nothing else.
 */
async function calmMotion(page: Page) {
    await page.emulateMedia({ reducedMotion: 'reduce' });
    expect(
        await page.evaluate(() => matchMedia('(prefers-reduced-motion: reduce)').matches),
        'reduced motion must be in effect, or canvas/rAF effects randomise the capture',
    ).toBe(true);
}

async function settle(page: Page) {
    await page.evaluate(async () => { await document.fonts.ready; });
    expect(
        await page.evaluate(() => document.fonts.check('800 24px Outfit')),
        'Outfit must be loaded before capture, or text reflows mid-screenshot',
    ).toBe(true);
    // Two frames: let React flush and layout settle before the shutter opens.
    await page.evaluate(() => new Promise<void>((resolve) => {
        requestAnimationFrame(() => requestAnimationFrame(() => resolve()));
    }));
}

async function shoot(page: Page, name: string, options: { fullPage?: boolean; mask?: Locator[] } = {}) {
    await settle(page);
    await expect(page).toHaveScreenshot(`${name}.png`, {
        // fullPage for scrolling layouts; viewport-only for fixed overlays (a fixed drawer or
        // modal in a fullPage capture renders pinned to the top of a tall image, which tells you
        // nothing about where it actually sits on screen).
        fullPage: options.fullPage ?? true,
        mask: options.mask,
        stylePath: STYLE_PATH,
        animations: 'disabled',
        caret: 'hide',
        // Capture in CSS pixels so the mobile project's DPR doesn't triple image size (and noise).
        scale: 'css',
        maxDiffPixels: MAX_DIFF_PIXELS,
        threshold: PIXEL_THRESHOLD,
    });
}

/** Context options that mirror the current project's device, for pages we open ourselves. */
function deviceContextOptions(): Parameters<Browser['newContext']>[0] {
    const projectUse = test.info().project.use as Parameters<Browser['newContext']>[0];
    return {
        viewport: projectUse?.viewport,
        deviceScaleFactor: projectUse?.deviceScaleFactor,
        isMobile: projectUse?.isMobile,
        hasTouch: projectUse?.hasTouch,
        userAgent: projectUse?.userAgent,
        reducedMotion: 'reduce',
        baseURL: liveBaseURL,
    };
}

/** Replace Math.random with a seeded LCG. PlayerPage picks its avatar emoji with Math.random on
 *  mount, so without this the lobby/podium avatars change every run. A distinct seed per player
 *  keeps the avatars different from each other while still being reproducible. */
async function seedRandom(context: BrowserContext, seed: number) {
    await context.addInitScript((initialSeed: number) => {
        let state = initialSeed;
        Math.random = () => {
            state = (state * 1103515245 + 12345) % 2147483648;
            return state / 2147483648;
        };
    }, seed);
}

/** Join one player and wait for the lobby confirmation. Deliberately sequential — parallel joins
 *  land in a nondeterministic order and reshuffle the lobby roster between runs. */
async function joinPlayer(browser: Browser, roomCode: string, nickname: string, seed: number): Promise<Player> {
    const context = await browser.newContext(deviceContextOptions());
    await seedRandom(context, seed);
    const page = await context.newPage();
    await calmMotion(page);
    await page.goto(`/join/${roomCode}`);
    await page.getByPlaceholder('Your nickname').fill(nickname);
    await page.getByRole('button', { name: 'Join' }).click();
    await expect(page.getByRole('heading', { name: "You're in!" })).toBeVisible({ timeout: 20_000 });
    return { context, page, nickname };
}

test.describe('Visual regression', () => {
    test.beforeEach(async ({ page }) => {
        test.skip(
            process.env.VISUAL_SNAPSHOTS !== '1',
            'Visual baselines need the deterministic local stack — run `npm run test:e2e:visual`.',
        );
        await calmMotion(page);
        // Seed the host/organizer context too, so any Math.random-derived visual is reproducible.
        await seedRandom(page.context(), 987654321);
    });

    test('game catalog', async ({ page }) => {
        await page.goto('/');
        await expect(page.getByRole('heading', { name: 'Choose a Game' })).toBeVisible({ timeout: 30_000 });
        // The catalog comes from the backend. Assert the count so a game appearing or disappearing
        // fails with "expected 38, got N" instead of a confusing whole-page pixel diff. Shipping
        // game #39 is then a deliberate two-step: bump this number, update the baseline.
        await expect(page.locator('.game-select-card')).toHaveCount(38);
        await shoot(page, '01-catalog', { mask: chromeMasks(page) });
    });

    test('TV launcher shell', async ({ page }) => {
        // /tv hides the phone app chrome (no spark badge, no hamburger), so nothing to mask:
        // with no room open, connected phones is 0 and the "Play now (n)" count is a pure
        // function of the catalog.
        await page.goto('/tv');
        await expect(page.getByTestId('tv-home')).toBeVisible({ timeout: 30_000 });
        await expect(page.getByRole('heading', { name: 'Games on TV' })).toBeVisible();
        await expect(page.locator('.tv-game-card').first()).toBeVisible();
        await shoot(page, '02-tv-launcher-play-now');

        // "All games" is the view that renders the locked / phone-host tiles, which is where the
        // TV-specific styling actually lives.
        await page.getByRole('button', { name: 'All games' }).click();
        await expect(page.locator('.tv-game-card--locked').first()).toBeVisible();
        await shoot(page, '03-tv-launcher-all-games');
    });

    test('Get Sparks paywall modal', async ({ page }) => {
        await page.goto('/');
        await expect(page.getByRole('heading', { name: 'Choose a Game' })).toBeVisible({ timeout: 30_000 });
        await page.locator('[aria-label="Get Sparks"]').first().click();
        await expect(page.getByTestId('spark-purchase-modal')).toBeVisible({ timeout: 15_000 });
        // Pack sizes and prices are static on web (no RevenueCat), so the pack rows are asserted.
        await expect(page.getByTestId('spark-purchase-terms')).toBeVisible();
        await shoot(page, '04-paywall-get-sparks', { fullPage: false, mask: chromeMasks(page) });
    });

    test('settings drawer', async ({ page }) => {
        // Google draws its own sign-in button into the drawer from a remote script. Its artwork is
        // not ours, it is not versioned with this repo, and it re-rasterises slightly between
        // loads — it was the one surface that still diffed after everything else was pinned. Block
        // the script so the suite is hermetic (no accounts.google.com dependency in a local run),
        // and mask the slot as well so the shot is stable whether or not the button ever appears.
        await page.route(/accounts\.google\.com|apis\.google\.com/, (route) => route.abort());

        await page.goto('/');
        await expect(page.getByRole('heading', { name: 'Choose a Game' })).toBeVisible({ timeout: 30_000 });
        await page.locator('.settings-trigger').click();
        await expect(page.locator('.settings-drawer-open')).toBeVisible();
        // A fresh wallet has hosted nothing, so StatsSection hides itself — no dates or counts
        // to mask. If that section ever shows up here, mask it rather than accept the diff.
        await shoot(page, '05-settings-drawer', {
            fullPage: false,
            mask: [...chromeMasks(page), page.getByTestId('google-signin-slot')],
        });
    });

    test('lobby, question and podium', async ({ page, browser, request }) => {
        test.setTimeout(240_000);
        const host = page;
        const deviceId = liveDeviceId('visual');
        const { quiz_id: quizId } = await postJson<{ quiz_id: string }>(
            request, '/quiz/import', { quiz: deterministicQuiz }, deviceId,
        );
        // time_limit 60 keeps the countdown well clear of the 10s/5s colour thresholds for the
        // whole capture window, so only the masked digits change — not the palette around them.
        const room = await createRoomViaApi(request, deviceId, { game_type: 'quiz', quiz_id: quizId, time_limit: 60 });
        await openOrganizerFromRoom(host, room);
        await expect(host.getByTestId('organizer-room-code')).toBeVisible({ timeout: 30_000 });

        const players: Player[] = [];
        try {
            // Sequential + fixed seeds: roster order and avatars are then reproducible.
            players.push(await joinPlayer(browser, room.roomCode, 'Maya', 11));
            players.push(await joinPlayer(browser, room.roomCode, 'Leo', 22));
            players.push(await joinPlayer(browser, room.roomCode, 'Ada', 33));
            const [maya] = players;

            await expect(host.getByTestId('organizer-player-count')).toHaveText('3', { timeout: 20_000 });
            await shoot(host, '06-lobby', { mask: [...chromeMasks(host), ...roomMasks(host)] });

            await startLobbyGame(host, 3);

            const q1 = deterministicQuiz.questions[0];
            await expect(host.getByText(q1.text)).toBeVisible({ timeout: 30_000 });
            // Captured before anyone answers, so the progress row is a real assertion.
            await expect(host.getByText('0 of 3 answered')).toBeVisible();
            await shoot(host, '07-question-organizer', { mask: [...chromeMasks(host), ...timerMasks(host)] });

            await expect(maya.page.getByText(q1.text)).toBeVisible({ timeout: 30_000 });
            await shoot(maya.page, '08-question-player', { mask: [...chromeMasks(maya.page), ...timerMasks(maya.page)] });

            // Maya 2 correct, Leo 1, Ada 0 -> a strict 1st/2nd/3rd that does not depend on
            // answer speed, so the champion line and the podium order can be asserted.
            const answerPlan: Record<string, boolean[]> = {
                Maya: [true, true],
                Leo: [true, false],
                Ada: [false, false],
            };

            for (let q = 0; q < deterministicQuiz.questions.length; q++) {
                const question = deterministicQuiz.questions[q];
                const correct = question.options[question.answer_index];
                const wrong = question.options.find((option) => option !== correct)!;
                for (const player of players) {
                    const choice = answerPlan[player.nickname][q] ? correct : wrong;
                    const button = player.page.getByRole('button', { name: choice });
                    await expect(button.first()).toBeEnabled({ timeout: 20_000 });
                    await button.first().click();
                }

                // The host advances in two steps: reveal -> "Show Scores" -> leaderboard ->
                // "Next Question" / "Show Results". Never match "End Game" loosely; it would cut
                // the game short and land on a one-question podium.
                const showScores = host.getByRole('button', { name: /Show Scores/ });
                if (await showScores.first().isVisible({ timeout: 20_000 }).catch(() => false)) {
                    await showScores.first().click();
                }
                const advance = host.getByRole('button', { name: /Next Question|Show Results/ });
                if (await advance.first().isVisible({ timeout: 20_000 }).catch(() => false)) {
                    await advance.first().click().catch(() => { /* may auto-advance on countdown */ });
                }
            }

            await expect(host.getByText(/Final Results/i).first()).toBeVisible({ timeout: 30_000 });
            await expect(host.getByText('Maya is the Champion!')).toBeVisible({ timeout: 20_000 });
            // .podium-actions only renders at the last reveal phase, so this is the signal that
            // the staged reveal (and its count-up numbers) has finished.
            await expect(host.locator('.podium-actions')).toBeVisible({ timeout: 15_000 });
            await shoot(host, '09-podium', {
                mask: [...chromeMasks(host), host.locator('.podium-score')],
            });
        } finally {
            await Promise.all(players.map((player) => player.context.close()));
        }
    });
});
