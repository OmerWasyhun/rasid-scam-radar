"""Default watchlists and the multilingual lure dictionary.

Official domains below are the public sites of each organisation. Official phone numbers are
left empty on purpose: fill them from each organisation's own website before the demo, so the
Maps Verifier compares listings against numbers you have checked yourselves.
"""
from . import db

DEFAULT_LANGS = ["AR", "EN", "HI", "UR", "ML", "TA", "SI", "TL", "BN", "NE"]

BRANDS = [
    ("TAMM", ["tamm.abudhabi"], "brand"),
    ("Abu Dhabi Police", ["adpolice.gov.ae"], "brand"),
    ("ADCB", ["adcb.com"], "brand"),
    ("First Abu Dhabi Bank", ["bankfab.com"], "brand"),
    ("Emirates NBD", ["emiratesnbd.com"], "brand"),
    ("Etisalat e&", ["etisalat.ae", "eand.com"], "brand"),
    ("du", ["du.ae"], "brand"),
    ("Aramex", ["aramex.com"], "brand"),
    ("Emirates Post", ["emiratespost.ae"], "brand"),
    ("Salik", ["salik.ae"], "brand"),
    ("RTA Dubai", ["rta.ae"], "brand"),
    ("ICP", ["icp.gov.ae"], "brand"),
    ("Dubai Police", ["dubaipolice.gov.ae"], "brand"),
]
EVENTS = [
    ("Abu Dhabi Grand Prix", ["yasmarinacircuit.com", "formula1.com"], "event", "2026-12-06"),
    ("Eid Al Etihad National Day", ["u.ae"], "brand", "2026-12-02"),
    ("Dubai Shopping Festival", ["mydsf.ae"], "event", None),
    ("Umrah", ["nusuk.sa"], "religious", None),
    ("Hajj", ["nusuk.sa"], "religious", None),
]
JOBS = [
    ("MOHRE", ["mohre.gov.ae"], "jobs"),
    ("Tadbeer", ["tadbeer.ae"], "jobs"),
    ("ADNOC careers", ["adnoc.ae"], "jobs"),
    ("Emirates Group careers", ["emiratesgroupcareers.com", "emirates.com"], "jobs"),
    ("Etihad careers", ["etihad.com"], "jobs"),
]


def ensure_defaults():
    if db.watch_count():
        return
    for name, doms, lure in BRANDS:
        db.add_watch("brand", name, doms, [], lure, DEFAULT_LANGS)
    for name, doms, lure, date in EVENTS:
        db.add_watch("event", name, doms, [], lure, DEFAULT_LANGS + ["RU", "ZH"], date)
    for name, doms, lure in JOBS:
        db.add_watch("jobs", name, doms, [], lure, DEFAULT_LANGS)


# Lure keywords used inside domain names (Latin script, including transliterations).
DOMAIN_LURES = {
    "brand": ["pay", "fines", "verify", "update", "refund", "secure", "login", "rewards", "support", "ae", "uae", "online", "portal"],
    "event": ["tickets", "pass", "vip", "offer", "booking", "2026", "live", "official", "tiket", "bilety"],
    "religious": ["packages", "visa", "booking", "2027", "cheap", "agent", "travels", "tours"],
    "jobs": ["careers", "jobs", "hiring", "visa", "recruit", "naukri", "trabaho", "joli", "velai", "rakiya", "chakri", "rojgari"],
}

# Lure words per language and theme, native script + transliteration where scammers use it.
SEED_WORDS = {
    "tickets": {"AR": "تذاكر", "HI": "टिकट", "UR": "ٹکٹ", "ML": "ടിക്കറ്റ്", "TA": "டிக்கெட்", "TL": "tiket", "BN": "টিকিট", "RU": "билеты", "ZH": "门票", "EN": "tickets"},
    "job": {"AR": "وظائف", "HI": "नौकरी · naukri", "UR": "نوکری · naukri", "ML": "ജോലി · joli", "TA": "வேலை · velai", "SI": "රැකියා · rakiya", "TL": "trabaho", "BN": "চাকরি · chakri", "NE": "रोजगारी · rojgari", "EN": "jobs"},
    "fine": {"AR": "مخالفات", "HI": "जुर्माना · jurmana", "UR": "جرمانہ · jurmana", "TL": "multa", "RU": "штраф · shtraf", "EN": "fines"},
    "visa": {"AR": "تأشيرة", "HI": "वीज़ा", "UR": "ویزا", "ML": "വിസ", "TA": "விசா", "SI": "වීසා", "TL": "visa", "BN": "ভিসা", "NE": "भिसा", "EN": "visa"},
}

# Search-sweep query templates per language ({b} = entity name).
SEARCH_TEMPLATES = {
    "brand": {
        "EN": ["{b} pay fines online", "{b} customer care number", "{b} refund"],
        "AR": ["{b} دفع المخالفات", "{b} رقم خدمة العملاء", "{b} تحديث البيانات"],
        "HI": ["{b} कस्टमर केयर नंबर"],
        "UR": ["{b} کسٹمر کیئر نمبر"],
        "TL": ["{b} customer service number"],
    },
    "event": {
        "EN": ["{b} tickets cheap", "{b} tickets sale"],
        "AR": ["تذاكر {b}"],
        "RU": ["{b} билеты"],
        "ZH": ["{b} 门票"],
    },
    "religious": {
        "EN": ["{b} visa from UAE cheap", "{b} packages Dubai"],
        "AR": ["تأشيرة {b} من الإمارات"],
        "UR": ["{b} ویزا دبئی"],
        "ML": ["{b} വിസ ദുബായ്"],
        "BN": ["{b} ভিসা দুবাই"],
    },
    "jobs": {
        "EN": ["{b} jobs visa free", "{b} hiring drivers Dubai"],
        "HI": ["दुबई नौकरी वीज़ा फ्री {b}"],
        "UR": ["دبئی نوکری ویزا فری {b}"],
        "ML": ["ദുബായ് ജോലി {b}"],
        "TL": ["{b} hiring Dubai walang placement"],
        "TA": ["துபாய் வேலை {b}"],
    },
}
