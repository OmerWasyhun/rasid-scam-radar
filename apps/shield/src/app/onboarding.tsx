import { router } from 'expo-router';
import { useState } from 'react';
import { Pressable, Text, View } from 'react-native';
import { Button, Card, Field, H1, Label, P, Screen, s } from '@/components/ui';
import { askNotificationPermission } from '@/lib/alerts';
import { api } from '@/lib/api';
import { isRTL, LANGS, t } from '@/lib/i18n';
import { useSettings } from '@/lib/settings-context';
import { C } from '@/lib/theme';

export default function Onboarding() {
  const { settings, update } = useSettings();
  const [lang, setLang] = useState(settings.lang || 'en');
  const [server, setServer] = useState(settings.server || '');
  const [phone, setPhone] = useState(settings.phone || '');
  const [err, setErr] = useState('');
  const [busy, setBusy] = useState(false);
  const rtl = isRTL(lang);

  async function finish() {
    setBusy(true); setErr('');
    const srv = server.trim().replace(/\/+$/, '');
    try {
      await api.status(srv);
    } catch {
      setErr(`Can't reach RASID at ${srv}. Use the computer's address shown by the RASID server, on the same Wi-Fi.`);
      setBusy(false);
      return;
    }
    await update({ lang, server: srv, phone: phone.trim(), onboarded: true });
    await askNotificationPermission().catch(() => {});
    setBusy(false);
    router.replace('/');
  }

  return (
    <Screen>
      <View style={{ alignItems: 'center', gap: 10, paddingVertical: 20 }}>
        <View style={{ width: 70, height: 70, borderRadius: 35, borderWidth: 3, borderColor: C.accent, alignItems: 'center', justifyContent: 'center' }}>
          <View style={{ width: 14, height: 14, borderRadius: 7, backgroundColor: C.crit }} />
        </View>
        <H1>{t(lang, 'appName')}</H1>
        <P muted>{t(lang, 'tagline')}</P>
      </View>
      <Label>{t(lang, 'language')}</Label>
      <View style={s.row}>
        {LANGS.map(l => (
          <Pressable key={l.code} onPress={() => setLang(l.code)}
            style={{ paddingHorizontal: 12, paddingVertical: 8, borderRadius: 8, borderWidth: 1, borderColor: l.code === lang ? C.accent : C.line2 }}>
            <Text style={{ color: l.code === lang ? C.accent : C.text }}>{l.name}</Text>
          </Pressable>
        ))}
      </View>
      <Card style={{ gap: 12 }}>
        <Field label={t(lang, 'server')} value={server} onChangeText={setServer} autoCapitalize="none" keyboardType="url" placeholder="http://192.168.1.20:8042" />
        <Field label={t(lang, 'myPhone')} value={phone} onChangeText={setPhone} keyboardType="phone-pad" placeholder="+971 5x xxx xxxx" />
        <P muted rtl={rtl}>RASID checks links and numbers against Abu Dhabi Police's fraud database. Message text stays on your phone unless it contains a link, a number or scam wording.</P>
      </Card>
      {err ? <Card accent={C.crit}><Text style={{ color: C.crit }}>{err}</Text></Card> : null}
      <Button title={t(lang, 'getStarted')} onPress={finish} busy={busy} disabled={!server.trim()} />
    </Screen>
  );
}
