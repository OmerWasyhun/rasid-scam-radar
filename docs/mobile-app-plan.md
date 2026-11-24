# RASID Shield — mobile app plan (React Native + Expo)

The citizen side of RASID. The phone app watches what reaches the user (notifications, links, calls) and asks the RASID backend for a verdict. Every check and every report flows back into RASID, so one person's warning protects the next.

---

## 1. What phones allow (read this first)

Some parts of the idea work as described. Some do not on any phone sold today, so the plan routes around them.

| Feature | Android | iOS | Notes |
|---|---|---|---|
| Read incoming notifications (SMS, WhatsApp, Telegram, email apps) | **Yes**: `NotificationListenerService`, user grants it in Settings | **No**: no app can read other apps' notifications | Android 15 hides OTP-type content from listener apps, which is fine: we don't need OTPs. Don't use `READ_SMS`; Google Play only allows it for the default SMS app. |
| Check SMS from unknown senders | Covered by the listener | **Partly**: Message Filter extension (`ILMessageFilterExtension`) classifies SMS from unknown senders as junk; it can ask our server | iOS covers SMS only, not WhatsApp |
| Check a link or message the user shares | **Yes**: share target | **Yes**: Share extension | Works everywhere, so it's the universal fallback |
| Hold an incoming call and check the number before it rings | **Yes**: `CallScreeningService` (role `ROLE_CALL_SCREENING`, Android 10+). It can silence, reject or let the call ring, and show our verdict | **Partly**: Call Directory extension labels or blocks numbers from a list synced in advance. No live lookup (iOS 18 Live Caller ID Lookup exists, but needs an Apple-approved privacy server) | Android: the screening service must answer within a few seconds, so keep a local cache of known numbers. Third-party screening apps only see calls from numbers **not in contacts** (verify on device) |
| End the call from the app | **Usually**: `TelecomManager.endCall()` with `ANSWER_PHONE_CALLS` (deprecated since Android 10; verify on target devices) | **No** | Fallback: a full-screen "Hang up now" alert |
| **Listen to the call audio** (live agent) | **No**: apps can't capture call audio (system permission only), and since Android 10 other apps' microphones get silence during a call | **No** | The app can't listen, but RASID can if the call passes through RASID's own phone line. That's the **cloud call screener** in section 4.1, the main path for the live agent |
| Emergency (high-level) alert | **Yes**: full-screen intent plus a high-importance channel with alarm sound | **Partly**: "Critical alerts" that break Do Not Disturb need a special Apple entitlement; time-sensitive notifications work without it | |

**Recommendation:** build Android first; it's where almost all of this works. On iOS, ship sharing, SMS filtering and the synced caller-ID list.

**Expo setup:** this needs a **development build** (`expo-dev-client` + `npx expo prebuild`). It won't run in Expo Go, because the listener, call screening and iOS extensions are native code. Write them with the **Expo Modules API** (Kotlin/Swift), and add them to the manifest and Xcode project with **config plugins**. `@bacons/apple-targets` handles the iOS extensions.

---

## 2. Main flows

### A. Notification guard (Android)
1. `NotificationListenerService` receives each notification. Kotlin pulls out the app, sender, text, URLs and phone numbers. This runs in native code, so it keeps working when the JS app is asleep.
2. Quick local check: URLs and numbers already in the on-device cache get an answer instantly.
3. Otherwise it calls `POST /api/v1/check/message`. Personal text stays on the phone unless the message contains a link or a number, or a lure was detected.
4. A verdict of **scam** or **suspicious** posts our own notification in the user's language: "This message pretends to be from Aramex. The link was registered 2 days ago. Don't pay." Buttons: *Report*, *I trust it*, *Details*.
5. Every result is saved to the in-app history.

### B. Link check: found in RASID, or investigated on demand
1. The app sends the URL to `POST /api/v1/check/link`.
2. RASID looks up the domain among its cases. If it's **known**, it answers at once with the stored verdict.
3. If it's **unknown**, RASID runs a quick investigation of that one host, reusing the existing code: DNS, RDAP age, lookalike match against every watchlist, page analysis for card/OTP fields and cloaking, and kit fingerprints.
   - If the answer is ready within about 8 seconds, it comes back in the same response.
   - Otherwise the reply is "checking…" with a ticket, and the verdict arrives as a push notification.
4. The new case is stored, so the next person gets the answer instantly, and it appears on the police console.

### C. Incoming call guard
```
incoming call
  → CallScreeningService (Android) gets the number
  → local cache: official number? reported scam? (answer in under 50 ms)
  → not cached: GET /api/v1/check/number?prefix=<hash prefix>  (≈ 1–2 s budget)
  → verdict:
      OFFICIAL  (e.g. ADCB's own number)   → ring normally, label "ADCB (verified)"
      SCAM      (reported or linked actor) → silence or reject + notification "Blocked: reported scam number"
      UNKNOWN / normal 05x mobile          → ring normally, show "Unknown number — tap during the call if they say they're from a company"
```

### D. "Who is calling?" check during an answered call (realistic version of the live agent)
The app can't hear the call, but the user can tell it what the caller claims in one tap:
1. When an unknown-number call is answered, the app shows a sticky notification: **"Did they say they're from a company or the police? Tap to check."**
2. Tapping it opens a quick sheet with big buttons (ADCB, FAB, Emirates NBD, e&, du, Aramex, Police, TAMM…) and a search box. It also accepts voice from the user *after* they mute the call.
3. The app calls `POST /api/v1/verify/claim {number, claimed_org}`, which compares the number against that organisation's official numbers in RASID's registry.
4. **The number doesn't belong to that organisation:**
   - **Level 1 (scam warning):** vibration plus a full-screen card: "This is NOT an ADCB number. ADCB will never ask for your OTP or card PIN. Hang up." Buttons: **End call** (Android, where `endCall` works) and **Report**.
   - **Level 2 (emergency alert):** used when the claim is police, a bank asking for an OTP, or the number is a known scam. Alarm sound, full-screen alert, and an optional SMS or push to a **trusted contact** the user chose in Settings ("Your father may be on a scam call").
5. The number is saved with the claim ("pretended to be ADCB"). This adds a report to RASID's number history so the next person's phone blocks it before it rings.

---

## 3. Number history: protecting other people

- **Table `numbers`:** E.164 number, status (`official`, `reported`, `scam`, `cleared`), owning org if official, number of distinct reporters, claims made ("pretended to be ADCB" ×14), first/last seen, linked RASID actor, and the source (report, Maps listing, job post, scam page).
- **Status rules** (so one angry user can't brand a number as scam):
  - `reported` after 1 report.
  - `scam` after **3 or more distinct devices** report it, or a claim/registry mismatch is confirmed, or it's linked to a flagged RASID actor.
  - An analyst can confirm or clear a number on the police console.
  - Official numbers can never be marked scam.
- **Privacy-preserving lookup** (k-anonymity, as Have I Been Pwned does): the phone sends only the first 5 hex characters of `SHA-256(number)`. The server returns every matching hash with its verdict, and the phone matches locally. RASID never learns who called whom.
- **Offline cache:** the app syncs a compact list of scam-number hashes plus all official org numbers every few hours. Call screening answers from it instantly.
- **Official phone registry** is the foundation for flows C and D. Collect each bank's, telco's and government body's published numbers (600/800 numbers and landlines) from their own websites, and add them to the RASID watchlists. Without it, the claim check can't decide anything.

---

## 4. The live call agent: three options

| Option | How | Pros | Cons |
|---|---|---|---|
| **1. One-tap claim check** (flow D) | The user taps what the caller claims; the number is checked against the registry | Works today on Android, partly on iOS; no recording, so no consent problems | Not automatic |
| **2. AI call screener in the cloud** | Unknown calls are forwarded by conditional call forwarding to a RASID line (e.g. Twilio Voice). An AI receptionist answers: "This call is screened by RASID. Who are you and why are you calling?" Speech-to-text runs, Claude reads the claim ("I'm from ADCB") and checks the number against the registry, then the call is put through to the user with a verdict, or rejected | A truly automatic agent, works on any phone | Needs carrier forwarding setup, telephony costs and **legal approval** (UAE law restricts recording calls without consent; the screener must announce itself). Best done as an Abu Dhabi Police service with e&/du |
| **3. In-app calls** | Calls made through the app's own VoIP (WebRTC). The app owns the audio, so the agent can transcribe live | Full live analysis | Only covers calls made through RASID, not normal phone calls |

**Decision:** option 2, the cloud call screener, is the **main path** for the live agent. It's the only option where an agent really hears and talks to the caller, on any phone. Option 1 stays in the app as the fallback for calls that don't pass through the screener.

### 4.1 Cloud call screener: the agent answers, investigates, then connects or blocks

```
Caller dials the user
   │  carrier forwards the call (see "Routing" below)
   ▼
RASID screener number (Twilio Voice)
   │
   ├─ Caller is in the user's contacts (synced as hashes), or is a verified official number
   │      → connect to the user right away
   │
   └─ Unknown number → the AI agent answers in the caller's language:
        "This call is screened by RASID for the person you're calling and may be recorded.
         Please say your name, your organisation, and why you're calling."
        • Live speech-to-text (Arabic, English, Hindi, Urdu, Malayalam, Tagalog…)
        • Claude reads the conversation and fills in: caller name, claimed org, purpose, requests (OTP, card, transfer, ID)
        • Checks: the number against the claimed org's official numbers; the number in RASID's history and actors;
          the request against red flags (no bank asks for an OTP or PIN by phone)
        • Asks up to 2 follow-up questions ("Which branch?", "What is the reference number?")
        │
        ├─ PASS    → "Please hold, connecting you." The call goes through to the user;
        │            the app shows "Screened: Ahmed, ADCB, verified number ✓"
        ├─ UNSURE  → "They're unavailable. I'll pass on your message." The app shows the transcript and summary;
        │            the user taps Call back / Report / Ignore
        └─ SCAM    → "This call can't be connected." The call ends; the app fires the emergency alert
                     (level 2 if they claimed to be police or a bank and asked for an OTP, card or money);
                     the number and claim are saved to RASID's history, and other phones now block it
```

If the caller hangs up as soon as the agent introduces itself, that's logged as a signal too ("hung up when screened"). Scammers do this often.

**Routing (avoiding the call loop).** If the user forwards *all* calls to RASID, then when RASID connects the call back to the user's number, the carrier forwards it to RASID again. So:
- **Main setup: forward only when busy or declined.**
  - **Android:** the app's call screening silently rejects unknown numbers; the carrier's "forward when busy" sends them to RASID. Contacts and official numbers ring normally. The connected call comes from RASID's number, which the app always lets through and labels.
  - **iPhone:** unknown calls ring as usual; the user declines them and they forward to RASID. The synced caller-ID list labels them "Unknown: decline to screen".
  - The app's onboarding sets this up with the carrier code for "forward when busy" (for example `**67*<RASID number>#` on GSM networks; confirm the codes with e& and du).
- **Alternative: deliver the screened call inside the app** as an internet call (Twilio Voice SDK with ConnectionService on Android and CallKit on iOS). It never goes back through the phone number, so forwarding everything is safe. Needs a VoIP push setup.

**Original caller number.** The registry check needs the real caller's number, not the user's. When a call is forwarded, Twilio usually passes the original number as `From` and the user's number as `ForwardedFrom`. **Test this with e& and du SIMs early**, because it depends on the carrier.

**Components (inside RASID, FastAPI):**

| Piece | What it does |
|---|---|
| `POST /voice/incoming` | Twilio webhook for each call. Looks up the user by `ForwardedFrom`, applies the contacts/official fast path, otherwise starts the agent through Twilio **ConversationRelay** (built-in speech-to-text and text-to-speech, conversation sent to our WebSocket) |
| `WS /voice/relay` | The agent loop: caller speech comes in as text; Claude, with tools, replies in about 1 second per turn. Tools: `lookup_number`, `official_numbers(org)`, `number_history`, `decide(pass / unsure / scam, reason)` |
| `POST /voice/status` | End-of-call webhook: stores the transcript, decision and duration on a new `calls` case, then sends the push to the user's app |
| `calls` sensor on the console | A new map layer and case type: screened calls with transcript, claimed org, verdict and linked numbers/actors |
| App screen `screened.tsx` | List of screened calls with transcript, verdict, call back, report and trust buttons |

**Agent rules:**
- Always disclose screening and possible recording at the start.
- Never ask the caller for personal data about the user, and never reveal anything about the user.
- Cap screening at about 60 seconds.
- Fail safe: if speech-to-text or Claude is down, take a message instead of guessing.

**Language:** the agent opens in Arabic and English, then switches to the caller's language once it's detected. The text-to-speech voice is chosen per language.

**Rules and rollout:**
- The disclosure line is mandatory. Get the recording/retention policy reviewed with Abu Dhabi Police legal.
- Keep transcripts and delete audio after analysis, unless the case goes to a takedown or investigation.
- Forwarding to a foreign Twilio number costs the user international rates. A real launch needs a **local UAE number through e& or du**, which fits the police partnership. Any Twilio number is fine for the hackathon.

---

## 5. Backend additions to RASID (FastAPI)

| Endpoint | Purpose |
|---|---|
| `POST /api/v1/devices` | Register a device: language, Expo push token, platform. Returns a device token |
| `POST /api/v1/check/link` | Known verdict, or quick investigation of one host (synchronous up to ~8 s, then by push) |
| `POST /api/v1/check/message` | Extract URLs and numbers, detect language and lures (existing `lexicon.py`), check links and numbers |
| `GET /api/v1/check/number?prefix=abcde` | k-anonymity number lookup |
| `GET /api/v1/sync/numbers?since=` | Incremental sync of official numbers and scam hashes for the offline cache |
| `POST /api/v1/verify/claim` | `{number, claimed_org}` → match / mismatch / org unknown, with advice text in the user's language |
| `POST /api/v1/report` | Report a number, link or message, with optional claim and note |
| `GET /api/v1/tickets/{id}` | Status of an on-demand investigation |

Reuse `generator.similarity`, `analyzer.analyze`, `hunters.*`, `lexicon.*` and `cluster.recluster` as they are. New pieces:
- A `numbers` table and phone registry.
- A `quick_investigate(host)` that skips lookalike generation.
- Expo push sending.
- Rate limits per device.
- Abuse protection: Play Integrity / App Attest tokens, and report weighting.

The police console gains a **Numbers** layer: reported numbers, the organisations they pretend to be, and links to actors already found by the other sensors. The same WhatsApp number on a fake Maps listing and in a job post now also shows up in citizen reports.

---

## 6. App structure (Expo)

```
apps/shield/
  app/                      expo-router screens
    (onboarding)/           welcome, language, permissions (with clear disclosure), call-screening role
    index.tsx               shield status + latest alerts
    check.tsx               paste or share: link / message / number
    calls.tsx               call log with verdicts, "report this number"
    alerts.tsx              history of everything checked
    claim.tsx               "who is calling?" sheet (flow D)
    settings.tsx            language, trusted contact, alert level, data & privacy
  modules/
    rasid-notifications/    Kotlin NotificationListenerService + Expo module + config plugin
    rasid-calls/            Kotlin CallScreeningService, endCall, call-state listener
    rasid-ios-extensions/   Call Directory, Message Filter, Share extension (via @bacons/apple-targets)
  src/
    api/                    typed client for /api/v1 (TanStack Query)
    cache/                  MMKV: official numbers, scam hashes, recent verdicts
    i18n/                   i18next: AR, EN, HI, UR, ML, TA, SI, TL, BN, NE, RU, ZH (RTL for AR/UR)
    alerts/                 notification channels, full-screen alert, expo-speech spoken warning
```

**Libraries:** `expo-router`, `expo-notifications`, `expo-dev-client`, `expo-localization`, `expo-speech` (warnings read aloud in the user's language), `expo-haptics`, `expo-secure-store`, `react-native-mmkv`, `@tanstack/react-query`, `i18next`.

**Language:** the app asks for the user's language at onboarding and writes every warning in it. Detection of the message's language comes from RASID, so a Malayalam scam SMS gets a Malayalam warning even if the phone is set to English.

---

## 7. Build order

**Hackathon slice (Android, about 10 hours with 2 people):**
1. Backend: `check/link`, `check/message`, `check/number`, `verify/claim`, `report`, numbers table, phone registry for 6 brands.
2. App shell: onboarding, language, check screen (paste/share), alerts history.
3. `rasid-notifications` module: listener → API → our warning notification.
4. `rasid-calls` module: screening with local cache → silence/label; "who is calling?" sheet with levels 1/2 and end call.
5. **Cloud call screener** (about 5 more hours; one person in parallel with steps 2–4):
   - Twilio number, `/voice/incoming`, ConversationRelay, `WS /voice/relay` agent with Claude and the 4 tools.
   - Connect / take a message / block, end-of-call webhook, push to the app, `screened.tsx`.
   - Rehearse with real UAE SIMs: check that the original caller number arrives after forwarding.
6. Demo script:
   - A scam SMS arrives on the phone → warning appears in Malayalam.
   - A reported number calls → screened as scam before it rings.
   - **A judge calls the RASID screener and says "I'm from ADCB, I need your card details."** The agent talks to them, catches the claim, finds the number isn't ADCB's, and ends the call. The demo phone fires the emergency alert with the transcript, and the number is saved.
   - **A number from the official registry calls** → the agent connects it straight through, labelled "verified".
   - A second phone receives a call from the scam number → it's now blocked before it rings.
   - Fallback if the venue network fails: an unknown 05x number calls and "says ADCB" → one-tap check → "NOT an ADCB number".

**After the hackathon:**
- iOS extensions.
- k-anonymity lookup and offline sync hardening.
- Play Integrity / App Attest.
- Trusted-contact alerts.
- Cloud screener rollout: a local UAE number with e& and du, carrier-side forwarding for opted-in users, and an in-app VoIP delivery option.
- Play Store policy declarations for notification access and call screening.

---

## 8. Keys and setup needed

These are in addition to the RASID keys (`ANTHROPIC_API_KEY`, `GOOGLE_MAPS_API_KEY`, `SERPAPI_KEY`). All go in `.env`, never in the app.

| Key / setup | Used for |
|---|---|
| `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN` | Cloud call screener |
| `TWILIO_SCREENER_NUMBER` | The number calls are forwarded to |
| `PUBLIC_BASE_URL` | A public HTTPS address of the RASID server for Twilio webhooks (ngrok for the demo, a cloud host later) |
| Expo account + EAS project ID | Development builds and push notifications |
| Two test phones with e& / du SIMs | Testing call forwarding and that the original caller number arrives |

Speech-to-text and text-to-speech are included in Twilio ConversationRelay, so no separate keys are needed for the first version.

## 9. Risks and approvals

- **Google Play review:** notification access and call screening need a prominent in-app disclosure and a clear core purpose. Scam protection qualifies, but plan for review time.
- **Privacy:** message text is processed on the phone first; only links, numbers and flagged lure text go to RASID. Number lookups use hash prefixes. State this in onboarding.
- **False positives:** never auto-block a number on one report. Official numbers always win. Users can mark "I trust this".
- **Legal:** the cloud screener records and analyses calls, so it needs legal review with Abu Dhabi Police and a spoken notice at the start of every screened call.
- **Carrier behaviour:** forwarding codes and whether the original caller number survives forwarding vary by carrier. Test both on day one, because the screener's number check depends on them. Reporting and blocking numbers is fine, but publishing them should stay inside the police system, not a public list.
