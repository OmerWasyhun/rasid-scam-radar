// Alerts: notification channels, spoken warnings, vibration, and the emergency screen.
import * as Haptics from 'expo-haptics';
import * as Notifications from 'expo-notifications';
import * as Speech from 'expo-speech';
import { router } from 'expo-router';
import { Platform, Vibration } from 'react-native';
import { speechCode } from './i18n';

Notifications.setNotificationHandler({
  handleNotification: async () => ({ shouldPlaySound: true, shouldSetBadge: false, shouldShowBanner: true, shouldShowList: true }),
});

export async function setupChannels() {
  if (Platform.OS !== 'android') return;
  await Notifications.setNotificationChannelAsync('alerts', {
    name: 'Scam warnings', importance: Notifications.AndroidImportance.HIGH, vibrationPattern: [0, 250, 150, 250],
  });
  await Notifications.setNotificationChannelAsync('emergency', {
    name: 'Emergency scam alerts', importance: Notifications.AndroidImportance.MAX, vibrationPattern: [0, 600, 200, 600, 200, 600],
    bypassDnd: true,
  });
}

export async function askNotificationPermission() {
  const cur = await Notifications.getPermissionsAsync();
  if (cur.granted) return true;
  const r = await Notifications.requestPermissionsAsync();
  return r.granted;
}

export async function notify(title: string, body: string, emergency = false, data: Record<string, any> = {}) {
  try {
    await Notifications.scheduleNotificationAsync({
      content: { title, body, data, sound: true, ...(Platform.OS === 'android' ? {} : {}) },
      trigger: Platform.OS === 'android' ? { channelId: emergency ? 'emergency' : 'alerts' } as any : null,
    });
  } catch {
    // notifications not permitted: the in-app screen still shows the warning
  }
}

export function speak(text: string, lang: string) {
  Speech.stop();
  Speech.speak(text, { language: speechCode(lang), rate: 0.95 });
}

export function emergency(params: { title: string; message: string; number?: string; org?: string; reasons?: string[] }) {
  Vibration.vibrate([0, 700, 250, 700, 250, 700]);
  Haptics.notificationAsync(Haptics.NotificationFeedbackType.Error).catch(() => {});
  router.push({ pathname: '/alert', params: { ...params, reasons: JSON.stringify(params.reasons ?? []) } });
}
