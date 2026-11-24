import { createContext, ReactNode, useCallback, useContext, useEffect, useState } from 'react';
import { defaultSettings, loadSettings, saveSettings, Settings } from './store';
import { native } from './native';

type Ctx = { settings: Settings; ready: boolean; update: (patch: Partial<Settings>) => Promise<void> };
const SettingsCtx = createContext<Ctx>({ settings: defaultSettings, ready: false, update: async () => {} });

export function SettingsProvider({ children }: { children: ReactNode }) {
  const [settings, setSettings] = useState<Settings>(defaultSettings);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    loadSettings().then(s => { setSettings(s); setReady(true); });
  }, []);

  const update = useCallback(async (patch: Partial<Settings>) => {
    const cur = await loadSettings();  // keep device credentials written by the API client
    const next = { ...cur, ...patch };
    if (patch.server !== undefined && patch.server !== cur.server) {
      next.deviceId = undefined;
      next.deviceToken = undefined;
    }
    await saveSettings(next);
    setSettings(next);
    if (next.deviceId && next.deviceToken) native.configure(next.server, next.deviceId, next.deviceToken, next.lang);
  }, []);

  return <SettingsCtx.Provider value={{ settings, ready, update }}>{children}</SettingsCtx.Provider>;
}

export const useSettings = () => useContext(SettingsCtx);
