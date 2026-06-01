import { expect, test } from '@playwright/test';
import { expectNoHorizontalOverflow, stubCoreBackend } from './helpers';

test.describe('Standalone app shell', () => {
  test.beforeEach(async ({ page }) => {
    await stubCoreBackend(page);
  });

  test('shows the main game catalog without layout overflow', async ({ page }) => {
    await page.goto('/');

    await expect(page.getByRole('button', { name: /AI Quiz/ })).toBeVisible();
    await expect(page.getByRole('button', { name: /Most Likely To/ })).toBeVisible();
    await expect(page.getByRole('button', { name: /Drawing Game/ })).toBeVisible();
    await expect(page.getByRole('button', { name: /Bluff/ })).toBeVisible();
    await expect(page.locator('.settings-trigger')).toBeVisible();
    await expectNoHorizontalOverflow(page);
  });

  test('menu uses multi-game branding and fits without horizontal overflow', async ({ page }) => {
    await page.goto('/');

    await page.locator('.settings-trigger').click();
    await expect(page.getByText('Revelry Games v1.0')).toBeVisible();
    await expect(page.getByText('Revelry Quiz v1.0')).not.toBeVisible();
    await expectNoHorizontalOverflow(page);
  });

  test('standalone custom quiz ignores old unscoped party drafts', async ({ page }) => {
    await page.addInitScript(() => {
      localStorage.setItem('localplay_custom_quiz_draft_v1', JSON.stringify({
        title: 'Christmas Quiz',
        questions: [
          {
            id: 'q_party',
            type: 'multiple_choice',
            text: 'When was the first Christmas celebrated?',
            options: ['1965', '2001', '1001', '501'],
            answerIndex: 0,
            imageUrl: 'https://media.revelryapp.me/apps/localplay/gamma/uploads/christmas.webp',
          },
        ],
        selectedId: 'q_party',
      }));
    });

    await page.goto('/');
    await page.getByRole('button', { name: /AI Quiz/ }).click();
    await page.getByRole('button', { name: 'Create Your Own' }).click();

    await expect(page.getByRole('heading', { name: 'Create Your Own' })).toBeVisible();
    await expect(page.getByLabel('Quiz title')).toHaveValue('Custom Quiz');
    await expect(page.getByLabel('Question text')).toHaveValue('');
    await expect(page.getByText('Christmas Quiz')).not.toBeVisible();
    await expect(page.getByText('When was the first Christmas celebrated?')).not.toBeVisible();
    await expectNoHorizontalOverflow(page);
  });

  test('saved quizzes have readable actions, prepare without generation copy, and can return home', async ({ page }) => {
    await page.route('**/*', async (route) => {
      const url = new URL(route.request().url());
      if (url.pathname === '/quiz-packs' || url.pathname === '/quiz-packs/') {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            packs: [
              {
                id: 'pack-1',
                title: 'Custom Quiz#1',
                question_count: 1,
                updated_at: '2026-05-24T00:00:00Z',
              },
            ],
          }),
        });
        return;
      }
      await route.fallback();
    });
    await page.route('**/quiz-packs/pack-1/materialize', async (route) => {
      await route.fulfill({
        json: {
          quiz_id: 'materialized-quiz-1',
          quiz: {
            quiz_title: 'Custom Quiz#1',
            questions: [
              {
                id: 1,
                text: 'What are these people celebrating?',
                options: ['Mothers Day', 'Birthday Party', 'Barbeque', 'Halloween'],
                answer_index: 1,
                image_url: 'https://media.revelryapp.me/apps/localplay/gamma/uploads/party.webp',
                image_prompt: '',
              },
            ],
          },
        },
      });
    });
    await page.route('**/quiz-packs/pack-1', async (route) => {
      await route.fulfill({
        json: {
          pack: { id: 'pack-1', title: 'Custom Quiz#1', question_count: 1 },
          quiz: {
            quiz_title: 'Custom Quiz#1',
            questions: [
              {
                id: 1,
                text: 'What are these people celebrating?',
                options: ['Mothers Day', 'Birthday Party', 'Barbeque', 'Halloween'],
                answer_index: 1,
                image_url: 'https://media.revelryapp.me/apps/localplay/gamma/uploads/party.webp',
                image_prompt: '',
              },
            ],
          },
        },
      });
    });

    await page.goto('/');
    await page.getByRole('button', { name: /AI Quiz/ }).click();
    await page.getByRole('button', { name: 'My Quizzes' }).click();

    await expect(page.getByRole('heading', { name: 'My Quizzes' })).toBeVisible();
    await expect(page.getByText('Custom Quiz#1')).toBeVisible();
    await expect(page.getByRole('button', { name: 'Start' })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Edit' })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Delete' })).toBeVisible();
    const startBox = await page.getByRole('button', { name: 'Start' }).boundingBox();
    const editBox = await page.getByRole('button', { name: 'Edit' }).boundingBox();
    const deleteBox = await page.getByRole('button', { name: 'Delete' }).boundingBox();
    expect(startBox?.width).toBeGreaterThan(60);
    expect(editBox?.width).toBeGreaterThan(60);
    expect(deleteBox?.width).toBeGreaterThan(60);
    expect(Math.abs((startBox?.y || 0) - (editBox?.y || 0))).toBeLessThan(4);
    expect(Math.abs((startBox?.y || 0) - (deleteBox?.y || 0))).toBeLessThan(4);

    await page.getByRole('button', { name: 'Start' }).click();
    await expect(page.getByRole('heading', { name: 'Preparing Quiz' })).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Generating Quiz' })).not.toBeVisible();

    await expect(page.getByRole('heading', { name: 'Custom Quiz#1' })).toBeVisible();
    await expect(page.getByText('1 questions ready to go')).toBeVisible();

    await page.locator('.settings-trigger').click();
    await page.getByText('Home').click();
    await expect(page.getByRole('heading', { name: 'Choose a Game' })).toBeVisible();
    await expectNoHorizontalOverflow(page);
  });
});
