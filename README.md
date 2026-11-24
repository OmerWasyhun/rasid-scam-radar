# RASID راصد: the Call Guardian and scam radar for the UAE

Built for the **ScamShield AI Hackathon** (42 Abu Dhabi × Abu Dhabi Police), challenge: *Detecting Fraudulent Links and Websites Used in Cybercrimes and Financial Fraud.*

**Live demo:** https://rasid-scam-radar.onrender.com (open, no login) · **Team:** Omer Wasiyehun · Ibrahim Abulaban · Ahmed Ismail Bulbul

Walkthrough: https://omerwasyhun.github.io/rasid-scam-radar/presentation/ · Pitch deck: [RASID-ScamShield-pitch.pptx](RASID-ScamShield-pitch.pptx) ([PDF](RASID-ScamShield-pitch.pdf)) · Project description: [RASID-project-description.pdf](RASID-project-description.pdf)

## The problem

Scam sites in the UAE copy banks, TAMM, UAE PASS, traffic-fine payment, couriers, events (F1, National Day, Hajj and Umrah) and job agencies. They reach victims through new lookalike domains, paid ads, Google search results, fake Google Maps listings with fake helpline numbers, and posts written in the languages migrant workers read. Almost every one of them ends in a phone call that asks for the OTP, the card or a transfer. Most tools only react after a victim pastes a link or files a report. By then the site has done its damage and often moved to a new domain.

## Our solution

### Main feature: the Call Guardian

The scammer is on the line, and so is RASID. During a call you are unsure about, put the phone on **speakerphone** next to the laptop and press **Listen**. RASID hears both people, stays quiet while the call is normal, and **warns out loud in Arabic and English** the moment the scam script starts, so the scammer hears the warning too. One click then reports the call as a case in the police console.

- **What it catches:** OTP and verification codes, card number/CVV/PIN, Emirates ID and passport, transfers and gift cards, AnyDesk and remote access, secrecy and pressure, arrest and fine threats, prizes with fees, links by SMS, and fake bank, police or government identities. Reassurances such as "we will never ask for your PIN" are not counted.
- **How it decides:** 10 rule families score every sentence instantly and offline; with an `ANTHROPIC_API_KEY`, Claude also reads the whole call so far and writes the spoken warning. 50+ is a caution, 80+ a warning.
- **Tested:** on the 5 synthetic sample calls it gets 5/5 right: fake bank OTP (Arabic) 100, fake police fine + AnyDesk (English) 100, parcel link 50, a friend's call (Arabic) 0, a real bank reminder (English) 10.
- **Private and free:** no app, no phone number, no paid voice service. The browser does speech in and out; no audio is recorded and no transcript is kept.

Details: [docs/call-guardian.md](docs/call-guardian.md).

### Behind every call is a link: the scam radar

RASID hunts first. An officer names a brand, a government service or an event. RASID then:

1. **Predicts** the domains a scammer would register: typos, Arabic/Latin/Cyrillic homoglyphs (punycode), combosquats with lure words in transliterated languages, TLD swaps.
2. **Watches** where new threats appear first: the daily list of newly registered domains (~70k a day), Certificate Transparency logs, Google search and ads from the UAE, the Meta Ad Library, Google Maps listings, and public Telegram job channels.
3. **Visits every live suspect in its own browser**: screenshot, visual comparison with the official site, card/OTP/Emirates ID/password fields, Telegram-bot exfiltration, malicious links and code, payment requests (IBAN, crypto wallets), cloaking (Googlebot vs a UAE mobile phone), redirects and link shorteners.
4. **Scores with reasons.** Each flag has a 0–100 risk score and the list of reasons behind it. A similar name alone never flags a site: something on the page itself has to back it up. This keeps real banks, government sites and unrelated businesses from being flagged.
5. **Links scam sites into networks.** Sites sharing a favicon hash, Telegram bot, analytics ID, phone/WhatsApp number or hosting fingerprint are grouped into one *actor*.
6. **Exports evidence for takedown:** a strike pack with screenshots, WHOIS/RDAP, DNS, hosting location, timestamps, the reasons, and pre-filled abuse letters to the registrar and host. Claude writes the case note in Arabic and English. Nothing is sent automatically.

## Sensors

| Sensor | What it does | Needs |
|---|---|---|
| **Call Guardian** (main) | Speakerphone listener: live scam risk, spoken warnings in Arabic and English, one-click report. | Claude optional |
| **Lookalike Radar** | Generates typos, homoglyphs (punycode), combosquats with lure words (`naukri`, `trabaho`, `fine`, `tickets`…), TLD swaps and subdomain tricks for every watchlist; checks which exist. Watchlists come preloaded with UAE banks, TAMM, police, telcos, couriers, Salik, RTA, ICP, F1, National Day, DSF, Hajj/Umrah and recruiters; **+ Add** creates your own. | nothing |
| **Newborn Domains** | Matches the daily newly-registered-domains list and Certificate Transparency logs (crt.sh) against every watchlist. | nothing |
| **Maps Verifier** | Google Places listings for a brand in each emirate, checked against the official domains and phones; flags mobile numbers on bank/telco listings and numbers reused across brands. | `GOOGLE_MAPS_API_KEY` |
| **Social & Search Ads** | Meta Ad Library and Google Ads Transparency Center (UAE) for ads using a watched name from someone else; Google results from the UAE in several languages; paste-an-ad inspector with screenshot reading. | `SERPAPI_KEY`, `META_ACCESS_TOKEN`, `ANTHROPIC_API_KEY` (screenshots) |
| **Kit Fingerprint** | Union-find clustering of flagged sites on shared favicon hash, Telegram bot, analytics ID, phone/WhatsApp number, or two weak links (IP + NS + DOM hash). | nothing |
| **Job & Visa Linguist** | Scores job and visa posts in Arabic, English, Hindi, Urdu, Roman Urdu, Malayalam, Tamil, Sinhala, Tagalog, Bengali and Nepali; reads public Telegram channels. Claude extracts employer, fee, salary and a translation. | Claude optional |
| **Check a link** | Any link someone received: follows redirects and shorteners, opens the page in RASID's browser and scores it, including brand-agnostic checks (a known brand on a domain it does not own, a password form, free site builders). `POST /api/check` takes a list of links. | nothing |

## Technical choices

- **Python 3.11 + FastAPI** for the server and API; **SQLite** for cases, watchlists and jobs (one file, no setup).
- **Playwright (headless Chromium)** as RASID's own browser: renders each suspect page, takes the screenshots and records network requests. Private and internal addresses are refused and forms are never submitted.
- **Pillow** for visual comparison (perceptual hashes, colour histogram and layout blocks) between a suspect's screenshot and the official site's.
- **dnspython, RDAP, crt.sh, mmh3, BeautifulSoup** for DNS, registration data, certificate logs, favicon hashes and page analysis.
- **Claude (Anthropic API)**, optional: Arabic/English case notes, reading ad screenshots, job-post extraction and translation, screenshot scans, and live call analysis. Every Claude feature has a rules-only fallback, so RASID works with no keys at all.
- **Explainable scoring:** each signal adds or removes points and is shown to the officer. A content gate caps name-only matches at 35, below the 50 "flag" line. Lookalikes that redirect to the official site are treated as the brand's own defensive domains (score 0).
- **Browser speech recognition and synthesis** for the Call Guardian listener, so it needs no paid voice service.

### APIs and data sources

| Source | Used for | Key |
|---|---|---|
| whoisds.com newly registered domains (daily, free) | Newborn Domains | none |
| crt.sh Certificate Transparency | Newborn Domains, Lookalike Radar | none |
| rdap.org | Domain age, registrar, abuse contact | none |
| ip-api.com | Hosting location for the map | none |
| Google Places API (New) | Maps Verifier | `GOOGLE_MAPS_API_KEY` |
| SerpApi (Google search + Ads Transparency, UAE) | Social & Search Ads | `SERPAPI_KEY` |
| Meta Ad Library API | Social ads | `META_ACCESS_TOKEN` |
| Google Safe Browsing v4 | Reputation | `GOOGLE_SAFE_BROWSING_KEY` |
| VirusTotal v3 | Reputation | `VIRUSTOTAL_API_KEY` |
| Anthropic API (Claude) | Case notes, screenshots, extraction, call analysis | `ANTHROPIC_API_KEY` |
| Public Telegram channel previews (t.me/s) | Job & Visa Linguist | none |

Test data: `data/sample_job_posts.json` and `data/sample_calls.json` are **synthetic** examples, labelled as samples in the console.

## Build and run

Requirements: Windows, macOS or Linux with Python 3.11+ and Microsoft Edge or Google Chrome.

```powershell
git clone https://github.com/OmerWasyhun/rasid-scam-radar.git
cd rasid-scam-radar
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python -m playwright install chromium
copy .env.example .env
.venv\Scripts\python -m uvicorn rasid.api:app --port 8042
```

On macOS/Linux use `.venv/bin/python` and `cp .env.example .env`.

Open **http://localhost:8042**. Every key in `.env` is optional; a sensor without its key says so in the console instead of failing.

### Try it

- **Hunt:** type an entity in the command bar (for example `Aramex` or `TAMM`) and press **Hunt**. A hunt takes 2–3 minutes; the first one also downloads three days of newly registered domains.
- **Check a link:** open **Tools → Check a link**, paste any link, and get a case file with the score, reasons and screenshot. For a list of links:
  ```powershell
  curl.exe -X POST http://localhost:8042/api/check -H "Content-Type: application/json" -d "{\"urls\": [\"https://example.com\", \"bit.ly/xyz\"]}"
  ```
  Each result has `score` (0–100), `verdict` (`fraud` ≥ 50, `suspicious` 36–49, `clean` ≤ 35), `reasons` and the `case` id.
- **Evidence:** open a case and press **Strike pack** for the exportable takedown pack (JSON or printable HTML).
- **Call Guardian:** open the **Call Guardian** tab in Edge, put a call on speakerphone and press **Listen**, or press a sample call. See [docs/call-guardian.md](docs/call-guardian.md).

### Hosted demo

- **From a laptop:** install `cloudflared`, then run `deploy\live.ps1`. It serves an open demo of RASID on port 8045 behind a public HTTPS link, and visitors can use the Call Guardian from their own browser.
- **On Render (free plan):** `render.yaml` is a Blueprint for the `Dockerfile`. It starts from the demo cases and screenshots in `demo/`, runs Chromium in low-memory mode, and asks for the API keys in the Render dashboard.
- **On any other server:** build the `Dockerfile` and set the keys and `RASID_GUARDIAN_REMOTE=1` as environment variables.

### Tests

```powershell
.venv\Scripts\python -m pytest -q
```

## Safety and privacy

- Suspect pages are visited read-only: no forms submitted, downloads capped, private/internal IPs refused.
- Takedown letters are drafts for an officer to review and send.
- The Call Guardian runs in the user's own browser; by default only on the computer running RASID, and on the hosted demo (`RASID_GUARDIAN_REMOTE=1`) for any visitor. It records no audio and keeps no transcript, only the verdict and the red flags of a call that is reported.
- Keys stay in `.env`, which git ignores.

## Limitations (honest)

- Brand-agnostic link checks are tuned against impersonation with a login or payment form. Phishing kits that show nothing until a specific path, cookie or country is used can still look clean, and pages already taken down score as clean.
- Free API tiers limit volume: SerpApi searches, Google Places calls, VirusTotal lookups. The Meta Ad Library only returns political and issue ads outside the EU, so most commercial scam ads there are out of reach for now.
- The UAE has no public feed of newly registered `.ae` domains; `.ae` lookalikes are found by generation + DNS, not by registration date.
- The Call Guardian depends on the browser's speech recognition, which needs an internet connection and is weaker on noisy calls and mixed Arabic dialects. The officer must have the caller's consent.
- Visual comparison needs a screenshot of the official site; sites that block automated visitors can be saved once into `data/official_snapshots/`.

## Route to a police pilot

1. **Week 1–4:** run RASID on a police laptop or server with watchlists for the most impersonated UAE brands; analysts review the *Strike queue* daily.
2. **Month 2:** connect official sources: `.ae` registrations from TDRA, Aman reports as seeds, and takedown channels with registrars and hosts.
3. **Month 3+:** move SQLite to PostgreSQL and run the sensors on a schedule across several workers. The sensors are independent jobs, so they scale out without changing the scoring or the console.
