"""Kit fingerprint clustering: cases that share a rare fingerprint are joined into one actor (union-find)."""
from collections import defaultdict

from . import db

# Features that tie sites to one operator. Shared hosting IPs and big-CDN nameservers are too common,
# so a feature only links cases when it is shared by at most MAX_SHARE cases.
FEATURES = ["favicon_hash", "dom_hash", "telegram", "analytics", "phone", "whatsapp", "ip", "ns"]
MAX_SHARE = 40
COMMON_NS = ("cloudflare.com", "awsdns", "googledomains.com", "domaincontrol.com", "registrar-servers.com", "dns-parking.com")
WEAK = {"ip", "ns", "dom_hash"}  # need two weak features (or one strong) to link


def _feature_keys(f: dict) -> list[tuple[str, str]]:
    keys = []
    for name in FEATURES:
        v = f.get(name)
        if not v:
            continue
        vals = v if isinstance(v, list) else [v]
        for x in vals:
            x = str(x)
            if name == "ns" and any(c in x for c in COMMON_NS):
                continue
            keys.append((name, x))
    return keys


def recluster() -> dict:
    cases = [c for c in db.list_cases(limit=5000) if c["score"] >= 40]
    by_feat = defaultdict(list)
    for c in cases:
        for k in _feature_keys(c["features"]):
            by_feat[k].append(c["id"])
    parent = {c["id"]: c["id"] for c in cases}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[max(ra, rb)] = min(ra, rb)

    # strong features link directly
    for (name, _), ids in by_feat.items():
        if name not in WEAK and 1 < len(ids) <= MAX_SHARE:
            for i in ids[1:]:
                union(ids[0], i)
    # weak features: link pairs that share two or more
    pair = defaultdict(set)
    for (name, val), ids in by_feat.items():
        if name in WEAK and 1 < len(ids) <= MAX_SHARE:
            for a in ids:
                for b in ids:
                    if a < b:
                        pair[(a, b)].add(name)
    for (a, b), names in pair.items():
        if len(names) >= 2:
            union(a, b)

    groups = defaultdict(list)
    for c in cases:
        groups[find(c["id"])].append(c["id"])
    actors = {}
    for root, ids in groups.items():
        if len(ids) < 2:
            continue
        actor = f"A-{root:03d}"
        actors[actor] = ids
        for i in ids:
            db.set_case_fields(i, actor=actor)
    linked = {i for ids in actors.values() for i in ids}
    for c in cases:
        if c["actor"] and c["id"] not in linked:
            db.set_case_fields(c["id"], actor=None)
    return actors


def shared_features(ids: list[int]) -> list[str]:
    seen = defaultdict(set)
    for i in ids:
        c = db.get_case(i)
        for k in _feature_keys(c["features"]):
            seen[k].add(i)
    return [f"{n}: {v}" for (n, v), s in seen.items() if len(s) > 1][:12]
