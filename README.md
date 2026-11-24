# RASID راصد — proactive scam radar

Built for the **ScamShield AI** hackathon (Abu Dhabi Police × 42 Abu Dhabi): *Detecting Fraudulent Links and Websites Used in Cybercrimes and Financial Fraud.*

Most tools wait for a victim to paste a suspicious link. RASID hunts first. An investigator names a brand, a government service or an event, and RASID finds the lookalike domains, newborn phishing sites, fake Google Maps listings, scam ads and search results, and job/visa scam posts in the languages the victims read. It groups sites that share a phishing kit into one actor and exports an evidence pack for takedown.

## Sensors

| Sensor | What it does | Needs |
|---|---|---|
| **Lookalike Radar** | Generates typos, Latin and Cyrillic homoglyphs (punycode), combosquats with lure words in transliterated languages (`naukri`, `trabaho`, `joli`), TLD swaps, subdomain tricks. Checks which exist. | nothing |
| **Newborn Domains** | Matches the daily newly-registered-domains list (~70k/day) and Certificate Transparency logs (crt.sh) against every watchlist. | nothing |
| **Analyser** (all web sensors) | Read-only fetch: card/CVV/OTP/Emirates ID fields, brand claims, multilingual lure text, cloaking (Googlebot vs UAE phone), Telegram exfil tokens, analytics IDs, favicon hash, DOM hash, RDAP age, hosting location. | nothing |
| **Kit Fingerprint** | Union-find clustering of flagged items on shared favicon hash, Telegram bot, analytics ID, phone/WhatsApp number, or two weak links (IP + NS + DOM). | nothing |
| **Maps Verifier** | Google Places listings for a brand in each emirate, checked against official domains and phones; flags mobile numbers on bank/telco listings and numbers reused across brands. | `GOOGLE_MAPS_API_KEY` |
| **Social & Search Ads** | Meta Ad Library (Facebook, Instagram, WhatsApp, Messenger, Threads) and Google Ads Transparency Center (UAE) for ads using a watched name from someone else; Google results from the UAE in several languages; paste-an-ad inspector with screenshot reading. | `META_ACCESS_TOKEN`, `SERPAPI_KEY`, `ANTHROPIC_API_KEY` (screenshots) |
| **Job & Visa Linguist** | Scores posts in Arabic, English, Hindi, Urdu, Roman Urdu, Malayalam, Tamil, Sinhala, Tagalog, Bengali, Nepali; reads public Telegram channels. Claude extracts employer, fee, salary and translation. | Claude optional |
| **Site inspection** | Every live lookalike is opened in RASID's own headless browser: screenshot, visual comparison with the official site, rendered-page checks for copied design, malicious links and code, network calls (e.g. to Telegram bots) and payment/data capture. A similar name alone never flags a site. Optional Claude screenshot scan; Google Safe Browsing and VirusTotal reputation. | none (`ANTHROPIC_API_KEY`, `GOOGLE_SAFE_BROWSING_KEY`, `VIRUSTOTAL_API_KEY` optional) |
| **Case notes & strike packs** | Claude writes the case note in Arabic and English; strike pack bundles evidence and pre-filled abuse letters. Nothing is sent automatically. | Claude optional (template fallback) |

## Call Guardian (voice agent)

A phone number you add to a call you're unsure about: tap **Add call**, dial the Guardian, tap **Merge**. It listens, warns aloud in Arabic and English when the call matches a scam (OTP, card, AnyDesk, transfers, fake police or bank), texts you a summary, and lets you reply **REPORT** to open a case in this console. It works on Android and iPhone with no app. Setup, the keys to fill in and the demo script are in [docs/call-guardian.md](docs/call-guardian.md). **Test it for free:** run the server and open http://localhost:8042/guardian in Edge. Put a real call on speakerphone next to the laptop, or play a sample call. No Twilio and no keys are needed.

## Call Guardian

The console has two tabs: **Fraud Hunt** (the six sensors) and **Call Guardian** (the voice agent that listens to a suspicious call and warns out loud; see `docs/call-guardian.md`). The Call Guardian tab keeps running while you use Fraud Hunt; a **● LIVE** badge shows it is listening. Calls reported from it appear in the console as the *Call Guardian* sensor.

## Run it

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python -m playwright install chromium   # RASID's own browser for screenshots
copy .env.example .env      # then fill in the keys you have
.venv\Scripts\python -m uvicorn rasid.api:app --port 8042
```

Open http://localhost:8042. Type an entity in the command bar (for example `Aramex`) and press **Hunt**. A hunt takes about 2–3 minutes; the first one also downloads three days of newly-registered domains.

## API keys

All keys go in `.env` (see `.env.example`). Every sensor without a key says so in the console instead of failing.

| Key | Used for |
|---|---|
| `ANTHROPIC_API_KEY` | Case notes (AR + EN), job-post extraction and translation, ad screenshot reading |
| `GOOGLE_MAPS_API_KEY` | Maps Verifier (enable **Places API (New)** in Google Cloud) |
| `SERPAPI_KEY` | Search & ads sweep |
| `META_ACCESS_TOKEN` | Meta Ad Library sweep (Facebook / Instagram ads) |
| `GOOGLE_SAFE_BROWSING_KEY` | Google's phishing/malware list check |
| `VIRUSTOTAL_API_KEY` | Security-vendor reputation of each domain |
| `RASID_PASSWORD` | Officer login for the console (off when empty) |

## Before the demo

- Fill each brand's **official phone numbers** in its watchlist (from the brand's own website), so the Maps Verifier can confirm genuine listings.
- Optionally add `data/licensed_agencies.txt` (one MOHRE-licensed agency name per line).
- `data/sample_job_posts.json` holds **synthetic** example posts for testing; label them as samples in the demo.

## Safety

Suspect sites are fetched with plain GET requests only: no JavaScript, no form submission, private/internal IPs refused, downloads capped. Takedown reports are drafts for an officer to review.

## Tests

```powershell
.venv\Scripts\python -m pytest -q tests
```

