"""Newly registered domains: the free daily list from whoisds.com (about 70k domains a day).

Downloaded once per day and cached under data/nrd/. Matching runs against every watchlist base label.
"""
import base64
import datetime as dt
import io
import zipfile

import httpx

from .config import DATA_DIR

NRD_DIR = DATA_DIR / "nrd"


def _url(day: dt.date) -> str:
    token = base64.b64encode(f"{day.isoformat()}.zip".encode()).decode()
    return f"https://www.whoisds.com/whois-database/newly-registered-domains/{token}/nrd"


def fetch_day(day: dt.date) -> list[str]:
    NRD_DIR.mkdir(parents=True, exist_ok=True)
    cache = NRD_DIR / f"{day.isoformat()}.txt"
    if cache.exists():
        return cache.read_text(encoding="utf-8").split()
    try:
        r = httpx.get(_url(day), timeout=60, follow_redirects=True)
        if r.status_code != 200 or not r.content.startswith(b"PK"):
            return []
        with zipfile.ZipFile(io.BytesIO(r.content)) as z:
            text = z.read(z.namelist()[0]).decode("utf-8", "ignore")
    except (httpx.HTTPError, zipfile.BadZipFile, KeyError, IndexError):
        return []
    cache.write_text(text, encoding="utf-8")
    return text.split()


def recent(days: int = 3) -> list[tuple[str, str]]:
    """[(domain, registered_day)] for the last `days` published lists."""
    out = []
    today = dt.datetime.utcnow().date()
    for i in range(1, days + 1):
        d = today - dt.timedelta(days=i)
        out += [(x.strip().lower(), d.isoformat()) for x in fetch_day(d) if x.strip()]
    return out
