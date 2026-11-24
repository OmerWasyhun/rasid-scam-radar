"""Social media & paid ads sweep.

- Meta Ad Library (Facebook, Instagram, Messenger, WhatsApp, Threads): ads mentioning a watched entity, run by a
  Page that isn't the entity. Limitation stated by Meta: ads that never reached the EU are returned only when they
  are about social issues, elections or politics, so UAE-only commercial scam ads may not appear. The paste-an-ad /
  screenshot inspector covers those.
- Google Ads Transparency Center (via SerpApi), UAE region: advertisers running ads for the entity's name or
  domain who are not the entity.
Every landing domain found is investigated like any other suspect site.
"""
import re
from urllib.parse import urlparse

import httpx

from .. import cluster, config, db, generator
from ..lexicon import detect_langs, lure_hits
from ..pipeline import investigate, refresh_official_cache, watch_bases

UAE_GOOGLE_REGION = "2784"
DOMAIN_RE = re.compile(r"\b((?:[a-z0-9-]+\.)+[a-z]{2,})\b", re.I)


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def _is_entity(name: str, w: dict) -> bool:
    n = _norm(name)
    keys = {_norm(w["name"])} | {_norm(d.split(".")[0]) for d in w["official_domains"]}
    return any(k and (k in n or n in k) for k in keys if len(k) >= 3)


def meta_ads(term: str, countries=("AE",)) -> list[dict]:
    if not config.META_ACCESS_TOKEN:
        raise RuntimeError("META_ACCESS_TOKEN is not set. Add it to .env to sweep the Meta Ad Library.")
    fields = ("id,page_id,page_name,ad_snapshot_url,ad_creative_bodies,ad_creative_link_captions,ad_creative_link_titles,"
              "ad_creative_link_descriptions,ad_delivery_start_time,publisher_platforms,languages")
    r = httpx.get(f"https://graph.facebook.com/{config.META_GRAPH_VERSION}/ads_archive", timeout=30, params={
        "access_token": config.META_ACCESS_TOKEN, "search_terms": term[:100], "ad_type": "ALL",
        "ad_reached_countries": str(list(countries)).replace("'", '"'), "ad_active_status": "ACTIVE",
        "fields": fields, "limit": 100})
    j = r.json()
    if r.status_code != 200:
        raise RuntimeError(f"Meta Ad Library: {(j.get('error') or {}).get('message', r.status_code)}")
    return j.get("data", [])


def google_ads(term: str) -> list[dict]:
    if not config.SERPAPI_KEY:
        raise RuntimeError("SERPAPI_KEY is not set. Add it to .env to search the Google Ads Transparency Center.")
    r = httpx.get("https://serpapi.com/search.json", timeout=40, params={
        "engine": "google_ads_transparency_center", "text": term, "region": UAE_GOOGLE_REGION,
        "num": 100, "api_key": config.SERPAPI_KEY})
    j = r.json()
    if r.status_code != 200 or j.get("error"):
        raise RuntimeError(f"Google Ads Transparency: {j.get('error') or r.status_code}")
    return j.get("ad_creatives", [])


def sweep(watch_id: int, job_id: str):
    log = lambda m: db.job_log(job_id, m)
    try:
        refresh_official_cache()
        w = db.get_watch(watch_id)
        bases = watch_bases(w)
        hosts, extra, ids, ran = {}, {}, [], 0

        # --- Meta (Facebook / Instagram / WhatsApp / Messenger / Threads)
        if config.META_ACCESS_TOKEN:
            ran += 1
            log(f"Meta Ad Library: active ads mentioning “{w['name']}” that reached the UAE")
            try:
                ads = meta_ads(w["name"])
            except RuntimeError as e:
                ads = []
                log(str(e))
            log(f"{len(ads)} Meta ads returned")
            for ad in ads:
                if _is_entity(ad.get("page_name", ""), w):
                    continue
                text = " ".join((ad.get("ad_creative_bodies") or []) + (ad.get("ad_creative_link_titles") or [])
                                + (ad.get("ad_creative_link_descriptions") or []))
                captions = " ".join(ad.get("ad_creative_link_captions") or [])
                doms = [d.lower() for d in DOMAIN_RE.findall(captions + " " + text)]
                doms = [d for d in doms if generator.registrable(d) not in generator.OFFICIAL_CACHE
                        and not d.endswith(("facebook.com", "fb.me", "instagram.com", "whatsapp.com", "wa.me"))]
                lures = lure_hits(text)
                sig = [{"text": f"Meta ad by Page “{ad.get('page_name')}”, which is not {w['name']}", "points": 20},
                       {"text": "Runs on " + ", ".join(p.lower() for p in ad.get("publisher_platforms") or []), "points": 0}]
                if lures:
                    sig.append({"text": "Ad text uses lures: " + ", ".join(sorted({l['theme'] for l in lures})), "points": 15})
                if doms:
                    for d in doms[:2]:
                        p, why = generator.similarity(d, bases)
                        hosts[d] = (max(p, 10), why or f"landing page of a Meta ad mentioning {w['name']}")
                        extra[d] = {"signals": sig, "evidence": {"meta_ad": ad}}
                else:
                    sc = min(100, sum(s["points"] for s in sig) + 15)
                    ids.append(db.upsert_case(
                        "ads", f"meta:{ad.get('id')}", f"Meta ad: {ad.get('page_name')}", sc, target=w["name"], watch_id=w["id"],
                        langs=detect_langs(text) or ["EN"], where_txt="Meta Ad Library · " + ", ".join(ad.get("publisher_platforms") or []),
                        signals=sig + [{"text": "No landing link in the ad: contact is probably by message or WhatsApp", "points": 15}],
                        evidence={"meta_ad": ad, "text": text}, features={}))

        # --- Google Ads Transparency Center (UAE)
        if config.SERPAPI_KEY:
            ran += 1
            for term in dict.fromkeys([w["name"]] + w["official_domains"][:1]):
                log(f"Google Ads Transparency Center (UAE): “{term}”")
                try:
                    creatives = google_ads(term)
                except RuntimeError as e:
                    creatives = []
                    log(str(e))
                log(f"{len(creatives)} Google ad creatives returned")
                for c in creatives:
                    if _is_entity(c.get("advertiser", ""), w):
                        continue
                    host = (urlparse(c.get("link") or "").hostname or "").lower()
                    sig = [{"text": f"Google ad by “{c.get('advertiser')}”, which is not {w['name']}", "points": 20},
                           {"text": f"Shown for {c.get('total_days_shown', '?')} days, format {c.get('format', '?')}", "points": 0}]
                    if host and "google." not in host and generator.registrable(host) not in generator.OFFICIAL_CACHE:
                        p, why = generator.similarity(host, bases)
                        hosts[host] = (max(p, 10), why or f"advertised while searching for {w['name']}")
                        extra[host] = {"signals": sig, "evidence": {"google_ad": c}}
                    else:
                        ids.append(db.upsert_case(
                            "ads", f"gads:{c.get('ad_creative_id')}", f"Google ad: {c.get('advertiser')}", 45, target=w["name"],
                            watch_id=w["id"], langs=["EN"], where_txt="Google Ads Transparency Center (UAE)", signals=sig,
                            evidence={"google_ad": c}, features={}))
        if not ran:
            raise RuntimeError("Add META_ACCESS_TOKEN and/or SERPAPI_KEY to .env to sweep social media and Google ads.")
        log(f"{len(hosts)} landing domains to investigate")
        if hosts:
            ids += investigate(hosts, w, log, {h: "ads" for h in hosts}, extra)
        cluster.recluster()
        log(f"Done: {len(ids)} ads and landing pages stored")
        db.job_done(job_id, {"cases": ids})
    except Exception as e:
        log(f"Error: {e}")
        db.job_done(job_id, {"error": str(e)}, status="error")
