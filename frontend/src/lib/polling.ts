import { createContext, useContext, useSyncExternalStore } from 'react';

export const PollingContext = createContext<{ interval: number; setInterval: (interval: number) => void }>({
  interval: 5000,
  setInterval: () => {},
});

function subscribeVisibility(listener: () => void): () => void {
  document.addEventListener('visibilitychange', listener);
  return () => document.removeEventListener('visibilitychange', listener);
}

export function useDocumentVisible(): boolean {
  return useSyncExternalStore(subscribeVisibility, () => !document.hidden, () => true);
}

export const usePollingControl = () => useContext(PollingContext);

export function usePollingPolicy(cadence = 5000) {
  const { interval } = usePollingControl();
  const visible = useDocumentVisible();
  const enabled = interval > 0 && visible;
  return {
    refetchInterval: enabled ? Math.max(interval, cadence) : false as const,
    refetchIntervalInBackground: false as const,
    refetchOnWindowFocus: enabled,
    refetchOnReconnect: enabled,
    retry: false as const,
  };
}
