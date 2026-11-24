"""Citizen API (/api/v1) for the RASID Shield mobile app.

Links are answered from RASID's cases; unknown links are investigated on demand. Numbers are checked against
the official registry and citizen reports. Every report flows back into RASID for the next person.
"""
import concurrent.futures as cf
import re
import secrets
import threading
import time
import uuid
from collections import defaultdict, deque
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field

from . import analyzer, cluster, db, generator, hunters, phones, pipeline
from .lexicon import detect_langs, lure_hits

router = APIRouter(prefix="/api/v1", tags=["citizen"])
_pool = cf.ThreadPoolExecutor(8)
URL_RE = re.compile(r"(?:https?://|www\.)[^\s<>\"']+|\b(?:[a-z0-9-]+\.)+(?:com|net|org|ae|top|xyz|shop|online|info|live|vip|cc|site|link|click|app|me|co)\b(?:/[^\s<>\"']*)?", re.I)
PHONE_RE = re.compile(r"(?:\+|00)?\d[\d\s-]{7,15}\d")
QUICK_WAIT = 8.0


# ---------- devices & auth ----------
class DeviceIn(BaseModel):
    platform: str = "android"
    lang: str = "en"
    push_token: str | None = None
    phone: str | None = None


@router.post("/devices")
def register(d: DeviceIn):
    did, tok = uuid.uuid4().hex[:16], secrets.token_urlsafe(24)
    with db.conn() as c:
        c.execute("INSERT INTO devices(id,token,platform,lang,push,phone,created) VALUES (?,?,?,?,?,?,?)",
                  (did, tok, d.platform, d.lang, d.push_token, phones.e164(d.phone) if d.phone else None, time.time()))
    return {"device_id": did, "device_token": tok}


def device(x_device_id: str = Header(default=""), x_device_token: str = Header(default="")) -> dict:
    with db.conn() as c:
        r = db.row(c.execute("SELECT * FROM devices WHERE id=?", (x_device_id,)).fetchone())
    if not r or not secrets.compare_digest(r["token"], x_device_token):
        raise HTTPException(401, "Register the device first (POST /api/v1/devices)")
    _rate(r["id"])
    return r


_hits = defaultdict(deque)


def _rate(did, limit=120, window=60):
    q, now = _hits[did], time.time()
    while q and now - q[0] > window:
        q.popleft()
    if len(q) >= limit:
        raise HTTPException(429, "Too many checks, try again in a minute")
    q.append(now)


class DeviceUpdate(BaseModel):
    lang: str | None = None
    push_token: str | None = None
    phone: str | None = None
    contacts: list[str] | None = Field(default=None, description="sha256 hashes of contact numbers")


@router.patch("/devices/me")
def update_device(u: DeviceUpdate, dev=Depends(device)):
    fields = {}
    if u.lang:
        fields["lang"] = u.lang
    if u.push_token is not None:
        fields["push"] = u.push_token
    if u.phone is not None:
        fields["phone"] = phones.e164(u.phone)
    if u.contacts is not None:
        fields["contacts"] = db.dumps(u.contacts[:5000])
    if fields:
        with db.conn() as c:
            c.execute(f"UPDATE devices SET {','.join(k + '=?' for k in fields)} WHERE id=?", list(fields.values()) + [dev["id"]])
    return {"ok": True}


# ---------- push ----------
def push(device_row: dict | None, title: str, body: str, data: dict | None = None, emergency=False):
    tok = (device_row or {}).get("push")
    if not tok:
        return
    msg = {"to": tok, "title": title, "body": body, "data": data or {}, "sound": "default",
           "priority": "high", "channelId": "emergency" if emergency else "alerts"}
    try:
        httpx.post("https://exp.host/--/api/v2/push/send", json=msg, timeout=8)
    except httpx.HTTPError:
        pass


def device_by_id(did: str | None) -> dict | None:
    if not did:
        return None
    with db.conn() as c:
        return db.row(c.execute("SELECT * FROM devices WHERE id=?", (did,)).fetchone())


# ---------- links ----------
def _host(url: str) -> str:
    u = url.strip()
    if not re.match(r"^[a-z]+://", u, re.I):
        u = "http://" + u
    return (urlparse(u).hostname or "").lower().strip(".")


def _case_verdict(c: dict) -> dict:
    s = c["score"]
    return {"verdict": "scam" if s >= 80 else "suspicious" if s >= 50 else "safe" if s < 20 else "unclear",
            "score": s, "case_id": c["id"], "title": c["title"], "impersonates": c.get("target"),
            "reasons": [x["text"] for x in c.get("signals", []) if not x.get("ok") and x.get("points", 0) > 0][:5],
            "first_seen": c["created"]}


def known_link(host: str) -> dict | None:
    reg = generator.registrable(host)
    if reg in generator.OFFICIAL_CACHE:
        return {"verdict": "official", "score": 0, "reasons": [f"{reg} is an official domain on RASID's list"]}
    with db.conn() as c:
        r = c.execute("SELECT * FROM cases WHERE key IN (?,?,?) ORDER BY score DESC LIMIT 1",
                      (host, reg, "ad:" + host)).fetchone()
    return _case_verdict(db.row(r)) if r else None


def quick_investigate(host: str) -> dict:
    """One-host investigation for a link nobody has seen yet. Stores a case either way."""
    pipeline.refresh_official_cache()
    best, why, target = 0, "", None
    for w in db.list_watch():
        p, r = generator.similarity(host, pipeline.watch_bases(w))
        if p > best:
            best, why, target = p, r, w
    dns_info = hunters.resolve(host)
    if not dns_info:
        return {"verdict": "unreachable", "score": 0, "reasons": ["The site does not exist or is already down"]}
    wv = target or {"id": None, "name": None, "official_domains": []}
    info = {"dns": dns_info, "rdap": hunters.rdap(generator.registrable(host)),
            "page": analyzer.analyze(host, [wv["name"]] if wv["name"] else [])}
    ages = {host: hunters.age_days(info["rdap"].get("created"))}
    geo = hunters.geolocate([dns_info["a"][0]])
    cid = pipeline._store(host, wv, "domains", best, why, info, ages, geo,
                          [{"text": "Reported through the RASID Shield app", "points": 0}], {"source": "citizen"})
    cluster.recluster()
    return _case_verdict(db.get_case(cid))


def _ticket(kind, fn, *args, device_id=None, notify=None):
    jid = uuid.uuid4().hex[:12]
    db.new_job(jid, kind)
    fut = _pool.submit(fn, *args)

    def done(f):
        try:
            res = f.result()
            db.job_done(jid, res)
            if notify and res.get("verdict") in ("scam", "suspicious"):
                notify(res)
        except Exception as e:
            db.job_done(jid, {"error": str(e)}, status="error")
    fut.add_done_callback(done)
    return jid, fut


class LinkIn(BaseModel):
    url: str = Field(min_length=3, max_length=2000)


def check_link_value(url: str, dev: dict) -> dict:
    host = _host(url)
    if not host or "." not in host:
        raise HTTPException(400, "That doesn't look like a link")
    pipeline.refresh_official_cache() if not generator.OFFICIAL_CACHE else None
    k = known_link(host)
    if k:
        return {"host": host, "source": "rasid", **k}
    notify = lambda res: push(dev, "RASID: dangerous link", f"{host}: {res['verdict']} ({res['score']}/100)", {"host": host}, res["verdict"] == "scam")
    jid, fut = _ticket("citizen-link", quick_investigate, host, notify=notify)
    try:
        res = fut.result(timeout=QUICK_WAIT)
        return {"host": host, "source": "investigated", **res}
    except cf.TimeoutError:
        return {"host": host, "source": "investigating", "verdict": "checking", "ticket": jid,
                "reasons": ["RASID is investigating this link now; you'll get a notification"]}


@router.post("/check/link")
def check_link(body: LinkIn, dev=Depends(device)):
    return check_link_value(body.url, dev)


@router.get("/tickets/{jid}")
def ticket(jid: str, dev=Depends(device)):
    j = db.get_job(jid)
    if not j:
        raise HTTPException(404, "No such ticket")
    return {"status": j["status"], "result": j.get("result")}


# ---------- messages ----------
class MessageIn(BaseModel):
    text: str = Field(min_length=1, max_length=5000)
    sender: str | None = None
    app: str | None = None


@router.post("/check/message")
def check_message(m: MessageIn, dev=Depends(device)):
    text = m.text
    urls = list(dict.fromkeys(u.rstrip(".,)") for u in URL_RE.findall(text)))[:3]
    nums = list(dict.fromkeys(phones.e164(p) for p in PHONE_RE.findall(text) if len(re.sub(r"\D", "", p)) >= 9))[:3]
    lures = lure_hits(text)
    org = phones.detect_org(text)
    links = [check_link_value(u, dev) for u in urls]
    numbers = [phones.verdict(n) for n in nums]
    sender = phones.verdict(m.sender) if m.sender and re.search(r"\d{6,}", m.sender) else None
    score = 0
    reasons = []
    for l in links:
        if l["verdict"] in ("scam", "suspicious"):
            score = max(score, l.get("score", 60))
            reasons.append(f"Link {l['host']} is {l['verdict']}")
        elif l["verdict"] == "checking":
            score = max(score, 40)
            reasons.append(f"Link {l['host']} is being investigated")
    for n in numbers + ([sender] if sender else []):
        if n["verdict"] in ("scam", "reported"):
            score = max(score, 85 if n["verdict"] == "scam" else 60)
            reasons.append(f"{n['number']} was reported by {n['reports']} {'person' if n['reports'] == 1 else 'people'}")
    if lures:
        score += 15 * min(3, len(lures))
        reasons.append("Uses scam wording: " + ", ".join(sorted({l['theme'] for l in lures})))
    if org and links and all(l["verdict"] != "official" for l in links):
        score += 20
        reasons.append(f"Mentions {org} but links to a site that isn't {org}'s")
    if sender and sender["verdict"] == "unknown" and sender.get("mobile") and org in phones.BANKS_AND_POLICE:
        score += 20
        reasons.append(f"Claims to be {org} but sent from a personal mobile number")
    score = min(100, score)
    verdict = "scam" if score >= 80 else "suspicious" if score >= 50 else "unclear" if score >= 25 else "safe"
    return {"verdict": verdict, "score": score, "reasons": reasons, "langs": detect_langs(text), "org": org,
            "links": links, "numbers": numbers, "sender": sender}


# ---------- numbers ----------
@router.get("/check/number")
def check_number_prefix(prefix: str, dev=Depends(device)):
    """k-anonymity: the app sends the first 5+ hex chars of sha256(number) and matches locally."""
    return {"matches": phones.by_prefix(prefix)}


class NumberIn(BaseModel):
    number: str = Field(min_length=6, max_length=30)


@router.post("/check/number")
def check_number(n: NumberIn, dev=Depends(device)):
    return phones.verdict(n.number)


@router.get("/sync/numbers")
def sync_numbers(since: float = 0, dev=Depends(device)):
    return {"now": time.time(), "numbers": phones.since(since)}


@router.get("/orgs")
def orgs(dev=Depends(device)):
    have = phones.orgs_with_numbers()
    names = list(phones.ORG_ALIASES) + [w["name"] for w in db.list_watch() if w["name"] not in phones.ORG_ALIASES]
    return [{"name": n, "official_numbers": have.get(n, 0), "bank_or_police": n in phones.BANKS_AND_POLICE}
            for n in dict.fromkeys(names)]


class ClaimIn(BaseModel):
    number: str = Field(min_length=6, max_length=30)
    org: str = Field(min_length=2, max_length=80)
    asked_sensitive: bool = False


@router.post("/verify/claim")
def verify(c: ClaimIn, dev=Depends(device)):
    res = phones.verify_claim(c.number, c.org, c.asked_sensitive)
    if res["decision"] == "scam":
        phones.report(c.number, dev["id"], c.org, source="claim-check")
    return {"number": phones.pretty(c.number), "org": c.org, **res}


class ReportIn(BaseModel):
    kind: str = Field(pattern="^(number|link|message)$")
    value: str = Field(min_length=3, max_length=5000)
    claim: str | None = None
    note: str | None = Field(default=None, max_length=500)


@router.post("/report")
def report(r: ReportIn, dev=Depends(device)):
    if r.kind == "number":
        return {"number": phones.report(r.value, dev["id"], r.claim)}
    if r.kind == "link":
        host = _host(r.value)
        jid, _ = _ticket("citizen-report", quick_investigate, host)
        return {"ticket": jid, "host": host}
    # message: store as a job/visa or generic post case through the jobs linguist
    from .sensors import jobs
    cid = jobs.ingest(r.value, "citizen report", use_llm=True)
    return {"case_id": cid}


# ---------- screened calls ----------
@router.get("/calls")
def my_calls(dev=Depends(device)):
    with db.conn() as c:
        rows = c.execute("SELECT * FROM calls WHERE device_id=? ORDER BY created DESC LIMIT 100", (dev["id"],)).fetchall()
    out = []
    for r in rows:
        d = db.row(r)
        d["caller_pretty"] = phones.pretty(d["caller"] or "")
        out.append(d)
    return out


@router.get("/screener")
def screener_info(dev=Depends(device)):
    from .config import TWILIO_SCREENER_NUMBER
    n = phones.e164(TWILIO_SCREENER_NUMBER) if TWILIO_SCREENER_NUMBER else ""
    return {"enabled": bool(n), "number": "+" + n if n else None,
            "forward_busy_code": f"**67*+{n}#" if n else None, "cancel_code": "##67#",
            "note": "Codes are standard GSM; confirm with your carrier (e& / du)."}
