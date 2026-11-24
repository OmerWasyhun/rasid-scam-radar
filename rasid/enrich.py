"""Third-party enrichment for suspect sites: Google Safe Browsing, VirusTotal, urlscan.io screenshots.

Each function returns {} when its key is missing or the service fails, so the pipeline never depends on them.
"""
import time

import httpx

from . import config


def safe_browsing(url: str) -> dict:
    """Google Safe Browsing Lookup API v4: is this URL on Google's phishing/malware lists?"""
    if not config.GOOGLE_SAFE_BROWSING_KEY:
        return {}
    body = {
        "client": {"clientId": "rasid", "clientVersion": "1.0"},
        "threatInfo": {
            "threatTypes": ["MALWARE", "SOCIAL_ENGINEERING", "UNWANTED_SOFTWARE", "POTENTIALLY_HARMFUL_APPLICATION"],
            "platformTypes": ["ANY_PLATFORM"], "threatEntryTypes": ["URL"], "threatEntries": [{"url": url}],
        },
    }
    try:
        r = httpx.post("https://safebrowsing.googleapis.com/v4/threatMatches:find",
                       params={"key": config.GOOGLE_SAFE_BROWSING_KEY}, json=body, timeout=10)
        if r.status_code != 200:
            return {"error": f"HTTP {r.status_code}"}
        matches = r.json().get("matches", [])
        return {"listed": bool(matches), "threats": sorted({m.get("threatType") for m in matches})}
    except (httpx.HTTPError, ValueError):
        return {}


def virustotal(domain: str) -> dict:
    """VirusTotal v3 domain report: how many security vendors flag the domain."""
    if not config.VIRUSTOTAL_API_KEY:
        return {}
    try:
        r = httpx.get(f"https://www.virustotal.com/api/v3/domains/{domain}", headers={"x-apikey": config.VIRUSTOTAL_API_KEY}, timeout=12)
        if r.status_code == 404:
            return {"known": False}
        if r.status_code != 200:
            return {"error": f"HTTP {r.status_code}"}
        a = r.json().get("data", {}).get("attributes", {})
        stats = a.get("last_analysis_stats", {})
        return {"known": True, "malicious": stats.get("malicious", 0), "suspicious": stats.get("suspicious", 0),
                "harmless": stats.get("harmless", 0), "reputation": a.get("reputation"),
                "categories": sorted(set((a.get("categories") or {}).values()))[:5]}
    except (httpx.HTTPError, ValueError):
        return {}


def urlscan_submit(url: str) -> dict:
    """Submit to urlscan.io (unlisted, so the scammer doesn't see it in public feeds). Returns uuid + result link."""
    if not config.URLSCAN_API_KEY:
        return {}
    try:
        r = httpx.post("https://urlscan.io/api/v1/scan/", timeout=15,
                       headers={"API-Key": config.URLSCAN_API_KEY, "Content-Type": "application/json"},
                       json={"url": url, "visibility": "unlisted", "tags": ["rasid"]})
        if r.status_code not in (200, 201):
            return {"error": f"HTTP {r.status_code}: {r.text[:120]}"}
        j = r.json()
        return {"uuid": j.get("uuid"), "result": j.get("result"),
                "screenshot": f"https://urlscan.io/screenshots/{j.get('uuid')}.png" if j.get("uuid") else None}
    except (httpx.HTTPError, ValueError):
        return {}


def urlscan_result(uuid: str, wait_s: int = 60) -> dict:
    """Poll until the scan finishes (usually 10–30 s). Returns verdict, final URL, page title, screenshot."""
    deadline = time.time() + wait_s
    while time.time() < deadline:
        try:
            r = httpx.get(f"https://urlscan.io/api/v1/result/{uuid}/", timeout=15)
            if r.status_code == 200:
                j = r.json()
                v = (j.get("verdicts") or {}).get("overall", {})
                page = j.get("page") or {}
                return {"uuid": uuid, "done": True, "malicious": bool(v.get("malicious")), "score": v.get("score"),
                        "brands": [b.get("name") for b in v.get("brands", []) if isinstance(b, dict)] or v.get("brands", []),
                        "final_url": page.get("url"), "title": page.get("title"), "country": page.get("country"),
                        "screenshot": f"https://urlscan.io/screenshots/{uuid}.png",
                        "report": f"https://urlscan.io/result/{uuid}/"}
        except (httpx.HTTPError, ValueError):
            pass
        time.sleep(5)
    return {"uuid": uuid, "done": False, "screenshot": f"https://urlscan.io/screenshots/{uuid}.png",
            "report": f"https://urlscan.io/result/{uuid}/"}


def reputation_signals(host: str, url: str | None = None) -> tuple[dict, list[dict]]:
    """Run Safe Browsing + VirusTotal (fast) and turn them into scoring signals."""
    url = url or f"http://{host}/"
    sb, vt = safe_browsing(url), virustotal(host)
    sig = []
    if sb.get("listed"):
        sig.append({"text": "Google Safe Browsing lists it as " + ", ".join(t.replace("_", " ").lower() for t in sb["threats"]), "points": 25})
    if vt.get("malicious", 0) >= 2:
        sig.append({"text": f"{vt['malicious']} security vendors on VirusTotal flag it as malicious", "points": 15})
    elif vt.get("malicious", 0) == 1 or vt.get("suspicious", 0) >= 2:
        sig.append({"text": "VirusTotal: flagged by one vendor or marked suspicious", "points": 5})
    return {"safe_browsing": sb, "virustotal": vt}, sig
