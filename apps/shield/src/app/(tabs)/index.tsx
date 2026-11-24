import { router, useFocusEffect } from 'expo-router';
import { useCallback, useState } from 'react';
import { Pressable, Text, View } from 'react-native';
import { Button, Card, H1, Label, P, Pill, Screen, s } from '@/components/ui';
import { api } from '@/lib/api';
import { isRTL, t } from '@/lib/i18n';
import { native } from '@/lib/native';
import { useSettings } from '@/lib/settings-context';
import { HistoryItem, loadHistory } from '@/lib/store';
import { C, verdictColor } from '@/lib/theme';

export default function Home() {
  const { settings } = useSettings();
  const L = settings.lang, rtl = isRTL(L);
  const [recent, setRecent] = useState<HistoryItem[]>([]);
  const [status, setStatus] = useState({ notif: false, calls: false });

  useFocusEffect(useCallback(() => {
    loadHistory().then(h => setRecent(h.slice(0, 5)));
    setStatus({ notif: native.notificationAccess(), calls: native.callScreening() });
    api.syncNumbers().catch(() => {});
  }, []));

  const blocked = recent.filter(r => r.verdict === 'scam').length;

  return (
    <Screen>
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }}>
        <View style={{ width: 38, height: 38, borderRadius: 19, borderWidth: 2, borderColor: C.accent, alignItems: 'center', justifyContent: 'center' }}>
          <View style={{ width: 8, height: 8, borderRadius: 4, backgroundColor: C.crit }} />
        </View>
        <View>
          <H1>{t(L, 'appName')}</H1>
          <Text style={{ color: C.muted, fontSize: 12 }}>{t(L, 'tagline')}</Text>
        </View>
      </View>

      <Card style={{ gap: 10 }}>
        <Label>{t(L, 'protected')}</Label>
        {native.available ? (
          <View style={{ gap: 8 }}>
            <Row label={t(L, 'notifAccess')} on={status.notif} onPress={() => native.openNotificationAccess()} L={L} />
            <Row label={t(L, 'callRole')} on={status.calls} onPress={() => native.requestCallScreening()} L={L} />
          </View>
        ) : <P muted rtl={rtl}>{t(L, 'nativeOff')}</P>}
        {blocked ? <P>{blocked} scam{blocked > 1 ? 's' : ''} caught in your recent checks.</P> : null}
      </Card>

      <Pressable onPress={() => router.push('/claim')}>
        <Card accent={C.crit} style={{ gap: 6 }}>
          <Text style={{ color: C.crit, fontWeight: '800', fontSize: 18 }}>{t(L, 'whoIsCalling')}</Text>
          <P rtl={rtl}>{t(L, 'whoIsCallingHint')}</P>
        </Card>
      </Pressable>

      <View style={s.row}>
        <View style={{ flex: 1 }}><Button title={t(L, 'checkSomething')} onPress={() => router.push('/check')} /></View>
      </View>
      <Button kind="ghost" title={t(L, 'screener')} onPress={() => router.push('/screener')} />

      <Label>{t(L, 'recent')}</Label>
      {recent.length ? recent.map(r => (
        <Card key={r.id} style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }}>
          <Pill text={t(L, (`verdict_${r.verdict}`) as any) || r.verdict} color={verdictColor(r.verdict)} />
          <Text style={{ color: C.text, flex: 1 }} numberOfLines={1}>{r.title}</Text>
        </Card>
      )) : <P muted>{t(L, 'nothingYet')}</P>}
    </Screen>
  );
}

function Row({ label, on, onPress, L }: { label: string; on: boolean; onPress: () => void; L: string }) {
  return (
    <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 8 }}>
      <Text style={{ color: C.text, flex: 1 }}>{label}</Text>
      {on ? <Pill text="ON" color={C.ok} /> : <Pressable onPress={onPress}><Pill text={t(L, 'grant')} color={C.warn} /></Pressable>}
    </View>
  );
}
