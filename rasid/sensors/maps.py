"""Maps Verifier: Google Places API (New) listings for a brand, checked against the official registry.

A listing is suspicious when its phone or website does not match the brand's official ones, when a bank
or telco "branch" uses a mobile/WhatsApp number, or when one number appears on several brands' listings.
"""
import re

import httpx

from .. import cluster, db, generator
from ..config import GOOGLE_MAPS_API_KEY

PLACES_URL = "https://places.googleapis.com/v1/places:searchText"
FIELDS = ("places.id,places.displayName,places.formattedAddress,places.location,places.nationalPhoneNumber,"
          "places.internationalPhoneNumber,places.websiteUri,places.googleMapsUri,places.userRatingCount,places.types,"
          "places.businessStatus")
CITIES = ["Abu Dhabi", "Dubai", "Sharjah", "Al Ain", "Ajman"]
QUERIES = ["{b} customer service", "{b} branch", "{b} office", "{b} خدمة العملاء"]
MOBILE = re.compile(r"^(?:\+?971|0)?5\d{8}$")
STUFFED = re.compile(r"24\s*/?\s*7|helpline|hotline|customer\s*care|refund|support\s*center|خدمة\s*العملاء", re.I)


def norm_phone(p: str | None) -> str:
    if not p:
        return ""
    d = re.sub(r"\D", "", p)
    if d.startswith("00971"):
        d = d[5:]
    elif d.startswith("971"):
        d = d[3:]
    return d.lstrip("0")


def search(query: str) -> list[dict]:
    r = httpx.post(PLACES_URL, timeout=20, json={"textQuery": query, "regionCode": "AE", "languageCode": "en"},
                   headers={"X-Goog-Api-Key": GOOGLE_MAPS_API_KEY, "X-Goog-FieldMask": FIELDS})
    if r.status_code != 200:
        raise RuntimeError(f"Places API {r.status_code}: {r.text[:200]}")
    return r.json().get("places", [])


def verify_place(p: dict, w: dict, official_domains: set, official_phones: set, phone_index: dict) -> tuple[int, list]:
    name = (p.get("displayName") or {}).get("text", "")
    phone = norm_phone(p.get("internationalPhoneNumber") or p.get("nationalPhoneNumber"))
    site = p.get("websiteUri") or ""
    host = (re.sub(r"^https?://", "", site).split("/")[0].lower()) if site else ""
    reg = generator.registrable(host) if host else ""
    sig = []
    brand_in_name = any(b.lower() in name.lower() for b in [w["name"]] + [d.split(".")[0] for d in w["official_domains"]])
    if not brand_in_name:
        return -1, []  # unrelated business, skip
    if reg and reg in official_domains:
        sig.append({"text": f"Website {host} is an official domain", "points": -40, "ok": True})
    elif reg:
        p_sim, why = generator.similarity(host, [generator.slugs(w["name"], d)[0] for d in w["official_domains"]] or generator.slugs(w["name"]))
        sig.append({"text": f"Website {host} is not on the official list" + (f" ({why})" if why else ""), "points": 25 + min(p_sim, 15)})
    else:
        sig.append({"text": "No website on the listing", "points": 5})
    if phone:
        if official_phones and phone in official_phones:
            sig.append({"text": "Phone matches the official registry", "points": -40, "ok": True})
        elif official_phones:
            sig.append({"text": "Phone is not in the brand's official registry", "points": 20})
        if MOBILE.match(phone):
            sig.append({"text": f"Uses a mobile number (+971 {phone[:2]} ••• {phone[-4:]}) for an official brand listing", "points": 25})
        others = phone_index.get(phone, set()) - {w["name"]}
        if others:
            sig.append({"text": "Same number appears on listings for " + ", ".join(sorted(others)[:4]), "points": 25})
    else:
        sig.append({"text": "No phone number on the listing", "points": 0, "ok": True})
    if STUFFED.search(name):
        sig.append({"text": f"Name stuffed with service keywords: “{name}”", "points": 10})
    if (p.get("userRatingCount") or 0) < 3:
        sig.append({"text": "Almost no reviews", "points": 5})
    return max(0, min(100, sum(s["points"] for s in sig))), sig


def scan(watch_id: int, job_id: str):
    log = lambda m: db.job_log(job_id, m)
    try:
        if not GOOGLE_MAPS_API_KEY:
            raise RuntimeError("GOOGLE_MAPS_API_KEY is not set. Add it to .env to run the Maps Verifier.")
        w = db.get_watch(watch_id)
        official_domains = {generator.registrable(d) for d in db.all_official_domains()}
        official_phones = {norm_phone(p) for p in w["official_phones"]}
        places = {}
        for city in CITIES:
            for q in QUERIES[:2] if city != "Abu Dhabi" else QUERIES:
                query = q.format(b=w["name"]) + f" {city}"
                log(f"Places search: {query}")
                for p in search(query):
                    places[p["id"]] = p
        log(f"{len(places)} listings found")
        # phone index across everything already stored, so reuse across brands shows up
        phone_index = {}
        for c in db.list_cases(limit=5000):
            for ph in (c["features"] or {}).get("phone", []) or []:
                phone_index.setdefault(ph, set()).add(c["target"])
        for p in places.values():
            ph = norm_phone(p.get("internationalPhoneNumber") or p.get("nationalPhoneNumber"))
            if ph:
                phone_index.setdefault(ph, set()).add(w["name"])
        ids = []
        for p in places.values():
            sc, sig = verify_place(p, w, official_domains, official_phones, phone_index)
            if sc < 0:
                continue
            loc = p.get("location") or {}
            ph = norm_phone(p.get("internationalPhoneNumber") or p.get("nationalPhoneNumber"))
            site = p.get("websiteUri") or ""
            ids.append(db.upsert_case(
                "maps", "place:" + p["id"], (p.get("displayName") or {}).get("text", "Listing"), sc,
                target=w["name"], watch_id=w["id"], langs=["EN"], lat=loc.get("latitude"), lon=loc.get("longitude"),
                where_txt="Google Maps · " + (p.get("formattedAddress") or ""), signals=sig,
                evidence={"place": p}, features={"phone": [ph] if ph else [], "site": site},
            ))
        cluster.recluster()
        log(f"Done: {len(ids)} listings verified, {sum(1 for i in ids if db.get_case(i)['score'] >= 50)} flagged")
        db.job_done(job_id, {"cases": ids})
    except Exception as e:
        log(f"Error: {e}")
        db.job_done(job_id, {"error": str(e)}, status="error")
