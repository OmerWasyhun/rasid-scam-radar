"""Arabic for everything the server shows people: case reasons, titles, places, job progress and errors.

Sensors write their findings in English (the scoring, the tests and the API for test sets read those words). The console
is used by Arabic speakers, so the API translates the text on the way out with these templates. Stored cases stay as
they are; any text without a template is passed through unchanged.
"""
import re
from contextvars import ContextVar

# Language of the current request: "ar" (default, the console opens in Arabic) or "en". Set per request in api.py.
LANG: ContextVar[str] = ContextVar("rasid_lang", default="ar")


def is_ar() -> bool:
    return LANG.get() == "ar"


def msg(en: str, ar: str) -> str:
    """A message in the language of the current request."""
    return ar if is_ar() else en

WORDS = {
    # lure themes and job-post flags
    "fee for visa or job": "رسوم مقابل التأشيرة أو الوظيفة", "free visa": "تأشيرة مجانية", "visit visa for work": "تأشيرة زيارة للعمل",
    "no interview / no experience": "بدون مقابلة أو خبرة", "urgency": "استعجال", "discount or refund": "خصم أو استرداد",
    "payment request": "طلب دفع", "parcel / customs fee": "طرد أو رسوم جمارك", "prize / gift": "جائزة أو هدية", "fines": "مخالفات",
    "whatsapp-only contact": "تواصل عبر واتساب فقط", "job or recruitment offer": "عرض وظيفة أو توظيف",
    # what a page asks for
    "card number": "رقم البطاقة", "CVV": "CVV", "card expiry": "تاريخ انتهاء البطاقة", "OTP": "رمز OTP", "Emirates ID": "الهوية الإماراتية",
    "password/PIN": "كلمة المرور أو الرقم السري", "payment": "الدفع",
    # name-imitation techniques
    "combosquat": "اسم مركّب", "lookalike": "اسم متشابه", "tld swap": "تبديل الامتداد", "homoglyph": "حروف متشابهة", "typo": "خطأ إملائي",
    # suspicious code
    "Self-decoding script (eval of encoded code)": "سكربت يفك تشفير نفسه (تنفيذ كود مشفّر)",
    "Obfuscated JavaScript (javascript-obfuscator pattern)": "كود JavaScript مموّه",
    "Writes hidden encoded HTML into the page": "يكتب HTML مشفّراً مخفياً داخل الصفحة",
    "Builds code from character codes": "يبني الكود من رموز الحروف",
}


def w(s: str) -> str:
    """One word or phrase, or a comma list of them."""
    s = s.strip()
    if s in WORDS:
        return WORDS[s]
    if s.lower() in WORDS:
        return WORDS[s.lower()]
    if ", " in s:
        return "، ".join(w(x) for x in s.split(", "))
    return s


def _sim(reason: str) -> str:
    """Name-imitation reason from generator.similarity."""
    m = re.fullmatch(r"contains '(.+)' plus extra words \(combosquat\)", reason)
    if m:
        return f"يحتوي '{m[1]}' مع كلمات إضافية (اسم مركّب)"
    m = re.fullmatch(r"homoglyph of '(.+)' \((.+)\)", reason)
    if m:
        return f"حروف متشابهة مع '{m[1]}' ({m[2]})"
    m = re.fullmatch(r"(one|two) characters? away from '(.+)'", reason)
    if m:
        return f"يختلف عن '{m[2]}' {'بحرف واحد' if m[1] == 'one' else 'بحرفين'}"
    return w(reason)


# (pattern, Arabic template or function). Order matters: the first full match wins.
RULES = [
    # ---- link / page checks
    (r"Claims to be (.+) but is on (\S+), a domain \1 does not own", r"يدّعي أنه \1 لكنه على \2، وهو نطاق لا تملكه \1"),
    (r"Fake (.+) page: asks for a password on a domain \1 does not own", r"صفحة \1 مزيفة: تطلب كلمة مرور على نطاق لا تملكه \1"),
    (r"Fake (.+) page: shows a sign-in or verification page on a domain \1 does not own", r"صفحة \1 مزيفة: صفحة دخول أو تحقق على نطاق لا تملكه \1"),
    (r"Uses the (.+) name on a free-hosted page", r"يستخدم اسم \1 على صفحة باستضافة مجانية"),
    (r"Hosted on a free site builder \((.+)\), where anyone can publish a page in minutes", r"مستضاف على منصة مواقع مجانية (\1) يمكن لأي شخص النشر عليها في دقائق"),
    (r"Password form on a free-hosted page", "نموذج كلمة مرور على صفحة باستضافة مجانية"),
    (r"Cloaking: Googlebot and a mobile phone see different pages", "تمويه: Googlebot والجوال يريان صفحتين مختلفتين"),
    (r"(\S+) sends visitors to (\S+) \((.+)\)", lambda m: f"{m[1]} يحوّل الزوار إلى {m[2]} ({'رابط مختصر أو تحويل' if 'shortener' in m[3] or 'redirect' in m[3] else m[3]})"),
    (r"Redirects to the official site (\S+): a brand-owned defensive domain", r"يحوّل إلى الموقع الرسمي \1: نطاق دفاعي تملكه العلامة"),
    (r"Landing domain (\S+) does not resolve \(taken down or not live yet\)", r"نطاق الصفحة \1 لا يعمل (أُغلق أو لم يُفعَّل بعد)"),
    (r"Domain resolves but no page answered \(parked or not live yet\)", "النطاق يعمل لكن لا توجد صفحة (مركون أو غير مفعّل بعد)"),
    (r"Parked or for-sale domain: nothing live yet \(kept on watch in case it's activated\)", "نطاق مركون أو معروض للبيع: لا شيء حي بعد (تحت المراقبة إن فُعِّل)"),
    (r"Domain registered (\d+) days ago", r"النطاق مسجّل منذ \1 يوماً"),
    (r"Domain is (\d+) years old", r"عمر النطاق \1 سنة"),
    (r"In the newly-registered list for (\S+)", r"ضمن قائمة النطاقات المسجلة حديثاً بتاريخ \1"),
    (r"New TLS certificate issued (\S+)", r"شهادة TLS جديدة صدرت في \1"),
    (r"Name imitation: (.+)", lambda m: "تقليد الاسم: " + _sim(m[1])),
    (r"Name stuffed with service keywords: “(.+)”", r"اسم محشو بكلمات خدمة: «\1»"),
    (r"Page asks for (.+)", lambda m: "الصفحة تطلب " + w(m[1])),
    (r"Collects (.+)", lambda m: "تجمع " + w(m[1])),
    (r"Page presents itself as (.+)", r"الصفحة تقدّم نفسها على أنها \1"),
    (r"Takes payments through (.+)", r"تستقبل المدفوعات عبر \1"),
    (r"Form submits to another site: (.+)", r"النموذج يرسل البيانات إلى موقع آخر: \1"),
    (r"Suspicious code: (.+)", lambda m: "كود مشبوه: " + w(m[1])),
    (r"Telegram bot token in page code \(typical card-data exfiltration\)", "رمز بوت Telegram في كود الصفحة (أسلوب شائع لسرقة بيانات البطاقات)"),
    (r"Page code calls the Telegram bot API \(typical for stealing form data\)", "كود الصفحة يستدعي واجهة بوت Telegram (أسلوب شائع لسرقة بيانات النماذج)"),
    (r"Form sends data straight to a Telegram bot", "النموذج يرسل البيانات مباشرة إلى بوت Telegram"),
    (r"While loading, the page contacted a Telegram bot", "أثناء التحميل تواصلت الصفحة مع بوت Telegram"),
    (r"While loading, the page talks to (\S+), already flagged by RASID", r"أثناء التحميل تتواصل الصفحة مع \1 الذي سبق أن أدانه راصد"),
    (r"Form posts sensitive fields to a PHP script", "النموذج يرسل حقولاً حساسة إلى سكربت PHP"),
    (r"Asks for payment to a crypto wallet", "يطلب الدفع إلى محفظة عملات رقمية"),
    (r"Asks the visitor to pay an amount \((.+)\)", r"يطلب من الزائر دفع مبلغ (\1)"),
    (r"Shows a UAE IBAN for bank transfer", "يعرض رقم IBAN إماراتي للتحويل البنكي"),
    (r"Crypto wallet-drainer pattern \(connect wallet to claim\)", "نمط سرقة المحافظ الرقمية (اربط محفظتك لتستلم)"),
    (r"Offers an Android app \(\.apk\) download outside the Play Store", "يعرض تنزيل تطبيق Android (apk.) خارج متجر Play"),
    (r"Blocks right-click or detects developer tools \(hides from inspection\)", "يمنع النقر الأيمن أو يكشف أدوات المطور (يتهرب من الفحص)"),
    (r"Hidden iframe loading (.+)", r"إطار مخفي يحمّل \1"),
    (r"Links to a bare IP address \((.+)\)", r"روابط إلى عنوان IP مباشر (\1)"),
    (r"Loads a script from a bare IP address \((.+)\)", r"يحمّل سكربتاً من عنوان IP مباشر (\1)"),
    (r"Links to a site on Google's malicious list: (.+)", r"روابط إلى موقع على قائمة Google للمواقع الضارة: \1"),
    (r"Links to (\S+), already flagged by RASID", r"روابط إلى \1 الذي سبق أن أدانه راصد"),
    (r"Uses a link shortener \((.+)\) to hide the destination", r"يستخدم رابطاً مختصراً (\1) لإخفاء الوجهة"),
    (r"Loads images or styles straight from the official site \((.+)\)", r"يحمّل الصور أو التنسيقات مباشرة من الموقع الرسمي (\1)"),
    (r"Looks like the official (.+) site \((\d+)% UI match\)", r"يشبه موقع \1 الرسمي (تطابق الواجهة \2%)"),
    (r"Partly copies the official (.+) site \((\d+)% UI match\)", r"ينسخ جزءاً من موقع \1 الرسمي (تطابق الواجهة \2%)"),
    (r"Screenshot looks like the official (.+) site \((\d+)% visual match\)", r"الصورة تشبه موقع \1 الرسمي (تطابق بصري \2%)"),
    (r"Screenshot partly resembles the official (.+) site \((\d+)% visual match\)", r"الصورة تشبه جزئياً موقع \1 الرسمي (تطابق بصري \2%)"),
    (r"Screenshot scan: imitates (.+) and asks for (.+)", lambda m: f"فحص الصورة: ينتحل {m[1]} ويطلب {w(m[2])}"),
    (r"Screenshot: (.+)", r"الصورة: \1"),
    (r"Uses the exact same favicon as (.+)", r"يستخدم نفس أيقونة \1 تماماً"),
    (r"Inspected: a separate, unrelated business; no brand copying, payment capture or malicious code", "فُحص: نشاط مستقل غير مرتبط؛ لا نسخ للعلامة ولا جمع للمدفوعات ولا كود ضار"),
    (r"Only the name looks similar: nothing on the site copies the brand, takes payments or runs malicious code", "التشابه في الاسم فقط: لا شيء في الموقع ينسخ العلامة أو يجمع المدفوعات أو يشغّل كوداً ضاراً"),
    (r"Shares a fingerprint with other flagged sites", "يشترك في بصمة مع مواقع أخرى مدانة"),
    (r"Couldn't load (\S+) to compare designs \(it blocks automated visitors\)\.(.*)", r"تعذّر تحميل \1 لمقارنة التصميم (يحجب الزوار الآليين)."),
    # ---- reputation
    (r"Google Safe Browsing lists it as (.+)", r"Google Safe Browsing يصنّفه: \1"),
    (r"(\d+) security vendors on VirusTotal flag it as malicious", r"\1 جهة أمنية على VirusTotal تصنّفه ضاراً"),
    (r"VirusTotal: flagged by one vendor or marked suspicious", "VirusTotal: جهة واحدة صنّفته أو اعتُبر مشبوهاً"),
    (r"Runs on (.+)", r"يعمل على \1"),
    (r"On the official allowlist", "ضمن القائمة الرسمية المعتمدة"),
    # ---- maps
    (r"Website (\S+) is an official domain", r"الموقع \1 نطاق رسمي"),
    (r"Website (\S+) is not on the official list", r"الموقع \1 ليس ضمن القائمة الرسمية"),
    (r"Uses a mobile number \((.+)\) for an official brand listing", r"يستخدم رقم جوال (\1) لقائمة علامة رسمية"),
    (r"Phone matches the official registry", "الرقم يطابق السجل الرسمي"),
    (r"Phone is not in the brand's official registry", "الرقم غير موجود في السجل الرسمي للعلامة"),
    (r"Same number appears on listings for (.+)", r"الرقم نفسه يظهر في قوائم \1"),
    (r"No website on the listing", "لا يوجد موقع إلكتروني في القائمة"),
    (r"No phone number on the listing", "لا يوجد رقم هاتف في القائمة"),
    (r"Almost no reviews", "تقييمات شبه معدومة"),
    # ---- ads and search
    (r"Ad text uses lures: (.+)", lambda m: "نص الإعلان يستخدم طُعماً: " + w(m[1])),
    (r"Result text uses lures: (.+)", lambda m: "نص النتيجة يستخدم طُعماً: " + w(m[1])),
    (r"Lure language: (.+)", lambda m: "لغة طُعم: " + w(m[1])),
    (r"Contact through WhatsApp only", "التواصل عبر واتساب فقط"),
    (r"No landing link in the ad: contact is probably by message or WhatsApp", "لا يوجد رابط في الإعلان: التواصل غالباً برسالة أو واتساب"),
    (r"Meta ad by Page “(.+)”, which is not (.+)", r"إعلان Meta من صفحة «\1» وهي ليست \2"),
    (r"Google ad by “(.+)”, which is not (.+)", r"إعلان Google من «\1» وهو ليس \2"),
    (r"Shown for (.+) days, format (.+)", r"عُرض \1 يوماً، بصيغة \2"),
    (r"Sponsored ad for “(.+)” \((.+)\)", r"إعلان ممول لعبارة «\1» (\2)"),
    (r"Search result for “(.+)” \((.+)\)", r"نتيجة بحث لعبارة «\1» (\2)"),
    # ---- jobs
    (r"Job or recruitment offer", "عرض وظيفة أو توظيف"),
    (r"Free email address instead of a company domain", "بريد إلكتروني مجاني بدلاً من نطاق شركة"),
    (r"UAE law puts recruitment costs on the employer, not the worker", "قانون الإمارات يلزم صاحب العمل بتكاليف التوظيف، لا العامل"),
    (r"No licensed recruitment agency named", "لم تُذكر وكالة توظيف مرخّصة"),
    (r"Salary AED ([\d,]+) is far above the market for this role", r"راتب \1 درهم أعلى بكثير من سوق هذه الوظيفة"),
    (r"(Fee for visa or job|Free visa|Visit visa for work|No interview / no experience|Urgency|Whatsapp-only contact|Fines|Payment request|Prize / gift|Discount or refund|Parcel / customs fee): “(.+)”",
     lambda m: f"{w(m[1])}: «{m[2]}»"),
    # ---- Call Guardian flags (also bilingual in rasid/guardian.py)
    (r"Asks for a one-time code \(OTP\)", "يطلب رمز التحقق (OTP)"),
    (r"Claims to be a bank, police or government body", "يدّعي أنه بنك أو شرطة أو جهة حكومية"),
    (r"Pressure to keep it secret or stay on the line", "ضغط لإبقاء الأمر سراً أو البقاء على الخط"),
    (r"Threats or urgency", "تهديد أو استعجال"),
    (r"LLM: (.+)", r"تحليل Claude: \1"),
]
RULES = [(re.compile(p + r"\Z"), t) for p, t in RULES]


_GUARDIAN = None


def _guardian_flags() -> dict:
    """English -> Arabic labels of the Call Guardian rules (a reported call stores its English red flags)."""
    global _GUARDIAN
    if _GUARDIAN is None:
        from .guardian import RULES as G
        _GUARDIAN = {r[3]: r[4] for r in G}
    return _GUARDIAN


def tr(text):
    """Arabic for one server-made sentence; unknown text comes back unchanged."""
    if not isinstance(text, str) or not text:
        return text
    if text in _guardian_flags():
        return _guardian_flags()[text]
    for rx, t in RULES:
        m = rx.match(text)
        if m:
            return t(m) if callable(t) else m.expand(t)
    return text


PLACES = [
    (r"(Ad|Link) landing · (.+)", lambda m: ("صفحة الإعلان · " if m[1] == "Ad" else "صفحة الرابط · ") + m[2]),
    (r"Ad \(no live landing page\)", lambda m: "إعلان (لا توجد صفحة حية)"),
    (r"No live landing page", lambda m: "لا توجد صفحة حية"),
    (r"Recruitment corridor · (.+) → UAE · (.+)", lambda m: f"ممر التوظيف · {m[1]} ← الإمارات · {m[2].replace('(synthetic sample)', '(عينة مصطنعة)')}"),
    (r"Google Maps · (.+)", lambda m: "خرائط Google · " + m[1]),
    (r"Meta Ad Library · (.+)", lambda m: "مكتبة إعلانات Meta · " + m[1]),
    (r"Google Ads Transparency Center \(UAE\)", lambda m: "مركز شفافية إعلانات Google (الإمارات)"),
    (r"Call Guardian \((live call|speakerphone listener)\)", lambda m: "حارس المكالمات"),
]
PLACES = [(re.compile(p + r"\Z"), f) for p, f in PLACES]


def place(text):
    if not isinstance(text, str):
        return text
    for rx, f in PLACES:
        m = rx.match(text)
        if m:
            return f(m)
    return text


def title(text):
    if not isinstance(text, str):
        return text
    m = re.match(r"(Link|Ad|Meta ad|Google ad): (.*)", text, re.S)
    if m:
        return {"Link": "رابط", "Ad": "إعلان", "Meta ad": "إعلان Meta", "Google ad": "إعلان Google"}[m[1]] + ": " + m[2]
    m = re.match(r"Phone scam reported via Call Guardian(?: [—-] (.*))?$", text)
    if m:
        return "مكالمة احتيال مبلَّغ عنها عبر حارس المكالمات" + (" — " + m[1] if m[1] else "")
    return text


def case(c: dict | None) -> dict | None:
    """A case as the console shows it (a copy; the stored case is not changed)."""
    if not c or not is_ar():
        return c
    c = dict(c)
    c["title"] = title(c.get("title"))
    c["where_txt"] = place(c.get("where_txt"))
    if isinstance(c.get("signals"), list):
        c["signals"] = [{**s, "text": tr(s.get("text"))} for s in c["signals"]]
    ev = c.get("evidence")
    if isinstance(ev, dict) and isinstance(ev.get("inspection"), dict):
        insp = dict(ev["inspection"])
        for k in ("links", "code", "payment", "ui", "visual"):
            v = insp.get(k)
            if isinstance(v, list):
                insp[k] = [tr(x) if isinstance(x, str) else ({**x, "text": tr(x.get("text"))} if isinstance(x, dict) and "text" in x else x) for x in v]
        c["evidence"] = {**ev, "inspection": insp}
    if isinstance(c.get("siblings"), list):
        c["siblings"] = [case(s) for s in c["siblings"]]
    return c


JOB_LOG = [
    (r"Downloading newly-registered-domains lists", "تنزيل قوائم النطاقات المسجلة حديثاً"),
    (r"Matching the newly-registered-domains lists \(last 3 days\)", "مطابقة قوائم النطاقات المسجلة حديثاً (آخر 3 أيام)"),
    (r"Analysing (\d+) live sites \(RDAP, page, fingerprints\)", r"تحليل \1 موقعاً حياً (RDAP، الصفحة، البصمات)"),
    (r"Done: (\d+) ads and landing pages stored", r"تم: حُفظ \1 إعلاناً وصفحة"),
    (r"Done: (\d+) listings verified, (\d+) flagged", r"تم: التحقق من \1 قائمة، أُدين منها \2"),
    (r"Done: (\d+) live sites stored, (\d+) scored 50 or more, (\d+) actors", r"تم: حُفظ \1 موقعاً حياً، \2 بدرجة 50 أو أكثر، \3 جهات"),
    (r"Done: (\d+) posts stored", r"تم: حُفظ \1 منشوراً"),
    (r"Done: (\d+) sites stored", r"تم: حُفظ \1 موقعاً"),
    (r"Done: (\d+) newborn sites analysed", r"تم: تحليل \1 موقعاً وليداً"),
    (r"Error: (.+)", r"خطأ: \1"),
    (r"Generated (\d+) lookalike names for (.+)", r"توليد \1 اسماً متشابهاً لـ \2"),
    (r"Google \(UAE, (.+)\): (.+)", r"Google (الإمارات، \1): \2"),
    (r"Google Ads Transparency Center \(UAE\): “(.+)”", r"مركز شفافية إعلانات Google (الإمارات): «\1»"),
    (r"Meta Ad Library: active ads mentioning “(.+)” that reached the UAE", r"مكتبة إعلانات Meta: إعلانات نشطة تذكر «\1» ووصلت إلى الإمارات"),
    (r"Places search: (.+)", r"بحث الخرائط: \1"),
    (r"Reading public Telegram channel (.+)", r"قراءة قناة Telegram العامة \1"),
    (r"Resolving (\d+) names in DNS", r"التحقق من \1 اسماً في DNS"),
    (r"Scoring (\d+) posts", r"تقييم \1 منشوراً"),
    (r"Searching Certificate Transparency logs for '(.+)'", r"البحث في سجلات Certificate Transparency عن '\1'"),
    (r"(\d+) Meta ads returned", r"وصل \1 إعلاناً من Meta"),
    (r"(\d+) Google ad creatives returned", r"وصل \1 إعلاناً من Google"),
    (r"(\d+) landing domains to investigate", r"\1 نطاقاً للتحقيق"),
    (r"(\d+) suspicious result domains", r"\1 نطاقاً مشبوهاً في النتائج"),
    (r"(\d+) names resolve", r"\1 اسماً يعمل"),
    (r"(\d+) listings found", r"وُجدت \1 قائمة"),
    (r"(\d+) new domains to check against (\d+) watchlists", r"\1 نطاقاً جديداً للمطابقة مع \2 قائمة مراقبة"),
    (r"(.+): (\d+) matches", r"\1: \2 تطابقاً"),
    (r"Telegram channel (.+): HTTP (\d+)", r"قناة Telegram \1: HTTP \2"),
]
JOB_LOG = [(re.compile(p + r"\Z"), t) for p, t in JOB_LOG]


def log_line(text):
    if not isinstance(text, str):
        return text
    for rx, t in JOB_LOG:
        m = rx.match(text)
        if m:
            return m.expand(t)
    return text


def job(j: dict | None) -> dict | None:
    if not j or not is_ar():
        return j
    j = dict(j)
    if isinstance(j.get("progress"), list):
        j["progress"] = [log_line(x) if isinstance(x, str) else ({**x, "msg": log_line(x.get("msg"))} if isinstance(x, dict) else x) for x in j["progress"]]
    return j
