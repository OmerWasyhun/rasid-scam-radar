// "Who is calling?" — check a caller's claimed organisation against RASID's official number registry.
import { router } from 'expo-router';
import { useEffect, useState } from 'react';
import { Pressable, Switch, Text, View } from 'react-native';
import { Button, Card, Field, H1, Label, P, Screen, VerdictCard, s } from '@/components/ui';
import { emergency, notify, speak } from '@/lib/alerts';
import { api } from '@/lib/api';
import { isRTL, t, verifiedOrg, warnNotOrg } from '@/lib/i18n';
import { native } from '@/lib/native';
import { useSettings } from '@/lib/settings-context';
import { addHistory } from '@/lib/store';
import { C } from '@/lib/theme';

const FALLBACK_ORGS = ['ADCB', 'First Abu Dhabi Bank', 'Emirates NBD', 'Abu Dhabi Police', 'Dubai Police', 'Etisalat e&', 'du', 'Aramex', 'Emirates Post', 'TAMM', 'ICP', 'MOHRE'];

export default function Claim() {
  const { settings } = useSettings();
  const L = settings.lang, rtl = isRTL(L);
  const [number, setNumber] = useState(native.lastIncomingNumber() ?? '');
  const [orgs, setOrgs] = useState<string[]>(FALLBACK_ORGS);
  const [org, setOrg] = useState('');
  const [other, setOther] = useState('');
  const [sensitive, setSensitive] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');
  const [res, setRes] = useState<any>(null);

  useEffect(() => { api.orgs().then(o => setOrgs(o.map(x => x.name))).catch(() => {}); }, []);

  async function verify() {
    const claimed = other.trim() || org;
    if (!number.trim() || !claimed) return;
    setBusy(true); setErr(''); setRes(null);
    try {
      const r: any = await api.verifyClaim(number.trim(), claimed, sensitive);
      setRes(r);
      await addHistory({ kind: 'claim', input: `${r.number} → ${claimed}`, verdict: r.decision === 'pass' ? 'official' : r.decision === 'scam' ? 'scam' : 'suspicious',
        title: `${r.number} says ${claimed}`, reasons: r.reasons });
      if (r.decision === 'pass') {
        speak(verifiedOrg(L, claimed), L);
      } else if (r.decision === 'scam') {
        const msg = warnNotOrg(L, claimed);
        speak(msg, L);
        notify(r.level >= 2 ? '🚨 EMERGENCY: scam call' : 'RASID: scam call', msg, r.level >= 2);
        if (r.level >= 2) emergency({ title: t(L, 'emergency'), message: msg, number: r.number, org: claimed, reasons: r.reasons });
      } else {
        speak(warnNotOrg(L, claimed), L);
      }
    } catch (e: any) { setErr(e.message); }
    setBusy(false);
  }

  const verdict = res ? (res.decision === 'pass' ? 'official' : res.decision === 'scam' ? 'scam' : 'suspicious') : '';
  const claimed = other.trim() || org;

  return (
    <Screen>
      <H1 rtl={rtl}>{t(L, 'whoIsCalling')}</H1>
      <P muted rtl={rtl}>{t(L, 'whoIsCallingHint')}</P>
      <Field label={t(L, 'callerNumber')} value={number} onChangeText={setNumber} keyboardType="phone-pad" placeholder="+971 5x xxx xxxx" />
      <Label>{t(L, 'theySay')}</Label>
      <View style={s.row}>
        {orgs.slice(0, 16).map(o => (
          <Pressable key={o} onPress={() => { setOrg(o); setOther(''); }}
            style={{ paddingHorizontal: 12, paddingVertical: 10, borderRadius: 8, borderWidth: 1, borderColor: org === o && !other ? C.accent : C.line2, backgroundColor: org === o && !other ? C.panel2 : 'transparent' }}>
            <Text style={{ color: org === o && !other ? C.accent : C.text, fontWeight: '600' }}>{o}</Text>
          </Pressable>
        ))}
      </View>
      <Field value={other} onChangeText={setOther} placeholder="Other organisation…" />
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }}>
        <Switch value={sensitive} onValueChange={setSensitive} thumbColor={sensitive ? C.crit : C.muted} trackColor={{ true: '#5a1f2a', false: C.line2 }} />
        <Text style={{ color: C.text, flex: 1 }}>{t(L, 'askedSensitive')}</Text>
      </View>
      <Button title={t(L, 'verify')} onPress={verify} busy={busy} disabled={!number.trim() || !claimed} />
      {err ? <Card accent={C.crit}><Text style={{ color: C.crit }}>{err}</Text></Card> : null}
      {res ? (
        <VerdictCard verdict={verdict} title={`${res.number} · ${res.org}`} reasons={res.reasons} lang={L}>
          {res.decision === 'pass'
            ? <P style={{ color: C.ok, fontWeight: '700' }}>{verifiedOrg(L, res.org)}</P>
            : <P rtl={rtl} style={{ color: C.crit, fontWeight: '800', fontSize: 17 }}>{warnNotOrg(L, res.org)}</P>}
          {res.decision !== 'pass' ? (
            <View style={{ gap: 8 }}>
              {native.available ? <Button kind="danger" title={t(L, 'endCall')} onPress={() => native.endCall()} /> : null}
              <Button kind="ghost" title={t(L, 'report')} onPress={async () => { await api.report('number', res.number, res.org).catch(() => {}); router.back(); }} />
            </View>
          ) : null}
        </VerdictCard>
      ) : null}
    </Screen>
  );
}
