import { useState, useEffect, useCallback } from 'react';
import { type RemoteConfig, DEFAULT_CONFIG } from '../types/remoteConfig';
import { track } from '../utils/analytics';

const CACHE_KEY = 'revelry_remote_config';
const FETCH_TIMEOUT_MS = 3000;
const DEFAULT_CACHE_TTL_MS = 24 * 60 * 60 * 1000; // 24 hours

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

const MAX_CACHE_TTL_MS = 24 * 60 * 60 * 1000; // Cap at 24 hours

function getCacheTtlMs(config: RemoteConfig): number {
  const ttl = config.cache_ttl_seconds;
  const ms = ttl && ttl > 0 ? ttl * 1000 : DEFAULT_CACHE_TTL_MS;
  return Math.min(ms, MAX_CACHE_TTL_MS);
}

function getCachedConfig(forceFresh?: boolean): RemoteConfig | null {
  try {
    const raw = localStorage.getItem(CACHE_KEY);
    if (!raw) return null;
    const cached: CachedConfig = JSON.parse(raw);
    const merged = mergeWithDefaults(cached.config ?? {});

    if (forceFresh) return null;

    const ttlMs = getCacheTtlMs(merged);
    if (Date.now() - cached.fetched_at > ttlMs) {
      localStorage.removeItem(CACHE_KEY);
      return null;
    }
    return merged;
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

  const fetchConfig = useCallback((forceFresh = false) => {
    const cached = getCachedConfig(forceFresh);
    if (cached && !forceFresh) {
      setConfig(cached);
      setLoading(false);
      return;
    }

    const controller = new AbortController();
    const configUrl = `${import.meta.env.BASE_URL}config.json`;

    fetch(configUrl, { signal: controller.signal, cache: forceFresh ? 'no-cache' : 'default' })
      .then(res => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return res.json();
      })
      .then((data: Partial<RemoteConfig>) => {
        const merged = mergeWithDefaults(data);
        setConfig(merged);
        setCachedConfig(merged);
        track('config_loaded', { source: forceFresh ? 'refresh' : 'remote', version: merged.version });
      })
      .catch(err => {
        if (err.name === 'AbortError') return;
        const c = getCachedConfig();
        if (c) {
          setConfig(c);
          track('config_loaded', { source: 'cache', version: c.version });
        } else {
          track('config_loaded', { source: 'default' });
        }
      })
      .finally(() => setLoading(false));

    const timeout = setTimeout(() => controller.abort(), FETCH_TIMEOUT_MS);
    return () => { clearTimeout(timeout); controller.abort(); };
  }, []);

  // Initial fetch
  useEffect(() => {
    const cleanup = fetchConfig();
    return cleanup;
  }, [fetchConfig]);

  // Foreground refresh: re-fetch config when tab becomes visible
  useEffect(() => {
    let pendingCleanup: (() => void) | undefined;
    const handleVisibility = () => {
      if (document.visibilityState === 'visible') {
        pendingCleanup?.();
        const forceRefresh = config.operations.force_config_refresh ?? false;
        pendingCleanup = fetchConfig(forceRefresh) ?? undefined;
      }
    };
    document.addEventListener('visibilitychange', handleVisibility);
    return () => {
      pendingCleanup?.();
      document.removeEventListener('visibilitychange', handleVisibility);
    };
  }, [fetchConfig, config.operations.force_config_refresh]);

  return { config, loading };
}
