"""Ads & Search Inspector.

- Search sweep: Google results from the UAE (via SerpAPI) for lure queries in several languages; any result
  whose domain imitates the watched entity and is not official becomes a case. Sponsored results are marked.
- Ad inspection: an analyst pastes ad text, a landing URL and/or a screenshot. Claude reads the screenshot,
  the landing page is analysed (including cloaking), and the ad text is checked for lures.
"""
import re
from urllib.parse import urlparse

import httpx

from .. import analyzer, cluster, db, enrich, generator, hunters, llm, verify
from ..config import SERPAPI_KEY
from ..lexicon import detect_langs, lure_hits
from ..pipeline import investigate, refresh_official_cache, watch_bases
from ..seeds import SEARCH_TEMPLATES

HL = {"EN": "en", "AR": "ar", "HI": "hi", "UR": "ur", "ML": "ml", "TA": "ta", "TL": "tl", "BN": "bn", "RU": "ru", "ZH": "zh-cn"}
URL_RE = re.compile(r"https?://[^\s\"'<>]+|(?:[a-z0-9-]+\.)+(?:com|net|org|ae|top|xyz|shop|online|info|live|vip|cc|site)\b[^\s]*", re.I)


def serp(query: str, hl: str) -> dict:
    r = httpx.get("https://serpapi.com/search.json", timeout=30, params={
        "engine": "google", "q": query, "gl": "ae", "hl": hl, "location": "Abu Dhabi,United Arab Emirates",
        "num": 20, "api_key": SERPAPI_KEY})
    if r.status_code != 200:
        raise RuntimeError(f"SerpAPI {r.status_code}: {r.text[:200]}")
    return r.json()


def sweep(watch_id: int, job_id: str):
    log = lambda m: db.job_log(job_id, m)
    try:
        if not SERPAPI_KEY:
            raise RuntimeError("SERPAPI_KEY is not set. Add it to .env to run the search sweep.")
        refresh_official_cache()
        w = db.get_watch(watch_id)
        bases = watch_bases(w)
        templates = SEARCH_TEMPLATES.get(w["lure"], SEARCH_TEMPLATES["brand"])
        hosts, extra = {}, {}
        for lang, qs in templates.items():
            for q in qs:
                query = q.format(b=w["name"])
                log(f"Google (UAE, {lang}): {query}")
                res = serp(query, HL.get(lang, "en"))
                rows = [("ad", a) for a in res.get("ads", [])] + [("organic", o) for o in res.get("organic_results", [])]
                for kind, item in rows:
                    host = (urlparse(item.get("link") or "").hostname or "").lower()
                    if not host or generator.registrable(host) in generator.OFFICIAL_CACHE:
                        continue
                    p, why = generator.similarity(host, bases)
                    text = f"{item.get('title', '')} {item.get('snippet', '') or item.get('description', '')}"
                    lures = lure_hits(text)
                    if p < 16 and not (lures and w["name"].lower() in text.lower()):
                        continue
                    hosts[host] = (max(p, 10), why or "uses the entity name in a search result")
                    sig = [{"text": f"{'Sponsored ad' if kind == 'ad' else 'Search result'} for “{query}” ({lang})", "points": 10 if kind == "ad" else 5}]
                    if lures:
                        sig.append({"text": "Result text uses lures: " + ", ".join(sorted({l['theme'] for l in lures})), "points": 5})
                    extra[host] = {"signals": sig, "evidence": {"search": {"query": query, "lang": lang, "kind": kind,
                                                                           "title": item.get("title"), "snippet": item.get("snippet")}}}
        log(f"{len(hosts)} suspicious result domains")
        ids = investigate(hosts, w, log, {h: "ads" for h in hosts}, extra)
        cluster.recluster()
        log(f"Done: {len(ids)} sites stored")
        db.job_done(job_id, {"cases": ids})
    except Exception as e:
        log(f"Error: {e}")
        db.job_done(job_id, {"error": str(e)}, status="error")


def inspect(text: str = "", url: str = "", image_b64: str = "", media_type: str = "image/png") -> int:
    """Synchronous single-ad inspection; returns the case id."""
    refresh_official_cache()
    read = llm.read_ad_image(image_b64, media_type) if image_b64 else None
    full_text = "\n".join(x for x in [text, (read or {}).get("text") or ""] if x)
    if not url:
        url = (read or {}).get("landing_url") or ""
    if not url:
        m = URL_RE.search(full_text)
        url = m.group(0) if m else ""
    if url and not url.startswith("http"):
        url = "https://" + url
    host = (urlparse(url).hostname or "").lower() if url else ""
    watches = db.list_watch()
    target, best, why, wid = None, 0, "", None
    for w in watches:
        claimed = ((read or {}).get("brand_claimed") or "").lower()
        if w["name"].lower() in full_text.lower() or (claimed and (claimed in w["name"].lower() or w["name"].lower() in claimed)):
            if not best:
                target, wid = w["name"], w["id"]
        if host:
            p, r = generator.similarity(host, watch_bases(w))
            if p > best:
                best, why, target, wid = p, r, w["name"], w["id"]
    sig = []
    lures = lure_hits(full_text)
    if lures:
        sig.append({"text": "Ad text uses lures: " + ", ".join(sorted({l["theme"] for l in lures})), "points": 10, "kind": "content"})
    for f in ((read or {}).get("red_flags") or [])[:4]:
        sig.append({"text": f"Screenshot: {f}", "points": 0})
    page, rd, dns_info, age, geo, inspection = None, {}, None, None, None, None
    official = bool(host) and generator.registrable(host) in generator.OFFICIAL_CACHE
    if host and not official:
        dns_info = hunters.resolve(host)
        if dns_info:
            rd = hunters.rdap(generator.registrable(host))
            age = hunters.age_days(rd.get("created"))
            page = analyzer.analyze(host, [target] if target else [])
            geo = hunters.geolocate([dns_info["a"][0]]).get(dns_info["a"][0])
            wrow = db.get_watch(wid) if wid else None
            if page.get("reachable"):
                insp = verify.inspect(host, page, wrow)
                sig += insp.pop("signals", [])
                inspection = insp
            page.pop("_html", None)
            rep, rep_sig = enrich.reputation_signals(host, page.get("final_url"))
            sig += rep_sig
        else:
            sig.append({"text": f"Landing domain {host} does not resolve (taken down or not live yet)", "points": 0, "ok": True})
    sc, signals = analyzer.score(best, why, age, page, official=official, extra=sig)
    langs = detect_langs(full_text) or (page or {}).get("langs") or []
    title = (read or {}).get("offer") or (text[:80] if text else host or "Ad")
    key = "ad:" + (host or str(abs(hash(full_text))))
    feats = {}
    if page and page.get("reachable"):
        feats = {"favicon_hash": page.get("favicon_hash"), "dom_hash": page.get("dom_hash"),
                 "telegram": page.get("telegram_tokens"), "analytics": page.get("analytics_ids")}
    if dns_info:
        feats["ip"] = dns_info["a"][0]
    cid = db.upsert_case("ads", key, f"Ad: {title}", sc, target=target, watch_id=wid, langs=langs,
                         lat=geo["lat"] if geo else None, lon=geo["lon"] if geo else None,
                         where_txt=(f"Ad landing · {geo.get('city')}, {geo.get('country')}" if geo else "Ad (no live landing page)"),
                         signals=signals, evidence={"text": full_text, "url": url, "screenshot_read": read, "page": page, "inspection": inspection,
                                                     "rdap": rd, "dns": dns_info, "geo": geo}, features=feats)
    cluster.recluster()
    return cid
