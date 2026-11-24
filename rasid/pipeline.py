"""Hunts: generate lookalikes for an entity, find which exist (DNS + newly-registered list + CT logs),
analyse the live ones, score them and store them as cases."""
import concurrent.futures as cf
import threading
import time
import uuid

from . import analyzer, cluster, db, enrich, generator, hunters, nrd, verify
from .sensors.maps import norm_phone

ANALYZE_CAP = 25


def refresh_official_cache():
    generator.OFFICIAL_CACHE.clear()
    generator.OFFICIAL_CACHE.update(generator.registrable(d) for d in db.all_official_domains())


def watch_bases(w: dict) -> list[str]:
    bases = []
    for d in w["official_domains"]:
        bases += generator.slugs(w["name"], d)[:1]
    bases += generator.slugs(w["name"])
    return list(dict.fromkeys(b for b in bases if len(b) >= 4))


def _store(host, w, sensor, sim, why, info, ages, geo, extra_sig=None, extra_ev=None):
    official = generator.registrable(host) in generator.OFFICIAL_CACHE
    page = info.get("page")
    age = ages.get(host)
    sc, sig = analyzer.score(sim, why, age, page, official=official, extra=extra_sig)
    ip = (info.get("dns") or {}).get("a", [None])[0]
    g = geo.get(ip) if ip else None
    feats = {}
    if page and page.get("reachable"):
        feats = {"favicon_hash": page.get("favicon_hash"), "dom_hash": page.get("dom_hash"),
                 "telegram": page.get("telegram_tokens", []) + page.get("telegram_chats", []),
                 "analytics": page.get("analytics_ids"), "whatsapp": page.get("whatsapp"),
                 "phone": sorted({norm_phone(p) for p in (page.get("phones") or []) + (page.get("whatsapp") or []) if norm_phone(p)})}
    if ip:
        feats["ip"] = ip
    if info.get("dns"):
        feats["ns"] = info["dns"].get("ns")
    langs = (page or {}).get("langs") or []
    ev = {"dns": info.get("dns"), "rdap": info.get("rdap"), "page": page, "geo": g}
    ev.update(extra_ev or {})
    return db.upsert_case(
        sensor, host, generator.to_unicode(host) if "xn--" in host else host, sc,
        target=w["name"], watch_id=w["id"], langs=langs,
        lat=g["lat"] if g else None, lon=g["lon"] if g else None,
        where_txt=f"{g.get('city') or ''}, {g.get('country')} · {g.get('as') or g.get('org') or ''}".strip(", ") if g else None,
        signals=sig, evidence=ev, features=feats,
    )


def investigate(hosts: dict, w: dict, log, sensor_of=None, extra_of=None):
    """hosts: {host: (sim_points, reason)}. Resolves, enriches, analyses and stores."""
    log(f"Resolving {len(hosts)} names in DNS")
    live = hunters.resolve_many(list(hosts))
    log(f"{len(live)} names resolve")
    order = sorted(live, key=lambda h: -hosts[h][0])[:ANALYZE_CAP]
    brand_names = [w["name"]] + [d.split(".")[0] for d in w["official_domains"]]
    info = {h: {"dns": live[h]} for h in order}

    def work(h):
        reg = generator.registrable(h)
        rd = hunters.rdap(reg)
        page = analyzer.analyze(h, brand_names)
        rep, rep_sig = enrich.reputation_signals(h, (page or {}).get("final_url"))
        insp = None
        if page.get("reachable"):
            try:
                insp = verify.inspect(h, page, w)
            except Exception as e:  # never let one odd page break a hunt
                insp = {"verdict": "inspection failed", "error": str(e)[:200], "signals": []}
        page.pop("_html", None)
        return h, rd, page, rep, rep_sig, insp

    log(f"Analysing {len(order)} live sites (RDAP, page, fingerprints)")
    with cf.ThreadPoolExecutor(16) as ex:
        for h, rd, page, rep, rep_sig, insp in ex.map(work, order):
            info[h]["inspection"] = insp
            info[h]["rdap"] = rd
            info[h]["page"] = page
            info[h]["reputation"] = rep
            info[h]["rep_sig"] = rep_sig
    ages = {h: hunters.age_days((info[h].get("rdap") or {}).get("created")) for h in order}
    for h in order:
        if ages[h] is None and extra_of and extra_of.get(h, {}).get("age"):
            ages[h] = extra_of[h]["age"]
    geo = hunters.geolocate([info[h]["dns"]["a"][0] for h in order])
    ids = []
    for h in order:
        ex = (extra_of or {}).get(h, {})
        insp = info[h].get("inspection") or {}
        ev = {**(ex.get("evidence") or {}), **({"reputation": info[h]["reputation"]} if any(info[h]["reputation"].values()) else {})}
        if insp:
            ev["inspection"] = {k: v for k, v in insp.items() if k != "signals"}
        ids.append(_store(h, w, (sensor_of or {}).get(h, "domains"), hosts[h][0], hosts[h][1], info[h], ages, geo,
                          (ex.get("signals") or []) + info[h]["rep_sig"] + (insp.get("signals") or []), ev))
    return ids


def hunt(watch_id: int, job_id: str, include_nrd=True, include_ct=True):
    w = db.get_watch(watch_id)
    log = lambda m: db.job_log(job_id, m)
    try:
        refresh_official_cache()
        dom = w["official_domains"][0] if w["official_domains"] else None
        cands = generator.generate(w["name"], dom, w["lure"])
        log(f"Generated {len(cands)} lookalike names for {w['name']}")
        bases = watch_bases(w)
        hosts = {}
        for c in cands:
            p, why = generator.similarity(c["domain"], bases)
            hosts[c["domain"]] = (max(p, 12), why or c["technique"])
        sensor_of, extra = {}, {}
        if include_nrd:
            log("Matching the newly-registered-domains lists (last 3 days)")
            for d, day in nrd.recent(3):
                p, why = generator.similarity(d, bases)
                if p >= 16:
                    hosts[d] = (p, why)
                    sensor_of[d] = "ct"
                    extra[d] = {"age": 1.0, "signals": [{"text": f"In the newly-registered list for {day}", "points": 5}],
                                "evidence": {"newborn": {"source": "whoisds NRD", "day": day}}}
        if include_ct:
            for b in bases[:1]:
                log(f"Searching Certificate Transparency logs for '{b}'")
                for c in hunters.crtsh(b, days=30):
                    p, why = generator.similarity(c["host"], bases)
                    if p >= 16:
                        hosts[c["host"]] = (p, why)
                        sensor_of[c["host"]] = "ct"
                        extra[c["host"]] = {"signals": [{"text": f"New TLS certificate issued {c['not_before'][:10]}", "points": 5}],
                                            "evidence": {"ct": c}}
        ids = investigate(hosts, w, log, sensor_of, extra)
        actors = cluster.recluster()
        flagged = [db.get_case(i) for i in ids]
        flagged = [c for c in flagged if c and c["score"] >= 50]
        log(f"Done: {len(ids)} live sites stored, {len(flagged)} scored 50 or more, {len(actors)} actors")
        db.job_done(job_id, {"cases": ids, "flagged": [c["id"] for c in flagged], "candidates": len(cands)})
    except Exception as e:  # report failures to the console instead of dying silently
        log(f"Error: {e}")
        db.job_done(job_id, {"error": str(e)}, status="error")


def start(kind, fn, *args):
    jid = uuid.uuid4().hex[:12]
    db.new_job(jid, kind)
    threading.Thread(target=fn, args=args + (jid,), daemon=True).start()
    return jid


def newborn_sweep(job_id: str):
    """Match every watchlist against the newly-registered list in one pass."""
    log = lambda m: db.job_log(job_id, m)
    try:
        refresh_official_cache()
        watches = db.list_watch()
        bases = {w["id"]: watch_bases(w) for w in watches}
        log("Downloading newly-registered-domains lists")
        rows = nrd.recent(3)
        log(f"{len(rows)} new domains to check against {len(watches)} watchlists")
        hits = {}
        for d, day in rows:
            for w in watches:
                p, why = generator.similarity(d, bases[w["id"]])
                if p >= 16:
                    hits.setdefault(w["id"], {})[d] = (p, why, day)
        total = []
        for wid, hs in hits.items():
            w = db.get_watch(wid)
            log(f"{w['name']}: {len(hs)} matches")
            extra = {d: {"age": 1.0, "signals": [{"text": f"In the newly-registered list for {v[2]}", "points": 5}],
                         "evidence": {"newborn": {"source": "whoisds NRD", "day": v[2]}}} for d, v in hs.items()}
            total += investigate({d: v[:2] for d, v in hs.items()}, w, log, {d: "ct" for d in hs}, extra)
        cluster.recluster()
        log(f"Done: {len(total)} newborn sites analysed")
        db.job_done(job_id, {"cases": total})
    except Exception as e:
        log(f"Error: {e}")
        db.job_done(job_id, {"error": str(e)}, status="error")


def poll_loop(minutes: int):
    while True:
        try:
            jid = uuid.uuid4().hex[:12]
            db.new_job(jid, "newborn-auto")
            newborn_sweep(jid)
        except Exception:
            pass
        time.sleep(minutes * 60)
