import { describe, it, expect, vi } from 'vitest';

// posthog-js is dynamically driven by init; without VITE_POSTHOG_KEY, init never runs,
// so track/identify must be safe no-ops (the real risk is a crash before init).
vi.mock('posthog-js', () => ({
  default: {
    init: vi.fn(),
    capture: vi.fn(),
    identify: vi.fn(),
  },
}));

import { track, identify } from '../analytics';
import posthog from 'posthog-js';

// Before initAnalytics() runs, track/identify must be safe no-ops — a crash here would take
// down every call site (useRemoteConfig, AuthContext, etc.). This is the load-bearing contract.
describe('analytics no-op safety (pre-init)', () => {
  it('track does not call posthog before init', () => {
    track('some_event', { a: 1 });
    expect((posthog.capture as ReturnType<typeof vi.fn>)).not.toHaveBeenCalled();
  });

  it('identify does not call posthog before init', () => {
    identify('wallet-1', { signed_in: true });
    expect((posthog.identify as ReturnType<typeof vi.fn>)).not.toHaveBeenCalled();
  });
});
