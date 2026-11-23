"""Network hunters: DNS resolution, RDAP registration data, Certificate Transparency (crt.sh), IP geolocation."""
import concurrent.futures as cf
import datetime as dt
import time

import dns.exception
import dns.resolver
import httpx

_resolver = dns.resolver.Resolver()
_resolver.timeout = 2.5
_resolver.lifetime = 4.0


def _q(host, rtype):
    try:
        return [r.to_text().rstrip(".") for r in _resolver.resolve(host, rtype)]
    except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer, dns.resolver.NoNameservers, dns.exception.Timeout,
            dns.name.LabelTooLong, dns.name.EmptyLabel, ValueError):
        return []
    except Exception:
        return []


def resolve(host: str) -> dict | None:
    """A/NS/MX for a host; None when the name does not exist."""
    a = _q(host, "A")
    if not a:
        return None
    return {"host": host, "a": a, "ns": sorted(_q(".".join(host.split(".")[-2:]), "NS")), "mx": _q(host, "MX")}


def resolve_many(hosts, workers=48):
    out = {}
    with cf.ThreadPoolExecutor(workers) as ex:
        for h, r in zip(hosts, ex.map(resolve, hosts)):
            if r:
                out[h] = r
    return out


# ---------- RDAP ----------
def rdap(domain: str) -> dict:
    """Registration date, registrar and abuse contact via rdap.org (follows to the right registry)."""
    try:
        r = httpx.get(f"https://rdap.org/domain/{domain}", timeout=10, follow_redirects=True)
        if r.status_code != 200:
            return {}
        j = r.json()
    except (httpx.HTTPError, ValueError):
        return {}
    info = {"registrar": None, "created": None, "abuse_email": None, "status": j.get("status", [])}
    for e in j.get("events", []):
        if e.get("eventAction") == "registration":
            info["created"] = e.get("eventDate")
    for ent in j.get("entities", []):
        roles = ent.get("roles", [])
        if "registrar" in roles:
            info["registrar"] = _vcard_name(ent) or info["registrar"]
            for sub in ent.get("entities", []):
                if "abuse" in sub.get("roles", []):
                    info["abuse_email"] = _vcard_email(sub)
        if "abuse" in roles and not info["abuse_email"]:
            info["abuse_email"] = _vcard_email(ent)
    return info


def _vcard_name(ent):
    for item in (ent.get("vcardArray") or [None, []])[1]:
        if item[0] == "fn":
            return item[3]
    return None


def _vcard_email(ent):
    for item in (ent.get("vcardArray") or [None, []])[1]:
        if item[0] == "email":
            return item[3]
    return None


def age_days(iso: str | None) -> float | None:
    if not iso:
        return None
    try:
        t = dt.datetime.fromisoformat(iso.replace("Z", "+00:00"))
        return (dt.datetime.now(dt.timezone.utc) - t).total_seconds() / 86400
    except ValueError:
        return None


# ---------- Certificate Transparency ----------
def crtsh(term: str, days: int = 30) -> list[dict]:
    """Recent certificates whose names contain `term` (crt.sh full-text). Slow: give it time."""
    url = "https://crt.sh/"
    for attempt in range(2):
        try:
            r = httpx.get(url, params={"q": f"%{term}%", "output": "json"}, timeout=45)
            if r.status_code == 200:
                rows = r.json()
                break
        except (httpx.HTTPError, ValueError):
            pass
        time.sleep(2)
    else:
        return []
    cutoff = dt.datetime.utcnow() - dt.timedelta(days=days)
    seen, out = set(), []
    for c in rows:
        try:
            nb = dt.datetime.fromisoformat(c["not_before"][:19])
        except (KeyError, ValueError):
            continue
        if nb < cutoff:
            continue
        for name in str(c.get("name_value", "")).split("\n"):
            name = name.strip().lower().lstrip("*.")
            if name and ":" not in name and "." in name and " " not in name and name not in seen:
                seen.add(name)
                out.append({"host": name, "not_before": c["not_before"], "issuer": c.get("issuer_name", "")})
    return out


# ---------- IP geolocation ----------
def geolocate(ips: list[str]) -> dict:
    """ip-api.com batch (free, no key, 100 IPs per call)."""
    out = {}
    ips = [i for i in dict.fromkeys(ips) if i]
    for i in range(0, len(ips), 100):
        try:
            r = httpx.post("http://ip-api.com/batch?fields=status,query,country,countryCode,city,lat,lon,as,org",
                           json=ips[i:i + 100], timeout=10)
            for g in r.json():
                if g.get("status") == "success":
                    out[g["query"]] = g
        except (httpx.HTTPError, ValueError):
            pass
    return out
