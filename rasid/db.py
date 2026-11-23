"""SQLite storage: watchlists, cases (anything suspicious a sensor found), actors and jobs."""
import json
import sqlite3
import threading
import time
from contextlib import contextmanager

from .config import DB_PATH

_lock = threading.RLock()

SCHEMA = """
CREATE TABLE IF NOT EXISTS watchlist (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  kind TEXT NOT NULL,            -- brand | event | jobs
  name TEXT NOT NULL,
  official_domains TEXT NOT NULL DEFAULT '[]',
  official_phones TEXT NOT NULL DEFAULT '[]',
  lure TEXT NOT NULL DEFAULT 'brand',   -- brand | event | religious | jobs
  langs TEXT NOT NULL DEFAULT '[]',
  date TEXT,
  created REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS cases (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  sensor TEXT NOT NULL,          -- maps | domains | ct | ads | kits | jobs
  key TEXT NOT NULL UNIQUE,      -- domain, place id, post hash...
  title TEXT NOT NULL,
  target TEXT,
  watch_id INTEGER,
  score INTEGER NOT NULL DEFAULT 0,
  langs TEXT NOT NULL DEFAULT '[]',
  lat REAL, lon REAL, where_txt TEXT,
  signals TEXT NOT NULL DEFAULT '[]',     -- [{text, points, ok}]
  evidence TEXT NOT NULL DEFAULT '{}',
  features TEXT NOT NULL DEFAULT '{}',    -- fingerprints used for clustering
  actor TEXT,
  explanation TEXT,
  created REAL NOT NULL,
  updated REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS cases_created ON cases(created);
CREATE TABLE IF NOT EXISTS jobs (
  id TEXT PRIMARY KEY,
  kind TEXT NOT NULL,
  status TEXT NOT NULL,
  progress TEXT NOT NULL DEFAULT '[]',
  result TEXT,
  created REAL NOT NULL
);
"""

JSON_FIELDS = {"explanation", "official_domains", "official_phones", "langs", "signals", "evidence", "features", "progress", "result"}


def _connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=30)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    return con


_con = None


@contextmanager
def conn():
    global _con
    with _lock:
        if _con is None:
            _con = _connect()
            _con.executescript(SCHEMA)
        yield _con
        _con.commit()


def row(r):
    if r is None:
        return None
    d = dict(r)
    for k in JSON_FIELDS & d.keys():
        if d[k] is not None:
            try:
                d[k] = json.loads(d[k])
            except (TypeError, ValueError):
                pass
    return d


def dumps(v):
    return json.dumps(v, ensure_ascii=False)


# ---------- watchlists ----------
def add_watch(kind, name, official_domains=(), official_phones=(), lure="brand", langs=(), date=None):
    with conn() as c:
        cur = c.execute(
            "INSERT INTO watchlist(kind,name,official_domains,official_phones,lure,langs,date,created) VALUES (?,?,?,?,?,?,?,?)",
            (kind, name, dumps(list(official_domains)), dumps(list(official_phones)), lure, dumps(list(langs)), date, time.time()),
        )
        return cur.lastrowid


def list_watch():
    with conn() as c:
        return [row(r) for r in c.execute("SELECT * FROM watchlist ORDER BY id")]


def get_watch(wid):
    with conn() as c:
        return row(c.execute("SELECT * FROM watchlist WHERE id=?", (wid,)).fetchone())


def delete_watch(wid):
    with conn() as c:
        c.execute("DELETE FROM watchlist WHERE id=?", (wid,))


def watch_count():
    with conn() as c:
        return c.execute("SELECT COUNT(*) FROM watchlist").fetchone()[0]


def all_official_domains():
    out = set()
    for w in list_watch():
        out.update(d.lower() for d in w["official_domains"])
    return out


def all_official_phones():
    out = set()
    for w in list_watch():
        out.update(w["official_phones"])
    return out


# ---------- cases ----------
def upsert_case(sensor, key, title, score, *, target=None, watch_id=None, langs=(), lat=None, lon=None,
                where_txt=None, signals=(), evidence=None, features=None):
    now = time.time()
    with conn() as c:
        old = c.execute("SELECT id FROM cases WHERE key=?", (key,)).fetchone()
        vals = (sensor, title, target, watch_id, int(score), dumps(list(langs)), lat, lon, where_txt,
                dumps(list(signals)), dumps(evidence or {}), dumps(features or {}), now)
        if old:
            c.execute(
                "UPDATE cases SET sensor=?,title=?,target=?,watch_id=?,score=?,langs=?,lat=?,lon=?,where_txt=?,"
                "signals=?,evidence=?,features=?,updated=? WHERE id=?",
                vals + (old["id"],),
            )
            return old["id"]
        cur = c.execute(
            "INSERT INTO cases(sensor,title,target,watch_id,score,langs,lat,lon,where_txt,signals,evidence,features,updated,key,created)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            vals + (key, now),
        )
        return cur.lastrowid


def get_case(cid):
    with conn() as c:
        return row(c.execute("SELECT * FROM cases WHERE id=?", (cid,)).fetchone())


def list_cases(limit=300, since=None, min_score=0):
    q = "SELECT * FROM cases WHERE score>=?"
    args = [min_score]
    if since:
        q += " AND created>=?"
        args.append(since)
    q += " ORDER BY created DESC LIMIT ?"
    args.append(limit)
    with conn() as c:
        return [row(r) for r in c.execute(q, args)]


def set_case_fields(cid, **fields):
    if not fields:
        return
    cols = ",".join(f"{k}=?" for k in fields)
    vals = [dumps(v) if k in JSON_FIELDS else v for k, v in fields.items()]
    with conn() as c:
        c.execute(f"UPDATE cases SET {cols} WHERE id=?", vals + [cid])


def cases_for_actor(actor):
    with conn() as c:
        return [row(r) for r in c.execute("SELECT * FROM cases WHERE actor=? ORDER BY score DESC", (actor,))]


# ---------- jobs ----------
def new_job(jid, kind):
    with conn() as c:
        c.execute("INSERT INTO jobs(id,kind,status,progress,created) VALUES (?,?,?,?,?)", (jid, kind, "running", "[]", time.time()))


def job_log(jid, msg):
    with conn() as c:
        r = c.execute("SELECT progress FROM jobs WHERE id=?", (jid,)).fetchone()
        if not r:
            return
        p = json.loads(r["progress"])
        p.append({"t": time.time(), "msg": msg})
        c.execute("UPDATE jobs SET progress=? WHERE id=?", (dumps(p), jid))


def job_done(jid, result, status="done"):
    with conn() as c:
        c.execute("UPDATE jobs SET status=?, result=? WHERE id=?", (status, dumps(result), jid))


def get_job(jid):
    with conn() as c:
        return row(c.execute("SELECT * FROM jobs WHERE id=?", (jid,)).fetchone())
