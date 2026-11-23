"""Job & Visa Linguist: scores job/visa posts in any of the UAE's main languages.

Sources: text pasted by an analyst, public Telegram channels (t.me/s/<name> web preview, no key needed),
and data/sample_job_posts.json (synthetic examples for testing and the demo).
"""
import hashlib
import json
import re

import httpx
from bs4 import BeautifulSoup

from .. import cluster, db, llm
from ..config import DATA_DIR, DESKTOP_UA
from ..lexicon import GMAIL, JOB_WORDS, LOW_WAGE_ROLES, SALARY, detect_langs, lure_hits, normalize
from .maps import norm_phone

ORIGIN = {  # victim's home city by language, for the corridor arc on the map
    "ML": (9.93, 76.27, "Kochi"), "TA": (13.08, 80.27, "Chennai"), "HI": (28.61, 77.21, "Delhi"),
    "UR": (31.55, 74.35, "Lahore"), "UR-L": (24.86, 67.0, "Karachi"), "BN": (23.81, 90.41, "Dhaka"),
    "NE": (27.71, 85.32, "Kathmandu"), "SI": (6.93, 79.86, "Colombo"), "TL": (14.6, 120.98, "Manila"),
    "PS": (34.01, 71.58, "Peshawar"), "AR": (30.04, 31.24, "Cairo"), "EN": (19.08, 72.88, "Mumbai"),
}
PHONE_ANY = re.compile(r"(?:\+|00)?\d[\d\s-]{8,15}\d")


def licensed_agencies() -> set[str]:
    """Optional list the team fills from MOHRE's published licensed agencies: data/licensed_agencies.txt, one name per line."""
    p = DATA_DIR / "licensed_agencies.txt"
    if not p.exists():
        return set()
    return {l.strip().lower() for l in p.read_text(encoding="utf-8").splitlines() if l.strip()}


def score_post(text: str) -> tuple[int, list, dict]:
    t = normalize(text)
    sig, info = [], {"langs": detect_langs(text)}
    hits = lure_hits(t)
    themes = {h["theme"] for h in hits}
    is_job = bool(JOB_WORDS.search(t))
    if is_job:
        sig.append({"text": "Job or recruitment offer", "points": 5})
    weights = {"fee for visa or job": 30, "free visa": 20, "visit visa for work": 25, "no interview / no experience": 10,
               "WhatsApp-only contact": 10, "urgency": 5, "payment request": 10}
    for h in hits:
        if h["theme"] in weights:
            sig.append({"text": f"{h['theme'].capitalize()}: “{h['match']}”", "points": weights[h["theme"]]})
    if "fee for visa or job" in themes:
        sig.append({"text": "UAE law puts recruitment costs on the employer, not the worker", "points": 5})
    if GMAIL.search(t):
        sig.append({"text": "Free email address instead of a company domain", "points": 10})
    sal = [int(s.replace(",", "")) for s in SALARY.findall(t)]
    if sal and LOW_WAGE_ROLES.search(t) and max(sal) >= 6000:
        sig.append({"text": f"Salary AED {max(sal):,} is far above the market for this role", "points": 15})
    lic = licensed_agencies()
    if lic and is_job and not any(a in t.lower() for a in lic):
        sig.append({"text": "No licensed recruitment agency named", "points": 5})
    info["phones"] = sorted({norm_phone(p) for p in PHONE_ANY.findall(t) if len(re.sub(r"\D", "", p)) >= 9})[:6]
    total = min(100, sum(s["points"] for s in sig)) if is_job or themes else 0
    return total, sig, info


def ingest(text: str, source: str, use_llm: bool = True) -> int | None:
    text = text.strip()
    if len(text) < 15:
        return None
    sc, sig, info = score_post(text)
    extracted = llm.extract_job_post(text) if use_llm else None
    if extracted:
        likely = extracted.get("scam_likelihood")
        if isinstance(likely, (int, float)):
            sc = round(0.6 * sc + 0.4 * likely)
        for f in (extracted.get("red_flags") or [])[:4]:
            sig.append({"text": f"LLM: {f}", "points": 0})
    langs = info["langs"] or ["EN"]
    lat, lon, city = ORIGIN.get(langs[0], ORIGIN["EN"])
    title = (extracted or {}).get("role") or text.split("\n")[0][:80]
    target = (extracted or {}).get("employer_named") or "Job & visa offer"
    key = "post:" + hashlib.sha1(text.encode()).hexdigest()[:16]
    return db.upsert_case(
        "jobs", key, title, sc, target=target, langs=langs, lat=lat, lon=lon,
        where_txt=f"Recruitment corridor · {city} → UAE · {source}", signals=sig,
        evidence={"text": text, "source": source, "extracted": extracted},
        features={"phone": info["phones"]},
    )


def telegram_channel(name: str, limit: int = 30) -> list[str]:
    name = re.sub(r"[^A-Za-z0-9_]", "", name.replace("https://t.me/", "").replace("s/", ""))
    r = httpx.get(f"https://t.me/s/{name}", timeout=15, headers={"User-Agent": DESKTOP_UA}, follow_redirects=True)
    if r.status_code != 200:
        raise RuntimeError(f"Telegram channel {name}: HTTP {r.status_code}")
    soup = BeautifulSoup(r.text, "html.parser")
    return [m.get_text("\n", strip=True) for m in soup.select(".tgme_widget_message_text")][-limit:]


def scan(sources: dict, job_id: str):
    """sources: {"texts": [...], "telegram": [...], "samples": bool}"""
    log = lambda m: db.job_log(job_id, m)
    try:
        posts = [(t, "pasted by analyst") for t in sources.get("texts", []) if t.strip()]
        for ch in sources.get("telegram", []):
            log(f"Reading public Telegram channel {ch}")
            posts += [(t, f"Telegram · {ch}") for t in telegram_channel(ch)]
        if sources.get("samples"):
            data = json.loads((DATA_DIR / "sample_job_posts.json").read_text(encoding="utf-8"))
            posts += [(p["text"], p["source"] + " (synthetic sample)") for p in data]
        log(f"Scoring {len(posts)} posts" + (" with Claude extraction" if llm.available() else " (rules only, no Claude key)"))
        ids = [i for i in (ingest(t, s) for t, s in posts) if i]
        cluster.recluster()
        log(f"Done: {len(ids)} posts stored")
        db.job_done(job_id, {"cases": ids})
    except Exception as e:
        log(f"Error: {e}")
        db.job_done(job_id, {"error": str(e)}, status="error")
