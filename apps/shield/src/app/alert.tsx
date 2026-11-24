// Full-screen emergency alert (level 2): vibration, spoken warning, hang-up and trusted-contact actions.
import * as Speech from 'expo-speech';
import { router, useLocalSearchParams } from 'expo-router';
import { useEffect } from 'react';
import { Linking, Text, Vibration, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Button } from '@/components/ui';
import { speak } from '@/lib/alerts';
import { isRTL, t, warnNotOrg } from '@/lib/i18n';
import { native } from '@/lib/native';
import { useSettings } from '@/lib/settings-context';
import { C } from '@/lib/theme';

export default function Alert() {
  const p = useLocalSearchParams<{ title: string; message: string; number?: string; org?: string; reasons?: string }>();
  const { settings } = useSettings();
  const L = settings.lang, rtl = isRTL(L);
  const reasons: string[] = (() => { try { return JSON.parse(p.reasons || '[]'); } catch { return []; } })();
  const message = p.org ? warnNotOrg(L, p.org) : p.message;

  useEffect(() => {
    speak(message, L);
    const timer = setInterval(() => Vibration.vibrate([0, 500, 200, 500]), 3000);
    return () => { clearInterval(timer); Vibration.cancel(); Speech.stop(); };
  }, [message, L]);

  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: '#3a0812' }}>
      <View style={{ flex: 1, padding: 24, gap: 18, justifyContent: 'center' }}>
        <Text style={{ color: C.crit, fontSize: 14, fontWeight: '800', letterSpacing: 3, fontFamily: 'monospace' }}>{t(L, 'emergency')}</Text>
        <Text style={[{ color: '#fff', fontSize: 30, fontWeight: '800', lineHeight: 38 }, rtl && { writingDirection: 'rtl', textAlign: 'right' }]}>{message}</Text>
        {p.number ? <Text style={{ color: '#ffd1d8', fontSize: 18, fontFamily: 'monospace' }}>{p.number}{p.org ? ` → ${p.org}` : ''}</Text> : null}
        {reasons.map((r, i) => <Text key={i} style={{ color: '#ffd1d8', fontSize: 15 }}>• {r}</Text>)}
        <View style={{ gap: 10, marginTop: 10 }}>
          {native.available ? <Button kind="danger" title={t(L, 'hangUpNow')} onPress={() => native.endCall()} /> : null}
          {settings.trusted ? (
            <Button kind="ghost" title={`Alert ${settings.trusted}`} onPress={() =>
              Linking.openURL(`sms:${settings.trusted}?body=${encodeURIComponent(`RASID alert: I may be on a scam call from ${p.number ?? 'an unknown number'} pretending to be ${p.org ?? 'an organisation'}.`)}`).catch(() => {})} />
          ) : null}
          <Button title={t(L, 'dismiss')} onPress={() => router.back()} />
        </View>
      </View>
    </SafeAreaView>
  );
}
