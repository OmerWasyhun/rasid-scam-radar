# RASID Root Guardian — ends scam calls on a rooted Android phone

**What it does:** while you are on a normal phone call, RASID listens to the call audio, and if it hears a scam
(asks for an OTP, card details, claims to be your bank or the police, threatens you…) it **ends the call by itself**
and shows a notification: *"🚨 RASID ended a scam call"* with the reasons in English and Arabic. The case appears in
the police console under **Call Guardian**. It does not speak into the call.

```
 rooted phone (system app)          laptop: RASID server
 ┌──────────────────────┐  audio   ┌───────────────────────────────────┐
 │ call starts           │ ───────▶ │ Whisper (local, free) → text      │
 │ VOICE_CALL capture    │          │ Guardian scam rules (+ Claude)    │
 │ ends call ◀───────────┼───────── │ "likely scam" → hangup command    │
 │ notification          │ hangup   │ case filed in the console         │
 └──────────────────────┘          └───────────────────────────────────┘
```

Audio is never stored: it is transcribed in memory and dropped. Only the verdict and red flags are kept.

## Requirements

- An Android phone **rooted with Magisk** (v20.4+), Android 10 or newer.
- The laptop running RASID, on the **same Wi-Fi** as the phone.
- **Consent:** UAE law forbids recording calls without consent. Test only with team members who agree.
- Whether call audio can be captured depends on the phone's chipset. Some phones give only your own voice or silence; test on the exact phone you will demo with.

## Setup

1. **Server** (laptop):
   ```powershell
   .venv\Scripts\python -m uvicorn rasid.api:app --host 0.0.0.0 --port 8042
   ```
   The phone key is `RASID_PHONE_KEY` in `.env`. Allow Python through the Windows firewall if asked.
2. **Make the Magisk module** from the APK built on EAS:
   ```powershell
   .venv\Scripts\python tools\make_magisk_module.py rasid-guardian.apk
   ```
3. **Install on the phone:** uninstall any normal copy of *RASID Guardian* first. Copy `rasid-guardian-magisk.zip` to the phone → Magisk → Modules → Install from storage → pick the zip → **Reboot**.
4. **Open RASID Guardian:**
   - All checks should be green: root, system app, call audio access, permissions (tap **Grant permissions**).
   - Enter the server address `http://<laptop IP>:8042` and the phone key → **Save and test connection**.
   - Tap **Arm Guardian**. A "RASID Guardian · Armed" notification stays visible.
5. **Test:** a teammate calls you and plays the scammer ("I'm from your bank, read me the OTP code"). Within a few
   seconds of the scam signs, the call ends and the notification appears. A normal call is left alone.

## Tuning

- `RASID_WHISPER_MODEL` in `.env`: `small` (default, good Arabic and English on a laptop CPU), `base` (faster, weaker Arabic), `medium` (better, slower).
- The Guardian hangs up at the rules' "likely scam" level (risk ≥ the DANGER threshold in `rasid/guardian.py`). With `ANTHROPIC_API_KEY` set, Claude also judges each part of the call.

## If something doesn't work

| Check in the app | Fix |
|---|---|
| Not a system app / no call audio access | The Magisk module isn't active: flash it again and reboot; make sure no normal copy of the app is installed |
| "Couldn't capture call audio" during a call | This phone's audio driver doesn't expose call audio to apps, even with root; try another phone |
| "RASID server not reachable" | Same Wi-Fi? Firewall? Address must be the laptop's Wi-Fi IP, with `:8042` |
| Call not ended | Grant "Phone" permissions; the app falls back to a root key press to end the call |
