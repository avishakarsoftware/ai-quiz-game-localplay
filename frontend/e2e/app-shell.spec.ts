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
    await expect(page.locator('.settings-trigger')).toBeVisible();
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
});

