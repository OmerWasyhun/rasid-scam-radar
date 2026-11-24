"""Settings and API keys, read from the environment (.env is loaded if present)."""
import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

DATA_DIR = ROOT / "data"
DATA_DIR.mkdir(exist_ok=True)
DB_PATH = Path(os.getenv("RASID_DB", DATA_DIR / "rasid.db"))
PACK_DIR = DATA_DIR / "packs"
DEMO_SEED = os.getenv("RASID_DEMO_SEED", "0") == "1"  # hosted demo: start from demo/ when the disk is empty
LOW_MEMORY = os.getenv("RASID_LOW_MEMORY", "0") == "1"  # 512 MB hosting plans: leaner Chromium

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "").strip()
MODEL = os.getenv("RASID_MODEL", "claude-opus-5-5").strip() or "claude-opus-5-5"
GOOGLE_MAPS_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY", "").strip()
SERPAPI_KEY = os.getenv("SERPAPI_KEY", "").strip()
GOOGLE_SAFE_BROWSING_KEY = os.getenv("GOOGLE_SAFE_BROWSING_KEY", "").strip()
VIRUSTOTAL_API_KEY = os.getenv("VIRUSTOTAL_API_KEY", "").strip()
META_ACCESS_TOKEN = os.getenv("META_ACCESS_TOKEN", "").strip()
META_GRAPH_VERSION = os.getenv("META_GRAPH_VERSION", "v27.0").strip() or "v27.0"

# Console login: when set, officers must sign in with this password to use the console and API.
RASID_PASSWORD = os.getenv("RASID_PASSWORD", "").strip()
SESSION_SECRET = os.getenv("RASID_SESSION_SECRET", "").strip()

# Call Guardian listener (laptop listens to a speakerphone call)
GUARDIAN_MODEL = os.getenv("RASID_GUARDIAN_MODEL", "").strip() or MODEL
GUARDIAN_LANG = os.getenv("RASID_GUARDIAN_LANG", "ar-AE").strip() or "ar-AE"  # language heard first: ar-AE or en-US
# Hosted demo: let visitors use the listener from their own browser (needs HTTPS for the microphone)
GUARDIAN_REMOTE = os.getenv("RASID_GUARDIAN_REMOTE", "0") == "1"

CT_POLL = os.getenv("RASID_CT_POLL", "0") == "1"
CT_POLL_MINUTES = int(os.getenv("RASID_CT_POLL_MINUTES", "20") or 20)

# Network behaviour for fetching suspect pages: read-only GETs, never submit forms.
FETCH_TIMEOUT = 8.0
FETCH_MAX_BYTES = 1_500_000
DESKTOP_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)
MOBILE_UA = (
    "Mozilla/5.0 (Linux; Android 14; SM-S918B) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0 Mobile Safari/537.36"
)
BOT_UA = "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)"


def key_status() -> dict:
    """Which sensors are ready, for the console's status panel."""
    return {
        "claude": bool(ANTHROPIC_API_KEY),
        "google_maps": bool(GOOGLE_MAPS_API_KEY),
        "serpapi": bool(SERPAPI_KEY),
        "safe_browsing": bool(GOOGLE_SAFE_BROWSING_KEY),
        "virustotal": bool(VIRUSTOTAL_API_KEY),
        "meta_ads": bool(META_ACCESS_TOKEN),
        "login": bool(RASID_PASSWORD),
        "model": MODEL,
    }
