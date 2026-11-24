import { DarkTheme, Stack, ThemeProvider } from 'expo-router';
import * as SplashScreen from 'expo-splash-screen';
import { StatusBar } from 'expo-status-bar';
import { useEffect } from 'react';
import { SettingsProvider } from '@/lib/settings-context';
import { setupChannels } from '@/lib/alerts';
import { C } from '@/lib/theme';

SplashScreen.preventAutoHideAsync();

const theme = { ...DarkTheme, colors: { ...DarkTheme.colors, background: C.ink, card: C.panel, text: C.text, border: C.line, primary: C.accent } };

export default function RootLayout() {
  useEffect(() => {
    setupChannels().catch(() => {});
    SplashScreen.hideAsync().catch(() => {});
  }, []);
  return (
    <SettingsProvider>
      <ThemeProvider value={theme}>
        <StatusBar style="light" />
        <Stack screenOptions={{ headerStyle: { backgroundColor: C.panel }, headerTintColor: C.text, contentStyle: { backgroundColor: C.ink } }}>
          <Stack.Screen name="(tabs)" options={{ headerShown: false }} />
          <Stack.Screen name="onboarding" options={{ headerShown: false }} />
          <Stack.Screen name="claim" options={{ title: 'Who is calling?', presentation: 'modal' }} />
          <Stack.Screen name="screener" options={{ title: 'Call screener' }} />
          <Stack.Screen name="alert" options={{ headerShown: false, presentation: 'fullScreenModal' }} />
        </Stack>
      </ThemeProvider>
    </SettingsProvider>
  );
}
