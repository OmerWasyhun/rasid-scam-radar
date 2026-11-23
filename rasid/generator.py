"""Lookalike domain generator: typos, homoglyphs (Latin and Cyrillic), combosquats, TLD swaps.

Also provides the homoglyph "skeleton" used to match newly seen domains against watchlists.
"""
import re
import unicodedata

from .seeds import DOMAIN_LURES

KEYBOARD = {
    "q": "wa", "w": "qes", "e": "wrd", "r": "etf", "t": "ryg", "y": "tuh", "u": "yij", "i": "uok", "o": "ipl", "p": "ol",
    "a": "qsz", "s": "awdz", "d": "sefx", "f": "drgc", "g": "fthv", "h": "gyjb", "j": "hukn", "k": "jilm", "l": "kop",
    "z": "asx", "x": "zsdc", "c": "xdfv", "v": "cfgb", "b": "vghn", "n": "bhjm", "m": "njk",
}
LATIN_GLYPHS = {
    "l": ["1", "i"], "i": ["1", "l"], "o": ["0"], "m": ["rn"], "w": ["vv"], "d": ["cl"], "e": ["3"],
    "a": ["4"], "s": ["5"], "b": ["8"], "g": ["9", "q"], "n": ["m"], "u": ["v"],
}
CYRILLIC = {"a": "а", "e": "е", "o": "о", "p": "р", "c": "с", "x": "х", "y": "у", "i": "і", "s": "ѕ", "j": "ј"}
TLDS = [".com", ".net", ".co", ".online", ".top", ".xyz", ".shop", ".info", ".live", ".vip", ".cc", ".site", ".org"]
STOP = {"the", "of", "and", "al", "el", "careers", "career"}
OFFICIAL_CACHE: set[str] = set()  # registrable official domains, filled by the pipeline
LURE_WORDS = sorted({w for ws in DOMAIN_LURES.values() for w in ws} | {
    "bank", "app", "help", "care", "service", "services", "pay", "card", "cards", "account", "online", "net", "ae", "uae",
    "dubai", "abudhabi", "gov", "auth", "id", "sms", "otp", "track", "tracking", "delivery", "redelivery", "parcel", "customs", "fee", "fees", "shipping", "post", "gift", "promo", "bonus", "topup", "recharge", "branch", "customer"}, key=len, reverse=True)

# skeleton: map look-alike characters to one canonical form
_SKEL = {"0": "o", "1": "l", "i": "l", "3": "e", "4": "a", "5": "s", "8": "b", "9": "g", "q": "g", "v": "u"}
_MULTI = [("rn", "m"), ("vv", "w"), ("cl", "d")]
_CYR_TO_LAT = {v: k for k, v in CYRILLIC.items()}


def to_unicode(label: str) -> str:
    try:
        return label.encode("ascii").decode("idna") if "xn--" in label else label
    except UnicodeError:
        return label


def to_ascii(host: str) -> str:
    try:
        return host.encode("idna").decode("ascii")
    except UnicodeError:
        return host


def skeleton(s: str) -> str:
    s = to_unicode(s.lower())
    s = "".join(_CYR_TO_LAT.get(ch, ch) for ch in s)
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    for a, b in _MULTI:
        s = s.replace(a, b)
    s = "".join(_SKEL.get(ch, ch) for ch in s)
    return re.sub(r"[^a-z0-9]", "", s)


def levenshtein(a: str, b: str) -> int:
    if a == b:
        return 0
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def slugs(name: str, domain: str | None = None) -> list[str]:
    """Base labels for an entity: from its official domain if given, else from the name."""
    out = []
    if domain and "." in domain:
        out.append(re.sub(r"[^a-z0-9-]", "", domain.lower().split(".")[0]))
    words = [w for w in re.sub(r"[^a-z0-9 ]", " ", name.lower().replace("&", " and ")).split() if w and w not in STOP]
    if words:
        out += ["".join(words), "-".join(words)]
        if len(words) > 1:
            out.append("".join(w[0] for w in words))
        if "grand" in words and "prix" in words:
            core = [w for w in words if w not in ("grand", "prix")]
            out += ["".join(core) + "gp", "f1" + "".join(core), "-".join(core) + "-gp"]
    seen, res = set(), []
    for s in out:
        if s and len(s) >= 2 and s not in seen:
            seen.add(s)
            res.append(s)
    return res


def generate(name: str, domain: str | None = None, lure: str = "brand", limit: int = 400) -> list[dict]:
    """Return [{domain, technique, label}] lookalike candidates, most deceptive first."""
    bases = slugs(name, domain)
    if not bases:
        return []
    L = bases[0]
    tld = domain[domain.index("."):] if domain and "." in domain else ".com"
    if tld.count(".") > 1 or len(tld) > 8:  # e.g. .gov.ae -> keep as-is for typos
        pass
    res, seen = [], {f"{L}{tld}"}

    def add(d, t):
        d_ascii = to_ascii(d)
        if d_ascii not in seen and len(d_ascii) <= 253:
            seen.add(d_ascii)
            res.append({"domain": d_ascii, "display": d, "technique": t})

    for i, ch in enumerate(L):
        if ch in CYRILLIC:
            add(L[:i] + CYRILLIC[ch] + L[i + 1:] + ".com", "cyrillic homoglyph")
        for g in LATIN_GLYPHS.get(ch, []):
            add(L[:i] + g + L[i + 1:] + tld, "homoglyph")
        add(L[:i] + L[i + 1:] + tld, "omission")
        if i < len(L) - 1:
            add(L[:i] + L[i + 1] + L[i] + L[i + 2:] + tld, "transposition")
        add(L[:i] + ch + L[i:] + tld, "repetition")
        for k in KEYBOARD.get(ch, "")[:2]:
            add(L[:i] + k + L[i + 1:] + tld, "keyboard")
        if 0 < i < len(L):
            add(L[:i] + "-" + L[i:] + tld, "hyphenation")
    for t in TLDS:
        add(L + t, "tld swap")
    add(L + "-ae.com", "tld swap")
    add(L + "ae.com", "tld swap")
    words = DOMAIN_LURES.get(lure, DOMAIN_LURES["brand"])
    for b in bases:
        for j, k in enumerate(words):
            t = [".com", ".top", ".xyz", ".online", ".info", ".net"][j % 6]
            add(f"{b}-{k}{t}", "combosquat")
            add(f"{b}{k}.com", "combosquat")
            add(f"{k}-{b}.com", "combosquat")
    for k in words[:3]:
        add(f"{L}.com-{k}.top", "subdomain trick")
    order = {"cyrillic homoglyph": 0, "homoglyph": 1, "omission": 2, "transposition": 3, "combosquat": 4,
             "repetition": 5, "subdomain trick": 6, "keyboard": 7, "hyphenation": 8, "tld swap": 9}
    res.sort(key=lambda r: order.get(r["technique"], 99))
    return res[:limit]


def registrable(host: str) -> str:
    """Best-effort registrable domain (handles common two-level suffixes)."""
    host = host.lower().strip(".")
    parts = host.split(".")
    two = {"co.uk", "com.au", "gov.ae", "co.ae", "com.sa", "com.pk", "co.in", "com.ph", "net.ae", "org.ae", "ac.ae"}
    if len(parts) >= 3 and ".".join(parts[-2:]) in two:
        return ".".join(parts[-3:])
    return ".".join(parts[-2:]) if len(parts) >= 2 else host


_LS: list[str] = []


def _lure_skel() -> list[str]:
    if not _LS:
        _LS.extend(sorted({skeleton(w) for w in LURE_WORDS if skeleton(w)}, key=len, reverse=True))
    return _LS


def _lure_sequence(s: str) -> bool:
    """True when s is made only of lure words and digits, e.g. 'securelogin', 'pay2026'."""
    s = re.sub(r"\d+", "", s)
    if not s:
        return True
    ok = [True] + [False] * len(s)
    for i in range(len(s)):
        if ok[i]:
            for w in _lure_skel():
                if s.startswith(w, i):
                    ok[i + len(w)] = True
    return ok[len(s)]


def similarity(host: str, bases: list[str]) -> tuple[int, str]:
    """0-25 points for how closely a host imitates any base label, plus a reason."""
    reg = registrable(host)
    label = reg.split(".")[0]
    full = host.split(".")
    tokens = [t for t in re.split(r"[-0-9]+", to_unicode(label)) if t]
    best, why = 0, ""
    for b in bases:
        sb, sl = skeleton(b), skeleton(label)
        if not sb or len(sb) < 4:
            continue
        if reg in OFFICIAL_CACHE:
            return 0, ""
        if sl == sb and label != b:
            return 25, f"homoglyph of '{b}' ({to_unicode(label)})"
        d = levenshtein(sl, sb)
        if d == 1:
            # short names (4 letters) collide with random words, so one edit is weak evidence on its own
            best, why = max((best, why), (22 if len(sb) >= 5 else 10, f"one character away from '{b}'"))
        elif d == 2 and len(sb) >= 7:
            best, why = max((best, why), (16, f"two characters away from '{b}'"))
        if sb in sl and sl != sb:
            rest = sl.replace(sb, "", 1)
            bounded = (any(skeleton(t) == sb for t in tokens)
                       or (len(sb) >= 9)
                       or ((sl.startswith(sb) or sl.endswith(sb))
                           and (_lure_sequence(rest) or _lure_sequence(skeleton(re.sub(r"\d+", "", label.lower().replace(b.lower(), "", 1)))))))
            if bounded:
                best, why = max((best, why), (18, f"contains '{b}' plus extra words (combosquat)"))
        if any(skeleton(p) == sb for p in full[:-2]):
            best, why = max((best, why), (20, f"'{b}' used as a subdomain of another domain"))
    return best, why
