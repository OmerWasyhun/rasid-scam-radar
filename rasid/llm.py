"""Claude: evidence explanations in Arabic + English, job-post extraction, ad screenshot reading.

Every function has a non-LLM fallback so the console still works before ANTHROPIC_API_KEY is set.
"""
import json
import re

import anthropic

from .config import ANTHROPIC_API_KEY, MODEL

_client = None


def available() -> bool:
    return bool(ANTHROPIC_API_KEY)


def _c():
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    return _client


SYSTEM = (
    "You are an analyst in the Abu Dhabi Police fraud-hunting unit. You write short, factual case notes from the "
    "evidence you are given. Use only the evidence provided; never invent facts, numbers or names. Plain language, "
    "no hedging filler. The reader is a police officer deciding whether to request a takedown."
)


def _ask(content, max_tokens=2000, effort="low") -> str:
    kwargs = dict(
        model=MODEL,
        max_tokens=max_tokens,
        system=SYSTEM,
        messages=[{"role": "user", "content": content}],
        output_config={"effort": effort},
    )
    try:
        resp = _c().beta.messages.create(betas=["server-side-fallback-2026-07-01"], fallbacks="default", **kwargs)
    except anthropic.BadRequestError:
        # model or account without server-side fallbacks: plain request
        resp = _c().messages.create(**kwargs)
    if resp.stop_reason == "refusal":
        raise RuntimeError("The model declined this request")
    return "".join(b.text for b in resp.content if b.type == "text").strip()


def _json(text: str) -> dict:
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        raise ValueError("no JSON in reply")
    return json.loads(m.group(0))


def _evidence_digest(case: dict) -> dict:
    ev = case.get("evidence") or {}
    page = ev.get("page") or {}
    return {
        "sensor": case["sensor"], "subject": case["title"], "impersonates": case.get("target"), "score": case["score"],
        "signals": case.get("signals"), "registrar": (ev.get("rdap") or {}).get("registrar"),
        "registered": (ev.get("rdap") or {}).get("created"), "hosting": case.get("where_txt"),
        "page_title": page.get("title"), "asks_for": page.get("asks_for"), "lures": page.get("lures"),
        "text_sample": (page.get("text_sample") or ev.get("text") or "")[:500], "actor": case.get("actor"),
        "place": {k: (ev.get("place") or {}).get(k) for k in ("displayName", "formattedAddress", "websiteUri", "internationalPhoneNumber")} if ev.get("place") else None,
    }


def explain(case: dict) -> dict:
    """{'en': str, 'ar': str, 'recommendation': str}"""
    if not available():
        return template_explain(case)
    prompt = (
        "Write a case note for this detection. Return JSON only, with keys:\n"
        '"en": 3-5 sentences in English: what it impersonates, the strongest evidence, the risk to victims.\n'
        '"ar": the same note in Modern Standard Arabic.\n'
        '"recommendation": one of "request takedown", "analyst review", "keep watching".\n\n'
        f"Evidence:\n{json.dumps(_evidence_digest(case), ensure_ascii=False, default=str)}"
    )
    try:
        return _json(_ask(prompt))
    except (anthropic.APIError, ValueError, RuntimeError) as e:
        out = template_explain(case)
        out["note"] = f"Template used ({type(e).__name__})"
        return out


def template_explain(case: dict) -> dict:
    bad = [s["text"] for s in case.get("signals", []) if not s.get("ok") and s.get("points", 0) > 0]
    rec = "request takedown" if case["score"] >= 80 else "analyst review" if case["score"] >= 50 else "keep watching"
    en = f"{case['title']} appears to impersonate {case.get('target') or 'a watched entity'} (risk {case['score']}/100). "
    en += ("Evidence: " + "; ".join(bad[:4]) + ".") if bad else "No strong evidence of fraud was found."
    ar = f"يبدو أن {case['title']} ينتحل صفة {case.get('target') or 'جهة مراقبة'} (درجة الخطورة {case['score']}/100). "
    ar += f"عدد المؤشرات: {len(bad)}. " + {"request takedown": "يوصى بطلب الإغلاق.", "analyst review": "يوصى بمراجعة المحلل.",
                                            "keep watching": "يوصى بالاستمرار في المراقبة."}[rec]
    return {"en": en, "ar": ar, "recommendation": rec}


def extract_job_post(text: str) -> dict | None:
    """Structured fields from a job/visa post in any language, plus an English translation."""
    if not available():
        return None
    prompt = (
        "This is a job or visa advertisement collected from a public source. It may be in any language "
        "(Arabic, Hindi, Urdu, Roman Urdu, Malayalam, Tamil, Sinhala, Tagalog, Bengali, Nepali, English...). "
        "Return JSON only with keys: language (name), translation_en, employer_named (string or null), role, "
        "salary_aed (number or null), fee_asked (string or null: who pays what for visa/recruitment), "
        "contact (phones, WhatsApp, emails as a list), visa_type (string or null), red_flags (list of short English strings), "
        "scam_likelihood (0-100).\n\nPost:\n" + text[:4000]
    )
    try:
        return _json(_ask(prompt))
    except (anthropic.APIError, ValueError, RuntimeError):
        return None


def read_ad_image(b64: str, media_type: str) -> dict | None:
    """Read an ad screenshot: advertiser, brand, offer, price, URL, language, verbatim text."""
    if not available():
        return None
    content = [
        {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": b64}},
        {"type": "text", "text": "Read this ad screenshot. Return JSON only with keys: advertiser, brand_claimed, offer, price, "
                                 "landing_url (or null), language, text (verbatim, original language), red_flags (list)."},
    ]
    try:
        return _json(_ask(content, max_tokens=3000))
    except (anthropic.APIError, ValueError, RuntimeError):
        return None
