// Local storage: settings, device credentials and the history of everything checked.
import AsyncStorage from '@react-native-async-storage/async-storage';

export type Settings = {
  server: string;          // RASID server, e.g. http://192.168.1.20:8042
  lang: string;            // en, ar, hi, ur, ml, ta, si, tl, bn, ne, ru, zh
  phone: string;           // user's own number (screener connects calls back to it)
  trusted: string;         // trusted contact number for emergency alerts
  deviceId?: string;
  deviceToken?: string;
  onboarded?: boolean;
};

export type HistoryItem = {
  id: string;
  kind: 'link' | 'message' | 'number' | 'claim' | 'call';
  input: string;
  verdict: string;
  score?: number;
  title: string;
  reasons: string[];
  at: number;
  extra?: any;
};

const K_SETTINGS = 'rasid.settings';
const K_HISTORY = 'rasid.history';

export const defaultSettings: Settings = { server: '', lang: 'en', phone: '', trusted: '' };

export async function loadSettings(): Promise<Settings> {
  try {
    const raw = await AsyncStorage.getItem(K_SETTINGS);
    return raw ? { ...defaultSettings, ...JSON.parse(raw) } : { ...defaultSettings };
  } catch {
    return { ...defaultSettings };
  }
}

export async function saveSettings(s: Settings) {
  await AsyncStorage.setItem(K_SETTINGS, JSON.stringify(s));
}

export async function loadHistory(): Promise<HistoryItem[]> {
  try {
    const raw = await AsyncStorage.getItem(K_HISTORY);
    return raw ? JSON.parse(raw) : [];
  } catch {
    return [];
  }
}

export async function addHistory(item: Omit<HistoryItem, 'id' | 'at'>) {
  const list = await loadHistory();
  const full: HistoryItem = { ...item, id: Math.random().toString(36).slice(2), at: Date.now() };
  await AsyncStorage.setItem(K_HISTORY, JSON.stringify([full, ...list].slice(0, 300)));
  return full;
}

export async function clearHistory() {
  await AsyncStorage.removeItem(K_HISTORY);
}
