"""Phone number registry and history: official numbers per organisation, citizen reports, claim checks.

Official numbers come from two places:
  - each watchlist's official_phones (console / API)
  - data/official_numbers.csv  (org,number per line) — fill it from each organisation's own website.
"""
import csv
import hashlib
import json
import re
import time

from . import db
from .config import DATA_DIR

SCAM_REPORTS = 3  # distinct devices before a reported number becomes "scam"

# Names callers use for each organisation (EN/AR/transliterated), for claim detection in speech.
ORG_ALIASES = {
    "Abu Dhabi Police": ["abu dhabi police", "police", "شرطة أبوظبي", "الشرطة", "شرطة", "polis"],
    "Dubai Police": ["dubai police", "شرطة دبي"],
    "ADCB": ["adcb", "abu dhabi commercial bank", "بنك أبوظبي التجاري"],
    "First Abu Dhabi Bank": ["fab", "first abu dhabi bank", "بنك أبوظبي الأول"],
    "Emirates NBD": ["emirates nbd", "enbd", "بنك الإمارات دبي الوطني"],
    "Etisalat e&": ["etisalat", " e& ", "اتصالات"],
    "du": [" du ", "du telecom", "دو"],
    "Aramex": ["aramex", "أرامكس"],
    "Emirates Post": ["emirates post", "بريد الإمارات"],
    "TAMM": ["tamm", "تطبيق تم", "منصة تم"],
    "ICP": ["icp", "immigration", "الهوية والجنسية", "الإقامة"],
    "MOHRE": ["mohre", "ministry of labour", "وزارة الموارد البشرية"],
    "Salik": ["salik", "سالك"],
    "RTA Dubai": ["rta", "هيئة الطرق"],
}
BANKS_AND_POLICE = {"Abu Dhabi Police", "Dubai Police", "ADCB", "First Abu Dhabi Bank", "Emirates NBD"}
SENSITIVE = re.compile(
    r"\botp\b|one.?time|verification code|\bpin\b|cvv|card (number|details)|password|transfer|wire|gift card|bitcoin|crypto|"
    r"emirates id|account (number|details)|\biban\b|رمز|كلمة السر|البطاقة|تحويل|رقم الحساب|الهوية", re.I)


def e164(raw: str | None) -> str:
    """Digits in international form. UAE local numbers (05x, 02, 600, 800) get 971."""
    if not raw:
        return ""
    s = raw.strip()
    d = re.sub(r"\D", "", s)
    if not d:
        return ""
    if s.startswith("+"):
        return d
    if d.startswith("00"):
        return d[2:]
    if d.startswith("971"):
        return d
    if d.startswith("0"):
        return "971" + d[1:]
    if re.match(r"^(5\d{8}|[2-9]\d{7}|[68]00\d{3,7})$", d):
        return "971" + d
    return d


def phash(number: str) -> str:
    return hashlib.sha256(e164(number).encode()).hexdigest()


def is_uae_mobile(number: str) -> bool:
    return bool(re.match(r"^9715\d{8}$", e164(number)))


def pretty(number: str) -> str:
    n = e164(number)
    if n.startswith("971"):
        rest = n[3:]
        if rest.startswith("5") and len(rest) == 9:
            return f"+971 {rest[:2]} {rest[2:5]} {rest[5:]}"
        return f"+971 {rest}"
    return "+" + n


# ---------- registry ----------
def sync_registry() -> int:
    """Load official numbers from watchlists and data/official_numbers.csv into the numbers table."""
    rows = []
    for w in db.list_watch():
        rows += [(w["name"], p) for p in w["official_phones"]]
    path = DATA_DIR / "official_numbers.csv"
    if path.exists():
        with path.open(encoding="utf-8") as f:
            for r in csv.reader(f):
                if len(r) >= 2 and r[0].strip() and not r[0].startswith("#") and r[0].strip().lower() != "org":
                    rows.append((r[0].strip(), r[1].strip()))
    now = time.time()
    with db.conn() as c:
        for org, num in rows:
            n = e164(num)
            if len(n) < 6:
                continue
            c.execute(
                "INSERT INTO numbers(number,hash,status,org,source,first,last) VALUES (?,?,?,?,?,?,?) "
                "ON CONFLICT(number) DO UPDATE SET status='official', org=excluded.org, last=excluded.last",
                (n, phash(n), "official", org, "registry", now, now))
    return len(rows)


def get(number: str) -> dict | None:
    with db.conn() as c:
        return db.row(c.execute("SELECT * FROM numbers WHERE number=?", (e164(number),)).fetchone())


def official_numbers(org: str) -> list[str]:
    with db.conn() as c:
        return [r[0] for r in c.execute("SELECT number FROM numbers WHERE status='official' AND org=?", (org,))]


def orgs_with_numbers() -> dict:
    with db.conn() as c:
        return {r[0]: r[1] for r in c.execute("SELECT org, COUNT(*) FROM numbers WHERE status='official' GROUP BY org")}


def by_prefix(prefix: str) -> list[dict]:
    prefix = re.sub(r"[^0-9a-f]", "", prefix.lower())[:8]
    if len(prefix) < 4:
        return []
    with db.conn() as c:
        rows = c.execute("SELECT hash,status,org,reporters,claims FROM numbers WHERE hash LIKE ?", (prefix + "%",)).fetchall()
    return [public(db.row(r)) for r in rows]


def public(r: dict) -> dict:
    return {"hash": r["hash"], "status": r["status"], "org": r.get("org"),
            "reports": len(r.get("reporters") or []), "claims": r.get("claims") or {}}


def since(t: float) -> list[dict]:
    with db.conn() as c:
        rows = c.execute("SELECT hash,status,org,reporters,claims FROM numbers WHERE last>=? AND status IN ('official','scam','reported')", (t,)).fetchall()
    return [public(db.row(r)) for r in rows]


def report(number: str, device_id: str, claim: str | None = None, source: str = "citizen", force_scam: bool = False) -> dict:
    n = e164(number)
    if len(n) < 6:
        raise ValueError("Not a phone number")
    now = time.time()
    r = get(n)
    if r and r["status"] == "official":
        return public(r)  # official numbers can never be marked scam
    reporters = set((r or {}).get("reporters") or [])
    if device_id:
        reporters.add(device_id)
    claims = (r or {}).get("claims") or {}
    if claim:
        claims[claim] = claims.get(claim, 0) + 1
    status = "scam" if force_scam or len(reporters) >= SCAM_REPORTS else "reported"
    if r and r["status"] == "scam":
        status = "scam"
    with db.conn() as c:
        c.execute(
            "INSERT INTO numbers(number,hash,status,reporters,claims,source,first,last) VALUES (?,?,?,?,?,?,?,?) "
            "ON CONFLICT(number) DO UPDATE SET status=excluded.status, reporters=excluded.reporters, claims=excluded.claims, last=excluded.last",
            (n, phash(n), status, json.dumps(sorted(reporters)), json.dumps(claims, ensure_ascii=False), source, now, now))
    return public(get(n))


def verdict(number: str) -> dict:
    """What the app shows for a number on its own."""
    n = e164(number)
    r = get(n)
    if r and r["status"] == "official":
        return {"verdict": "official", "org": r["org"], "number": pretty(n)}
    if r and r["status"] == "scam":
        return {"verdict": "scam", "reports": len(r["reporters"]), "claims": r["claims"], "number": pretty(n)}
    if r and r["status"] == "reported":
        return {"verdict": "reported", "reports": len(r["reporters"]), "claims": r["claims"], "number": pretty(n)}
    return {"verdict": "unknown", "mobile": is_uae_mobile(n), "number": pretty(n)}


def detect_org(text: str) -> str | None:
    t = f" {text.lower()} "
    for org, names in ORG_ALIASES.items():
        if any(a in t for a in names):
            return org
    return None


def verify_claim(number: str, org: str, sensitive: bool = False) -> dict:
    """Does this number belong to the organisation the caller claims? Returns decision + reasons."""
    n = e164(number)
    r = get(n)
    official = official_numbers(org)
    reasons = []
    if r and r["status"] == "official" and r["org"] == org:
        return {"result": "match", "decision": "pass", "level": 0, "reasons": [f"Number is on {org}'s official list"]}
    if r and r["status"] == "official":
        reasons.append(f"Number belongs to {r['org']}, not {org}")
    if r and r["status"] in ("scam", "reported"):
        n_rep = len(r['reporters'])
        reasons.append(f"Number reported by {n_rep} {'person' if n_rep == 1 else 'people'}" + (f" (pretended to be {', '.join(r['claims'])})" if r["claims"] else ""))
    if official:
        reasons.append(f"Not one of {org}'s {len(official)} official numbers")
    else:
        reasons.append(f"No official numbers registered for {org} yet")
    if is_uae_mobile(n) and org in BANKS_AND_POLICE:
        reasons.append(f"{org} does not call customers from a personal mobile number")
    if sensitive:
        reasons.append("Caller asked for codes, card details or money")
    mismatch = bool(official) or (r and r["status"] == "official")
    bad_history = bool(r and r["status"] == "scam")
    if bad_history or (mismatch and (sensitive or org in BANKS_AND_POLICE)) or (is_uae_mobile(n) and org in BANKS_AND_POLICE and sensitive):
        level = 2 if (org in BANKS_AND_POLICE and sensitive) or bad_history else 1
        return {"result": "mismatch", "decision": "scam", "level": level, "reasons": reasons}
    if mismatch or (is_uae_mobile(n) and org in BANKS_AND_POLICE):
        return {"result": "mismatch" if mismatch else "unverified", "decision": "unsure", "level": 1, "reasons": reasons}
    return {"result": "unverified", "decision": "unsure", "level": 0, "reasons": reasons}
