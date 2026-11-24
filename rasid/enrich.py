"""Third-party reputation for suspect sites: Google Safe Browsing and VirusTotal. (Screenshots are RASID's own: browser.py.)

Each function returns {} when its key is missing or the service fails, so the pipeline never depends on them.
"""
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


def safe_browsing_many(urls: list[str]) -> dict:
    """One Safe Browsing call for up to 500 URLs (e.g. every outbound link on a page)."""
    if not config.GOOGLE_SAFE_BROWSING_KEY or not urls:
        return {}
    body = {
        "client": {"clientId": "rasid", "clientVersion": "1.0"},
        "threatInfo": {
            "threatTypes": ["MALWARE", "SOCIAL_ENGINEERING", "UNWANTED_SOFTWARE", "POTENTIALLY_HARMFUL_APPLICATION"],
            "platformTypes": ["ANY_PLATFORM"], "threatEntryTypes": ["URL"], "threatEntries": [{"url": u} for u in urls[:500]],
        },
    }
    try:
        r = httpx.post("https://safebrowsing.googleapis.com/v4/threatMatches:find",
                       params={"key": config.GOOGLE_SAFE_BROWSING_KEY}, json=body, timeout=12)
        if r.status_code != 200:
            return {}
        return {"listed": sorted({m["threat"]["url"] for m in r.json().get("matches", []) if m.get("threat", {}).get("url")})}
    except (httpx.HTTPError, ValueError, KeyError):
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


def reputation_signals(host: str, url: str | None = None) -> tuple[dict, list[dict]]:
    """Run Safe Browsing + VirusTotal (fast) and turn them into scoring signals."""
    url = url or f"http://{host}/"
    sb, vt = safe_browsing(url), virustotal(host)
    sig = []
    if sb.get("listed"):
        sig.append({"text": "Google Safe Browsing lists it as " + ", ".join(t.replace("_", " ").lower() for t in sb["threats"]), "points": 25, "kind": "content"})
    if vt.get("malicious", 0) >= 2:
        sig.append({"text": f"{vt['malicious']} security vendors on VirusTotal flag it as malicious", "points": 15, "kind": "content"})
    elif vt.get("malicious", 0) == 1 or vt.get("suspicious", 0) >= 2:
        sig.append({"text": "VirusTotal: flagged by one vendor or marked suspicious", "points": 5, "kind": "content"})
    return {"safe_browsing": sb, "virustotal": vt}, sig
