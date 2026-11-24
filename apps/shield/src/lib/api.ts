// Typed client for the RASID citizen API (/api/v1). Registers the device on first use.
import { Platform } from 'react-native';
import { native } from './native';
import { loadSettings, saveSettings, Settings } from './store';

export class ApiError extends Error {}

async function ensureDevice(s: Settings): Promise<Settings> {
  if (s.deviceId && s.deviceToken) return s;
  if (!s.server) throw new ApiError('Set the RASID server address in Settings first.');
  const r = await fetch(`${s.server}/api/v1/devices`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ platform: Platform.OS, lang: s.lang, phone: s.phone || null }),
  });
  if (!r.ok) throw new ApiError(`Could not register with RASID (HTTP ${r.status})`);
  const j = await r.json();
  const next = { ...s, deviceId: j.device_id, deviceToken: j.device_token };
  await saveSettings(next);
  native.configure(next.server, j.device_id, j.device_token, next.lang);
  return next;
}

export async function call<T = any>(path: string, opts: { method?: string; body?: any; timeoutMs?: number } = {}): Promise<T> {
  let s = await loadSettings();
  s = await ensureDevice(s);
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), opts.timeoutMs ?? 20000);
  try {
    const r = await fetch(`${s.server}${path}`, {
      method: opts.method ?? (opts.body ? 'POST' : 'GET'),
      headers: { 'Content-Type': 'application/json', 'X-Device-Id': s.deviceId!, 'X-Device-Token': s.deviceToken! },
      body: opts.body ? JSON.stringify(opts.body) : undefined,
      signal: ctrl.signal,
    });
    const j = await r.json().catch(() => ({}));
    if (r.status === 401) {
      await saveSettings({ ...s, deviceId: undefined, deviceToken: undefined });
      throw new ApiError('Device was not recognised by RASID. Try again.');
    }
    if (!r.ok) throw new ApiError(typeof j.detail === 'string' ? j.detail : `RASID error (HTTP ${r.status})`);
    return j as T;
  } catch (e: any) {
    if (e instanceof ApiError) throw e;
    if (e?.name === 'AbortError') throw new ApiError('RASID took too long to answer.');
    throw new ApiError(`Can't reach RASID at ${s.server}. Check the address and that the phone is on the same network.`);
  } finally {
    clearTimeout(timer);
  }
}

export const api = {
  checkLink: (url: string) => call('/api/v1/check/link', { body: { url }, timeoutMs: 15000 }),
  checkMessage: (text: string, sender?: string) => call('/api/v1/check/message', { body: { text, sender }, timeoutMs: 25000 }),
  checkNumber: (number: string) => call('/api/v1/check/number', { body: { number } }),
  ticket: (id: string) => call(`/api/v1/tickets/${id}`),
  orgs: () => call<{ name: string; official_numbers: number; bank_or_police: boolean }[]>('/api/v1/orgs'),
  verifyClaim: (number: string, org: string, asked_sensitive: boolean) =>
    call('/api/v1/verify/claim', { body: { number, org, asked_sensitive } }),
  report: (kind: 'number' | 'link' | 'message', value: string, claim?: string) =>
    call('/api/v1/report', { body: { kind, value, claim } }),
  calls: () => call<any[]>('/api/v1/calls'),
  screener: () => call('/api/v1/screener'),
  simulate: (caller: string, lines: string[]) => call('/api/v1/screener/simulate', { body: { caller, lines }, timeoutMs: 60000 }),
  updateDevice: (body: any) => call('/api/v1/devices/me', { method: 'PATCH', body }),
  // Offline cache for call screening: official numbers + reported/scam hashes.
  syncNumbers: async () => {
    if (!native.available) return 0;
    const j: any = await call('/api/v1/sync/numbers?since=0');
    native.setNumberCache(JSON.stringify(j.numbers));
    const s = await loadSettings();
    if (s.deviceId && s.deviceToken) native.configure(s.server, s.deviceId, s.deviceToken, s.lang);
    return j.numbers.length;
  },
  status: async (server: string) => {
    const r = await fetch(`${server}/api/status`);
    if (!r.ok) throw new ApiError(`HTTP ${r.status}`);
    return r.json();
  },
};

export type Kind = 'link' | 'message' | 'number';
export function detectKind(input: string): Kind {
  const t = input.trim();
  if (/^[+\d][\d\s-]{6,}$/.test(t)) return 'number';
  if (!/\s/.test(t) && /\.[a-z]{2,}/i.test(t)) return 'link';
  return 'message';
}
