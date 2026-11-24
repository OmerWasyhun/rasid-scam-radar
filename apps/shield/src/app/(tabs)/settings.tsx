import * as Clipboard from 'expo-clipboard';
import { useEffect, useState } from 'react';
import { Pressable, Text, View } from 'react-native';
import { Button, Card, Field, H1, Label, P, Screen, s } from '@/components/ui';
import { api } from '@/lib/api';
import { isRTL, LANGS, t } from '@/lib/i18n';
import { native } from '@/lib/native';
import { useSettings } from '@/lib/settings-context';
import { C } from '@/lib/theme';

export default function SettingsScreen() {
  const { settings, update } = useSettings();
  const L = settings.lang, rtl = isRTL(L);
  const [server, setServer] = useState(settings.server);
  const [phone, setPhone] = useState(settings.phone);
  const [trusted, setTrusted] = useState(settings.trusted);
  const [msg, setMsg] = useState('');
  const [screener, setScreener] = useState<any>(null);

  useEffect(() => { setServer(settings.server); setPhone(settings.phone); setTrusted(settings.trusted); }, [settings.server, settings.phone, settings.trusted]);
  useEffect(() => { api.screener().then(setScreener).catch(() => setScreener(null)); }, [settings.server]);

  async function save() {
    const srv = server.trim().replace(/\/+$/, '');
    await update({ server: srv, phone: phone.trim(), trusted: trusted.trim() });
    try {
      await api.status(srv);
      await api.updateDevice({ phone: phone.trim() || null, lang: L });
      setMsg(t(L, 'connected'));
    } catch (e: any) { setMsg(`${t(L, 'saved')}. ${e.message ?? ''}`); }
  }

  return (
    <Screen>
      <H1 rtl={rtl}>{t(L, 'settings')}</H1>
      <Card style={{ gap: 12 }}>
        <Field label={t(L, 'server')} value={server} onChangeText={setServer} autoCapitalize="none" keyboardType="url" placeholder="http://192.168.1.20:8042" />
        <Field label={t(L, 'myPhone')} value={phone} onChangeText={setPhone} keyboardType="phone-pad" placeholder="+971 5x xxx xxxx" />
        <Field label={t(L, 'trusted')} value={trusted} onChangeText={setTrusted} keyboardType="phone-pad" placeholder="+971 5x xxx xxxx" />
        <Button title={t(L, 'save')} onPress={save} />
        {msg ? <P style={{ color: msg === t(L, 'connected') ? C.ok : C.warn }}>{msg}</P> : null}
      </Card>

      <Label>{t(L, 'language')}</Label>
      <View style={s.row}>
        {LANGS.map(l => (
          <Pressable key={l.code} onPress={() => { update({ lang: l.code }); api.updateDevice({ lang: l.code }).catch(() => {}); }}
            style={{ paddingHorizontal: 12, paddingVertical: 8, borderRadius: 8, borderWidth: 1, borderColor: l.code === L ? C.accent : C.line2 }}>
            <Text style={{ color: l.code === L ? C.accent : C.text }}>{l.name}</Text>
          </Pressable>
        ))}
      </View>

      <Card style={{ gap: 8 }}>
        <Label>{t(L, 'screener')}</Label>
        <P rtl={rtl}>{t(L, 'screenerHint')}</P>
        {screener?.enabled ? (
          <View style={{ gap: 6 }}>
            <P>{t(L, 'forwardSetup')}: {screener.number}</P>
            <P muted>{t(L, 'dialCode')}:</P>
            <Text selectable style={{ color: C.accent, fontSize: 18, fontFamily: 'monospace' }} onPress={() => Clipboard.setStringAsync(screener.forward_busy_code)}>{screener.forward_busy_code}</Text>
            <P muted>{t(L, 'cancelCode')}: {screener.cancel_code}  ·  {screener.note}</P>
          </View>
        ) : <P muted>The screener number isn't configured on the RASID server yet (Twilio keys).</P>}
      </Card>

      <Card style={{ gap: 8 }}>
        <Label>Android protection</Label>
        {native.available ? (
          <>
            <Button kind="ghost" title={t(L, 'notifAccess')} onPress={() => native.openNotificationAccess()} />
            <Button kind="ghost" title={t(L, 'callRole')} onPress={() => native.requestCallScreening()} />
          </>
        ) : <P muted rtl={rtl}>{t(L, 'nativeOff')}</P>}
      </Card>
    </Screen>
  );
}
