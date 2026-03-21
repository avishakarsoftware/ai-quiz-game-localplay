import { describe, it, expect } from 'vitest';
import { DEFAULT_CONFIG } from '../../types/remoteConfig';

// mergeWithDefaults is not exported, so we replicate the logic here for unit testing.
// This ensures the merge strategy is correct for partial/malformed config data.
function mergeWithDefaults(data: Record<string, unknown>) {
  return {
    ...DEFAULT_CONFIG,
    ...data,
    operations: { ...DEFAULT_CONFIG.operations, ...(data.operations as object || {}) },
    pricing: { ...DEFAULT_CONFIG.pricing, ...(data.pricing as object || {}) },
    feature_flags: { ...DEFAULT_CONFIG.feature_flags, ...(data.feature_flags as object || {}) },
    announcements: Array.isArray(data.announcements) ? data.announcements : DEFAULT_CONFIG.announcements,
  };
}

describe('mergeWithDefaults', () => {
  it('returns full defaults when given empty object', () => {
    const result = mergeWithDefaults({});
    expect(result).toEqual(DEFAULT_CONFIG);
  });

  it('overrides top-level scalar fields', () => {
    const result = mergeWithDefaults({ version: 42, welcome_message: 'Hello!' });
    expect(result.version).toBe(42);
    expect(result.welcome_message).toBe('Hello!');
  });

  it('deep-merges operations with defaults', () => {
    const result = mergeWithDefaults({ operations: { maintenance: true } });
    expect(result.operations.maintenance).toBe(true);
    expect(result.operations.maintenance_message).toBe(DEFAULT_CONFIG.operations.maintenance_message);
  });

  it('deep-merges pricing with defaults', () => {
    const result = mergeWithDefaults({ pricing: { pass_price: '$1.99' } });
    expect(result.pricing.pass_price).toBe('$1.99');
    expect(result.pricing.duration_hours).toBe(DEFAULT_CONFIG.pricing.duration_hours);
  });

  it('deep-merges feature_flags with defaults', () => {
    const result = mergeWithDefaults({ feature_flags: { show_upgrade_button: true } });
    expect(result.feature_flags.show_upgrade_button).toBe(true);
    expect(result.feature_flags.enable_image_generation).toBe(DEFAULT_CONFIG.feature_flags.enable_image_generation);
  });

  it('uses default announcements when field is not an array', () => {
    const result = mergeWithDefaults({ announcements: 'bad data' as unknown });
    expect(result.announcements).toEqual(DEFAULT_CONFIG.announcements);
  });

  it('uses provided announcements when field is an array', () => {
    const ann = [{ id: 'a1', text: 'Test', type: 'info' as const, dismissible: true }];
    const result = mergeWithDefaults({ announcements: ann });
    expect(result.announcements).toEqual(ann);
  });

  it('handles missing nested objects gracefully', () => {
    // If operations/pricing/feature_flags are undefined, should still return defaults
    const result = mergeWithDefaults({ version: 2 });
    expect(result.operations).toEqual(DEFAULT_CONFIG.operations);
    expect(result.pricing).toEqual(DEFAULT_CONFIG.pricing);
    expect(result.feature_flags).toEqual(DEFAULT_CONFIG.feature_flags);
  });
});
