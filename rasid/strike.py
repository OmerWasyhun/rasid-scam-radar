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


def to_html(pack: dict) -> str:
    e = html.escape
    rows = "".join(
        f"<tr><td>{e(str(c['subject']))}</td><td>{e(str(c['impersonates'] or ''))}</td><td>{c['score']}</td>"
        f"<td>{e(str(c['registered'] or ''))[:10]}</td><td>{e(str(c['registrar'] or ''))}</td><td>{e(str(c['hosting'] or ''))}</td>"
        f"<td>{e(', '.join(c['asks_for'] or []))}</td></tr>" for c in pack["cases"])
    notes = ""
    for c in pack["cases"]:
        bullets = "".join("<li>" + e(s["text"]) + "</li>" for s in c["signals"] if not s.get("ok"))
        notes += (f"<h3>{e(str(c['subject']))} · {c['score']}/100</h3><p>{e(c['note_en'] or '')}</p>"
                  f"<p dir='rtl'>{e(c['note_ar'] or '')}</p><ul>{bullets}</ul>")
    letters = "".join(f"<h3>To: {e(l['to'])}</h3><pre>{e(l['subject'])}\n\n{e(l['body'])}</pre>" for l in pack["abuse_letters"])
    return f"""<!doctype html><meta charset="utf-8"><title>Strike pack {e(pack['actor'] or '')}</title>
<style>body{{font:14px system-ui;margin:32px;max-width:1100px}}table{{border-collapse:collapse;width:100%}}td,th{{border:1px solid #ccc;padding:6px;text-align:left;vertical-align:top}}pre{{white-space:pre-wrap;background:#f5f5f5;padding:12px}}</style>
<h1>RASID strike pack {e(pack['actor'] or '')}</h1>
<p>Generated {e(pack['generated'])} · {pack['count']} sites · brands: {e(', '.join(pack['brands']))}</p>
<p><b>Shared fingerprints:</b> {e('; '.join(pack['shared_fingerprints']) or 'single case')}</p>
<table><tr><th>Site</th><th>Impersonates</th><th>Score</th><th>Registered</th><th>Registrar</th><th>Hosting</th><th>Asks for</th></tr>{rows}</table>
<h2>Case notes</h2>{notes}<h2>Abuse reports (review before sending)</h2>{letters or '<p>No registrar abuse contacts found in RDAP.</p>'}
<h2>Also report to</h2><ul>{''.join(f"<li>{e(r['name'])}: {e(r['url'])}</li>" for r in pack['also_report_to'])}</ul>"""
