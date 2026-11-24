import { useFocusEffect } from 'expo-router';
import { useCallback, useState } from 'react';
import { Text, View } from 'react-native';
import { Button, Card, H1, P, Pill, Screen } from '@/components/ui';
import { isRTL, t } from '@/lib/i18n';
import { useSettings } from '@/lib/settings-context';
import { clearHistory, HistoryItem, loadHistory } from '@/lib/store';
import { C, verdictColor } from '@/lib/theme';

export default function History() {
  const { settings } = useSettings();
  const L = settings.lang;
  const [items, setItems] = useState<HistoryItem[]>([]);
  useFocusEffect(useCallback(() => { loadHistory().then(setItems); }, []));

  return (
    <Screen>
      <H1 rtl={isRTL(L)}>{t(L, 'history')}</H1>
      {!items.length ? <P muted>{t(L, 'nothingYet')}</P> : null}
      {items.map(i => (
        <Card key={i.id} style={{ gap: 6 }}>
          <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }}>
            <Pill text={t(L, (`verdict_${i.verdict}`) as any) || i.verdict} color={verdictColor(i.verdict)} />
            <Text style={{ color: C.muted, fontSize: 12 }}>{i.kind} · {new Date(i.at).toLocaleString()}</Text>
          </View>
          <Text style={{ color: C.white, fontWeight: '600' }} numberOfLines={2} selectable>{i.title}</Text>
          {i.reasons.slice(0, 3).map((r, k) => <Text key={k} style={{ color: C.text, fontSize: 13 }}>• {r}</Text>)}
        </Card>
      ))}
      {items.length ? <Button kind="ghost" title={t(L, 'clear')} onPress={async () => { await clearHistory(); setItems([]); }} /> : null}
    </Screen>
  );
}
