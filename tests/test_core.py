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
