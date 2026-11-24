"""Site inspection: decide whether a lookalike domain actually impersonates the brand or is just a real, unrelated business.

A similar name is not evidence. The inspector opens the site and checks four things:
  1. UI similarity with the official site (favicon, title, text, layout, CSS classes, copied or hot-linked assets)
  2. Malicious links (forms posting elsewhere, Telegram bot endpoints, shorteners, APK downloads, known scam domains, Safe Browsing)
  3. Malicious code (obfuscated scripts, hidden iframes, wallet drainers, anti-inspection tricks)
  4. Payment / credential capture (card, CVV, OTP, payment gateways, IBANs, crypto wallets, "pay" amounts)
It also recognises parked "for sale" domains and genuine unrelated businesses, so those don't get flagged.
Every signal it emits has kind="content"; the scorer only flags a site when at least one content signal fires.
"""
import difflib
import re
import threading
import time
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from . import browser, db, enrich, generator, visual
from .config import DATA_DIR

_cache: dict[str, tuple[float, dict]] = {}
_lock = threading.Lock()
PROFILE_TTL = 6 * 3600

SHORTENERS = {"bit.ly", "tinyurl.com", "cutt.ly", "is.gd", "t.ly", "rb.gy", "rebrand.ly", "shorturl.at", "tiny.cc", "s.id", "t.co", "ow.ly", "goo.su"}
GATEWAYS = {"stripe": "Stripe", "checkout.com": "Checkout.com", "payfort": "PayFort (Amazon Payment Services)",
            "paytabs": "PayTabs", "telr": "Telr", "network.ae": "Network International", "ngenius": "N-Genius",
            "razorpay": "Razorpay", "paypal": "PayPal", "2checkout": "2Checkout", "tap.company": "Tap Payments",
            "hyperpay": "HyperPay", "moyasar": "Moyasar", "coinbase commerce": "Coinbase Commerce", "nowpayments": "NOWPayments"}
PARKED = re.compile(r"domain (is )?for sale|buy this domain|this domain may be for sale|parked (free|domain)|sedo|parkingcrew|bodis|dan\.com|afternic|"
                    r"hugedomains|domain parking|is available for purchase|related searches", re.I)
IBAN = re.compile(r"\bAE\d{2}\s?(?:\d{4}\s?){4}\d{3}\b")
BTC = re.compile(r"\b(bc1[a-z0-9]{25,60}|[13][a-km-zA-HJ-NP-Z1-9]{25,34})\b")
ETH = re.compile(r"\b0x[a-fA-F0-9]{40}\b")
TRON = re.compile(r"\bT[1-9A-HJ-NP-Za-km-z]{33}\b")
PAY_WORDS = re.compile(r"\bpay\b.{0,25}(?:AED|Dhs?|درهم)|\b(pay now|pay (the )?(fee|fine|amount)|payment (due|required)|complete (your )?payment|proceed to pay|checkout|"
                       r"bank transfer|wire transfer|send (the )?(money|amount))\b|ادفع|سدد|الدفع|تحويل بنكي", re.I)
AMOUNT = re.compile(r"(?:AED|Dhs?\.?|درهم)\s?\d+(?:[.,]\d+)?|\d+(?:[.,]\d+)?\s?(?:AED|Dhs?|درهم)", re.I)
OBFUSCATION = [
    (re.compile(r"eval\s*\(\s*(atob|unescape|decodeURIComponent|function\s*\(\s*p\s*,\s*a\s*,\s*c\s*,\s*k)", re.I), "Self-decoding script (eval of encoded code)"),
    (re.compile(r"_0x[a-f0-9]{4,6}\s*\[", re.I), "Obfuscated JavaScript (javascript-obfuscator pattern)"),
    (re.compile(r"document\.write\s*\(\s*unescape", re.I), "Writes hidden encoded HTML into the page"),
    (re.compile(r"(String\.fromCharCode\([^)]{0,40}\)\s*\+\s*){6,}", re.I), "Builds code from character codes"),
]
ANTI_INSPECT = re.compile(r"addEventListener\(\s*['\"]contextmenu['\"].{0,80}preventDefault|devtools(?:-detect|Open|isOpen)|debugger;\s*}\s*,\s*\d+", re.I | re.S)
DRAINER = re.compile(r"walletconnect|web3modal|ethers\.(?:js|min)|setApprovalForAll|seaport|permit2", re.I)
PARKING_HOSTS = ("parklogic.com", "parkingcrew.net", "bodis.com", "sedoparking.com", "sedo.com", "above.com", "skenzo.com",
                 "dan.com", "afternic.com", "hugedomains.com", "domainsponsor.com", "parked.com", "trafficparking", "porkbun.com/parked",
                 "smartname.com", "uniregistry", "namecheap.com/domains/marketplace", "domainmarket.com", "undeveloped.com")
TRACKERS = ("googletagmanager.com", "google.com", "doubleclick.net", "google-analytics.com", "facebook.com", "facebook.net",
            "youtube.com", "hotjar.com", "clarity.ms", "linkedin.com", "twitter.com", "tiktok.com", "snapchat.com", "bing.com",
            "googlesyndication.com", "recaptcha.net", "gstatic.com", "cloudflare.com", "hubspot.com", "zendesk.com", "intercom.io")
CLAIM = re.compile(r"claim|airdrop|reward|connect wallet", re.I)


# ---------- profiles ----------
def _profile(html: str, url: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    for t in soup(["script", "style", "noscript"]):
        t.extract()
    text = soup.get_text(" ", strip=True).lower()
    words = re.findall(r"[\w؀-ۿ]{3,}", text)[:4000]
    full = BeautifulSoup(html, "html.parser")
    classes = {c for el in full.find_all(class_=True) for c in el.get("class", []) if 2 < len(c) < 40}
    assets = set()
    for el in full.find_all(["img", "link", "script"]):
        src = el.get("src") or el.get("href") or ""
        name = urlparse(src).path.rsplit("/", 1)[-1].lower()
        if name and "." in name and len(name) > 4:
            assets.add(name)
    return {
        "url": url,
        "title": (full.title.string or "").strip().lower() if full.title and full.title.string else "",
        "shingles": {" ".join(words[i:i + 3]) for i in range(max(0, len(words) - 2))},
        "classes": classes,
        "tags": [t.name for t in full.find_all(True)][:800],
        "assets": assets,
        "colors": set(re.findall(r"#[0-9a-f]{6}\b", html.lower())),
        "logo_alts": {(i.get("alt") or "").strip().lower() for i in full.find_all("img") if "logo" in (i.get("alt") or "").lower() + " ".join(i.get("class", [])).lower()},
    }


CHALLENGE = re.compile(r"just a moment|attention required|cf-browser-verification|challenge-platform|checking your browser|"
                       r"access denied|request unsuccessful|incapsula|captcha|enable javascript and cookies", re.I)
SNAPSHOTS = DATA_DIR / "official_snapshots"


def is_challenge(html: str) -> bool:
    head = html[:6000]
    return bool(CHALLENGE.search(head)) and len(BeautifulSoup(html, "html.parser").get_text(" ", strip=True)) < 1500


def official_profile(w: dict) -> dict | None:
    """Profile of the brand's real homepage. Falls back to a saved copy in data/official_snapshots/<domain>.html
    when the live site blocks automated visitors (Cloudflare and similar challenge pages)."""
    from .analyzer import DESKTOP_UA, _favicon_hash, _get
    if not w.get("official_domains"):
        return None
    dom = w["official_domains"][0]
    with _lock:
        hit = _cache.get(dom)
        if hit and time.time() - hit[0] < PROFILE_TTL:
            return hit[1]
    prof = None
    snap = SNAPSHOTS / f"{dom}.html"
    page = None
    for u in (f"https://{dom}/", f"https://www.{dom}/", f"http://{dom}/"):
        page = _get(u, DESKTOP_UA)
        if page and len(page["body"]) > 500 and not is_challenge(page["body"]):
            break
        page = None
    shot = None
    r = browser.render(f"https://{dom}/", tag="official")
    if r.get("ok") and not is_challenge(r.get("html", "")):
        shot = r.get("screenshot")
        if not page:  # the live browser got through where the plain fetch was blocked
            page = {"body": r["html"], "url": r["final_url"]}
    if page:
        prof = _profile(page["body"], page["url"])
        prof["favicon_hash"] = _favicon_hash(page["url"], BeautifulSoup(page["body"], "html.parser"))
        prof["source"] = "live"
    elif snap.exists():
        html = snap.read_text(encoding="utf-8", errors="ignore")
        prof = _profile(html, f"https://{dom}/")
        prof["favicon_hash"] = None
        prof["source"] = "saved snapshot"
    if prof is not None:
        prof["screenshot"] = shot
    with _lock:
        _cache[dom] = (time.time(), prof)
    return prof


def _flagged_regs() -> set:
    with db.conn() as c:
        return {r[0] for r in c.execute("SELECT key FROM cases WHERE score>=60 AND key NOT LIKE '%:%'")}


def _jac(a: set, b: set) -> float:
    return len(a & b) / len(a | b) if a and b else 0.0


def ui_similarity(sus: dict, off: dict) -> dict:
    parts = {
        "favicon": 1.0 if sus.get("favicon_hash") and sus.get("favicon_hash") == off.get("favicon_hash") else 0.0,
        "title": difflib.SequenceMatcher(None, sus["title"], off["title"]).ratio() if sus["title"] and off["title"] else 0.0,
        "text": _jac(sus["shingles"], off["shingles"]),
        "css": _jac(sus["classes"], off["classes"]),
        "layout": difflib.SequenceMatcher(None, sus["tags"][:400], off["tags"][:400], autojunk=False).ratio() if sus["tags"] and off["tags"] else 0.0,
        "assets": _jac(sus["assets"], off["assets"]),
        "colors": _jac(sus["colors"], off["colors"]),
    }
    weights = {"favicon": .22, "title": .14, "text": .2, "css": .16, "layout": .1, "assets": .12, "colors": .06}
    score = sum(parts[k] * weights[k] for k in weights)
    # strong single tells: identical favicon or largely copied text/assets
    score = max(score, parts["favicon"] * 0.6, min(1.0, parts["text"] * 1.5), min(1.0, parts["assets"] * 1.3))
    return {"score": round(score, 2), "parts": {k: round(v, 2) for k, v in parts.items()}}


# ---------- inspection ----------
def inspect(host: str, page: dict, w: dict | None, rendered: dict | None = None) -> dict:
    """page is analyzer.analyze() output including the private _html field; rendered is browser.render() output
    (JavaScript executed, screenshot taken). Checks run on the rendered page when we have it."""
    rendered = rendered if rendered and rendered.get("ok") else None
    html = (rendered or {}).get("html") or page.get("_html") or ""
    url = (rendered or {}).get("final_url") or page.get("final_url") or f"http://{host}/"
    final_host = (urlparse(url).hostname or host).lower()
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(" ", strip=True)
    raw = html
    flagged_regs = _flagged_regs()
    sig, out = [], {"links": [], "code": [], "payment": [], "ui": None, "visual": None,
                    "screenshot": (rendered or {}).get("screenshot"), "screenshot_full": (rendered or {}).get("screenshot_full"),
                    "rendered": bool(rendered)}
    official_regs = generator.OFFICIAL_CACHE

    # 0. parked / for sale
    parking_hit = any(any((urlparse(rq["url"]).hostname or "").endswith(p) for p in PARKING_HOSTS) for rq in (rendered or {}).get("requests", []))
    out["parked"] = (bool(PARKED.search(text[:5000])) or parking_hit or any(p in raw for p in PARKING_HOSTS)) and not soup.find("form")

    # 1. UI similarity
    off = official_profile(w) if w else None
    if w and not off and w.get("official_domains"):
        out["ui_note"] = (f"Couldn't load {w['official_domains'][0]} to compare designs (it blocks automated visitors). "
                          f"Save its homepage as data/official_snapshots/{w['official_domains'][0]}.html to enable this check.")
    if off:
        sp = _profile(html, url)
        sp["favicon_hash"] = page.get("favicon_hash")
        ui = ui_similarity(sp, off)
        out["ui"] = ui
        off_regs = {generator.registrable(d) for d in w["official_domains"]}
        asset_hosts = {(urlparse(urljoin(url, el.get("src") or el.get("href") or "")).hostname or "").lower()
                       for el in soup.find_all(["img", "link", "script"])}
        hot = sorted(h for h in asset_hosts if h and generator.registrable(h) in off_regs and generator.registrable(final_host) not in off_regs)
        out["hotlinks"] = hot[:5]
        if ui["score"] >= 0.55:
            sig.append({"text": f"Looks like the official {w['name']} site ({int(ui['score'] * 100)}% UI match)", "points": 30, "kind": "content"})
        elif ui["score"] >= 0.35:
            sig.append({"text": f"Partly copies the official {w['name']} site ({int(ui['score'] * 100)}% UI match)", "points": 18, "kind": "content"})
        if rendered and off.get("screenshot"):
            sp_path, off_path = browser.SHOTS / rendered["screenshot"], browser.SHOTS / off["screenshot"]
            if sp_path.exists() and off_path.exists() and not visual.blank(sp_path):
                vis = visual.compare(sp_path, off_path)
                vis["official_screenshot"] = off["screenshot"]
                out["visual"] = vis
                if vis["score"] >= 0.7:
                    sig.append({"text": f"Screenshot looks like the official {w['name']} site ({int(vis['score'] * 100)}% visual match)", "points": 30, "kind": "content"})
                elif vis["score"] >= 0.5:
                    sig.append({"text": f"Screenshot partly resembles the official {w['name']} site ({int(vis['score'] * 100)}% visual match)", "points": 15, "kind": "content"})
        if ui["parts"]["favicon"] == 1.0:
            sig.append({"text": f"Uses the exact same favicon as {w['name']}", "points": 15, "kind": "content"})
        if hot:
            sig.append({"text": "Loads images or styles straight from the official site (" + ", ".join(hot[:2]) + ")", "points": 15, "kind": "content"})

    # 2. links
    external, findings = set(), []
    for f in soup.find_all("form"):
        act = urljoin(url, f.get("action") or url)
        ah = (urlparse(act).hostname or "").lower()
        if "api.telegram.org" in act:
            findings.append(("Form sends data straight to a Telegram bot", 30))
        elif ah and generator.registrable(ah) != generator.registrable(final_host):
            findings.append((f"Form submits to another site: {ah}", 15))
        elif re.search(r"\.php(\?|$)", act) and f.find("input", {"type": re.compile("password|tel|number", re.I)}):
            findings.append(("Form posts sensitive fields to a PHP script", 5))
    if re.search(r"api\.telegram\.org/bot", raw):
        findings.append(("Page code calls the Telegram bot API (typical for stealing form data)", 25))
    for rq in (rendered or {}).get("requests", []):
        rh = (urlparse(rq["url"]).hostname or "").lower()
        if not rh:
            continue
        if "api.telegram.org" in rh:
            findings.append(("While loading, the page contacted a Telegram bot", 25))
        elif rq["type"] == "script" and re.match(r"^\d{1,3}(\.\d{1,3}){3}$", rh):
            findings.append((f"Loads a script from a bare IP address ({rh})", 15))
        elif generator.registrable(rh) in flagged_regs and generator.registrable(rh) != generator.registrable(final_host):
            findings.append((f"While loading, the page talks to {generator.registrable(rh)}, already flagged by RASID", 20))
        # Ordinary background calls (analytics, ads, chat widgets, CDNs) are not evidence: big legitimate sites make dozens.
    for a in soup.find_all(["a", "iframe", "script"], href=True) + soup.find_all(["iframe", "script"], src=True):
        h = urljoin(url, a.get("href") or a.get("src") or "")
        hn = (urlparse(h).hostname or "").lower()
        if not hn or generator.registrable(hn) == generator.registrable(final_host):
            continue
        external.add(h)
        if re.match(r"^\d{1,3}(\.\d{1,3}){3}$", hn):
            findings.append((f"Links to a bare IP address ({hn})", 10))
        if hn in SHORTENERS:
            findings.append((f"Uses a link shortener ({hn}) to hide the destination", 10))
        if urlparse(h).path.lower().endswith(".apk"):
            findings.append(("Offers an Android app (.apk) download outside the Play Store", 25))
    known = []
    if external:
        regs = {generator.registrable(urlparse(u).hostname or "") for u in external}
        with db.conn() as c:
            for r in regs:
                row = c.execute("SELECT title, score FROM cases WHERE key=? AND score>=60", (r,)).fetchone()
                if row:
                    known.append(r)
        for r in known[:3]:
            findings.append((f"Links to {r}, already flagged by RASID", 20))
        sb = enrich.safe_browsing_many(sorted(external)[:50])
        for u in sb.get("listed", [])[:3]:
            findings.append((f"Links to a site on Google's malicious list: {urlparse(u).hostname}", 25))
    seen = set()
    for text_f, pts in findings:
        if text_f not in seen:
            seen.add(text_f)
            out["links"].append(text_f)
            sig.append({"text": text_f, "points": pts, "kind": "content"})

    # 3. malicious code
    for pat, label in OBFUSCATION:
        if pat.search(raw):
            out["code"].append(label)
    for fr in soup.find_all("iframe"):
        if fr.find_parent("noscript"):
            continue  # tag-manager / pixel fallbacks live here on ordinary sites
        src = (fr.get("src") or "").strip()
        src_host = (urlparse(urljoin(url, src)).hostname or "").lower()
        st = (fr.get("style") or "").replace(" ", "").lower()
        hidden = fr.get("width") in ("0", "1") or fr.get("height") in ("0", "1") or "display:none" in st or "visibility:hidden" in st
        # hidden tracker iframes are everywhere; only hidden frames to raw IPs, flagged sites or script URLs count
        if hidden and (src.lower().startswith(("javascript:", "data:text/html")) or re.match(r"^\d{1,3}(\.\d{1,3}){3}$", src_host)
                       or (src_host and generator.registrable(src_host) in flagged_regs)):
            out["code"].append(f"Hidden iframe loading {src_host or src[:30]}")
            break
    if ANTI_INSPECT.search(raw):
        out["code"].append("Blocks right-click or detects developer tools (hides from inspection)")
    if DRAINER.search(raw) and CLAIM.search(text):
        out["code"].append("Crypto wallet-drainer pattern (connect wallet to claim)")
    for c_ in out["code"]:
        sig.append({"text": "Suspicious code: " + c_, "points": 15 if "drainer" in c_ or "decoding" in c_ else 10, "kind": "content"})

    # 4. payment / credential capture
    pay = []
    low = raw.lower()
    gws = sorted({name for k, name in GATEWAYS.items() if k in low})
    if page.get("asks_for"):
        out["payment"].append("Collects " + ", ".join(page["asks_for"]))  # scored by analyzer.score
    if gws and not page.get("asks_for"):
        pay.append(("Takes payments through " + ", ".join(gws[:3]), 5))
    if IBAN.search(text):
        pay.append(("Shows a UAE IBAN for bank transfer", 15))
    wallets = BTC.findall(text) + ETH.findall(text) + TRON.findall(text)
    if wallets:
        pay.append(("Asks for payment to a crypto wallet", 25))
    if PAY_WORDS.search(text) and AMOUNT.search(text):
        pay.append(("Asks the visitor to pay an amount (" + AMOUNT.search(text).group(0) + ")", 15))
    for t_, pts in pay:
        out["payment"].append(t_)
        sig.append({"text": t_, "points": pts, "kind": "content"})

    # brand claims only count together with capture or copied UI
    brand = bool(page.get("brands_mentioned"))
    capture = bool(page.get("asks_for")) or any(p >= 15 for _, p in pay)  # card/OTP fields, IBAN, wallet, pay-an-amount
    copied = bool(out["ui"] and out["ui"]["score"] >= 0.35) or bool(out.get("hotlinks")) or bool(out["visual"] and out["visual"]["score"] >= 0.5)
    malicious = bool(out["links"] or out["code"])

    if out["parked"]:
        verdict = "parked"
        # parking networks run their own ad scripts; keep only signals that point at real abuse
        sig = [x for x in sig if x["points"] >= 25 or "Telegram" in x["text"]]
        out["code"] = []
    elif copied and (capture or malicious):
        verdict = "impersonation"
    elif copied:
        verdict = "copies brand"
    elif malicious:
        verdict = "malicious"
    elif capture and brand:
        verdict = "payment capture"
    elif not brand and not capture and not malicious and (not out["ui"] or out["ui"]["score"] < 0.2)             and (not out["visual"] or out["visual"]["score"] < 0.35) and len(text) > 400:
        verdict = "unrelated business"
    else:
        verdict = "name only"

    if verdict == "unrelated business":
        sig.append({"text": "Inspected: a separate, unrelated business; no brand copying, payment capture or malicious code", "points": -15, "ok": True, "kind": "verdict"})
    elif verdict == "parked":
        sig.append({"text": "Parked or for-sale domain: nothing live yet (kept on watch in case it's activated)", "points": -5, "ok": True, "kind": "verdict"})
    out["verdict"] = verdict
    out["signals"] = sig
    return out
