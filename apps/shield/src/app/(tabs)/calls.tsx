import { router, useFocusEffect } from 'expo-router';
import { useCallback, useState } from 'react';
import { RefreshControl, ScrollView, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Button, Card, H1, Label, P, Pill, s } from '@/components/ui';
import { api } from '@/lib/api';
import { isRTL, t } from '@/lib/i18n';
import { useSettings } from '@/lib/settings-context';
import { C, verdictColor } from '@/lib/theme';

export default function Calls() {
  const { settings } = useSettings();
  const L = settings.lang, rtl = isRTL(L);
  const [calls, setCalls] = useState<any[]>([]);
  const [err, setErr] = useState('');
  const [open, setOpen] = useState<number | null>(null);
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try { setCalls(await api.calls()); setErr(''); } catch (e: any) { setErr(e.message); }
    setLoading(false);
  }, []);
  useFocusEffect(useCallback(() => { load(); }, [load]));

  return (
    <SafeAreaView style={s.screen} edges={['top', 'left', 'right']}>
      <ScrollView contentContainerStyle={s.content} refreshControl={<RefreshControl refreshing={loading} onRefresh={load} tintColor={C.accent} />}>
        <H1 rtl={rtl}>{t(L, 'screenedCalls')}</H1>
        <P muted rtl={rtl}>{t(L, 'screenerHint')}</P>
        <View style={s.row}>
          <View style={{ flex: 1 }}><Button title={t(L, 'whoIsCalling')} kind="danger" onPress={() => router.push('/claim')} /></View>
          <View style={{ flex: 1 }}><Button title={t(L, 'testAgent')} kind="ghost" onPress={() => router.push('/screener')} /></View>
        </View>
        {err ? <Card accent={C.crit}><Text style={{ color: C.crit }}>{err}</Text></Card> : null}
        {!calls.length && !err ? <P muted>No screened calls yet.</P> : null}
        {calls.map(c => {
          const color = verdictColor(c.decision === 'scam' ? 'scam' : c.decision);
          return (
            <Card key={c.id} accent={c.decision === 'scam' ? C.crit : undefined} style={{ gap: 8 }}>
              <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }}>
                <Pill text={t(L, (`verdict_${c.decision}`) as any) || c.decision} color={color} />
                <Text style={{ color: C.muted, fontSize: 12 }}>{new Date(c.created * 1000).toLocaleString()}</Text>
              </View>
              <Text style={{ color: C.white, fontSize: 16, fontWeight: '600' }}>
                {c.caller_name ? `${c.caller_name} · ` : ''}{c.caller_pretty}{c.claimed_org ? `  (says ${c.claimed_org})` : ''}
              </Text>
              <P>{c.reason}</P>
              <Text style={{ color: C.accent }} onPress={() => setOpen(open === c.id ? null : c.id)}>
                {open === c.id ? '▾ ' : '▸ '}{t(L, 'transcript')}
              </Text>
              {open === c.id ? (c.transcript || []).map((m: any, i: number) => (
                <View key={i} style={{ gap: 2 }}>
                  <Label>{m.who === 'agent' ? 'RASID agent' : 'Caller'}</Label>
                  <P>{m.text}</P>
                </View>
              )) : null}
            </Card>
          );
        })}
      </ScrollView>
    </SafeAreaView>
  );
}
