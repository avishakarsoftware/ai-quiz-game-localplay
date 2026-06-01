import { expect, type Page } from '@playwright/test';

export async function stubCoreBackend(page: Page) {
  await page.route('**/config.json', async (route) => {
    await route.fulfill({
      json: {
        version: 'e2e',
        cache_ttl_seconds: 60,
        operations: {},
        pricing: {},
        feature_flags: {},
        announcements: [],
      },
    });
  });

  await page.route('**/providers', async (route) => {
    await route.fulfill({
      json: {
        providers: [
          { id: 'gemini', name: 'Gemini 2.5 Flash Lite', available: true },
        ],
      },
    });
  });

  await page.route('**/sd/status', async (route) => {
    await route.fulfill({ json: { available: false } });
  });
}

export async function expectNoHorizontalOverflow(page: Page) {
  const overflowing = await page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth + 1);
  expect(overflowing).toBe(false);
}

export function revelryLaunchContext() {
  return {
    host_app: 'revelry',
    external_container_type: 'party',
    external_container_id: 'party-e2e',
    external_container_title: 'Christmas 2026 Bash',
    return_url: 'https://api-gamma.revelryapp.me/party/party-e2e?tab=games',
    capabilities: ['manage_games', 'author_content', 'operate_game'],
    display: {
      container_label: 'Christmas 2026 Bash',
      guest_join_url: 'https://api-gamma.revelryapp.me/party/party-e2e/games/join',
      guest_join_label: 'Scan to join from Revelry',
      return_label: 'Back to Revelry',
    },
  };
}

export function revelryCatalog() {
  return [
    {
      id: 'quiz',
      game_type: 'quiz',
      title: 'AI Quiz',
      description: 'A fast trivia room with multiple-choice questions.',
      launchable: true,
      can_create_content: true,
      can_edit_content: true,
      can_quick_start: true,
      embedded_authoring_supported: true,
      creation_modes: ['manual', 'ai'],
    },
    {
      id: 'wmlt',
      game_type: 'wmlt',
      title: 'Most Likely To',
      description: 'Vote on who best matches each prompt.',
      launchable: true,
      can_create_content: true,
      can_edit_content: true,
      can_quick_start: false,
      supports_ai_generation: true,
      creation_modes: ['template', 'manual', 'ai'],
    },
    {
      id: 'drawing',
      game_type: 'drawing',
      title: 'Drawing Game',
      description: 'Draw secret prompts while everyone guesses.',
      launchable: true,
      can_create_content: true,
      can_edit_content: true,
      can_quick_start: false,
      supports_ai_generation: true,
      creation_modes: ['template', 'manual', 'ai'],
      config_schema: { time_limit: { min: 5, max: 60, default: 30 } },
    },
    {
      id: 'housie',
      game_type: 'housie',
      title: 'Housie',
      description: 'Classic 90-ball number calling with tickets and prize claims.',
      launchable: true,
      can_create_content: true,
      can_edit_content: true,
      can_quick_start: true,
      supports_ai_generation: false,
      creation_modes: ['manual', 'template'],
    },
    {
      id: 'rebus',
      game_type: 'rebus',
      title: 'Rebus Rush',
      description: 'Hidden standalone variant.',
      launchable: false,
      can_create_content: true,
    },
  ];
}

export function revelryWorkspace(overrides: Record<string, unknown> = {}) {
  return {
    active_session: null,
    catalog: revelryCatalog(),
    prepared_content: [
      {
        localplay_content_id: 'quiz-party-1',
        game_type: 'quiz',
        title: 'Christmas Quiz',
        question_count: 2,
        status: 'ready',
      },
    ],
    recent_results: [],
    ...overrides,
  };
}
