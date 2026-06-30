#!/usr/bin/env node
/**
 * Build the IONOS public web bundle (games.revelryapp.me) with the prod API host baked in, then
 * HARD-FAIL unless the built bundle actually points at gamesapi.revelryapp.me.
 *
 * Why this guard exists (lesson from revelryapp DEPLOY.md): the backend-served build uses an EMPTY
 * VITE_API_URL (same-origin). If that same-origin bundle is ever uploaded to IONOS, every /quiz, /room,
 * /tokens, /checkout call hits IONOS static hosting instead of the API and the public site breaks.
 * This script makes that mistake impossible to ship.
 *
 *   npm run ionos:build   # → frontend/dist, verified, ready to scp to ~/revelryapp/games/
 */
import { spawnSync } from 'node:child_process';
import { readdirSync, readFileSync } from 'node:fs';
import { join } from 'node:path';

const PROD_API = 'https://gamesapi.revelryapp.me';
const buildEnv = {
    ...process.env,
    VITE_BASE_PATH: '/',
    VITE_API_URL: PROD_API,
    VITE_WEB_URL: 'https://games.revelryapp.me/',
    VITE_APPLE_REDIRECT_URI: 'https://games.revelryapp.me',
    VITE_CAST_APP_ID: process.env.VITE_CAST_APP_ID || '1BC9ACD8',
    VITE_ENABLE_BINGO: process.env.VITE_ENABLE_BINGO || 'true',
};

console.log(`[ionos-build] building IONOS web bundle (VITE_API_URL=${PROD_API})`);
const r = spawnSync('npx', ['vite', 'build'], { stdio: 'inherit', env: buildEnv });
if (r.status !== 0) process.exit(r.status ?? 1);

// Verify the prod API host is actually baked into the JS — fail loudly if not (would be same-origin).
const assetsDir = join('dist', 'assets');
const js = readdirSync(assetsDir).filter((f) => f.endsWith('.js'));
const found = js.some((f) => readFileSync(join(assetsDir, f), 'utf8').includes('gamesapi.revelryapp.me'));
if (!found) {
    console.error('\n[ionos-build] FAIL: built bundle does not reference gamesapi.revelryapp.me.');
    console.error('  This looks like a same-origin build — uploading it to IONOS would break /api calls.');
    console.error('  Do NOT upload dist/. Rebuild with this script.');
    process.exit(1);
}
console.log('[ionos-build] OK — bundle points at gamesapi.revelryapp.me. Safe to upload dist/ to IONOS.');
