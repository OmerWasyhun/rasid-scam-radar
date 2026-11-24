// Test the cloud call screening agent without a phone line: type what a caller says, see what the agent does.
import { useState } from 'react';
import { Text, View } from 'react-native';
import { Button, Card, Field, H1, Label, P, Pill, Screen } from '@/components/ui';
import { emergency, speak } from '@/lib/alerts';
import { api } from '@/lib/api';
import { isRTL, t, warnNotOrg, warnScam } from '@/lib/i18n';
import { useSettings } from '@/lib/settings-context';
import { addHistory } from '@/lib/store';
import { C, verdictColor } from '@/lib/theme';

const EXAMPLES = [
  { caller: '+971 55 123 4567', lines: "Hello, my name is Ahmed, I'm calling from ADCB about your card.\nWe blocked it. Please tell me the OTP we just sent so I can unblock it." },
  { caller: '+971 52 765 4321', lines: 'مرحبا، معك خالد من شرطة أبوظبي.\nعليك مخالفة ويجب تحويل المبلغ الآن.' },
  { caller: '+971 50 222 3333', lines: "Hi, this is Sara, I'm calling about the apartment you listed.\nI wanted to ask if I can see it tomorrow." },
];

export default function Screener() {
  const { settings } = useSettings();
  const L = settings.lang, rtl = isRTL(L);
  const [caller, setCaller] = useState(EXAMPLES[0].caller);
  const [lines, setLines] = useState(EXAMPLES[0].lines);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');
  const [res, setRes] = useState<any>(null);

  async function run() {
    setBusy(true); setErr(''); setRes(null);
    try {
      const r: any = await api.simulate(caller, lines.split('\n').map(x => x.trim()).filter(Boolean));
      setRes(r);
      const d = r.decision;
      await addHistory({ kind: 'call', input: caller, verdict: d.decision === 'scam' ? 'scam' : d.decision === 'pass' ? 'official' : 'suspicious',
        title: `Screened call ${caller}${r.claimed_org ? ` (says ${r.claimed_org})` : ''}`, reasons: [d.reason] });
      if (d.decision === 'scam') {
        const msg = r.claimed_org ? warnNotOrg(L, r.claimed_org) : warnScam(L);
        if (d.level >= 2) emergency({ title: t(L, 'emergency'), message: msg, number: caller, org: r.claimed_org ?? undefined, reasons: [d.reason] });
        else speak(msg, L);
      }
    } catch (e: any) { setErr(e.message); }
    setBusy(false);
  }

  return (
    <Screen>
      <H1 rtl={rtl}>{t(L, 'testAgent')}</H1>
      <P muted rtl={rtl}>{t(L, 'screenerHint')}</P>
      <View style={{ flexDirection: 'row', gap: 8, flexWrap: 'wrap' }}>
        {EXAMPLES.map((e, i) => <Button key={i} kind="ghost" title={['Fake bank', 'Fake police (AR)', 'Real person'][i]} onPress={() => { setCaller(e.caller); setLines(e.lines); setRes(null); }} />)}
      </View>
      <Field label={t(L, 'callerNumber')} value={caller} onChangeText={setCaller} keyboardType="phone-pad" />
      <Field label={t(L, 'callerLines')} value={lines} onChangeText={setLines} multiline />
      <Button title={t(L, 'simulate')} onPress={run} busy={busy} />
      {err ? <Card accent={C.crit}><Text style={{ color: C.crit }}>{err}</Text></Card> : null}
      {res ? (
        <Card accent={verdictColor(res.decision.decision)} style={{ gap: 10 }}>
          <Pill text={(t(L, (`verdict_${res.decision.decision}`) as any) || res.decision.decision).toUpperCase()} color={verdictColor(res.decision.decision)} />
          <Text style={{ color: C.white, fontWeight: '600', fontSize: 16 }}>
            {res.caller_name ?? 'Caller'}{res.claimed_org ? ` · says ${res.claimed_org}` : ''}
          </Text>
          <P>{res.decision.reason}</P>
          <Label>{t(L, 'transcript')}</Label>
          {res.transcript.map((m: any, i: number) => (
            <View key={i} style={{ gap: 2 }}>
              <Text style={{ color: m.who === 'agent' ? C.accent : C.warn, fontSize: 11, fontFamily: 'monospace' }}>{m.who === 'agent' ? 'RASID AGENT' : 'CALLER'}</Text>
              <P>{m.text}</P>
            </View>
          ))}
        </Card>
      ) : null}
    </Screen>
  );
}
