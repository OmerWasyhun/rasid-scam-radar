"""Read-only page analysis of a suspect site, plus the risk score.

Safety rules: GET requests only, no JavaScript, never submit a form, refuse private/internal IPs,
cap the download size. Fingerprints collected here feed the actor clustering.
"""
import base64
import hashlib
import ipaddress
import re
import socket
import time
from urllib.parse import urljoin, urlparse

import httpx
import mmh3
from bs4 import BeautifulSoup

from .config import BOT_UA, DESKTOP_UA, FETCH_MAX_BYTES, FETCH_TIMEOUT, MOBILE_UA
from .lexicon import detect_langs, lure_hits

CARD_PAT = re.compile(r"card.?num|cc.?num|cardnumber|cc-number|credit|debit|pan\b|رقم.?البطاقة", re.I)
CVV_PAT = re.compile(r"cvv|cvc|csc|security.?code|الرمز.?السري", re.I)
EXP_PAT = re.compile(r"expir|exp.?date|mm.?yy|cc-exp|تاريخ.?الانتهاء", re.I)
OTP_PAT = re.compile(r"\botp\b|one.?time|verification.?code|sms.?code|رمز.?التحقق|كلمة.?المرور.?لمرة", re.I)
EID_PAT = re.compile(r"emirates.?id|\beid\b|الهوية|identity.?number", re.I)
PASS_PAT = re.compile(r"password|passcode|\bpin\b|كلمة.?المرور", re.I)

TG_TOKEN = re.compile(r"\b\d{8,11}:[A-Za-z0-9_-]{35}\b")
TG_CHAT = re.compile(r"chat_id[\"'=:\s]+(-?\d{6,15})")
GA_ID = re.compile(r"\b(G-[A-Z0-9]{6,12}|UA-\d{4,10}-\d{1,4}|GTM-[A-Z0-9]{4,10})\b")
PHONE = re.compile(r"(?:\+?971|00971|\b0)[\s-]?(?:5[0-9]|[2-9])[\s-]?\d{3}[\s-]?\d{4}\b")
WA = re.compile(r"(?:wa\.me|api\.whatsapp\.com/send\?phone=)/?(\d{8,15})")


def _safe_host(host: str) -> bool:
    try:
        for info in socket.getaddrinfo(host, None):
            ip = ipaddress.ip_address(info[4][0])
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
                return False
        return True
    except (socket.gaierror, ValueError, UnicodeError):
        return False


def _get(url: str, ua: str):
    host = urlparse(url).hostname or ""
    if not _safe_host(host):
        return None
    try:
        with httpx.Client(follow_redirects=True, timeout=FETCH_TIMEOUT, verify=False,
                          headers={"User-Agent": ua, "Accept-Language": "en-AE,ar;q=0.8"}) as c:
            with c.stream("GET", url) as r:
                body, t0 = b"", time.monotonic()
                for chunk in r.iter_bytes():
                    body += chunk
                    if len(body) > FETCH_MAX_BYTES or time.monotonic() - t0 > FETCH_TIMEOUT:
                        break
                hops = [str(h.url) for h in r.history] + [str(r.url)]
                if not all(_safe_host(urlparse(h).hostname or "") for h in hops):
                    return None
                return {"status": r.status_code, "url": str(r.url), "hops": hops,
                        "body": body.decode(r.encoding or "utf-8", "ignore"), "ctype": r.headers.get("content-type", "")}
    except (httpx.HTTPError, UnicodeError, ValueError):
        return None


def _favicon_hash(base_url: str, soup) -> int | None:
    href = None
    for l in soup.find_all("link", href=True):
        rel = " ".join(l.get("rel", [])).lower()
        if "icon" in rel:
            href = l["href"]
            break
    url = urljoin(base_url, href or "/favicon.ico")
    if url.startswith("data:"):
        try:
            data = base64.b64decode(url.split(",", 1)[1])
        except (ValueError, IndexError):
            return None
    else:
        if not _safe_host(urlparse(url).hostname or ""):
            return None
        try:
            r = httpx.get(url, timeout=6, verify=False, follow_redirects=True, headers={"User-Agent": DESKTOP_UA})
            if r.status_code != 200 or len(r.content) < 32 or "html" in r.headers.get("content-type", ""):
                return None
            data = r.content
        except httpx.HTTPError:
            return None
    return mmh3.hash(base64.encodebytes(data))  # Shodan-style favicon hash


def _dom_hash(soup) -> str:
    tags = [t.name for t in soup.find_all(True)][:500]
    return hashlib.md5(" ".join(tags).encode()).hexdigest()[:16]


def analyze(host: str, brand_names: list[str] | None = None, start_url: str | None = None) -> dict:
    """Fetch https:// (then http://) as a desktop browser; also as Googlebot and as a mobile phone to detect cloaking.
    start_url: a full link to fetch instead of the homepage (a pasted URL with its path)."""
    page = (_get(start_url, DESKTOP_UA) if start_url else None) or _get(f"https://{host}/", DESKTOP_UA) or _get(f"http://{host}/", DESKTOP_UA)
    if not page:
        return {"reachable": False}
    soup = BeautifulSoup(page["body"], "html.parser")
    text = soup.get_text(" ", strip=True)[:20000]
    title = (soup.title.string or "").strip()[:200] if soup.title and soup.title.string else ""
    fields = []
    for f in soup.find_all(["input", "select", "textarea"]):
        desc = " ".join(str(f.get(a, "")) for a in ("name", "id", "placeholder", "autocomplete", "aria-label", "type"))
        lab = f.find_previous("label")
        if lab:
            desc += " " + lab.get_text(" ", strip=True)[:60]
        fields.append(desc)
    blob = " ".join(fields)
    asks = sorted({k for k, p in [("card number", CARD_PAT), ("CVV", CVV_PAT), ("card expiry", EXP_PAT), ("OTP", OTP_PAT),
                                  ("Emirates ID", EID_PAT), ("password/PIN", PASS_PAT)] if p.search(blob)})
    raw = page["body"]
    lower = (title + " " + text).lower()
    brands = [b for b in (brand_names or []) if len(b) > 2 and re.search(r"(?<![a-z0-9])" + re.escape(b.lower()) + r"(?![a-z0-9])", lower)]

    cloak = None
    suspicious = bool(asks or brands or lure_hits(text) or soup.find("form"))
    mobile = _get(page["url"], MOBILE_UA) if suspicious else None
    bot = ((_get(start_url, BOT_UA) if start_url else None) or _get(f"https://{host}/", BOT_UA) or _get(f"http://{host}/", BOT_UA)) if suspicious else None
    if mobile and bot:
        def sig(p):
            s = BeautifulSoup(p["body"], "html.parser")
            return (urlparse(p["url"]).hostname, (s.title.string or "").strip() if s.title and s.title.string else "", len(p["body"]) // 2000)
        sm, sb = sig(mobile), sig(bot)
        if sm[0] != sb[0] or (sm[1] != sb[1] and sm[2] != sb[2]):
            cloak = {"mobile": sm[:2], "bot": sb[:2]}

    return {
        "reachable": True,
        "status": page["status"],
        "final_url": page["url"],
        "redirects": page["hops"],
        "title": title,
        "asks_for": asks,
        "form_count": len(soup.find_all("form")),
        "brands_mentioned": brands,
        "langs": detect_langs(text),
        "lures": lure_hits(text),
        "phones": sorted(set(re.sub(r"[\s-]", "", p) for p in PHONE.findall(raw)))[:10],
        "whatsapp": sorted(set(WA.findall(raw)))[:10],
        "telegram_tokens": sorted(set(TG_TOKEN.findall(raw)))[:5],
        "telegram_chats": sorted(set(TG_CHAT.findall(raw)))[:5],
        "analytics_ids": sorted(set(GA_ID.findall(raw)))[:10],
        "favicon_hash": _favicon_hash(page["url"], soup),
        "dom_hash": _dom_hash(soup),
        "cloaking": cloak,
        "text_sample": text[:600],
        "_html": raw,  # used by verify.inspect, stripped before storage
    }


NAME_ONLY_CAP = 35  # below the 50 "flag" line: stays visible as "watch"


def score(sim_points: int, sim_reason: str, age: float | None, page: dict | None, *, official: bool = False,
          shared_actor: bool = False, extra: list | None = None) -> tuple[int, list[dict]]:
    """Weighted, explainable score. Returns (0-100, signals)."""
    sig = []
    if official:
        return 0, [{"text": "On the official allowlist", "points": -100, "ok": True}]
    if page and page.get("reachable") and page.get("final_url"):
        from urllib.parse import urlparse
        from .generator import OFFICIAL_CACHE, registrable
        landed = registrable(urlparse(page["final_url"]).hostname or "")
        if landed in OFFICIAL_CACHE:
            # brands register misspellings of their own name and forward them home (e.g. appl-e.com -> apple.com)
            return 0, [{"text": f"Redirects to the official site {landed}: a brand-owned defensive domain", "points": -100, "ok": True}]
    if sim_points:
        sig.append({"text": f"Name imitation: {sim_reason}", "points": sim_points})
    if age is not None:
        if age < 30:
            sig.append({"text": f"Domain registered {age:.0f} days ago" if age >= 1 else "Domain registered in the last 24 hours", "points": 20})
        elif age > 365 * 3:
            sig.append({"text": f"Domain is {age / 365:.0f} years old", "points": -10, "ok": True})
    if page and page.get("reachable"):
        if page.get("asks_for"):
            sig.append({"text": "Page asks for " + ", ".join(page["asks_for"]), "points": 20, "kind": "content"})
        if page.get("brands_mentioned"):
            sig.append({"text": "Page presents itself as " + ", ".join(page["brands_mentioned"][:3]), "points": 10})
        if page.get("lures"):
            sig.append({"text": "Lure language: " + ", ".join(sorted({l['theme'] for l in page['lures']})), "points": 10})
        if page.get("cloaking"):
            sig.append({"text": "Cloaking: Googlebot and a mobile phone see different pages", "points": 10, "kind": "content"})
        if page.get("telegram_tokens"):
            sig.append({"text": "Telegram bot token in page code (typical card-data exfiltration)", "points": 15, "kind": "content"})
        if page.get("whatsapp") and not page.get("asks_for"):
            sig.append({"text": "Contact through WhatsApp only", "points": 5})
    elif page is not None:
        sig.append({"text": "Domain resolves but no page answered (parked or not live yet)", "points": 0, "ok": True})
    if shared_actor:
        sig.append({"text": "Shares a fingerprint with other flagged sites", "points": 15})
    for e in extra or []:
        sig.append(e)
    total = max(0, min(100, sum(s["points"] for s in sig)))
    # Gate: a lookalike name, a young domain or brand words alone never flag a site. Something on the site itself
    # (copied UI, data or payment capture, malicious links or code, bad reputation, cloaking) has to back it up.
    if not any(s.get("kind") == "content" and s.get("points", 0) > 0 for s in sig) and total > NAME_ONLY_CAP:
        total = NAME_ONLY_CAP
        sig.append({"text": "Only the name looks similar: nothing on the site copies the brand, takes payments or runs malicious code", "points": 0, "ok": True, "kind": "gate"})
    return total, sig
