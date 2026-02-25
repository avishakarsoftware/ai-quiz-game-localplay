import posthog from 'posthog-js';

const POSTHOG_KEY = import.meta.env.VITE_POSTHOG_KEY as string | undefined;
const POSTHOG_HOST = (import.meta.env.VITE_POSTHOG_HOST as string) || 'https://us.i.posthog.com';

let initialized = false;

export function initAnalytics() {
  if (initialized || !POSTHOG_KEY) return;
  posthog.init(POSTHOG_KEY, {
    api_host: POSTHOG_HOST,
    autocapture: false,           // we track events explicitly
    capture_pageview: true,       // auto track route changes
    capture_pageleave: true,
    persistence: 'localStorage',
    disable_session_recording: false,
  });
  initialized = true;
}

function getPlatform(): string {
  if ((window as any).Capacitor?.isNativePlatform?.()) {
    return (window as any).Capacitor.getPlatform?.() || 'native';
  }
  if (window.matchMedia('(display-mode: standalone)').matches) return 'pwa';
  return 'web';
}

/** Track a named event with optional properties. No-op if PostHog is not initialized. */
export function track(event: string, properties?: Record<string, any>) {
  if (!initialized) return;
  posthog.capture(event, { ...properties, platform: getPlatform() });
}

/** Identify a user (e.g. anonymous organizer ID). */
export function identify(id: string, properties?: Record<string, any>) {
  if (!initialized) return;
  posthog.identify(id, properties);
}
