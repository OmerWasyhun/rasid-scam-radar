"""Strike pack: one evidence bundle per actor (or single case) with pre-filled abuse reports.

Nothing is sent automatically. An officer reviews the pack and sends each report.
"""
import datetime as dt
import html

from . import cluster, db, llm

REPORT_TO = [
    ("Google Safe Browsing", "https://safebrowsing.google.com/safebrowsing/report_phish/"),
    ("Cloudflare abuse", "https://abuse.cloudflare.com/"),
    ("Meta (ads / pages)", "https://www.facebook.com/help/contact/1758255661104383"),
    ("TDRA / aeCERT", "https://tdra.gov.ae/"),
]


def build(case_ids: list[int], actor: str | None = None) -> dict:
    cases = [c for c in (db.get_case(i) for i in case_ids) if c]
    items = []
    for c in cases:
        ev = c["evidence"] or {}
        rd = ev.get("rdap") or {}
        page = ev.get("page") or {}
        note = c.get("explanation") or llm.template_explain(c)
        items.append({
            "id": c["id"], "sensor": c["sensor"], "subject": c["title"], "impersonates": c["target"], "score": c["score"],
            "hosting": c["where_txt"], "ips": (ev.get("dns") or {}).get("a"), "nameservers": (ev.get("dns") or {}).get("ns"),
            "registrar": rd.get("registrar"), "registered": rd.get("created"), "abuse_contact": rd.get("abuse_email"),
            "final_url": page.get("final_url"), "page_title": page.get("title"), "asks_for": page.get("asks_for"),
            "signals": c["signals"], "note_en": note.get("en"), "note_ar": note.get("ar"),
            "first_seen": dt.datetime.fromtimestamp(c["created"]).isoformat(timespec="seconds"),
        })
    abuse = {}
    for it in items:
        if it["abuse_contact"]:
            abuse.setdefault(it["abuse_contact"], []).append(it["subject"])
    letters = []
    for email, subjects in abuse.items():
        letters.append({
            "to": email,
            "subject": f"Phishing / fraud domains impersonating UAE entities ({len(subjects)})",
            "body": ("Dear abuse team,\n\nThe following domains registered through your service are being used to "
                     "impersonate UAE organisations and collect payment or identity data from the public:\n\n"
                     + "\n".join(f"- {s}" for s in subjects)
                     + "\n\nEvidence (screenshots of page content, DNS, registration data) is available on request. "
                       "We ask that you suspend these domains under your acceptable-use policy.\n\nRegards"),
        })
    return {
        "actor": actor, "generated": dt.datetime.now().isoformat(timespec="seconds"), "count": len(items),
        "shared_fingerprints": cluster.shared_features(case_ids) if len(case_ids) > 1 else [],
        "brands": sorted({i["impersonates"] for i in items if i["impersonates"]}),
        "cases": items, "abuse_letters": letters, "also_report_to": [{"name": n, "url": u} for n, u in REPORT_TO],
    }


LABELS = {
    "en": {"title": "RASID strike pack", "generated": "Generated", "sites": "sites", "brands": "brands", "shared": "Shared fingerprints",
           "single": "single case", "cols": ["Site", "Impersonates", "Score", "Registered", "Registrar", "Hosting", "Asks for"],
           "notes": "Case notes", "letters": "Abuse reports (review before sending)", "no_letters": "No registrar abuse contacts found in RDAP.",
           "to": "To", "also": "Also report to"},
    "ar": {"title": "ملف أدلة راصد", "generated": "أُنشئ في", "sites": "مواقع", "brands": "العلامات", "shared": "البصمات المشتركة",
           "single": "قضية واحدة", "cols": ["الموقع", "ينتحل", "الدرجة", "تاريخ التسجيل", "المسجّل", "الاستضافة", "يطلب"],
           "notes": "ملاحظات القضايا", "letters": "رسائل البلاغ (راجعها قبل الإرسال؛ تُرسل بالإنجليزية إلى جهات التسجيل والاستضافة)",
           "no_letters": "لم يُعثر على عناوين بلاغ للمسجّل في RDAP.", "to": "إلى", "also": "بلّغ أيضاً"},
}


def to_html(pack: dict, ar: bool = False) -> str:
    """Printable pack. ar=True: Arabic page (right-to-left) with Arabic reasons; the abuse letters stay in English."""
    from . import i18n
    e, L = html.escape, LABELS["ar" if ar else "en"]
    subj = (lambda c: i18n.title(c["subject"])) if ar else (lambda c: c["subject"])
    host = (lambda c: i18n.place(c["hosting"])) if ar else (lambda c: c["hosting"])
    why = i18n.tr if ar else (lambda t: t)
    asks = (lambda c: "، ".join(i18n.w(a) for a in c["asks_for"] or [])) if ar else (lambda c: ", ".join(c["asks_for"] or []))
    rows = "".join(
        f"<tr><td>{e(str(subj(c)))}</td><td>{e(str(c['impersonates'] or ''))}</td><td>{c['score']}</td>"
        f"<td>{e(str(c['registered'] or ''))[:10]}</td><td>{e(str(c['registrar'] or ''))}</td><td>{e(str(host(c) or ''))}</td>"
        f"<td>{e(asks(c))}</td></tr>" for c in pack["cases"])
    notes = ""
    for c in pack["cases"]:
        bullets = "".join("<li>" + e(why(s["text"])) + "</li>" for s in c["signals"] if not s.get("ok"))
        first, second = (("note_ar", "rtl"), ("note_en", "ltr")) if ar else (("note_en", "ltr"), ("note_ar", "rtl"))
        notes += (f"<h3>{e(str(subj(c)))} · {c['score']}/100</h3><p dir='{first[1]}'>{e(c[first[0]] or '')}</p>"
                  f"<p dir='{second[1]}'>{e(c[second[0]] or '')}</p><ul>{bullets}</ul>")
    letters = "".join(f"<h3>{L['to']}: {e(l['to'])}</h3><pre dir='ltr'>{e(l['subject'])}\n\n{e(l['body'])}</pre>" for l in pack["abuse_letters"])
    cols = "".join(f"<th>{c}</th>" for c in L["cols"])
    return f"""<!doctype html><html lang="{'ar' if ar else 'en'}" dir="{'rtl' if ar else 'ltr'}"><meta charset="utf-8"><title>{L['title']} {e(pack['actor'] or '')}</title>
<style>body{{font:14px system-ui,"Segoe UI",Tahoma;margin:32px;max-width:1100px}}table{{border-collapse:collapse;width:100%}}td,th{{border:1px solid #ccc;padding:6px;text-align:start;vertical-align:top}}pre{{white-space:pre-wrap;background:#f5f5f5;padding:12px;text-align:left}}</style>
<h1>{L['title']} {e(pack['actor'] or '')}</h1>
<p>{L['generated']} {e(pack['generated'])} · {pack['count']} {L['sites']} · {L['brands']}: {e(', '.join(pack['brands']))}</p>
<p><b>{L['shared']}:</b> {e('; '.join(pack['shared_fingerprints']) or L['single'])}</p>
<table><tr>{cols}</tr>{rows}</table>
<h2>{L['notes']}</h2>{notes}<h2>{L['letters']}</h2>{letters or '<p>' + L['no_letters'] + '</p>'}
<h2>{L['also']}</h2><ul>{''.join(f"<li>{e(r['name'])}: <span dir='ltr'>{e(r['url'])}</span></li>" for r in pack['also_report_to'])}</ul></html>"""
