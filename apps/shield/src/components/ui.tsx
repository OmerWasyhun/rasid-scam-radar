// Small shared UI pieces for RASID Shield.
import { ReactNode } from 'react';
import { ActivityIndicator, Pressable, ScrollView, StyleSheet, Text, TextInput, TextInputProps, View, ViewStyle } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { C, verdictColor } from '@/lib/theme';
import { t } from '@/lib/i18n';

export function Screen({ children, scroll = true }: { children: ReactNode; scroll?: boolean }) {
  return (
    <SafeAreaView style={s.screen} edges={['top', 'left', 'right']}>
      {scroll ? <ScrollView contentContainerStyle={s.content} keyboardShouldPersistTaps="handled">{children}</ScrollView>
        : <View style={[s.content, { flex: 1 }]}>{children}</View>}
    </SafeAreaView>
  );
}

export function H1({ children, rtl }: { children: ReactNode; rtl?: boolean }) {
  return <Text style={[s.h1, rtl && s.rtl]}>{children}</Text>;
}
export function Label({ children }: { children: ReactNode }) {
  return <Text style={s.label}>{children}</Text>;
}
export function P({ children, muted, rtl, style }: { children: ReactNode; muted?: boolean; rtl?: boolean; style?: any }) {
  return <Text style={[s.p, muted && { color: C.muted }, rtl && s.rtl, style]}>{children}</Text>;
}

export function Card({ children, style, accent }: { children: ReactNode; style?: ViewStyle; accent?: string }) {
  return <View style={[s.card, accent ? { borderColor: accent } : null, style]}>{children}</View>;
}

export function Button({ title, onPress, kind = 'primary', disabled, busy }:
  { title: string; onPress: () => void; kind?: 'primary' | 'ghost' | 'danger'; disabled?: boolean; busy?: boolean }) {
  const bg = kind === 'primary' ? C.accent : kind === 'danger' ? C.crit : 'transparent';
  const fg = kind === 'ghost' ? C.text : '#04121c';
  return (
    <Pressable accessibilityRole="button" onPress={onPress} disabled={disabled || busy}
      style={({ pressed }) => [s.btn, { backgroundColor: bg, opacity: disabled ? 0.45 : pressed ? 0.85 : 1 },
        kind === 'ghost' && { borderWidth: 1, borderColor: C.line2 }]}>
      {busy ? <ActivityIndicator color={fg} /> : <Text style={[s.btnText, { color: fg }]}>{title}</Text>}
    </Pressable>
  );
}

export function Field(props: TextInputProps & { label?: string }) {
  return (
    <View style={{ gap: 6 }}>
      {props.label ? <Label>{props.label}</Label> : null}
      <TextInput placeholderTextColor={C.faint} {...props} style={[s.input, props.multiline && { minHeight: 110, textAlignVertical: 'top' }, props.style]} />
    </View>
  );
}

export function Pill({ text, color }: { text: string; color: string }) {
  return <View style={[s.pill, { borderColor: color }]}><Text style={[s.pillText, { color }]}>{text}</Text></View>;
}

export function VerdictCard({ verdict, score, title, reasons, lang, children }:
  { verdict: string; score?: number; title: string; reasons: string[]; lang: string; children?: ReactNode }) {
  const color = verdictColor(verdict);
  const label = t(lang, (`verdict_${verdict}`) as any) || verdict;
  return (
    <Card accent={color} style={{ gap: 10 }}>
      <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 8 }}>
        <Pill text={label.toUpperCase()} color={color} />
        {score !== undefined ? <Text style={[s.score, { color }]}>{score}<Text style={{ color: C.muted, fontSize: 13 }}>/100</Text></Text> : null}
      </View>
      <Text style={s.cardTitle} selectable>{title}</Text>
      {score !== undefined ? <View style={s.bar}><View style={{ width: `${Math.min(100, score)}%`, height: '100%', backgroundColor: color }} /></View> : null}
      {reasons.length ? <View style={{ gap: 6 }}>
        <Label>{t(lang, 'why')}</Label>
        {reasons.map((r, i) => <Text key={i} style={s.reason}>• {r}</Text>)}
      </View> : null}
      {children}
    </Card>
  );
}

export const s = StyleSheet.create({
  screen: { flex: 1, backgroundColor: C.ink },
  content: { padding: 16, gap: 14, paddingBottom: 40 },
  h1: { color: C.white, fontSize: 24, fontWeight: '700' },
  label: { color: C.muted, fontSize: 11, letterSpacing: 1.4, textTransform: 'uppercase', fontFamily: 'monospace' },
  p: { color: C.text, fontSize: 15, lineHeight: 22 },
  rtl: { writingDirection: 'rtl', textAlign: 'right' },
  card: { backgroundColor: C.panel, borderColor: C.line, borderWidth: 1, borderRadius: 14, padding: 14 },
  cardTitle: { color: C.white, fontSize: 16, fontWeight: '600' },
  btn: { borderRadius: 10, paddingVertical: 13, paddingHorizontal: 16, alignItems: 'center', justifyContent: 'center' },
  btnText: { fontWeight: '700', fontSize: 15 },
  input: { backgroundColor: C.panel2, borderColor: C.line2, borderWidth: 1, borderRadius: 10, color: C.text, padding: 12, fontSize: 15 },
  pill: { borderWidth: 1, borderRadius: 6, paddingHorizontal: 8, paddingVertical: 3, alignSelf: 'flex-start' },
  pillText: { fontSize: 11, fontWeight: '700', letterSpacing: 1, fontFamily: 'monospace' },
  score: { fontSize: 26, fontWeight: '700', fontFamily: 'monospace' },
  bar: { height: 6, borderRadius: 3, backgroundColor: C.line, overflow: 'hidden' },
  reason: { color: C.text, fontSize: 14, lineHeight: 20 },
  row: { flexDirection: 'row', gap: 10, flexWrap: 'wrap' },
});
