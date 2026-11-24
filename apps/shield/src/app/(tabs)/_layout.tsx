import { Redirect } from 'expo-router';
import { Tabs } from 'expo-router/tabs';
import { ColorValue, Text } from 'react-native';
import { useSettings } from '@/lib/settings-context';
import { t } from '@/lib/i18n';
import { C } from '@/lib/theme';

const glyph = (g: string) => ({ color }: { color: ColorValue }) => <Text style={{ color, fontSize: 18, fontWeight: '700' }}>{g}</Text>;

export default function TabsLayout() {
  const { settings, ready } = useSettings();
  if (ready && !settings.onboarded) return <Redirect href="/onboarding" />;
  const L = settings.lang;
  return (
    <Tabs screenOptions={{
      headerShown: false,
      tabBarStyle: { backgroundColor: C.panel, borderTopColor: C.line },
      tabBarActiveTintColor: C.accent, tabBarInactiveTintColor: C.muted,
    }}>
      <Tabs.Screen name="index" options={{ title: t(L, 'home'), tabBarIcon: glyph('◉') }} />
      <Tabs.Screen name="check" options={{ title: t(L, 'check'), tabBarIcon: glyph('⌕') }} />
      <Tabs.Screen name="calls" options={{ title: t(L, 'calls'), tabBarIcon: glyph('☏') }} />
      <Tabs.Screen name="history" options={{ title: t(L, 'history'), tabBarIcon: glyph('≡') }} />
      <Tabs.Screen name="settings" options={{ title: t(L, 'settings'), tabBarIcon: glyph('⚙') }} />
    </Tabs>
  );
}
