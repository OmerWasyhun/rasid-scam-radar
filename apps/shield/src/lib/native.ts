// Bridge to the RasidNative Android module (notification listener + call screening).
// In Expo Go the module doesn't exist, so every function degrades gracefully.
import { requireOptionalNativeModule } from 'expo';

type RasidNativeModule = {
  configure(server: string, deviceId: string, deviceToken: string, lang: string): void;
  setNumberCache(json: string): void;
  isNotificationAccessGranted(): boolean;
  openNotificationAccessSettings(): void;
  isCallScreeningRoleHeld(): boolean;
  requestCallScreeningRole(): Promise<boolean>;
  endCall(): boolean;
  lastIncomingNumber(): string | null;
};

const mod = requireOptionalNativeModule<RasidNativeModule>('RasidNative');

export const native = {
  available: !!mod,
  configure: (server: string, id: string, token: string, lang: string) => mod?.configure(server, id, token, lang),
  setNumberCache: (json: string) => mod?.setNumberCache(json),
  notificationAccess: () => (mod ? mod.isNotificationAccessGranted() : false),
  openNotificationAccess: () => mod?.openNotificationAccessSettings(),
  callScreening: () => (mod ? mod.isCallScreeningRoleHeld() : false),
  requestCallScreening: async () => (mod ? mod.requestCallScreeningRole() : false),
  endCall: () => (mod ? mod.endCall() : false),
  lastIncomingNumber: () => (mod ? mod.lastIncomingNumber() : null),
};
