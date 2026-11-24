// RASID Root Guardian: arms a background service that listens to calls (rooted phone, system app) and hangs up scams.
import { requireOptionalNativeModule } from 'expo';
import { StatusBar } from 'expo-status-bar';
import { useCallback, useEffect, useState } from 'react';
import { PermissionsAndroid, Platform, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from 'react-native';

type Root = {
  saveConfig(server: string, key: string, lang: string): void;
  getConfig(): { server: string; key: string; lang: string };
  arm(): boolean;
  disarm(): boolean;
  status(): { armed: boolean; status: string; systemApp: boolean; captureAudioOutput: boolean };
  checkRoot(): Promise<boolean>;
  events(): string;
};
const R = requireOptionalNativeModule<Root>('RasidRoot');

const C = { ink: '#060b14', panel: '#0b1422', line: '#24395a', text: '#dbe5f2', muted: '#8395ae', accent: '#4cc9f0', ok: '#5ee0a0', warn: '#ff9f43', crit: '#ff5470' };

const PERMS = [
  PermissionsAndroid.PERMISSIONS.RECORD_AUDIO,
  PermissionsAndroid.PERMISSIONS.READ_PHONE_STATE,
  PermissionsAndroid.PERMISSIONS.READ_CALL_LOG,
  PermissionsAndroid.PERMISSIONS.ANSWER_PHONE_CALLS,
  ...(Platform.OS === 'android' && Platform.Version >= 33 ? [PermissionsAndroid.PERMISSIONS.POST_NOTIFICATIONS] : []),
];

export default function App() {
  const [server, setServer] = useState('');
  const [key, setKey] = useState('');
  const [lang, setLang] = useState('auto');
  const [st, setSt] = useState<ReturnType<Root['status']> | null>(null);
  const [root, setRoot] = useState<boolean | null>(null);
  const [perms, setPerms] = useState(false);
  const [msg, setMsg] = useState('');
  const [events, setEvents] = useState<any[]>([]);

  const refresh = useCallback(async () => {
    if (!R) return;
    setSt(R.status());
    try { setEvents(JSON.parse(R.events())); } catch { setEvents([]); }
    const res = await PermissionsAndroid.check(PermissionsAndroid.PERMISSIONS.RECORD_AUDIO);
    setPerms(res);
  }, []);

  useEffect(() => {
    if (!R) return;
    const c = R.getConfig();
    setServer(c.server); setKey(c.key); setLang(c.lang || 'auto');
    R.checkRoot().then(setRoot).catch(() => setRoot(false));
    refresh();
    const t = setInterval(refresh, 3000);
    return () => clearInterval(t);
  }, [refresh]);

  if (!R) {
    return <View style={s.screen}><Text style={s.p}>This build doesn't include the RASID native module. Install the RASID Root Guardian APK.</Text></View>;
  }

  async function grant() {
    const res = await PermissionsAndroid.requestMultiple(PERMS);
    const ok = Object.values(res).every(v => v === PermissionsAndroid.RESULTS.GRANTED);
    setMsg(ok ? 'Permissions granted.' : 'Some permissions were refused. Allow them in Settings → Apps → RASID Guardian.');
    refresh();
  }

  async function save() {
    R!.saveConfig(server.trim().replace(/\/+$/, ''), key.trim(), lang);
    try {
      const r = await fetch(`${server.trim().replace(/\/+$/, '')}/phone/ping?key=${encodeURIComponent(key.trim())}`);
      const j = await r.json();
      if (!r.ok) throw new Error(j.detail || `HTTP ${r.status}`);
      setMsg(`Connected to RASID · speech model ${j.whisper_model}${j.whisper_loaded ? ' (loaded)' : ' (loads on first call)'}`);
      fetch(`${server.trim().replace(/\/+$/, '')}/phone/warmup?key=${encodeURIComponent(key.trim())}`, { method: 'POST' }).catch(() => {});
    } catch (e: any) {
      setMsg(`Saved, but RASID didn't answer: ${e.message}. Same Wi-Fi? Right address and key?`);
    }
  }

  const ready = !!st?.systemApp && !!st?.captureAudioOutput && perms;
  return (
    <ScrollView style={s.screen} contentContainerStyle={{ padding: 18, gap: 14, paddingTop: 50 }}>
      <StatusBar style="light" />
      <Text style={s.h1}>RASID Guardian <Text style={{ color: C.accent }}>راصد</Text></Text>
      <Text style={s.muted}>Listens to your calls and ends them when they are a scam. Root required.</Text>

      <View style={s.card}>
        <Text style={s.label}>CHECKS</Text>
        <Row ok={root === true} text={root === null ? 'Checking root…' : root ? 'Root (Magisk) available' : 'No root access'} />
        <Row ok={!!st?.systemApp} text={st?.systemApp ? 'Installed as a system app' : 'Not a system app: flash the RASID Magisk module'} />
        <Row ok={!!st?.captureAudioOutput} text={st?.captureAudioOutput ? 'Call audio access granted' : 'No call audio access (needs the Magisk module)'} />
        <Row ok={perms} text={perms ? 'Microphone, phone and notification permissions' : 'Permissions not granted yet'} />
        {!perms ? <Btn title="Grant permissions" onPress={grant} /> : null}
      </View>

      <View style={s.card}>
        <Text style={s.label}>RASID SERVER</Text>
        <TextInput style={s.input} value={server} onChangeText={setServer} placeholder="http://192.168.1.20:8042" placeholderTextColor={C.muted} autoCapitalize="none" keyboardType="url" />
        <TextInput style={s.input} value={key} onChangeText={setKey} placeholder="Phone key (RASID_PHONE_KEY)" placeholderTextColor={C.muted} autoCapitalize="none" />
        <View style={{ flexDirection: 'row', gap: 8 }}>
          {[['auto', 'Auto'], ['ar', 'العربية'], ['en', 'English']].map(([v, l]) => (
            <Pressable key={v} onPress={() => setLang(v)} style={[s.chip, lang === v && { borderColor: C.accent }]}>
              <Text style={{ color: lang === v ? C.accent : C.text }}>{l}</Text>
            </Pressable>
          ))}
        </View>
        <Btn title="Save and test connection" onPress={save} />
        {msg ? <Text style={s.muted}>{msg}</Text> : null}
      </View>

      <View style={[s.card, { borderColor: st?.armed ? C.ok : C.line }]}>
        <Text style={s.label}>GUARDIAN</Text>
        <Text style={[s.p, { color: st?.armed ? C.ok : C.muted, fontWeight: '700' }]}>{st?.armed ? 'ARMED' : 'Off'}</Text>
        <Text style={s.muted}>{st?.status}</Text>
        {st?.armed
          ? <Btn title="Disarm" kind="ghost" onPress={() => { R!.disarm(); setTimeout(refresh, 500); }} />
          : <Btn title={ready ? 'Arm Guardian' : 'Arm Guardian (checks not all green)'} onPress={() => { R!.arm(); setTimeout(refresh, 800); }} />}
      </View>

      <Text style={s.label}>CALLS RASID ENDED</Text>
      {events.length ? events.map((e, i) => (
        <View key={i} style={[s.card, { borderColor: C.crit }]}>
          <Text style={[s.p, { color: C.crit, fontWeight: '700' }]}>{e.ended ? 'Ended' : 'Flagged'} · risk {e.risk}/100</Text>
          <Text style={s.muted}>{new Date(e.at).toLocaleString()}{e.number ? ` · ${e.number}` : ''}</Text>
          <Text style={s.p}>{e.reasons}</Text>
        </View>
      )) : <Text style={s.muted}>None yet.</Text>}
      <Text style={[s.muted, { fontSize: 11 }]}>Test only with people who agree to be recorded. Audio is transcribed on the RASID server and never stored.</Text>
    </ScrollView>
  );
}

function Row({ ok, text }: { ok: boolean; text: string }) {
  return <Text style={{ color: ok ? C.ok : C.warn }}>{ok ? '✓' : '•'} {text}</Text>;
}
function Btn({ title, onPress, kind }: { title: string; onPress: () => void; kind?: 'ghost' }) {
  return (
    <Pressable onPress={onPress} style={({ pressed }) => [s.btn, kind === 'ghost' && { backgroundColor: 'transparent', borderWidth: 1, borderColor: C.line }, pressed && { opacity: 0.8 }]}>
      <Text style={{ color: kind === 'ghost' ? C.text : '#04121c', fontWeight: '700' }}>{title}</Text>
    </Pressable>
  );
}

const s = StyleSheet.create({
  screen: { flex: 1, backgroundColor: C.ink },
  h1: { color: '#f1f6fc', fontSize: 24, fontWeight: '800' },
  p: { color: C.text, fontSize: 15 },
  muted: { color: C.muted, fontSize: 13 },
  label: { color: C.muted, fontSize: 11, letterSpacing: 1.4, fontFamily: 'monospace' },
  card: { backgroundColor: C.panel, borderWidth: 1, borderColor: C.line, borderRadius: 14, padding: 14, gap: 8 },
  input: { backgroundColor: C.ink, borderWidth: 1, borderColor: C.line, borderRadius: 10, color: C.text, padding: 10 },
  chip: { borderWidth: 1, borderColor: C.line, borderRadius: 8, paddingHorizontal: 12, paddingVertical: 7 },
  btn: { backgroundColor: C.accent, borderRadius: 10, paddingVertical: 12, alignItems: 'center' },
});
