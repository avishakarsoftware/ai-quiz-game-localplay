import { useState, useEffect } from 'react';
import { type RemoteConfig, DEFAULT_CONFIG } from '../types/remoteConfig';
import { track } from '../utils/analytics';

const CACHE_KEY = 'revelry_remote_config';
const FETCH_TIMEOUT_MS = 3000;
const CACHE_TTL_MS = 24 * 60 * 60 * 1000; // 24 hours

interface CachedConfig {
  config: RemoteConfig;
  fetched_at: number;
}

/** Merge partial/malformed remote config onto defaults to prevent crashes. */
function mergeWithDefaults(data: Partial<RemoteConfig>): RemoteConfig {
  return {
    ...DEFAULT_CONFIG,
    ...data,
    operations: { ...DEFAULT_CONFIG.operations, ...data.operations },
    pricing: { ...DEFAULT_CONFIG.pricing, ...data.pricing },
    feature_flags: { ...DEFAULT_CONFIG.feature_flags, ...data.feature_flags },
    announcements: Array.isArray(data.announcements)
      ? data.announcements
          .filter((a): a is Record<string, unknown> =>
            !!a && typeof a === 'object' && typeof (a as Record<string, unknown>).id === 'string' && typeof (a as Record<string, unknown>).text === 'string'
          )
          .map(a => ({
            id: a.id as string,
            text: a.text as string,
            type: (a.type === 'info' || a.type === 'warning' ? a.type : 'info') as 'info' | 'warning',
            dismissible: typeof a.dismissible === 'boolean' ? a.dismissible : true,
          }))
      : DEFAULT_CONFIG.announcements,
  };
}

function getCachedConfig(): RemoteConfig | null {
  try {
    const raw = localStorage.getItem(CACHE_KEY);
    if (!raw) return null;
    const cached: CachedConfig = JSON.parse(raw);
    // Discard stale cache to prevent outdated maintenance flags, etc.
    if (Date.now() - cached.fetched_at > CACHE_TTL_MS) {
      localStorage.removeItem(CACHE_KEY);
      return null;
    }
    // Validate shape through mergeWithDefaults in case schema changed between versions
    return mergeWithDefaults(cached.config ?? {});
  } catch {
    return null;
  }
}

function setCachedConfig(config: RemoteConfig) {
  try {
    const cached: CachedConfig = { config, fetched_at: Date.now() };
    localStorage.setItem(CACHE_KEY, JSON.stringify(cached));
  } catch {
    // localStorage full or unavailable
  }
}

export function useRemoteConfig() {
  const [config, setConfig] = useState<RemoteConfig>(getCachedConfig() || DEFAULT_CONFIG);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    const controller = new AbortController();
    const configUrl = `${import.meta.env.BASE_URL}config.json`;

    fetch(configUrl, { signal: controller.signal })
      .then(res => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return res.json();
      })
      .then((data: Partial<RemoteConfig>) => {
        if (cancelled) return;
        const merged = mergeWithDefaults(data);
        setConfig(merged);
        setCachedConfig(merged);
        track('config_loaded', { source: 'remote', version: merged.version });
      })
      .catch(err => {
        if (cancelled || err.name === 'AbortError') return;
        const cached = getCachedConfig();
        if (cached) {
          setConfig(cached);
          track('config_loaded', { source: 'cache', version: cached.version });
        } else {
          track('config_loaded', { source: 'default' });
        }
      })
      .finally(() => { if (!cancelled) setLoading(false); });

    const timeout = setTimeout(() => controller.abort(), FETCH_TIMEOUT_MS);
    return () => { cancelled = true; clearTimeout(timeout); controller.abort(); };
  }, []);

  return { config, loading };
}
