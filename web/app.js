/* RASID console: map + case file wired to the FastAPI backend. All server text is escaped before rendering. */
(function () {
'use strict';
window.t = window.t || ((s, v) => v ? s.replace(/\{(\w+)\}/g, (_, k) => v[k] ?? '') : s);
window.I18N = window.I18N || {lang: 'ar', EN: {}};
const t = (s, v) => window.t(s, v);
const AUH = [54.37, 24.45];
const SENS = {
  maps:    {name: 'مدقق الخرائط',          ar: 'قوائم Google Maps',            c: '#4cc9f0'},
  domains: {name: 'رادار النطاقات المشابهة', ar: 'أسماء تحاكي الجهات الرسمية',    c: '#b48cff'},
  ct:      {name: 'النطاقات الحديثة',       ar: 'تسجيلات جديدة وشهادات CT',      c: '#ffc857'},
  ads:     {name: 'إعلانات التواصل والبحث', ar: 'Meta و Google',                c: '#ff7eb6'},
  kits:    {name: 'بصمة أدوات التصيّد',      ar: 'حزم احتيال مشتركة',            c: '#ff5470'},
  jobs:    {name: 'الوظائف والتأشيرات',     ar: 'عروض توظيف وتأشيرات وهمية',     c: '#5ee0a0'},
  calls:   {name: 'حارس المكالمات',         ar: 'مكالمات مُبلَّغ عنها',           c: '#f4a261'},
};
const LANGS = ['ALL', 'AR', 'EN', 'HI', 'UR', 'UR-L', 'ML', 'TA', 'SI', 'TL', 'BN', 'NE', 'RU', 'ZH'];
const LANGFONT = {UR: 'ur', HI: 'indic', ML: 'indic', TA: 'indic', SI: 'indic', BN: 'indic', NE: 'indic', AR: 'ar', FA: 'ar', PS: 'ar'};
const loc = () => I18N.lang === 'en' ? 'en-GB' : 'ar-AE-u-nu-latn';
const reduce = matchMedia('(prefers-reduced-motion: reduce)').matches;
const $ = id => document.getElementById(id);
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
const sev = s => s >= 80 ? 'var(--crit)' : s >= 50 ? 'var(--high)' : 'var(--ok)';
const sname = k => SENS[k] ? t(SENS[k].name) : k;

const st = {cases: [], watch: [], stats: null, status: null, view: 'world', on: new Set(Object.keys(SENS)),
            lang: 'ALL', min: 40, sel: null, selActor: null, geo: null, jobs: new Set()};

async function api(path, opts = {}) {
  const r = await fetch(path, {headers: {'Content-Type': 'application/json', 'X-Lang': I18N.lang}, ...opts,
                               body: opts.body ? JSON.stringify(opts.body) : undefined});
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(j.detail ? (typeof j.detail === 'string' ? j.detail : JSON.stringify(j.detail)) : `HTTP ${r.status}`);
  return j;
}

/* ---------- projections ---------- */
const P = (lo, la) => [(lo + 180) / 360 * 1000, (84 - la) / 360 * 1000 + 13];
const IK = 600 / 5.6, IX = 200;
const PI = (lo, la) => [IX + (lo - 51) * IK, (26.35 - la) * IK];
const inUAE = c => c.lat != null && c.lat > 22.4 && c.lat < 26.4 && c.lon > 51 && c.lon < 56.6;
const SVGAR = 'font-family:var(--f-ar)';

/* ---------- rail ---------- */
function buildRail() {
  const sl = $('sensorlist');
  sl.innerHTML = Object.entries(SENS).map(([k, v]) =>
    `<button class="sensor" style="--c:${v.c}" aria-pressed="true" data-k="${k}"><span class="dot"></span><span>${t(v.name)}<small>${t(v.ar)}</small></span><span class="n" id="n-${k}">0</span></button>`).join('');
  sl.querySelectorAll('.sensor').forEach(b => b.onclick = () => {
    const k = b.dataset.k; st.on.has(k) ? st.on.delete(k) : st.on.add(k);
    b.setAttribute('aria-pressed', st.on.has(k)); render();
  });
  $('langs').innerHTML = LANGS.map(l => `<button class="lchip" aria-pressed="${l === 'ALL'}" data-l="${l}">${l === 'ALL' ? t('الكل') : l}</button>`).join('');
  $('langs').querySelectorAll('.lchip').forEach(b => b.onclick = () => {
    st.lang = b.dataset.l;
    $('langs').querySelectorAll('.lchip').forEach(x => x.setAttribute('aria-pressed', x === b));
    $('feedfilter').textContent = st.lang === 'ALL' ? t('كل اللغات') : t('{lang} فقط', {lang: st.lang});
    render();
  });
  $('minscore').oninput = e => { st.min = +e.target.value; $('minscoreval').textContent = st.min + '+'; render(); };
  $('legend').innerHTML = Object.values(SENS).map(v => `<span><i style="background:${v.c}"></i>${t(v.name)}</span>`).join('');
  $('vw-world').onclick = () => setView('world');
  $('vw-uae').onclick = () => setView('uae');
}
function setView(v) {
  st.view = v; $('vw-world').setAttribute('aria-pressed', v === 'world'); $('vw-uae').setAttribute('aria-pressed', v === 'uae'); render();
}
const visible = c => st.on.has(c.sensor) && c.score >= st.min && (st.lang === 'ALL' || (c.langs || []).includes(st.lang));

/* ---------- map ---------- */
function arc(a, b, color, i) {
  const mx = (a[0] + b[0]) / 2, d = Math.hypot(b[0] - a[0], b[1] - a[1]), cy = (a[1] + b[1]) / 2 - d * 0.28;
  const path = `M${a[0].toFixed(1)} ${a[1].toFixed(1)} Q${mx.toFixed(1)} ${cy.toFixed(1)} ${b[0].toFixed(1)} ${b[1].toFixed(1)}`;
  const dot = reduce || i > 40 ? '' : `<circle r="1.7" fill="${color}"><animateMotion dur="${(2.4 + (i % 5) * .5).toFixed(1)}s" repeatCount="indefinite" path="${path}"/></circle>`;
  return `<path class="arc" d="${path}" stroke="${color}"/>${dot}`;
}
function pin(c, p, label) {
  const color = c.sensor === 'maps' ? sev(c.score) : SENS[c.sensor].c;
  const ring = c.score >= 85 && !reduce ? `<circle class="ring" cx="${p[0]}" cy="${p[1]}" r="5" stroke="${color}"/>` : '';
  return `<g class="pin${st.sel === c.id ? ' sel' : ''}" tabindex="0" role="button" data-id="${c.id}" aria-label="${esc(c.title)} · ${t('درجة الخطر {n}', {n: c.score})}">${ring}` +
    `<circle class="core" cx="${p[0].toFixed(1)}" cy="${p[1].toFixed(1)}" r="${c.score >= 80 ? 4.2 : 3.3}" fill="${color}"/>` +
    (label ? `<text x="${p[0] + 6}" y="${p[1] + 2.5}" font-family="JetBrains Mono, monospace" font-size="7" fill="#dbe5f2">${esc(label)}</text>` : '') + '</g>';
}
function render() {
  const svg = $('map'); let h = '';
  const list = st.cases.filter(visible);
  const actorIds = st.selActor ? st.cases.filter(c => c.actor === st.selActor) : [];
  if (st.view === 'world') {
    $('mapnote').textContent = t('الأقواس: من الاستضافة ← إلى الجهة الإماراتية المنتحَلة · الأخضر: ممر التوظيف ← الإمارات');
    for (let lo = -150; lo <= 180; lo += 30) { const [x] = P(lo, 0); h += `<line x1="${x}" y1="0" x2="${x}" y2="420" stroke="#13243a" stroke-width=".5"/>`; }
    for (let la = -30; la <= 60; la += 30) { const [, y] = P(0, la); h += `<line x1="0" y1="${y}" x2="1000" y2="${y}" stroke="#13243a" stroke-width=".5"/>`; }
    if (st.geo) h += st.geo.world.map(c => `<path d="${c.d}" transform="translate(0,13)" fill="${c.id === '784' ? 'var(--uae)' : 'var(--land)'}" stroke="${c.id === '784' ? '#4cc9f0' : 'var(--land-line)'}" stroke-width="${c.id === '784' ? 1 : .45}"/>`).join('');
    const tg = P(...AUH);
    const pts = list.filter(c => c.lat != null && !inUAE(c));
    pts.forEach((c, i) => h += arc(P(c.lon, c.lat), tg, SENS[c.sensor].c, i));
    const al = actorIds.filter(c => c.lat != null && !inUAE(c));
    for (let i = 1; i < al.length; i++) { const a = P(al[i - 1].lon, al[i - 1].lat), b = P(al[i].lon, al[i].lat); h += `<line class="actorline" x1="${a[0]}" y1="${a[1]}" x2="${b[0]}" y2="${b[1]}"/>`; }
    h += `<circle cx="${tg[0]}" cy="${tg[1]}" r="9" fill="none" stroke="#4cc9f0" stroke-opacity=".5"/>${reduce ? '' : `<circle class="ring" cx="${tg[0]}" cy="${tg[1]}" r="8" stroke="#4cc9f0"/>`}<circle cx="${tg[0]}" cy="${tg[1]}" r="3" fill="#4cc9f0"/><text x="${tg[0] + 11}" y="${tg[1] + 14}" style="${SVGAR}" font-size="9" fill="#4cc9f0">${t('الإمارات')}</text>`;
    pts.forEach(c => h += pin(c, P(c.lon, c.lat), c.sensor === 'jobs' ? (c.langs || [])[0] : ''));
    if (!st.cases.length) h += `<text class="empty-map" x="500" y="400" text-anchor="middle">${t('لا توجد رصدات بعد. اكتب اسم جهة في شريط الأوامر، أو افتح «المراقبة» واضغط «تعقّب».')}</text>`;
  } else {
    $('mapnote').textContent = t('داخل الإمارات · قوائم Google Maps: الأخضر موثّق، الأحمر مُعلَّم');
    h += `<rect width="1000" height="420" fill="#081322"/>`;
    if (st.geo) h += st.geo.inset.map(c => `<path d="${c.d}" transform="translate(${IX},0)" fill="${c.id === '784' ? 'var(--uae)' : 'var(--land)'}" stroke="${c.id === '784' ? '#4cc9f0' : 'var(--land-line)'}" stroke-width="${c.id === '784' ? 1.2 : .6}"/>`).join('');
    h += `<rect x="0" y="0" width="${IX}" height="420" fill="#081322" opacity=".92"/><rect x="${IX + 600}" y="0" width="${1000 - IX - 600}" height="420" fill="#081322" opacity=".92"/>`;
    [['أبوظبي', 54.37, 24.45], ['دبي', 55.27, 25.2], ['الشارقة', 55.39, 25.35], ['العين', 55.76, 24.21], ['رأس الخيمة', 55.94, 25.79], ['الرويس', 52.73, 24.11]]
      .forEach(([n, lo, la]) => { const p = PI(lo, la); h += `<text x="${p[0] - 4}" y="${p[1] - 8}" text-anchor="end" style="${SVGAR}" font-size="9.5" fill="#8395ae">${t(n)}</text><circle cx="${p[0]}" cy="${p[1]}" r="1.5" fill="#8395ae"/>`; });
    const pts = st.cases.filter(c => inUAE(c) && st.on.has(c.sensor) && (st.lang === 'ALL' || (c.langs || []).includes(st.lang)));
    const al = actorIds.filter(inUAE);
    for (let i = 1; i < al.length; i++) { const a = PI(al[i - 1].lon, al[i - 1].lat), b = PI(al[i].lon, al[i].lat); h += `<line class="actorline" x1="${a[0]}" y1="${a[1]}" x2="${b[0]}" y2="${b[1]}"/>`; }
    pts.forEach(c => h += pin(c, PI(c.lon, c.lat), ''));
    if (!pts.length) h += `<text class="empty-map" x="500" y="400" text-anchor="middle">${t('لم تُفحص أي قوائم على Google Maps بعد. افتح «المراقبة» واضغط «الخرائط» على إحدى العلامات (يتطلب مفتاح Google Maps).')}</text>`;
  }
  svg.innerHTML = h;
  svg.querySelectorAll('.pin').forEach(g => {
    const go = () => openCase(+g.dataset.id);
    g.addEventListener('click', go);
    g.addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); go(); } });
  });
  renderFeed();
}

/* ---------- tabs ---------- */
const TABS = ['case', 'watch', 'tools', 'actors'];
function tab(name) { TABS.forEach(k => { $('t-' + k).setAttribute('aria-selected', k === name); $('p-' + k).hidden = k !== name; }); }
TABS.forEach(k => $('t-' + k).onclick = () => { tab(k); if (k === 'actors') loadActors(); });

function langText(t, l) {
  const cls = LANGFONT[l] || '';
  const dir = ['AR', 'UR', 'FA', 'PS'].includes(l) ? ' dir="rtl"' : ' dir="auto"';
  return `<span class="${cls}"${dir}>${esc(t)}</span>`;
}

/* ---------- case file ---------- */
async function openCase(id) {
  st.sel = id; tab('case');
  const p = $('p-case'); p.innerHTML = `<p class="hint">${t('جارٍ تحميل القضية…')}</p>`;
  let c;
  try { c = await api('/api/cases/' + id); } catch (e) { p.innerHTML = `<p class="err">${esc(e.message)}</p>`; return; }
  st.selActor = c.actor; render();
  const ev = c.evidence || {}, page = ev.page || {}, rd = ev.rdap || {}, dns = ev.dns || {}, place = ev.place;
  const color = SENS[c.sensor]?.c || '#888';
  const verdict = t(c.score >= 80 ? 'قائمة الإزالة' : c.score >= 50 ? 'مراجعة المحلل' : 'مراقبة');
  const kv = [];
  if (rd.registered || rd.created) kv.push(['تاريخ التسجيل', (rd.created || '').slice(0, 10)]);
  if (rd.registrar) kv.push(['جهة التسجيل', rd.registrar]);
  if (rd.abuse_email) kv.push(['بريد البلاغات', rd.abuse_email]);
  if (dns.a) kv.push(['IP', dns.a.join(', ')]);
  if (dns.ns && dns.ns.length) kv.push(['NS', dns.ns.join(', ')]);
  if (c.where_txt) kv.push(['الموقع', c.where_txt]);
  if (page.final_url) kv.push(['يصل إلى', page.final_url]);
  if (page.title) kv.push(['العنوان', page.title]);
  if (page.asks_for && page.asks_for.length) kv.push(['يطلب', page.asks_for.join(', ')]);
  if (page.phones && page.phones.length) kv.push(['الهواتف', page.phones.join(', ')]);
  if (page.analytics_ids && page.analytics_ids.length) kv.push(['معرّفات التحليلات', page.analytics_ids.join(', ')]);
  if (page.favicon_hash) kv.push(['بصمة الأيقونة', String(page.favicon_hash)]);
  if (place) { kv.push(['عنوان الإدراج', place.formattedAddress || '']); if (place.internationalPhoneNumber) kv.push(['الهاتف', place.internationalPhoneNumber]); if (place.websiteUri) kv.push(['الموقع الإلكتروني', place.websiteUri]); if (place.googleMapsUri) kv.push(['الخرائط', place.googleMapsUri]); }
  if (ev.search) kv.push(['اكتُشف عبر', `${ev.search.kind} · “${ev.search.query}” (${ev.search.lang})`]);
  if (ev.newborn) kv.push(['نطاق حديث', `${ev.newborn.source} · ${ev.newborn.day}`]);
  if (c.sensor === 'calls') {
    if (ev.scam_type) kv.push(['نوع الاحتيال', ev.scam_type]);
    if (ev.asks_for && ev.asks_for.length) kv.push(['طُلب', ev.asks_for.join(', ')]);
    if (ev.reporter) kv.push(['المُبلِّغ', ev.reporter]);
    if (ev.minutes) kv.push(['مدة المكالمة', t('{n} دقيقة', {n: ev.minutes})]);
    if (ev.analysed_by) kv.push(['حُلِّلت بواسطة', t(ev.analysed_by === 'claude' ? 'القواعد + Claude' : 'القواعد فقط')]);
  }
  const rep = ev.reputation || {};
  if (rep.safe_browsing && rep.safe_browsing.listed !== undefined) kv.push(['Safe Browsing', rep.safe_browsing.listed ? t('مُدرج: {list}', {list: rep.safe_browsing.threats.join(', ')}) : t('غير مُدرج')]);
  if (rep.virustotal && rep.virustotal.known !== undefined) kv.push(['VirusTotal', rep.virustotal.known ? t('{m} ضار · {s} مشبوه', {m: rep.virustotal.malicious, s: rep.virustotal.suspicious}) : t('لم يُرصد من قبل')]);
  const meta = ev.meta_ad, gad = ev.google_ad;
  if (meta) { kv.push(['صفحة Meta', meta.page_name || '']); kv.push(['المنصات', (meta.publisher_platforms || []).join(', ')]); if (meta.ad_snapshot_url) kv.push(['لقطة الإعلان', meta.ad_snapshot_url]); }
  if (gad) { kv.push(['المعلن', gad.advertiser || '']); if (gad.details_link) kv.push(['تفاصيل الإعلان', gad.details_link]); }
  const shot = ev.inspection;
  const text = ev.text || '';
  const sigs = (c.signals || []).map(s => `<li class="${s.ok ? 'okk' : s.points ? '' : 'neu'}"><span dir="auto">${esc(s.text)}</span><em>${s.points > 0 ? '+' : ''}${s.points || ''}</em></li>`).join('');
  const ex = c.explanation;
  const key = c.actor || c.id;
  p.innerHTML = `<div class="case">
    <span class="chip" style="--c:${color}">${esc(sname(c.sensor))}</span>${c.actor ? `<span class="chip" style="--c:#fff">${t('جهة احتيال {id}', {id: esc(c.actor)})}</span>` : ''}
    ${(c.langs || []).map(l => `<span class="chip">${esc(l)}</span>`).join('')}
    <h4 dir="auto">${esc(c.title)}</h4>
    <div class="who">${['name only', 'unrelated business', 'parked'].includes((ev.inspection || {}).verdict) ? t('الاسم يشبه') : t('ينتحل صفة')} <b dir="auto">${esc(c.target || '—')}</b></div>
    <div class="meter"><b style="color:${sev(c.score)}">${c.score}</b><div class="bar"><span style="width:${c.score}%;background:${sev(c.score)}"></span></div><span class="eyebrow">${verdict}</span></div>
    ${inspHTML(ev.inspection)}
    <ul class="sig">${sigs}</ul>
    ${text ? `<div class="quote">${langText(text.slice(0, 700), (c.langs || [])[0])}</div>` : ''}
    ${ev.extracted && ev.extracted.translation_en ? `<div class="note"><p class="eyebrow">${t('الترجمة')}</p><p dir="auto">${esc(ev.extracted.translation_en)}</p></div>` : ''}
    <dl class="kv">${kv.map(([k, v]) => `<dt>${esc(t(k))}</dt><dd dir="auto">${esc(v)}</dd>`).join('')}</dl>
    <div id="shot">${shotHTML(shot)}</div>
    ${c.sensor === 'calls' && (ev.summary_en || ev.summary_ar) ? `<div class="note"><p class="eyebrow">${t('ملخص المكالمة')}</p><p class="ar" dir="rtl">${esc(ev.summary_ar || '')}</p><p dir="ltr">${esc(ev.summary_en || '')}</p></div>` : ''}
    <div id="explain">${ex ? noteHTML(ex) : ''}</div>
    <div class="actions">
      <button class="btn" id="b-explain">${t(ex ? 'إعادة الشرح' : 'شرح (عربي + إنجليزي)')}</button>
      ${c.sensor !== 'jobs' && c.sensor !== 'maps' && /\./.test(c.title) && !/^(Ad|Meta ad|Google ad):/.test(c.title) ? `<button class="btn ghost" id="b-shot">${t('إعادة فحص الموقع')}</button>` : ''}
      <a class="btn ghost" href="/api/pack/${encodeURIComponent(key)}/html?lang=${I18N.lang}" target="_blank" rel="noopener">${c.actor ? t('حزمة الإزالة ({n} مواقع)', {n: c.siblings.length + 1}) : t('حزمة الإزالة')}</a>
    </div>
    ${c.siblings && c.siblings.length ? `<p class="eyebrow mt">${t('جهة الاحتيال نفسها · بصمات مشتركة')}</p><ul class="gen">${c.siblings.map(s => `<li class="link" data-id="${s.id}"><span dir="auto">${esc(s.title)}</span><em>${esc(sname(s.sensor))} · ${s.score}</em></li>`).join('')}</ul>` : ''}
  </div>`;
  p.querySelectorAll('.gen li.link').forEach(li => li.onclick = () => openCase(+li.dataset.id));
  const bs = $('b-shot');
  if (bs) bs.onclick = async () => {
    bs.disabled = true; bs.textContent = t('جارٍ فتح الموقع وفحصه…');
    try { await api(`/api/cases/${id}/rescan`, {method: 'POST'}); await refresh(); openCase(id); return; }
    catch (e) { $('shot').innerHTML = `<p class="err">${esc(e.message)}</p>`; bs.textContent = t('إعادة فحص الموقع'); }
    bs.disabled = false;
  };
  $('b-explain').onclick = async () => {
    const b = $('b-explain'); b.disabled = true; b.textContent = t('جارٍ الكتابة…');
    try { const n = await api(`/api/cases/${id}/explain`, {method: 'POST'}); $('explain').innerHTML = noteHTML(n); b.textContent = t('إعادة الشرح'); }
    catch (e) { $('explain').innerHTML = `<p class="err">${esc(e.message)}</p>`; b.textContent = t('شرح (عربي + إنجليزي)'); }
    b.disabled = false;
  };
}
const VERDICTS = {
  'impersonation': ['انتحال صفة', 'var(--crit)', 'ينسخ العلامة التجارية ويجمع البيانات أو يشغّل شيفرة ضارة'],
  'copies brand': ['ينسخ العلامة التجارية', 'var(--high)', 'يبدو مثل الموقع الرسمي'],
  'malicious': ['ضار', 'var(--crit)', 'عُثر على روابط أو شيفرة ضارة'],
  'payment capture': ['جمع بيانات الدفع', 'var(--high)', 'يستخدم العلامة التجارية ويطلب الدفع أو بيانات البطاقة'],
  'name only': ['تشابه في الاسم فقط', 'var(--muted)', 'الاسم وحده هو المتشابه'],
  'unrelated business': ['نشاط غير ذي صلة', 'var(--ok)', 'نشاط تجاري مختلف يبدو حقيقيًا'],
  'parked': ['موقوف / معروض للبيع', 'var(--muted)', 'لا محتوى فعليًا بعد؛ يبقى تحت المراقبة'],
};
function inspHTML(i) {
  if (!i || !i.verdict) return '';
  const [label, color, hint] = VERDICTS[i.verdict] || [i.verdict, 'var(--muted)', ''];
  const tl = VERDICTS[i.verdict] ? t(label) : label, th = hint ? t(hint) : '';
  const ui = i.ui ? `<div class="kv" style="grid-template-columns:110px 1fr"><dt>${t('تطابق الواجهة')}</dt><dd><b>${Math.round(i.ui.score * 100)}%</b> · ` +
    Object.entries(i.ui.parts).map(([k, v]) => `${k} ${Math.round(v * 100)}%`).join(' · ') + `</dd></div>` : '';
  const list = (title, arr) => arr && arr.length ? `<p class="eyebrow mt">${t(title)}</p><ul class="gen">${arr.map(x => `<li><span dir="auto">${esc(x)}</span></li>`).join('')}</ul>` : '';
  return `<div class="insp" style="border-color:${color}"><p class="eyebrow">${t('فحص الموقع')}</p>
    <span class="chip" style="--c:${color}">${esc(tl)}</span><span class="small">${esc(th)}</span>
    ${ui}${i.ui_note ? `<p class="small" dir="auto">${esc(i.ui_note)}</p>` : ''}
    ${list('روابط ضارة', i.links)}${list('شيفرة مشبوهة', i.code)}${list('جمع بيانات الدفع / البيانات الشخصية', i.payment)}
    ${(i.hotlinks || []).length ? list('يحمّل ملفات من الموقع الرسمي', i.hotlinks) : ''}</div>`;
}
function shotHTML(i) {
  if (!i || !i.screenshot) return i && i.rendered === false ? `<p class="small">${t('تعذّر على متصفح راصد عرض هذه الصفحة.')}</p>` : '';
  const v = i.visual, vs = i.vision;
  const off = v && v.official_screenshot ? `<figure><img src="/api/shots/${esc(v.official_screenshot)}" alt="${t('الموقع الرسمي')}" loading="lazy"><figcaption>${t('الموقع الرسمي')}</figcaption></figure>` : '';
  return `<div class="shot"><p class="eyebrow">${t('لقطة شاشة · التقطها راصد')}${v ? ` · <b style="color:${v.score >= 0.5 ? 'var(--crit)' : 'var(--text)'}">${t('تطابق بصري {n}%', {n: Math.round(v.score * 100)})}</b>` : ''}</p>
    <div class="shots"><figure><a href="/api/shots/${esc(i.screenshot_full || i.screenshot)}" target="_blank" rel="noopener"><img src="/api/shots/${esc(i.screenshot)}" alt="${t('الصفحة المشبوهة')}" loading="lazy"></a><figcaption>${t('الصفحة المشبوهة')}</figcaption></figure>${off}</div>
    ${v ? `<p class="small">${t('البنية {a}% · الشكل {b}% · الألوان {c}% · البكسلات {d}%', {a: Math.round(v.parts.structure * 100), b: Math.round(v.parts.shape * 100), c: Math.round(v.parts.colours * 100), d: Math.round(v.parts.pixels * 100)})}</p>` : ''}
    ${vs ? `<p class="small"><b>${t('فحص اللقطة:')}</b> <span dir="auto">${esc(vs.summary || '')}</span>${vs.asks_for && vs.asks_for.length ? ' · ' + t('يطلب {list}', {list: esc(vs.asks_for.join(', '))}) : ''}</p>` : ''}</div>`;
}
function noteHTML(n) {
  return `<div class="note"><p class="eyebrow">${t('ملاحظة القضية')} · ${esc(n.recommendation || '')}</p><p class="ar" dir="rtl">${esc(n.ar)}</p><p dir="ltr">${esc(n.en)}</p>${n.note ? `<p class="small" dir="auto">${esc(n.note)}</p>` : ''}</div>`;
}

/* ---------- watchlists ---------- */
const GROUPS = {brand: 'العلامات التجارية والجهات الحكومية', event: 'الفعاليات والمناسبات', jobs: 'جهات التوظيف وأصحاب العمل'};
function renderWatch() {
  const p = $('p-watch');
  p.innerHTML = Object.entries(GROUPS).map(([k, label]) => `
    <div class="grp"><div class="grp-h"><span class="eyebrow">${t(label)}</span><button class="plus" data-add="${k}" aria-label="${t('إضافة إلى {g}', {g: t(label)})}" title="${t('إضافة')}">+</button></div>
    <form class="stack" id="f-${k}" data-kind="${k}" hidden>
      <label>${t('الاسم')}<input name="name" id="w-${k}-name" required placeholder="${t(k === 'event' ? 'مثال: جائزة أبوظبي الكبرى' : k === 'jobs' ? 'مثال: وظائف الاتحاد للطيران' : 'مثال: الاتحاد للطيران')}"></label>
      <label>${t('النطاقات الرسمية (مفصولة بفواصل)')}<input name="domains" id="w-${k}-dom" dir="ltr" placeholder="${k === 'event' ? 'yasmarinacircuit.com' : 'etihad.com'}"></label>
      <label>${t('أرقام الهاتف الرسمية (مفصولة بفواصل)')}<input name="phones" id="w-${k}-ph" dir="ltr" placeholder="+971 600 ..."></label>
      <div class="row">
        <label>${t('نوع الإغراء')}<select name="lure" id="w-${k}-lure">${k === 'event' ? `<option value="event">${t('تذاكر / عروض')}</option><option value="religious">${t('تأشيرات / باقات')}</option><option value="brand">${t('هدايا / مخالفات')}</option>` : k === 'jobs' ? `<option value="jobs">${t('وظائف / تأشيرات')}</option>` : `<option value="brand">${t('مدفوعات / مخالفات / مبالغ مستردة')}</option>`}</select></label>
        ${k === 'event' ? `<label>${t('التاريخ')}<input type="date" name="date" id="w-${k}-date"></label>` : ''}
      </div>
      <label>${t('لغات الضحايا')}</label>
      <div class="langpick">${LANGS.slice(1).map(l => `<label><input type="checkbox" name="lang" value="${l}" ${['AR', 'EN', 'HI', 'UR', 'ML', 'TL', 'TA', 'SI', 'BN', 'NE'].includes(l) ? 'checked' : ''}>${l}</label>`).join('')}</div>
      <div class="row"><button class="btn" type="submit">${t('إضافة قائمة مراقبة')}</button><button class="btn ghost" type="button" data-cancel="${k}">${t('إلغاء')}</button></div>
    </form>
    <ul class="wl">${st.watch.filter(w => w.kind === k).map(w => `<li><span><span dir="auto">${esc(w.name)}</span><small dir="auto">${esc(w.official_domains.join(', ') || t('لا يوجد نطاق رسمي'))}${w.date ? ' · ' + esc(w.date) : ''}</small></span>
      <span class="acts"><button class="mini" data-hunt="${w.id}" title="${t('نطاقات مشابهة + نطاقات حديثة + سجلات CT')}">${t('تعقّب')}</button><button class="mini" data-maps="${w.id}" title="${t('قوائم Google Maps')}">${t('الخرائط')}</button><button class="mini" data-search="${w.id}" title="${t('نتائج Google والنتائج الممولة')}">${t('البحث')}</button><button class="mini" data-social="${w.id}" title="${t('إعلانات Facebook و Instagram و Google')}">${t('التواصل')}</button><button class="mini" data-seeds="${w.id}" title="${t('عرض الأسماء المشابهة المولَّدة')}">${t('البذور')}</button></span></li>`).join('')}</ul></div>`).join('');
  p.querySelectorAll('[data-add]').forEach(b => b.onclick = () => { const f = $('f-' + b.dataset.add); f.hidden = !f.hidden; if (!f.hidden) f.querySelector('input').focus(); });
  p.querySelectorAll('[data-cancel]').forEach(b => b.onclick = () => $('f-' + b.dataset.cancel).hidden = true);
  p.querySelectorAll('form.stack').forEach(f => f.onsubmit = async e => {
    e.preventDefault();
    const fd = new FormData(f), split = s => (s || '').split(',').map(x => x.trim()).filter(Boolean);
    try {
      const w = await api('/api/watchlists', {method: 'POST', body: {kind: f.dataset.kind, name: fd.get('name'), official_domains: split(fd.get('domains')),
        official_phones: split(fd.get('phones')), lure: fd.get('lure'), langs: fd.getAll('lang'), date: fd.get('date') || null}});
      await loadWatch(); showSeeds(w.id);
    } catch (err) { alertPane(err.message); }
  });
  p.querySelectorAll('[data-hunt]').forEach(b => b.onclick = () => runJob(`/api/hunt`, {watch_id: +b.dataset.hunt}, t('التعقّب')));
  p.querySelectorAll('[data-maps]').forEach(b => b.onclick = () => runJob(`/api/maps/${b.dataset.maps}`, null, t('فحص الخرائط')));
  p.querySelectorAll('[data-search]').forEach(b => b.onclick = () => runJob(`/api/search/${b.dataset.search}`, null, t('مسح نتائج البحث')));
  p.querySelectorAll('[data-social]').forEach(b => b.onclick = () => runJob(`/api/social/${b.dataset.social}`, null, t('مسح إعلانات التواصل')));
  p.querySelectorAll('[data-seeds]').forEach(b => b.onclick = () => showSeeds(+b.dataset.seeds));
}
async function showSeeds(wid) {
  const r = await api(`/api/watchlists/${wid}/candidates`);
  const counts = {}; r.candidates.forEach(c => counts[c.technique] = (counts[c.technique] || 0) + 1);
  tab('case');
  $('p-case').innerHTML = `<div class="case"><span class="chip" style="--c:var(--s-domains)">${t('بذور الأسماء المشابهة')}</span>
    <h4 dir="auto">${esc(r.watch.name)}</h4><div class="who">${t('{n} اسمًا مشابهًا. يفحص التعقّب كل اسم منها في DNS وفي قائمة النطاقات المسجّلة حديثًا وفي سجلات CT.', {n: r.candidates.length})}</div>
    <div>${Object.entries(counts).map(([k, v]) => `<span class="chip">${esc(k)} ${v}</span>`).join('')}</div>
    <p class="eyebrow mt">${t('كلمات الإغراء المضمَّنة')}</p><div>${Object.entries(r.seed_words).map(([l, w]) => `<span class="chip">${esc(l)} · ${langText(w, l)}</span>`).join('') || `<span class="hint">${t('لا شيء لهذه اللغات')}</span>`}</div>
    <div class="actions"><button class="btn" id="b-hunt">${t('تعقّب الآن')}</button></div>
    <ul class="gen">${r.candidates.slice(0, 60).map(c => `<li><span dir="ltr">${esc(c.display)}${c.display !== c.domain ? ' → ' + esc(c.domain) : ''}</span><em>${esc(c.technique)}</em></li>`).join('')}</ul></div>`;
  $('b-hunt').onclick = () => runJob('/api/hunt', {watch_id: wid}, t('التعقّب'));
}
function alertPane(msg) { tab('case'); $('p-case').innerHTML = `<p class="err" dir="auto">${esc(msg)}</p>`; }

/* ---------- tools ---------- */
function renderTools() {
  $('p-tools').innerHTML = `
  <div class="grp"><div class="eyebrow">${t('فحص رابط')}</div><p class="hint">${t('أي رابط وصل إلى شخص ما: يتتبّع راصد التحويلات وروابط الاختصار، ويفتح الصفحة في متصفحه الخاص، ويلتقط لقطة شاشة، ثم يعطي درجة مع الأسباب.')}</p>
    <form class="stack" id="f-link"><label>${t('الرابط')}<input id="link-url" name="url" dir="ltr" placeholder="${t('https://… أو bit.ly/…')}" required></label>
    <button class="btn" type="submit">${t('افحص الرابط')}</button></form></div>
  <div class="grp"><div class="eyebrow">${t('مسح النطاقات الحديثة')}</div><p class="hint">${t('مطابقة كل قوائم المراقبة مع النطاقات المسجّلة حديثًا خلال آخر 3 أيام (نحو 70 ألف نطاق يوميًا)، ثم تحليل النتائج.')}</p>
    <button class="btn" id="b-newborn">${t('تشغيل مسح النطاقات الحديثة')}</button></div>
  <div class="grp"><div class="eyebrow">${t('فحص إعلان')}</div>
    <form class="stack" id="f-ad"><label>${t('نص الإعلان')}<textarea id="ad-text" name="text" dir="auto" placeholder="${t('الصق نص الإعلان بأي لغة')}"></textarea></label>
    <label>${t('رابط الصفحة المقصودة')}<input id="ad-url" name="url" dir="ltr" placeholder="https://…"></label>
    <label>${t('لقطة شاشة (تتطلب مفتاح Claude)')}<input id="ad-img" type="file" accept="image/png,image/jpeg,image/webp"></label>
    <button class="btn" type="submit">${t('افحص الإعلان')}</button></form></div>
  <div class="grp"><div class="eyebrow">${t('منشورات الوظائف والتأشيرات')}</div>
    <form class="stack" id="f-jobs"><label>${t('الصق المنشورات (افصل بين كل منشور وآخر بسطر فارغ)')}<textarea id="jobs-text" name="text" dir="auto" placeholder="${t('بأي لغة: الهندية، الأردية، المالايالامية، التاغالوغية…')}"></textarea></label>
    <label>${t('قنوات Telegram العامة (مفصولة بفواصل)')}<input id="jobs-tg" name="tg" dir="ltr" placeholder="channelname, another_channel"></label>
    <label style="flex-direction:row;align-items:center;gap:6px"><input type="checkbox" id="jobs-samples" name="samples"> ${t('تضمين المنشورات التجريبية المصطنعة (11 منشورًا)')}</label>
    <button class="btn" type="submit">${t('تقييم المنشورات')}</button></form></div>`;
  $('b-newborn').onclick = () => runJob('/api/newborn', null, t('مسح النطاقات الحديثة'));
  $('f-link').onsubmit = async e => {
    e.preventDefault();
    showBusy(t('جارٍ فتح الرابط في متصفح راصد…'));
    try { const c = await api('/api/ads/inspect', {method: 'POST', body: {url: $('link-url').value.trim()}}); await refresh(); openCase(c.id); }
    catch (err) { alertPane(err.message); }
    hideBusy();
  };
  $('f-ad').onsubmit = async e => {
    e.preventDefault();
    const file = $('ad-img').files[0]; let image_b64 = '', media_type = 'image/png';
    if (file) { image_b64 = await new Promise(res => { const r = new FileReader(); r.onload = () => res(String(r.result).split(',')[1]); r.readAsDataURL(file); }); media_type = file.type; }
    showBusy(t('جارٍ فحص الإعلان والصفحة المقصودة…'));
    try { const c = await api('/api/ads/inspect', {method: 'POST', body: {text: $('ad-text').value, url: $('ad-url').value, image_b64, media_type}}); await refresh(); openCase(c.id); }
    catch (err) { alertPane(err.message); }
    hideBusy();
  };
  $('f-jobs').onsubmit = e => {
    e.preventDefault();
    const texts = $('jobs-text').value.split(/\n\s*\n/).map(s => s.trim()).filter(Boolean);
    const telegram = $('jobs-tg').value.split(',').map(s => s.trim()).filter(Boolean);
    runJob('/api/jobs/scan', {texts, telegram, samples: $('jobs-samples').checked}, t('منشورات الوظائف'));
  };
}

/* ---------- actors ---------- */
async function loadActors() {
  const a = await api('/api/actors');
  $('p-actors').innerHTML = a.length ? `<p class="hint">${t('مواقع تربطها بصمة مشتركة: أداة تصيّد، أو رقم هاتف، أو بوت Telegram، أو معرّف تحليلات، أو استضافة.')}</p><ul class="gen">${a.map(x =>
    `<li class="link" data-a="${esc(x.actor)}"><span>${esc(x.actor)} · ${t('{n} عناصر', {n: x.count})} · <span dir="auto">${esc(x.brands.join(', '))}</span></span><em>${esc(x.sensors.map(sname).join(' / '))} · ${x.max_score}</em></li>`).join('')}</ul>`
    : `<p class="hint">${t('لا توجد جهات احتيال بعد. تظهر الجهة عندما يشترك عنصران مُعلَّمان أو أكثر في بصمة واحدة.')}</p>`;
  $('p-actors').querySelectorAll('li.link').forEach(li => li.onclick = () => {
    const first = st.cases.filter(c => c.actor === li.dataset.a).sort((a, b) => b.score - a.score)[0];
    if (first) openCase(first.id);
  });
}

/* ---------- jobs ---------- */
function showBusy(msg) { $('jobbar').hidden = false; $('jobmsg').textContent = msg; }
function hideBusy() { if (!st.jobs.size) $('jobbar').hidden = true; }
async function runJob(path, body, label) {
  let r;
  try { r = await api(path, {method: 'POST', body: body || undefined}); } catch (e) { alertPane(`${label}: ${e.message}`); return; }
  st.jobs.add(r.job); showBusy(t('بدأ {label}…', {label}));
  if (r.watch_id) loadWatch();
  const tick = async () => {
    let j; try { j = await api('/api/jobs/' + r.job); } catch { setTimeout(tick, 2000); return; }
    const last = (j.progress || []).slice(-1)[0];
    if (last) showBusy(`${label}: ${last.msg}`);
    if (j.status === 'running') { refresh(); setTimeout(tick, 1500); return; }
    st.jobs.delete(r.job); await refresh();
    if (j.status === 'error') alertPane(t('تعذّر إكمال {label}: {err}', {label, err: (j.result || {}).error || t('خطأ غير معروف')}));
    else { showBusy(`${label}: ${last ? last.msg : t('اكتمل')}`); setTimeout(hideBusy, 6000);
      const best = ((j.result || {}).cases || []).map(id => st.cases.find(c => c.id === id)).filter(Boolean).sort((a, b) => b.score - a.score)[0];
      if (best) openCase(best.id); }
  };
  tick();
}

/* ---------- feed, kpis, pulse, events ---------- */
function renderFeed() {
  const rows = st.cases.filter(visible).slice(0, 40);
  $('feed').innerHTML = rows.length ? rows.map(c => `<li data-id="${c.id}"><time>${new Date(c.created * 1000).toLocaleTimeString(loc(), {timeZone: 'Asia/Dubai', hour: '2-digit', minute: '2-digit', hourCycle: 'h23'})}</time>
    <span class="txt"><span class="chip" style="--c:${SENS[c.sensor]?.c}">${esc(sname(c.sensor))}</span>${(c.langs || []).slice(0, 2).map(l => `<span class="chip">${esc(l)}</span>`).join('')}<br>${langText(c.title, (c.langs || [])[0])}<small class="small"> · <span dir="auto">${esc(c.target || '')}</span></small></span>
    <span class="sc" style="color:${sev(c.score)}">${c.score}</span></li>`).join('') : `<li><span></span><span class="txt hint">${t('لا توجد نتائج لهذا الفلتر بعد.')}</span><span></span></li>`;
  $('feed').querySelectorAll('li[data-id]').forEach(li => li.onclick = () => openCase(+li.dataset.id));
}
function renderStats() {
  const s = st.stats; if (!s) return;
  $('k-total').textContent = s.total.toLocaleString('en'); $('k-flag').textContent = s.flagged.toLocaleString('en');
  $('k-crit').textContent = s.critical.toLocaleString('en'); $('k-act').textContent = s.actors.toLocaleString('en');
  Object.keys(SENS).forEach(k => { const n = $('n-' + k); if (n) n.textContent = s.by_sensor[k] || 0; });
  drawPulse();
}
function drawPulse() {
  const cv = $('pulse'), cx = cv.getContext('2d'), w = cv.clientWidth, h = 140, dpr = devicePixelRatio || 1;
  cv.width = Math.round(w * dpr); cv.height = h * dpr; cx.setTransform(dpr, 0, 0, dpr, 0, 0);
  const data = (st.stats && st.stats.hourly) || new Array(24).fill(0), max = Math.max(50, ...data);
  cx.direction = 'ltr'; cx.textAlign = 'left';
  cx.font = '10px "JetBrains Mono", "IBM Plex Sans Arabic", monospace'; cx.strokeStyle = '#13243a'; cx.fillStyle = '#5a6c86';
  for (let i = 0; i <= 6; i++) { const x = 12 + i * (w - 24) / 6; cx.beginPath(); cx.moveTo(x, 8); cx.lineTo(x, h - 18); cx.stroke(); cx.fillText(t(['قبل 24 س', 'قبل 20 س', 'قبل 16 س', 'قبل 12 س', 'قبل 8 س', 'قبل 4 س', 'الآن'][i]), x - 12, h - 4); }
  const X = i => 12 + i * (w - 24) / 23, Y = v => h - 20 - (v / max) * (h - 34);
  cx.beginPath(); cx.moveTo(X(0), h - 20); data.forEach((v, i) => cx.lineTo(X(i), Y(v))); cx.lineTo(X(23), h - 20); cx.closePath();
  const g = cx.createLinearGradient(0, 0, 0, h); g.addColorStop(0, 'rgba(180,140,255,.4)'); g.addColorStop(1, 'rgba(76,201,240,.06)'); cx.fillStyle = g; cx.fill();
  cx.beginPath(); data.forEach((v, i) => i ? cx.lineTo(X(i), Y(v)) : cx.moveTo(X(i), Y(v))); cx.strokeStyle = '#4cc9f0'; cx.lineWidth = 1.6; cx.stroke();
  cx.fillStyle = '#ff5470'; cx.beginPath(); cx.arc(X(23), Y(data[23]), 3.5, 0, 7); cx.fill();
  $('pulseval').textContent = t('حجم المخاطر · الآن {n}', {n: data[23]});
}
function renderEvents() {
  const today = new Date(); today.setHours(0, 0, 0, 0);
  const ev = st.watch.filter(w => w.date).map(w => ({n: w.name, d: Math.round((new Date(w.date + 'T00:00:00') - today) / 864e5)})).filter(e => e.d >= -1).sort((a, b) => a.d - b.d);
  $('events').innerHTML = ev.length ? ev.map(e => `<span class="ev"><b>${t('{n} يوم', {n: e.d})}</b><span dir="auto">${esc(e.n)}</span></span>`).join('') : `<span class="hint">${t('أضف تاريخًا إلى قائمة مراقبة لفعالية لترى العدّ التنازلي هنا.')}</span>`;
}
function renderKeys() {
  const k = (st.status || {}).keys || {};
  const row = (on, label) => `<span class="${on ? 'on' : 'off'}" title="${t(on ? 'مفعّل' : 'غير مفعّل')}">${on ? '●' : '○'} ${t(label)}</span>`;
  $('keys').innerHTML = row(true, 'DNS · RDAP · NRD · CT') + row(k.claude, 'Claude') + row(k.google_maps, 'Google Maps') + row(k.serpapi, 'SerpApi') +
    row(k.meta_ads, 'مكتبة إعلانات Meta') + row(k.safe_browsing, 'Safe Browsing') + row(k.virustotal, 'VirusTotal') +
    (k.login ? `<a class="small" href="/logout">${t('تسجيل الخروج')}</a>` : '');
}

/* ---------- data ---------- */
async function loadWatch() { st.watch = await api('/api/watchlists'); renderWatch(); renderEvents(); }
async function refresh() {
  try {
    const [cases, stats] = await Promise.all([api('/api/cases?limit=800'), api('/api/stats')]);
    st.cases = cases; st.stats = stats; renderStats(); render();
  } catch (e) { /* server restarting */ }
}
$('cmdform').onsubmit = e => {
  e.preventDefault();
  const name = $('cmd').value.trim(); if (!name) return;
  const lure = /hajj|umrah|ramadan/i.test(name) ? 'religious' : /prix|gp\b|festival|concert|expo|season|day|eid/i.test(name) ? 'event' : /career|job|recruit|tadbeer|hiring/i.test(name) ? 'jobs' : 'brand';
  runJob('/api/hunt', {name, official_domain: $('cmddom').value.trim() || null, lure}, t('تعقّب «{name}»', {name}));
};
function tickClock() {
  const d = new Date();
  $('clock').textContent = d.toLocaleTimeString(loc(), {timeZone: 'Asia/Dubai', hour: '2-digit', minute: '2-digit', second: '2-digit', hourCycle: 'h23'});
  const en = I18N.lang === 'en', ds = d.toLocaleDateString(loc(), {timeZone: 'Asia/Dubai', day: '2-digit', month: en ? 'short' : 'long', year: 'numeric'});
  $('clockdate').textContent = (en ? ds.toUpperCase() : ds) + ' · ' + t('بتوقيت الخليج');
}

function showView() {
  const g = location.hash === '#guardian';
  $('view-hunt').hidden = g;
  $('view-guardian').hidden = !g;
  $('cmdform').hidden = g;
  $('nav-hunt').setAttribute('aria-selected', !g);
  $('nav-guardian').setAttribute('aria-selected', g);
  if (!g) { render(); drawPulse(); refresh(); }
}
addEventListener('hashchange', showView);

async function boot() {
  buildRail(); renderTools(); tickClock(); setInterval(tickClock, 1000); showView();
  $('p-case').innerHTML = `<p class="hint">${t('اكتب اسم جهة في شريط الأوامر واضغط «تعقّب»، أو افتح «المراقبة» وشغّل أحد المستشعرات. انقر أي دبوس على الخريطة أو أي صف في قائمة الرصدات لفتح ملف القضية.')}</p>`;
  fetch('/web/world.json').then(r => r.json()).then(j => { st.geo = j; render(); }).catch(() => {});
  try { st.status = await api('/api/status'); renderKeys(); } catch {}
  await loadWatch(); await refresh();
  setInterval(refresh, 8000);
  addEventListener('resize', drawPulse);
}
boot();
})();
