# Call Guardian: a speakerphone listener for scam calls

The Call Guardian is a tab in the RASID console. During a phone call you are unsure about, put the call on
**speakerphone** next to the laptop and press **Listen**. RASID hears both people, stays quiet while the call is normal,
and **warns out loud** in Arabic or English when it hears scam signs. Because the phone is on speaker, the caller
hears the warning too. After the call, a likely scam goes into the police console with one click.

No phone number, app or paid voice service is needed. No audio is recorded and no transcript is kept.

## Use it

1. Run the server (see the README) and open **http://localhost:8042/#guardian** in **Microsoft Edge** (it has free
   Arabic voices) or Google Chrome. The listener works on the computer running RASID, or from any browser on the
   hosted demo (https://rasid-scam-radar.onrender.com/#guardian, where `RASID_GUARDIAN_REMOTE=1`).
2. Choose the call language (العربية or English), press **Listen** and allow the microphone.
3. Talk normally. The risk meter and the red flags update live.
4. Say **"RASID"** / **"راصد"** (or press **Ask RASID**) to hear its opinion; say **"RASID leave"** / **"راصد اطلع"** or
   press **Stop** to end.
5. If the call was a scam, add the caller's number (optional) and press **Report**. The case appears in the
   console under the *Call Guardian* sensor.

No microphone? Type the caller's lines into the box, or press one of the **sample calls** (synthetic: fake bank OTP,
fake police fine, parcel link, and two normal calls).

## How it decides

```
speakerphone ─► browser speech-to-text ─► WS /voice/listen ─► rules (instant, offline)
                                                           └► Claude (optional, a few seconds)
browser speaks ◄── warning in AR / EN ◄── risk ≥ 50 caution, ≥ 80 warning
```

- **Rules** (`rasid/guardian.py`): multilingual phrases for one-time codes, card numbers, CVV and PINs, transfers and
  gift cards, AnyDesk/TeamViewer, secrecy and pressure, threats of arrest or fines, prizes with fees, and
  official-sounding identities. Reassurances like "we will never ask for your PIN" are not counted.
- **Claude** (when `ANTHROPIC_API_KEY` is set) reads the whole call so far and returns a risk, the scam type, the red
  flags and a short spoken warning. The transcript is treated as evidence only; a caller telling "the AI" that the
  call is safe is itself a red flag.
- Each warning level is spoken once, so the listener does not keep interrupting.

## Files

| File | Role |
|---|---|
| `rasid/guardian.py` | Rules, Claude assessment, warning wording, summary |
| `rasid/voice.py` | Listener session (WebSocket), report and sample endpoints, simulator API |
| `web/guardian.js`, `web/guardian.css` | The Call Guardian tab: speech in, speech out, live risk |
| `data/sample_calls.json` | Synthetic sample calls |
| `tests/test_guardian.py` | Offline tests of the rules and a full listener session |

Run a typed call through the same rules: `POST /api/v1/guardian/simulate` with
`{"lines": ["...", "..."], "lang": "ar-AE"}`.

## Limits

- Speech recognition comes from the browser and needs an internet connection. It is weaker on noisy calls and on
  mixed dialects.
- UAE law requires the other party's consent to have a call heard by a third party. Use it on your own calls with
  people who agree, or with test calls.
