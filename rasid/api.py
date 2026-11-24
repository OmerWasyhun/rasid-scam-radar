"""FastAPI server: the JSON API plus the map console (web/)."""
import threading
import time
from collections import Counter

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import cluster, config, db, generator, llm, pipeline, seeds, strike
from .sensors import ads, jobs, maps

app = FastAPI(title="RASID", version="0.2")
WEB = config.ROOT / "web"


@app.on_event("startup")
def _startup():
    seeds.ensure_defaults()
    pipeline.refresh_official_cache()
    if config.CT_POLL:
        threading.Thread(target=pipeline.poll_loop, args=(config.CT_POLL_MINUTES,), daemon=True).start()


# ---------- status ----------
@app.get("/api/status")
def status():
    return {"keys": config.key_status(), "watchlists": db.watch_count(), "time": time.time()}


@app.get("/api/stats")
def stats():
    cases = db.list_cases(limit=5000)
    now = time.time()
    hourly = [0] * 24
    for c in cases:
        h = int((now - c["created"]) // 3600)
        if 0 <= h < 24:
            hourly[23 - h] += c["score"]
    by_sensor = Counter(c["sensor"] for c in cases if c["score"] >= 50)
    langs = Counter(l for c in cases if c["score"] >= 50 for l in c["langs"])
    return {
        "total": len(cases), "flagged": sum(1 for c in cases if c["score"] >= 50),
        "critical": sum(1 for c in cases if c["score"] >= 80),
        "actors": len({c["actor"] for c in cases if c["actor"]}),
        "by_sensor": by_sensor, "langs": langs, "hourly": hourly,
    }


# ---------- watchlists ----------
class WatchIn(BaseModel):
    kind: str = Field(pattern="^(brand|event|jobs)$")
    name: str = Field(min_length=2, max_length=120)
    official_domains: list[str] = []
    official_phones: list[str] = []
    lure: str = "brand"
    langs: list[str] = seeds.DEFAULT_LANGS
    date: str | None = None


@app.get("/api/watchlists")
def watchlists():
    return db.list_watch()


@app.post("/api/watchlists")
def add_watch(w: WatchIn):
    lure = w.lure if w.lure in ("brand", "event", "religious", "jobs") else "brand"
    doms = [d.strip().lower().removeprefix("https://").removeprefix("http://").split("/")[0] for d in w.official_domains if d.strip()]
    wid = db.add_watch(w.kind, w.name.strip(), doms, [p.strip() for p in w.official_phones if p.strip()], lure, w.langs, w.date)
    pipeline.refresh_official_cache()
    return db.get_watch(wid)


@app.delete("/api/watchlists/{wid}")
def del_watch(wid: int):
    db.delete_watch(wid)
    return {"ok": True}


@app.get("/api/watchlists/{wid}/candidates")
def candidates(wid: int):
    w = db.get_watch(wid)
    if not w:
        raise HTTPException(404, "No such watchlist")
    dom = w["official_domains"][0] if w["official_domains"] else None
    cands = generator.generate(w["name"], dom, w["lure"])
    words = {"event": "tickets", "religious": "visa", "jobs": "job"}.get(w["lure"], "fine")
    return {"watch": w, "candidates": cands, "seed_words": {l: seeds.SEED_WORDS[words].get(l) for l in w["langs"] if seeds.SEED_WORDS[words].get(l)}}


# ---------- hunts / sensors ----------
class HuntIn(BaseModel):
    watch_id: int | None = None
    name: str | None = None          # command bar: hunt an entity by name (creates a watchlist if new)
    official_domain: str | None = None
    lure: str = "brand"


@app.post("/api/hunt")
def hunt(h: HuntIn):
    wid = h.watch_id
    if not wid:
        if not h.name:
            raise HTTPException(400, "Give watch_id or name")
        existing = [w for w in db.list_watch() if w["name"].lower() == h.name.strip().lower()]
        if existing:
            wid = existing[0]["id"]
        else:
            wid = db.add_watch("brand" if h.lure in ("brand", "jobs") else "event", h.name.strip(),
                               [h.official_domain] if h.official_domain else [], [], h.lure, seeds.DEFAULT_LANGS)
    if not db.get_watch(wid):
        raise HTTPException(404, "No such watchlist")
    return {"job": pipeline.start("hunt", pipeline.hunt, wid), "watch_id": wid}


@app.post("/api/newborn")
def newborn():
    return {"job": pipeline.start("newborn", pipeline.newborn_sweep)}


@app.post("/api/maps/{wid}")
def maps_scan(wid: int):
    if not config.GOOGLE_MAPS_API_KEY:
        raise HTTPException(400, "Maps Verifier needs GOOGLE_MAPS_API_KEY in .env")
    return {"job": pipeline.start("maps", maps.scan, wid)}


@app.post("/api/search/{wid}")
def search_sweep(wid: int):
    if not config.SERPAPI_KEY:
        raise HTTPException(400, "Search sweep needs SERPAPI_KEY in .env")
    return {"job": pipeline.start("search", ads.sweep, wid)}


class AdIn(BaseModel):
    text: str = ""
    url: str = ""
    image_b64: str = ""
    media_type: str = "image/png"


@app.post("/api/ads/inspect")
def inspect_ad(a: AdIn):
    if not (a.text or a.url or a.image_b64):
        raise HTTPException(400, "Give ad text, a landing URL or a screenshot")
    if a.image_b64 and not llm.available():
        raise HTTPException(400, "Reading screenshots needs ANTHROPIC_API_KEY in .env")
    return db.get_case(ads.inspect(a.text, a.url, a.image_b64, a.media_type))


class JobsIn(BaseModel):
    texts: list[str] = []
    telegram: list[str] = []
    samples: bool = False


@app.post("/api/jobs/scan")
def jobs_scan(j: JobsIn):
    return {"job": pipeline.start("jobs", jobs.scan, j.model_dump())}


@app.get("/api/jobs/{jid}")
def job(jid: str):
    j = db.get_job(jid)
    if not j:
        raise HTTPException(404, "No such job")
    return j


# ---------- cases / actors ----------
def _slim(c):
    return {k: c[k] for k in ("id", "sensor", "title", "target", "score", "langs", "lat", "lon", "where_txt", "actor", "created")}


@app.get("/api/cases")
def cases(limit: int = 400, min_score: int = 0, since: float | None = None):
    return [_slim(c) for c in db.list_cases(limit=limit, min_score=min_score, since=since)]


@app.get("/api/cases/{cid}")
def case(cid: int):
    c = db.get_case(cid)
    if not c:
        raise HTTPException(404, "No such case")
    c["siblings"] = [_slim(s) for s in db.cases_for_actor(c["actor"]) if s["id"] != cid] if c["actor"] else []
    return c


@app.post("/api/cases/{cid}/explain")
def explain(cid: int):
    c = db.get_case(cid)
    if not c:
        raise HTTPException(404, "No such case")
    note = llm.explain(c)
    db.set_case_fields(cid, explanation=note)
    return note


@app.get("/api/actors")
def actors():
    groups = {}
    for c in db.list_cases(limit=5000):
        if c["actor"]:
            groups.setdefault(c["actor"], []).append(c)
    return [{"actor": a, "count": len(cs), "max_score": max(c["score"] for c in cs),
             "brands": sorted({c["target"] for c in cs if c["target"]}), "sensors": sorted({c["sensor"] for c in cs})}
            for a, cs in sorted(groups.items(), key=lambda kv: -len(kv[1]))]


def _pack_ids(key: str) -> tuple[list[int], str | None]:
    if key.startswith("A-"):
        ids = [c["id"] for c in db.cases_for_actor(key)]
        return ids, key
    return [int(key)], None


@app.get("/api/pack/{key}")
def pack(key: str):
    ids, actor = _pack_ids(key)
    if not ids or not db.get_case(ids[0]):
        raise HTTPException(404, "Nothing to pack")
    return strike.build(ids, actor)


@app.get("/api/pack/{key}/html", response_class=HTMLResponse)
def pack_html(key: str):
    return strike.to_html(pack(key))


@app.post("/api/recluster")
def recluster():
    return {"actors": {k: len(v) for k, v in cluster.recluster().items()}}


# ---------- console ----------
@app.get("/")
def index():
    return FileResponse(WEB / "index.html")


app.mount("/web", StaticFiles(directory=WEB), name="web")
