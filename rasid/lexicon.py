"""Multilingual layer: script/language detection and lure detection across the UAE's main languages.

Languages: AR, EN, HI, UR, ML, TA, SI, TL, BN, NE, FA, PS, RU, ZH, plus Roman Urdu/Hindi (code "UR-L").
Patterns are deliberately short phrases scammers actually use; extend them in LURES below.
"""
import re

DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹०१२३४५६७८९০১২৩৪৫৬৭৮৯", "0123456789" * 4)

URDU_ONLY = set("ٹڈڑںےہ")
PASHTO_ONLY = set("ټډړږښګڼۍې")
PERSIAN = set("گچپژک")
NEPALI_CUES = ["रोजगारी", "भिसा", "निःशुल्क", "हुन्छ", "गर्नुहोस्", "तपाईं", "छ ।", "छ।"]
TAGALOG_CUES = {"sa", "ng", "walang", "bayad", "trabaho", "po", "libre", "agad", "kailangan", "sahod", "lang", "mag-apply", "hiring", "naman", "ang", "mga"}
ROMAN_UR_CUES = {"mein", "hai", "karein", "naukri", "sirf", "abhi", "rabta", "kamai", "tankhwa", "chahiye", "bhai", "paise",
                 "jaldi", "kare", "karo", "ke", "liye", "milegi", "salary", "visa", "aur"}


def normalize(text: str) -> str:
    return text.translate(DIGITS)


def detect_langs(text: str) -> list[str]:
    """Languages present, most frequent script first."""
    counts = {}
    for ch in text:
        o = ord(ch)
        k = None
        if 0x0600 <= o <= 0x06FF or 0x0750 <= o <= 0x077F or 0xFB50 <= o <= 0xFEFF:
            k = "arabic"
        elif 0x0900 <= o <= 0x097F:
            k = "deva"
        elif 0x0980 <= o <= 0x09FF:
            k = "BN"
        elif 0x0B80 <= o <= 0x0BFF:
            k = "TA"
        elif 0x0D00 <= o <= 0x0D7F:
            k = "ML"
        elif 0x0D80 <= o <= 0x0DFF:
            k = "SI"
        elif 0x0400 <= o <= 0x04FF:
            k = "RU"
        elif 0x4E00 <= o <= 0x9FFF:
            k = "ZH"
        elif ch.isascii() and ch.isalpha():
            k = "latin"
        if k:
            counts[k] = counts.get(k, 0) + 1
    out = []
    for k, n in sorted(counts.items(), key=lambda kv: -kv[1]):
        if n < 3:
            continue
        if k == "arabic":
            chars = set(text)
            if chars & PASHTO_ONLY:
                out.append("PS")
            elif chars & URDU_ONLY:
                out.append("UR")
            elif chars & PERSIAN and not re.search(r"[ةى]", text):
                out.append("FA")
            else:
                out.append("AR")
        elif k == "deva":
            out.append("NE" if any(c in text for c in NEPALI_CUES) else "HI")
        elif k == "latin":
            words = set(re.findall(r"[a-z\-]+", text.lower()))
            tl, ru = len(words & TAGALOG_CUES), len(words & ROMAN_UR_CUES)
            if tl >= 2 and tl >= ru:
                out.append("TL")
            elif ru >= 2:
                out.append("UR-L")
            else:
                out.append("EN")
        else:
            out.append(k)
    return out


def _p(*alts):
    return re.compile("|".join(alts), re.I)


LURES = {
    "fee for visa or job": _p(r"visa\s*(processing\s*)?fees?", r"pay\s+(for\s+)?(the\s+)?visa", r"processing\s+fee", r"registration\s+fee",
                              r"رسوم\s*(ال)?تأشيرة", r"رسوم\s*(ال)?فيزا", r"वीज़ा\s*फ़?फीस", r"(?<!निः)शुल्क",r"जमा\s*कर", r"ویزا\s*فیس", r"فیس\s*(صرف|جمع)",
                              r"ഫീസ്", r"கட்டணம்", r"ගාස්තු", r"bayad\s+(lang\s+)?(sa\s+)?visa", r"placement\s+fee", r"ভিসা\s*ফি", r"ফি\s*দিতে", r"fees?\s+(de|dein|jama)"),
    "free visa": _p(r"free\s+visa", r"visa\s+free", r"تأشيرة\s+مجان", r"فيزا\s+مجان", r"वीज़ा\s*फ्री", r"फ्री\s*वीज़ा", r"मुफ़्त\s*वीज़ा",
                    r"ویزا\s*فری", r"فری\s*ویزا", r"مفت\s*ویزا", r"വിസ\s*(ഫ്രീ|സൗജന്യം)", r"സൗജന്യ\s*വിസ", r"விசா\s*இலவச", r"இலவச\s*விசா",
                    r"වීසා\s*නොමිලේ", r"libre\s+(ang\s+)?visa", r"ফ্রি\s*ভিসা", r"ভিসা\s*ফ্রি", r"भिसा\s*निःशुल्क"),
    "visit visa for work": _p(r"visit\s+visa.{0,40}(job|work|trabaho)", r"(job|work).{0,40}visit\s+visa", r"تأشيرة\s+زيارة.{0,30}عمل"),
    "no interview / no experience": _p(r"no\s+interview", r"no\s+experience", r"walang\s+experience", r"بدون\s+(مقابلة|خبرة)", r"बिना\s+इंटरव्यू",
                                       r"انٹرویو\s+کے\s+بغیر", r"experience\s+(ki\s+)?zaroorat\s+nahi"),
    "WhatsApp-only contact": _p(r"whats\s*app", r"واتس\s*اب", r"واتساب", r"واٹس\s*ایپ", r"व्हाट्सएप", r"വാട്സ്ആപ്പ്", r"வாட்ஸ்அப்", r"হোয়াটসঅ্যাপ"),
    "urgency": _p(r"today\s+only", r"limited\s+(time|seats|slots)", r"last\s+chance", r"اليوم\s+فقط", r"فوراً", r"\babhi\b", r"\bagad\b", r"जल्दी",
                  r"فوری", r"срочно", r"只限今天"),
    "discount or refund": _p(r"\d{2}\s*%\s*off", r"discount", r"خصم", r"refund", r"استرداد", r"скидк", r"[−-]\s?\d{2}\s?%", r"特价", r"免费"),
    "payment request": _p(r"pay\s+now", r"pay\s+the\s+(fee|fine)", r"ادفع", r"سدد", r"оплат", r"付款", r"magbayad"),
    "parcel / customs fee": _p(r"redeliver", r"parcel", r"shipment\s+(is\s+)?on\s+hold", r"customs\s+fee", r"شحنت?ك", r"الطرد"),
    "prize / gift": _p(r"congratulations", r"you\s+(have\s+)?won", r"winner", r"مبروك", r"هدية", r"jackpot", r"raffle", r"gift\s+card"),
    "fines": _p(r"traffic\s+fines?", r"pay\s+(your\s+)?fines?", r"مخالفات", r"جرمانہ", r"जुर्माना", r"штраф"),
}

JOB_WORDS = _p(r"\bjobs?\b", r"hiring", r"vacanc", r"recruit", r"وظائف", r"وظيفة", r"مطلوب", r"नौकरी", r"نوکری", r"ജോലി", r"வேலை", r"රැකියා",
               r"trabaho", r"চাকরি", r"रोजगारी", r"naukri", r"\bkaam\b")
LOW_WAGE_ROLES = _p(r"driver", r"cleaner", r"guard", r"helper", r"labou?r", r"waiter", r"housemaid", r"construction", r"سائق", r"حارس",
                    r"ڈرائیور", r"گارڈ", r"ड्राइवर", r"गार्ड", r"सफाई", r"ഡ്രൈവർ", r"டிரைவர்", r"ஓட்டுநர்", r"ড্রাইভার", r"কনস্ট্রাকশন", r"ক্লিনার", r"හෝටල්", r"security")
SALARY = re.compile(r"(\d{1,3}(?:,\d{3})+|\d{3,6})\s*(?:aed|dhs?|dirhams?|درهم|درہم|दिरहम)", re.I)
GMAIL = re.compile(r"[\w.+-]+@(gmail|yahoo|hotmail|outlook)\.com", re.I)


def lure_hits(text: str) -> list[dict]:
    t = normalize(text)
    out = []
    for theme, pat in LURES.items():
        m = pat.search(t)
        if m:
            out.append({"theme": theme, "match": m.group(0)[:60]})
    return out
