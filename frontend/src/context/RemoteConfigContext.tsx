import { createContext, useContext, type ReactNode } from 'react';
import { type RemoteConfig, DEFAULT_CONFIG } from '../types/remoteConfig';
import { useRemoteConfig } from '../hooks/useRemoteConfig';

interface RemoteConfigContextValue {
  config: RemoteConfig;
  loading: boolean;
}

const RemoteConfigContext = createContext<RemoteConfigContextValue>({
  config: DEFAULT_CONFIG,
  loading: true,
});

export function RemoteConfigProvider({ children }: { children: ReactNode }) {
  const { config, loading } = useRemoteConfig();
  return (
    <RemoteConfigContext.Provider value={{ config, loading }}>
      {children}
    </RemoteConfigContext.Provider>
  );
}

export function useRemoteConfigContext() {
  return useContext(RemoteConfigContext);
}
