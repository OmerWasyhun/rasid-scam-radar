import * as Clipboard from 'expo-clipboard';
import { useState } from 'react';
import { Text, View } from 'react-native';
import { Button, Card, Field, H1, P, Screen, VerdictCard, s } from '@/components/ui';
import { api, detectKind } from '@/lib/api';
import { notify, speak } from '@/lib/alerts';
import { isRTL, t, warnScam } from '@/lib/i18n';
import { useSettings } from '@/lib/settings-context';
import { addHistory } from '@/lib/store';
import { C } from '@/lib/theme';

type Result = { verdict: string; score?: number; title: string; reasons: string[]; kind: string; value: string; ticket?: string };

export default function Check() {
  const { settings } = useSettings();
  const L = settings.lang, rtl = isRTL(L);
  const [input, setInput] = useState('');
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');
  const [res, setRes] = useState<Result | null>(null);
  const [reported, setReported] = useState(false);

  async function run() {
    const value = input.trim();
    if (!value) return;
    setBusy(true); setErr(''); setRes(null); setReported(false);
    try {
      const kind = detectKind(value);
      let r: Result;
      if (kind === 'link') {
        const j: any = await api.checkLink(value);
        r = { kind, value, verdict: j.verdict, score: j.score, title: j.host, reasons: j.reasons ?? [], ticket: j.ticket };
        if (j.impersonates) r.reasons = [`Pretends to be ${j.impersonates}`, ...r.reasons];
      } else if (kind === 'number') {
        const j: any = await api.checkNumber(value);
        const reasons = j.verdict === 'official' ? [`Official number of ${j.org}`]
          : j.reports ? [`Reported by ${j.reports} ${j.reports === 1 ? 'person' : 'people'}`, ...Object.keys(j.claims ?? {}).map(o => `Pretended to be ${o}`)]
          : j.mobile ? ['Personal UAE mobile number. Banks and the police do not call from these.'] : ['No reports about this number yet'];
        r = { kind, value, verdict: j.verdict === 'unknown' ? 'unclear' : j.verdict, title: j.number, reasons };
      } else {
        const j: any = await api.checkMessage(value);
        r = { kind, value, verdict: j.verdict, score: j.score, title: value.slice(0, 80), reasons: j.reasons ?? [] };
      }
      setRes(r);
      await addHistory({ kind: r.kind as any, input: value, verdict: r.verdict, score: r.score, title: r.title, reasons: r.reasons });
      if (r.verdict === 'scam') {
        speak(warnScam(L), L);
        notify('RASID: scam detected', `${r.title}: ${warnScam(L)}`, false);
      }
      if (r.ticket) pollTicket(r.ticket, r);
    } catch (e: any) {
      setErr(e.message);
    } finally {
      setBusy(false);
    }
  }

  function pollTicket(id: string, base: Result, tries = 0) {
    setTimeout(async () => {
      try {
        const j: any = await api.ticket(id);
        if (j.status === 'running' && tries < 20) return pollTicket(id, base, tries + 1);
        if (j.result?.verdict) {
          const next = { ...base, verdict: j.result.verdict, score: j.result.score, reasons: j.result.reasons ?? [], ticket: undefined };
          setRes(next);
          await addHistory({ kind: 'link', input: base.value, verdict: next.verdict, score: next.score, title: next.title, reasons: next.reasons });
          if (next.verdict === 'scam' || next.verdict === 'suspicious') notify('RASID finished checking a link', `${next.title}: ${next.verdict}`, false);
        }
      } catch {}
    }, 4000);
  }

  async function doReport() {
    if (!res) return;
    try {
      await api.report(res.kind as any, res.value);
      setReported(true);
    } catch (e: any) { setErr(e.message); }
  }

  return (
    <Screen>
      <H1 rtl={rtl}>{t(L, 'checkSomething')}</H1>
      <P muted rtl={rtl}>{t(L, 'checkHint')}</P>
      <Field value={input} onChangeText={setInput} multiline placeholder="https://…   ·   +971 5x xxx xxxx   ·   message text" autoCapitalize="none" />
      <View style={s.row}>
        <View style={{ flex: 1 }}><Button kind="ghost" title={t(L, 'paste')} onPress={async () => setInput(await Clipboard.getStringAsync())} /></View>
        <View style={{ flex: 2 }}><Button title={busy ? t(L, 'checking') : t(L, 'checkNow')} onPress={run} busy={busy} disabled={!input.trim()} /></View>
      </View>
      {err ? <Card accent={C.crit}><Text style={{ color: C.crit }}>{err}</Text></Card> : null}
      {res ? (
        <VerdictCard verdict={res.verdict} score={res.score} title={res.title} reasons={res.reasons} lang={L}>
          {res.verdict === 'scam' || res.verdict === 'suspicious' ? <P rtl={rtl} style={{ color: C.crit, fontWeight: '700' }}>{warnScam(L)}</P> : null}
          {reported ? <P style={{ color: C.ok }}>{t(L, 'reported')}</P>
            : <Button kind="ghost" title={t(L, 'report')} onPress={doReport} />}
        </VerdictCard>
      ) : null}
    </Screen>
  );
}
