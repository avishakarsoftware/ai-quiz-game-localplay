#!/usr/bin/env node
/**
 * Build the web bundle for a native Capacitor target and copy/sync it into the iOS/Android projects.
 * Mirrors VibePix's `cap:gamma`/`cap:prod` pattern, adapted for Vite.
 *
 *   node scripts/cap-build.mjs <local|gamma|prod> [copy|sync] [ios|android]
 *
 * Examples:
 *   npm run cap:sync:gamma            # build gamma + `cap sync`
 *   node scripts/cap-build.mjs gamma sync ios
 *
 * RevenueCat public SDK keys are per-PROJECT (same for gamma + prod builds) and publishable, so they
 * are baked in here as defaults; override with VITE_REVENUECAT_IOS_KEY / VITE_REVENUECAT_ANDROID_KEY.
 * The per-environment difference is only the API/web origin the app talks to.
 */
import { spawnSync } from 'node:child_process';

const ENVS = {
    local: { api: 'http://localhost:8000', web: 'http://localhost:5173/' },
    gamma: { api: 'https://gamesapi-gamma.revelryapp.me', web: 'https://gamesapi-gamma.revelryapp.me/' },
    prod: { api: 'https://gamesapi.revelryapp.me', web: 'https://games.revelryapp.me/' },
};

const [envName, capCmd = 'copy', platform = ''] = process.argv.slice(2);
if (!ENVS[envName]) {
    console.error('Usage: node scripts/cap-build.mjs <local|gamma|prod> [copy|sync] [ios|android]');
    process.exit(1);
}
const cfg = ENVS[envName];

// Publishable RevenueCat keys for the "Revelry Games" project (safe to bake into the client build).
const RC_IOS = process.env.VITE_REVENUECAT_IOS_KEY || 'appl_pGvqXcNifKTHWOsnGBXuyHfkJlm';
const RC_ANDROID = process.env.VITE_REVENUECAT_ANDROID_KEY || 'goog_pkOCCLwUzCmywutlnyNQFovpuAF';

// Public OAuth client ids for native sign-in (Google web + iOS clients, Apple Service ID). Safe to bake.
const GOOGLE_WEB = process.env.VITE_GOOGLE_CLIENT_ID || '458966837298-9hjencou1ag2o17ln06iuuj86j5p8igj.apps.googleusercontent.com';
const GOOGLE_IOS = process.env.VITE_GOOGLE_IOS_CLIENT_ID || '458966837298-ncc86ha91tct2lo9ah16g8v9ibp4ckki.apps.googleusercontent.com';
const APPLE_ID = process.env.VITE_APPLE_CLIENT_ID || 'me.revelryapp.quiz.web';

const buildEnv = {
    ...process.env,
    VITE_BASE_PATH: '/',
    VITE_API_URL: cfg.api,
    VITE_WEB_URL: cfg.web,
    VITE_CAST_APP_ID: process.env.VITE_CAST_APP_ID || '1BC9ACD8',
    VITE_REVENUECAT_IOS_KEY: RC_IOS,
    VITE_REVENUECAT_ANDROID_KEY: RC_ANDROID,
    VITE_GOOGLE_CLIENT_ID: GOOGLE_WEB,
    VITE_GOOGLE_IOS_CLIENT_ID: GOOGLE_IOS,
    VITE_APPLE_CLIENT_ID: APPLE_ID,
    // Native: let Apple JS fall back to window.location.origin (DEPLOY.md note).
    VITE_APPLE_REDIRECT_URI: '',
    // PostHog analytics — absent key ⇒ analytics stays disabled (see SPEC-ANALYTICS).
    VITE_POSTHOG_KEY: process.env.VITE_POSTHOG_KEY || '',
    VITE_POSTHOG_HOST: process.env.VITE_POSTHOG_HOST || 'https://us.i.posthog.com',
};

function run(cmd, args, env) {
    console.log(`[cap-build] ${cmd} ${args.join(' ')}`);
    const r = spawnSync(cmd, args, { stdio: 'inherit', env: env || process.env });
    if (r.status !== 0) process.exit(r.status ?? 1);
}

console.log(`[cap-build] env=${envName} api=${cfg.api} cap=${capCmd} ${platform}`.trim());
run('npx', ['vite', 'build'], buildEnv);
run('npx', ['cap', capCmd, ...(platform ? [platform] : [])]);
console.log('[cap-build] done');
