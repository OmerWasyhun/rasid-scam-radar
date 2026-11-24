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
| **Ads & Search** | Google results and sponsored ads from the UAE for lure queries in several languages; paste-an-ad inspector with screenshot reading. | `SERPAPI_KEY` (sweep), `ANTHROPIC_API_KEY` (screenshots) |
| **Job & Visa Linguist** | Scores posts in Arabic, English, Hindi, Urdu, Roman Urdu, Malayalam, Tamil, Sinhala, Tagalog, Bengali, Nepali; reads public Telegram channels. Claude extracts employer, fee, salary and translation. | Claude optional |
| **Case notes & strike packs** | Claude writes the case note in Arabic and English; strike pack bundles evidence and pre-filled abuse letters. Nothing is sent automatically. | Claude optional (template fallback) |

## Run it

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
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
| `URLSCAN_API_KEY`, `GOOGLE_SAFE_BROWSING_KEY` | Optional enrichment (reserved) |

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

