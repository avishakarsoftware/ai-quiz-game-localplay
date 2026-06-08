import { expect, test } from '@playwright/test';
import fs from 'node:fs/promises';
import path from 'node:path';
import {
  closePlayers,
  createRoomViaApi,
  deterministicChitPull,
  joinPlayers,
  liveDeviceId,
  openOrganizerFromRoom,
  postJson,
  startLobbyGame,
} from './liveGameHarness';
import { expectNoHorizontalOverflow } from './helpers';

test.describe('Pre-production visual UX audit', () => {
  test.beforeEach(async ({}, testInfo) => {
    test.skip(process.env.PREPROD_UX_AUDIT !== '1', 'Set PREPROD_UX_AUDIT=1 to capture the heavier visual audit states.');
    test.skip(testInfo.project.name !== 'chromium-desktop', 'visual audit runs desktop browser only with explicit viewports');
  });

  test('captures representative live game screens on mobile', async ({ browser, request }, testInfo) => {
    test.setTimeout(90_000);
    const outputDir = process.env.PREPROD_UX_AUDIT_DIR || '/private/tmp/localplay-preprod-ux-audit';
    await fs.mkdir(outputDir, { recursive: true });

    const catalog = await browser.newPage({ viewport: { width: 390, height: 844 } });
    await catalog.goto('/');
    await expect(catalog.getByPlaceholder('Search games')).toBeVisible({ timeout: 20_000 });
    await expectNoHorizontalOverflow(catalog);
    const catalogPath = path.join(outputDir, 'catalog-mobile.png');
    await catalog.screenshot({ path: catalogPath, fullPage: true });
    await testInfo.attach('catalog-mobile', { path: catalogPath, contentType: 'image/png' });
    await catalog.close();

    const bluffDeviceId = liveDeviceId('ux-bluff');
    const bluffRoom = await createRoomViaApi(request, bluffDeviceId, {
      game_type: 'bluff',
      time_limit: 30,
      bluff_config: { game_title: 'UX Bluff' },
    });
    const bluffHost = await browser.newPage({ viewport: { width: 390, height: 844 } });
    await openOrganizerFromRoom(bluffHost, bluffRoom);
    const bluffPlayers = await joinPlayers(browser, bluffRoom.roomCode, ['Alice', 'Bob', 'Cara']);
    try {
      await startLobbyGame(bluffHost, bluffPlayers.length);
      await expect(bluffHost.getByRole('heading', { name: 'Bluff' })).toBeVisible({ timeout: 20_000 });
      await expectNoHorizontalOverflow(bluffHost);
      const bluffPath = path.join(outputDir, 'bluff-mobile-host.png');
      await bluffHost.screenshot({ path: bluffPath, fullPage: true });
      await testInfo.attach('bluff-mobile-host', { path: bluffPath, contentType: 'image/png' });
    } finally {
      await closePlayers(bluffPlayers);
      await bluffHost.close();
    }

    const chitDeviceId = liveDeviceId('ux-chit');
    const { chit_pull_id: chitPullId } = await postJson<{ chit_pull_id: string }>(request, '/chit-pull/import', deterministicChitPull, chitDeviceId);
    const chitRoom = await createRoomViaApi(request, chitDeviceId, {
      game_type: 'chit_pull',
      chit_pull_id: chitPullId,
      time_limit: 20,
    });
    const chitHost = await browser.newPage({ viewport: { width: 390, height: 844 } });
    await openOrganizerFromRoom(chitHost, chitRoom);
    const chitPlayers = await joinPlayers(browser, chitRoom.roomCode, ['Alice', 'Bob', 'Cara']);
    try {
      await startLobbyGame(chitHost, chitPlayers.length);
      await chitHost.getByRole('button', { name: 'Pull Chit' }).click();
      await expect(chitHost.getByRole('button', { name: 'Completed' })).toBeVisible({ timeout: 20_000 });
      await expectNoHorizontalOverflow(chitHost);
      const chitPath = path.join(outputDir, 'chit-pull-mobile-host.png');
      await chitHost.screenshot({ path: chitPath, fullPage: true });
      await testInfo.attach('chit-pull-mobile-host', { path: chitPath, contentType: 'image/png' });
    } finally {
      await closePlayers(chitPlayers);
      await chitHost.close();
    }
  });
});
