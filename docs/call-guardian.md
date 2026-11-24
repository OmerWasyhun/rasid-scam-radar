# RASID Call Guardian — the voice agent you add to a suspicious call

**Idea:** you are on a call and something feels wrong. You tap **Add call**, dial the RASID Guardian number and tap **Merge**. The Guardian joins as a third person, says it is listening, and then stays quiet. When the call shows scam signs it **speaks a warning into the call**, in Arabic and English, so both sides hear it. It also **texts you a summary**. After the call you can reply **REPORT** to send the case to Abu Dhabi Police.

It works on **any phone, Android or iPhone**, with no app to install, because it uses the phone's own conference call feature.

## Test it for free, on this computer (no Twilio, no keys, no money)

Your laptop plays the Guardian's part on the line. Put a real phone call on **speakerphone** next to the laptop. The laptop hears both people and speaks its warnings out loud, and the phone carries them to the caller. The agent, rules and warnings are the same ones the phone-number version uses. Only the "ears and mouth" change: the browser does speech-to-text and the voice instead of Twilio.

1. Start the server:
   ```powershell
   .venv\Scripts\python -m uvicorn rasid.api:app --port 8042
   ```
2. Open **http://localhost:8042/guardian** in **Microsoft Edge** (best: free Arabic voices) or Google Chrome.
3. **No phone needed first:** click a **sample call** (e.g. *Fake bank, OTP (Arabic)*). You'll see the call, hear the warning and get the SMS summary. Or type lines into the box at the bottom.
4. **Real test:** call a friend and ask them to play the scammer ("I'm from the bank, read me the code we sent you"). Put the call on speaker, choose the call's language, press **Start listening** and allow the microphone.
5. Say **"RASID"** or **"راصد"** to ask its opinion, and **"RASID leave"** or **"راصد اطلع"** (or press **Stop**) to end. After the call you'll see the SMS the person would get. **Report** files it in the police console at http://localhost:8042 under *Call Guardian*.

What is free and what isn't:
- **Free:** the server, the rules engine, the browser's speech recognition and voices. No account and no key needed.
- **Not offline:** Edge and Chrome send the microphone audio to their own free speech service (Microsoft or Google) to turn it into text, so you need internet. Nothing is stored by RASID.
- **Costs money, and is optional:** Claude. Leave `ANTHROPIC_API_KEY` empty and the Guardian runs on the rules only. The page shows "Analysis: rules only (free, offline)".
- **No Arabic voice?** Arabic warnings are still shown on screen. Edge includes Arabic voices; in Chrome, add an Arabic voice in Windows: Settings → Time & language → Speech.
- **Tips:** keep the phone 30–50 cm from the laptop, at a medium speaker volume. The laptop stops listening while RASID speaks, so it doesn't hear itself. The page works only on this computer (it refuses other devices).

## What happens on a call

```
You ── call ── Other party
 │  Add call + Merge
 ▼
Twilio number ──► /voice/join (TwiML) ──► ConversationRelay ──WebSocket──► /voice/listen
                  speech-to-text (Google, ar-AE / en-US)          │
                  text-to-speech (Amazon Polly Hala / Joanna) ◄────┤ warnings
                                                                   ├─ rules (instant, offline)
                                                                   ├─ Claude assessment (background)
                                                                   └─ SMS summary (Twilio REST)
```

| Moment | What the Guardian does |
|---|---|
| Joins | Says, in Arabic and English, that RASID is listening and nothing is recorded |
| Normal talk | Stays silent |
| Warning signs (risk ≥ 50) | Short caution: "don't share any code, card details or password" |
| Scam pattern (risk ≥ 80) | Full warning naming the scam and advising you to hang up, plus an immediate SMS |
| You say "RASID" / "راصد" | Tells you its current opinion |
| You say "RASID leave" / "راصد اطلع" | Leaves the call |
| Keypad 1 / 2 / 3 / 9 | Opinion / switch to English / switch to Arabic / leave (some carriers don't pass keypad tones in a conference; voice commands always work) |
| Call ends | Texts the verdict, the signs and how to report |
| You reply `REPORT 05xxxxxxxx` | Files a case in the police console (`Call Guardian` sensor) with the summary and the scammer's number |

**How it decides:** first, multilingual phrase rules: OTP and verification codes, card and PIN, AnyDesk or app installs, transfers and gift cards, Emirates ID and IBAN, secrecy, arrest threats, prizes, links, and claims to be a bank or the police. They work with no key and react instantly. Then Claude reads the whole call so far and gives a structured verdict with its own wording for the warning. Strong rule hits are never ignored.

**Privacy:** no audio is recorded. The transcript lives in memory only while the call lasts. After the call, only the verdict, the signs and a one-sentence summary are kept, for one hour, in case you reply REPORT. The Guardian always announces itself when it joins.

## Code

| File | What |
|---|---|
| `rasid/guardian.py` | The brain: rules, Claude assessment, warning wording, SMS text |
| `rasid/voice.py` | Twilio webhooks and the ConversationRelay WebSocket, SMS sending and REPORT replies, simulator API |
| `rasid/guardian_sim.py` | Plays sample calls through the brain in the terminal |
| `data/sample_calls.json` | Synthetic sample calls (Arabic and English, scam and normal) |
| `tests/test_guardian.py` | Offline tests, including a full fake Twilio call over the WebSocket |

## Try it without a phone

```powershell
.venv\Scripts\python -m rasid.guardian_sim
.venv\Scripts\python -m rasid.guardian_sim bank_otp_ar --rules
.venv\Scripts\python -m pytest -q tests
```

Or `POST /api/v1/guardian/simulate` with `{"lines": ["...", "..."], "lang": "ar-AE"}`.

## Go live — what I need from you

Fill these in `.env`, then follow the steps.

| Item | Your value | Where to get it |
|---|---|---|
| `ANTHROPIC_API_KEY` | `______________` | console.anthropic.com → API keys. Without it the Guardian runs on rules only |
| `TWILIO_ACCOUNT_SID` | `______________` | console.twilio.com → Account info |
| `TWILIO_AUTH_TOKEN` | `______________` | same page |
| `RASID_GUARDIAN_NUMBER` | `+______________` | Twilio → Phone Numbers → Buy a number with **Voice** and **SMS** |
| `RASID_GUARDIAN_SMS_FROM` | `______________` | Optional. SMS to UAE numbers may need a registered sender ID; leave empty to use the number |
| `PUBLIC_BASE_URL` | `https://______________` | Your tunnel or server address (step 2) |
| `RASID_GUARDIAN_ALLOWED` | `______________` | Optional: your team's phone numbers for the pilot, comma-separated |
| Demo phone numbers | `______________` | The phones you'll use for the demo (one plays the "scammer") |

1. **Run the server:** `.venv\Scripts\python -m uvicorn rasid.api:app --port 8042`
2. **Make it reachable:** `ngrok http 8042` (or `cloudflared tunnel --url http://localhost:8042`), then put the `https://` address in `PUBLIC_BASE_URL` and restart the server.
3. **Point the number at it** (Twilio console → the number → Configure):
   - *A call comes in* → Webhook, `POST`, `https://<PUBLIC_BASE_URL>/voice/join`
   - *A message comes in* → Webhook, `POST`, `https://<PUBLIC_BASE_URL>/voice/sms`
4. **Twilio account settings:** ConversationRelay needs the AI/ML features addendum accepted (Twilio console → Voice → Settings → Predictive and Generative AI/ML Features). On a trial account, verify the demo phones under *Verified Caller IDs*. Trial calls also play a Twilio notice first.
5. **Test:** call `RASID_GUARDIAN_NUMBER` directly and say *"I'm from the bank, read me the code we sent"*. You should hear the warning and get an SMS. Then try the real flow: start a call between two phones, Add call → Guardian number → Merge.
6. **Check:** `GET /api/v1/guardian/status` shows what is configured and how many calls are live.

## Things to know

- **Conference calling** must be supported by the caller's carrier plan. e& and du support it, and so do most VoLTE plans. On iPhone: *add call* → *merge calls*. On Android: *Add call* → *Merge*.
- **Calling a US Twilio number from the UAE** is an international call. For a real launch, use a UAE number or short code through e& or du, ideally a free short number such as *Aman*.
- **The speech recogniser** is set to Gulf Arabic (`ar-AE`) or English. Mixed Arabic and English calls are transcribed less well. Voices and recognisers are in `VOICES` in `rasid/voice.py`.
- **Latency:** rules react within a second of the phrase being transcribed. The Claude verdict takes a few seconds and runs in the background. To trade depth for speed, set `RASID_GUARDIAN_MODEL` to a faster model.
- **Legal:** the Guardian announces itself and records nothing. For a public service, have Abu Dhabi Police legal confirm the consent wording under UAE privacy law.
- **Scammers hear the warning.** That is intended: most hang up. The Guardian cannot hang up *your* line. On Android, a companion app could end the call when it gets the danger SMS or push; that's the next step.
