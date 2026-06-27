import { expect, test, type Locator, type Page } from '@playwright/test';
import { expectNoHorizontalOverflow, stubCoreBackend } from './helpers';

const PNG_1X1 = Buffer.from(
  'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII=',
  'base64',
);

async function box(locator: Locator) {
  const value = await locator.boundingBox();
  expect(value).not.toBeNull();
  return value!;
}

async function stubImageUpload(page: Page) {
  await page.route('**/media/upload-url', async (route) => {
    await route.fulfill({
      json: {
        upload: {
          url: 'https://uploads.localplay.test/bingo-item',
          fields: { key: 'bingo/asset_bingo_1.png', policy: 'e2e' },
        },
        asset: { id: 'asset_bingo_1' },
      },
    });
  });

  await page.route('https://uploads.localplay.test/**', async (route) => {
    await route.fulfill({ status: 204 });
  });

  await page.route('**/media/asset_bingo_1/finalize', async (route) => {
    await route.fulfill({
      json: {
        asset: {
          id: 'asset_bingo_1',
          public_url: '/media/asset_bingo_1',
          status: 'ready',
        },
      },
    });
  });

  await page.route('**/media/asset_bingo_1', async (route) => {
    await route.fulfill({
      body: PNG_1X1,
      contentType: 'image/png',
    });
  });
}

test.describe('Bingo authoring', () => {
  test.beforeEach(async ({ page }) => {
    await stubCoreBackend(page);
    await stubImageUpload(page);
  });

  test('supports custom text and image deck setup before creating a room', async ({ page }, testInfo) => {
    let bingoCreateBody: Record<string, unknown> | null = null;
    let roomCreateBody: Record<string, unknown> | null = null;

    await page.route('**/bingo/create', async (route) => {
      bingoCreateBody = JSON.parse(route.request().postData() || '{}');
      await route.fulfill({
        json: {
          bingo_id: 'bingo-e2e',
          game: {
            game_title: 'Baby Shower Bingo',
            deck: bingoCreateBody.deck,
            patterns: [],
          },
        },
      });
    });

    await page.route('**/room/create', async (route) => {
      roomCreateBody = JSON.parse(route.request().postData() || '{}');
      await route.fulfill({
        json: {
          room_code: 'BINGO1',
          organizer_token: 'organizer-token',
        },
      });
    });

    await page.goto('/');
    await page.getByTestId('game-card-bingo').click();
    await expect(page.getByRole('heading', { name: 'Create Bingo' })).toBeVisible();
    await page.getByRole('button', { name: 'Custom Deck' }).click();

    await expect(page.getByRole('heading', { name: 'Set Up Bingo' })).toBeVisible();
    await expect(page.getByText('Deck (25/24 ready)')).toBeVisible();
    await expect(page.getByRole('button', { name: 'Create Room' })).toBeEnabled();

    await expectNoHorizontalOverflow(page);

    const deckRows = page.locator('.bingo-deck-row');
    const firstDeckRow = deckRows.nth(0);
    await expect(firstDeckRow.locator('input.input-field')).toHaveValue('Dance floor');
    const firstInputBox = await box(firstDeckRow.locator('input.input-field'));
    const uploadButtonBox = await box(firstDeckRow.locator('label.custom-upload-button'));
    expect(uploadButtonBox.x).toBeGreaterThan(firstInputBox.x + firstInputBox.width);

    const fileInput = firstDeckRow.locator('input[type="file"]');
    await fileInput.setInputFiles({
      name: 'baby-bottle.png',
      mimeType: 'image/png',
      buffer: PNG_1X1,
    });
    await expect(page.getByText('Image uploaded')).toBeVisible();
    await expect(firstDeckRow.getByAltText('Dance floor')).toBeVisible();

    await page.getByRole('button', { name: 'Use Starter Template' }).click();
    await deckRows.nth(0).locator('button.custom-upload-button').click();
    await deckRows.nth(0).locator('button.custom-upload-button').click();
    await expect(page.getByText('Deck (23/24 ready)')).toBeVisible();
    await expect(page.getByRole('button', { name: 'Create Room' })).toBeDisabled();

    await page.getByPlaceholder('Paste one item per line').fill('Diaper cake\nTiny shoes');
    await page.getByRole('button', { name: 'Add List' }).click();
    await expect(page.getByText('Deck (25/24 ready)')).toBeVisible();
    await expect(page.getByRole('button', { name: 'Create Room' })).toBeEnabled();

    await page.getByRole('button', { name: 'Use Starter Template' }).click();
    await fileInput.setInputFiles({
      name: 'baby-bottle.png',
      mimeType: 'image/png',
      buffer: PNG_1X1,
    });
    await page.getByLabel('Game title').fill('Baby Shower Bingo');

    await expect(page).toHaveScreenshot(`bingo-setup-${testInfo.project.name}.png`, {
      fullPage: true,
      animations: 'disabled',
      maxDiffPixelRatio: 0.02,
    });

    await page.getByRole('button', { name: 'Create Room' }).click();

    await expect.poll(() => bingoCreateBody).toMatchObject({
      game_title: 'Baby Shower Bingo',
      free_center: true,
      claim_requires_latest_call: false,
    });
    expect((bingoCreateBody?.deck as Array<Record<string, unknown>>)[0]).toMatchObject({
      kind: 'image',
      image_asset_id: 'asset_bingo_1',
      image_url: '/media/asset_bingo_1',
    });

    await expect.poll(() => roomCreateBody).toMatchObject({
      game_type: 'bingo',
      bingo_id: 'bingo-e2e',
    });

    page.once('dialog', async (dialog) => {
      expect(dialog.message()).toContain('Going home will leave this active room');
      await dialog.accept();
    });
    await page.getByTitle('Menu').click();
    await page.getByText('Home').click();
    await expect(page.getByRole('heading', { name: 'Choose a Game' })).toBeVisible();
  });

  test('generates a themed Bingo deck and lets the organizer edit before room creation', async ({ page }) => {
    let generateBody: Record<string, unknown> | null = null;
    let updateBody: Record<string, unknown> | null = null;
    let roomCreateBody: Record<string, unknown> | null = null;
    const generatedDeck = Array.from({ length: 30 }, (_, index) => ({
      id: `gen_${index + 1}`,
      kind: 'text',
      value: `generated ${index + 1}`,
      display: `Generated ${index + 1}`,
    }));

    await page.route('**/bingo/generate', async (route) => {
      generateBody = JSON.parse(route.request().postData() || '{}');
      await route.fulfill({
        json: {
          bingo_id: 'generated-bingo-e2e',
          game: {
            game_title: 'Baby Shower Bingo',
            deck: generatedDeck,
            free_center: true,
            claim_requires_latest_call: false,
          },
        },
      });
    });

    await page.route('**/bingo/generated-bingo-e2e', async (route) => {
      updateBody = JSON.parse(route.request().postData() || '{}');
      await route.fulfill({
        json: {
          bingo_id: 'generated-bingo-e2e',
          game: { ...updateBody, deck: updateBody.deck },
        },
      });
    });

    await page.route('**/room/create', async (route) => {
      roomCreateBody = JSON.parse(route.request().postData() || '{}');
      await route.fulfill({ json: { room_code: 'GENBGO', organizer_token: 'organizer-token' } });
    });

    await page.goto('/');
    await page.getByTestId('game-card-bingo').click();
    await page.getByTitle('Menu').click();
    await page.getByText('Home').click();
    await expect(page.getByRole('heading', { name: 'Choose a Game' })).toBeVisible();

    await page.getByTestId('game-card-bingo').click();
    await page.getByPlaceholder('Baby shower, office holiday party, wedding reception...').fill('baby shower');
    await page.getByRole('button', { name: 'Generate Bingo' }).click();

    await expect(page.getByRole('heading', { name: 'Set Up Bingo' })).toBeVisible();
    await expect(page.getByLabel('Game title')).toHaveValue('Baby Shower Bingo');
    await expect(page.getByText('Deck (30/24 ready)')).toBeVisible();
    await page.locator('.bingo-deck-row').nth(0).locator('input.input-field').fill('Tiny shoes');
    await page.getByRole('button', { name: 'Create Room' }).click();

    await expect.poll(() => generateBody).toMatchObject({
      prompt: 'baby shower',
      difficulty: 'medium',
      num_items: 30,
    });
    expect((updateBody?.deck as Array<Record<string, unknown>>)[0]).toMatchObject({ display: 'Tiny shoes' });
    await expect.poll(() => roomCreateBody).toMatchObject({
      game_type: 'bingo',
      bingo_id: 'generated-bingo-e2e',
    });
  });
});
