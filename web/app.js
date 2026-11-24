/* RASID console: map + case file wired to the FastAPI backend. All server text is escaped before rendering. */
(function () {
'use strict';
const AUH = [54.37, 24.45];
const SENS = {
  maps:    {name: 'Maps Verifier',   ar: 'مدقق الخرائط',        c: '#4cc9f0'},
  domains: {name: 'Lookalike Radar', ar: 'النطاقات المشابهة',    c: '#b48cff'},
  ct:      {name: 'Newborn Domains', ar: 'نطاقات حديثة',          c: '#ffc857'},
  ads:     {name: 'Ads & Search',    ar: 'الإعلانات والبحث',      c: '#ff7eb6'},
  kits:    {name: 'Kit Fingerprint', ar: 'بصمة الأدوات',          c: '#ff5470'},
  jobs:    {name: 'Job & Visa',      ar: 'الوظائف والتأشيرات',    c: '#5ee0a0'},
  calls:   {name: 'Call Screener',   ar: 'فحص المكالمات',         c: '#ff9f43'},
};
const LANGS = ['ALL', 'AR', 'EN', 'HI', 'UR', 'UR-L', 'ML', 'TA', 'SI', 'TL', 'BN', 'NE', 'RU', 'ZH'];
const LANGFONT = {UR: 'ur', HI: 'indic', ML: 'indic', TA: 'indic', SI: 'indic', BN: 'indic', NE: 'indic', AR: 'ar', FA: 'ar', PS: 'ar'};
const reduce = matchMedia('(prefers-reduced-motion: reduce)').matches;
const $ = id => document.getElementById(id);
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
const sev = s => s >= 80 ? 'var(--crit)' : s >= 50 ? 'var(--high)' : 'var(--ok)';

const st = {cases: [], watch: [], stats: null, status: null, view: 'world', on: new Set(Object.keys(SENS)),
            lang: 'ALL', min: 40, sel: null, selActor: null, geo: null, jobs: new Set()};

async function api(path, opts = {}) {
  const r = await fetch(path, {headers: {'Content-Type': 'application/json'}, ...opts,
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

/* ---------- rail ---------- */
function buildRail() {
  const sl = $('sensorlist');
  sl.innerHTML = Object.entries(SENS).map(([k, v]) =>
    `<button class="sensor" style="--c:${v.c}" aria-pressed="true" data-k="${k}"><span class="dot"></span><span>${v.name}<small>${v.ar}</small></span><span class="n" id="n-${k}">0</span></button>`).join('');
  sl.querySelectorAll('.sensor').forEach(b => b.onclick = () => {
    const k = b.dataset.k; st.on.has(k) ? st.on.delete(k) : st.on.add(k);
    b.setAttribute('aria-pressed', st.on.has(k)); render();
  });
  $('langs').innerHTML = LANGS.map(l => `<button class="lchip" aria-pressed="${l === 'ALL'}" data-l="${l}">${l}</button>`).join('');
  $('langs').querySelectorAll('.lchip').forEach(b => b.onclick = () => {
    st.lang = b.dataset.l;
    $('langs').querySelectorAll('.lchip').forEach(x => x.setAttribute('aria-pressed', x === b));
    $('feedfilter').textContent = st.lang === 'ALL' ? 'all languages' : st.lang + ' only';
    render();
  });
  $('minscore').oninput = e => { st.min = +e.target.value; $('minscoreval').textContent = st.min + '+'; render(); };
  $('legend').innerHTML = Object.values(SENS).map(v => `<span><i style="background:${v.c}"></i>${v.name}</span>`).join('');
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
  return `<g class="pin${st.sel === c.id ? ' sel' : ''}" tabindex="0" role="button" data-id="${c.id}" aria-label="${esc(c.title)} risk ${c.score}">${ring}` +
    `<circle class="core" cx="${p[0].toFixed(1)}" cy="${p[1].toFixed(1)}" r="${c.score >= 80 ? 4.2 : 3.3}" fill="${color}"/>` +
    (label ? `<text x="${p[0] + 6}" y="${p[1] + 2.5}" font-family="JetBrains Mono, monospace" font-size="7" fill="#dbe5f2">${esc(label)}</text>` : '') + '</g>';
}
function render() {
  const svg = $('map'); let h = '';
  const list = st.cases.filter(visible);
  const actorIds = st.selActor ? st.cases.filter(c => c.actor === st.selActor) : [];
  if (st.view === 'world') {
    $('mapnote').textContent = 'arcs: hosting → impersonated UAE target · green: recruitment corridor → UAE';
    for (let lo = -150; lo <= 180; lo += 30) { const [x] = P(lo, 0); h += `<line x1="${x}" y1="0" x2="${x}" y2="420" stroke="#13243a" stroke-width=".5"/>`; }
    for (let la = -30; la <= 60; la += 30) { const [, y] = P(0, la); h += `<line x1="0" y1="${y}" x2="1000" y2="${y}" stroke="#13243a" stroke-width=".5"/>`; }
    if (st.geo) h += st.geo.world.map(c => `<path d="${c.d}" transform="translate(0,13)" fill="${c.id === '784' ? 'var(--uae)' : 'var(--land)'}" stroke="${c.id === '784' ? '#4cc9f0' : 'var(--land-line)'}" stroke-width="${c.id === '784' ? 1 : .45}"/>`).join('');
    const t = P(...AUH);
    const pts = list.filter(c => c.lat != null && !inUAE(c));
    pts.forEach((c, i) => h += arc(P(c.lon, c.lat), t, SENS[c.sensor].c, i));
    const al = actorIds.filter(c => c.lat != null && !inUAE(c));
    for (let i = 1; i < al.length; i++) { const a = P(al[i - 1].lon, al[i - 1].lat), b = P(al[i].lon, al[i].lat); h += `<line class="actorline" x1="${a[0]}" y1="${a[1]}" x2="${b[0]}" y2="${b[1]}"/>`; }
    h += `<circle cx="${t[0]}" cy="${t[1]}" r="9" fill="none" stroke="#4cc9f0" stroke-opacity=".5"/>${reduce ? '' : `<circle class="ring" cx="${t[0]}" cy="${t[1]}" r="8" stroke="#4cc9f0"/>`}<circle cx="${t[0]}" cy="${t[1]}" r="3" fill="#4cc9f0"/><text x="${t[0] + 11}" y="${t[1] + 14}" font-family="JetBrains Mono, monospace" font-size="8" fill="#4cc9f0">UAE</text>`;
    pts.forEach(c => h += pin(c, P(c.lon, c.lat), c.sensor === 'jobs' ? (c.langs || [])[0] : ''));
    if (!st.cases.length) h += `<text class="empty-map" x="500" y="400" text-anchor="middle">No detections yet. Type an entity in the command bar, or open Watch and press Hunt.</text>`;
  } else {
    $('mapnote').textContent = 'UAE ground · Google Maps listings: green verified, red flagged';
    h += `<rect width="1000" height="420" fill="#081322"/>`;
    if (st.geo) h += st.geo.inset.map(c => `<path d="${c.d}" transform="translate(${IX},0)" fill="${c.id === '784' ? 'var(--uae)' : 'var(--land)'}" stroke="${c.id === '784' ? '#4cc9f0' : 'var(--land-line)'}" stroke-width="${c.id === '784' ? 1.2 : .6}"/>`).join('');
    h += `<rect x="0" y="0" width="${IX}" height="420" fill="#081322" opacity=".92"/><rect x="${IX + 600}" y="0" width="${1000 - IX - 600}" height="420" fill="#081322" opacity=".92"/>`;
    [['Abu Dhabi', 54.37, 24.45], ['Dubai', 55.27, 25.2], ['Sharjah', 55.39, 25.35], ['Al Ain', 55.76, 24.21], ['Ras Al Khaimah', 55.94, 25.79], ['Ruwais', 52.73, 24.11]]
      .forEach(([n, lo, la]) => { const p = PI(lo, la); h += `<text x="${p[0] - 4}" y="${p[1] - 8}" text-anchor="end" font-family="JetBrains Mono, monospace" font-size="8.5" fill="#8395ae">${n}</text><circle cx="${p[0]}" cy="${p[1]}" r="1.5" fill="#8395ae"/>`; });
    const pts = st.cases.filter(c => inUAE(c) && st.on.has(c.sensor) && (st.lang === 'ALL' || (c.langs || []).includes(st.lang)));
    const al = actorIds.filter(inUAE);
    for (let i = 1; i < al.length; i++) { const a = PI(al[i - 1].lon, al[i - 1].lat), b = PI(al[i].lon, al[i].lat); h += `<line class="actorline" x1="${a[0]}" y1="${a[1]}" x2="${b[0]}" y2="${b[1]}"/>`; }
    pts.forEach(c => h += pin(c, PI(c.lon, c.lat), ''));
    if (!pts.length) h += `<text class="empty-map" x="500" y="400" text-anchor="middle">No Maps listings checked yet. Open Watch and press Maps on a brand (needs the Google Maps key).</text>`;
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
  const rtl = ['AR', 'UR', 'FA', 'PS'].includes(l) ? ' dir="rtl"' : '';
  return `<span class="${cls}"${rtl}>${esc(t)}</span>`;
}

/* ---------- case file ---------- */
async function openCase(id) {
  st.sel = id; tab('case');
  const p = $('p-case'); p.innerHTML = '<p class="hint">Loading case…</p>';
  let c;
  try { c = await api('/api/cases/' + id); } catch (e) { p.innerHTML = `<p class="err">${esc(e.message)}</p>`; return; }
  st.selActor = c.actor; render();
  const ev = c.evidence || {}, page = ev.page || {}, rd = ev.rdap || {}, dns = ev.dns || {}, place = ev.place;
  const color = SENS[c.sensor]?.c || '#888';
  const verdict = c.score >= 80 ? 'Strike queue' : c.score >= 50 ? 'Analyst review' : 'Watch';
  const kv = [];
  if (rd.registered || rd.created) kv.push(['Registered', (rd.created || '').slice(0, 10)]);
  if (rd.registrar) kv.push(['Registrar', rd.registrar]);
  if (rd.abuse_email) kv.push(['Abuse', rd.abuse_email]);
  if (dns.a) kv.push(['IP', dns.a.join(', ')]);
  if (dns.ns && dns.ns.length) kv.push(['NS', dns.ns.join(', ')]);
  if (c.where_txt) kv.push(['Where', c.where_txt]);
  if (page.final_url) kv.push(['Lands on', page.final_url]);
  if (page.title) kv.push(['Title', page.title]);
  if (page.asks_for && page.asks_for.length) kv.push(['Asks for', page.asks_for.join(', ')]);
  if (page.phones && page.phones.length) kv.push(['Phones', page.phones.join(', ')]);
  if (page.analytics_ids && page.analytics_ids.length) kv.push(['Analytics', page.analytics_ids.join(', ')]);
  if (page.favicon_hash) kv.push(['Favicon', String(page.favicon_hash)]);
  if (place) { kv.push(['Listing', place.formattedAddress || '']); if (place.internationalPhoneNumber) kv.push(['Phone', place.internationalPhoneNumber]); if (place.websiteUri) kv.push(['Website', place.websiteUri]); if (place.googleMapsUri) kv.push(['Maps', place.googleMapsUri]); }
  if (ev.search) kv.push(['Found by', `${ev.search.kind} · “${ev.search.query}” (${ev.search.lang})`]);
  if (ev.newborn) kv.push(['Newborn', `${ev.newborn.source} · ${ev.newborn.day}`]);
  const text = ev.text || '';
  const sigs = (c.signals || []).map(s => `<li class="${s.ok ? 'okk' : s.points ? '' : 'neu'}"><span>${esc(s.text)}</span><em>${s.points > 0 ? '+' : ''}${s.points || ''}</em></li>`).join('');
  const ex = c.explanation;
  const key = c.actor || c.id;
  p.innerHTML = `<div class="case">
    <span class="chip" style="--c:${color}">${esc(SENS[c.sensor]?.name || c.sensor)}</span>${c.actor ? `<span class="chip" style="--c:#fff">actor ${esc(c.actor)}</span>` : ''}
    ${(c.langs || []).map(l => `<span class="chip">${esc(l)}</span>`).join('')}
    <h4>${esc(c.title)}</h4>
    <div class="who">Impersonates <b>${esc(c.target || '—')}</b></div>
    <div class="meter"><b style="color:${sev(c.score)}">${c.score}</b><div class="bar"><span style="width:${c.score}%;background:${sev(c.score)}"></span></div><span class="eyebrow">${verdict}</span></div>
    <ul class="sig">${sigs}</ul>
    ${text ? `<div class="quote">${langText(text.slice(0, 700), (c.langs || [])[0])}</div>` : ''}
    ${ev.extracted && ev.extracted.translation_en ? `<div class="note"><p class="eyebrow">Translation</p><p>${esc(ev.extracted.translation_en)}</p></div>` : ''}
    <dl class="kv">${kv.map(([k, v]) => `<dt>${esc(k)}</dt><dd>${esc(v)}</dd>`).join('')}</dl>
    <div id="explain">${ex ? noteHTML(ex) : ''}</div>
    <div class="actions">
      <button class="btn" id="b-explain">${ex ? 'Re-explain' : 'Explain (AR + EN)'}</button>
      <a class="btn ghost" href="/api/pack/${encodeURIComponent(key)}/html" target="_blank" rel="noopener">Strike pack${c.actor ? ' (' + (c.siblings.length + 1) + ' sites)' : ''}</a>
    </div>
    ${c.siblings && c.siblings.length ? `<p class="eyebrow mt">Same actor · shared fingerprints</p><ul class="gen">${c.siblings.map(s => `<li class="link" data-id="${s.id}"><span>${esc(s.title)}</span><em>${esc(s.sensor)} · ${s.score}</em></li>`).join('')}</ul>` : ''}
  </div>`;
  p.querySelectorAll('.gen li.link').forEach(li => li.onclick = () => openCase(+li.dataset.id));
  $('b-explain').onclick = async () => {
    const b = $('b-explain'); b.disabled = true; b.textContent = 'Writing…';
    try { const n = await api(`/api/cases/${id}/explain`, {method: 'POST'}); $('explain').innerHTML = noteHTML(n); b.textContent = 'Re-explain'; }
    catch (e) { $('explain').innerHTML = `<p class="err">${esc(e.message)}</p>`; b.textContent = 'Explain (AR + EN)'; }
    b.disabled = false;
  };
}
function noteHTML(n) {
  return `<div class="note"><p class="eyebrow">Case note · ${esc(n.recommendation || '')}</p><p>${esc(n.en)}</p><p class="ar" dir="rtl">${esc(n.ar)}</p>${n.note ? `<p class="small">${esc(n.note)}</p>` : ''}</div>`;
}

/* ---------- watchlists ---------- */
const GROUPS = {brand: 'Brands & government', event: 'Events & holidays', jobs: 'Recruiters & employers'};
function renderWatch() {
  const p = $('p-watch');
  p.innerHTML = Object.entries(GROUPS).map(([k, label]) => `
    <div class="grp"><div class="grp-h"><span class="eyebrow">${label}</span><button class="plus" data-add="${k}" aria-label="Add to ${label}">+</button></div>
    <form class="stack" id="f-${k}" data-kind="${k}" hidden>
      <label>Name<input name="name" id="w-${k}-name" required placeholder="${k === 'event' ? 'e.g. Abu Dhabi Grand Prix' : k === 'jobs' ? 'e.g. Etihad careers' : 'e.g. Etihad Airways'}"></label>
      <label>Official domains (comma separated)<input name="domains" id="w-${k}-dom" placeholder="${k === 'event' ? 'yasmarinacircuit.com' : 'etihad.com'}"></label>
      <label>Official phone numbers (comma separated)<input name="phones" id="w-${k}-ph" placeholder="+971 600 ..."></label>
      <div class="row">
        <label>Lure<select name="lure" id="w-${k}-lure">${k === 'event' ? '<option value="event">tickets / offers</option><option value="religious">visas / packages</option><option value="brand">gifts / fines</option>' : k === 'jobs' ? '<option value="jobs">jobs / visas</option>' : '<option value="brand">payments / fines / refunds</option>'}</select></label>
        ${k === 'event' ? `<label>Date<input type="date" name="date" id="w-${k}-date"></label>` : ''}
      </div>
      <label>Victim languages</label>
      <div class="langpick">${LANGS.slice(1).map(l => `<label><input type="checkbox" name="lang" value="${l}" ${['AR', 'EN', 'HI', 'UR', 'ML', 'TL', 'TA', 'SI', 'BN', 'NE'].includes(l) ? 'checked' : ''}>${l}</label>`).join('')}</div>
      <div class="row"><button class="btn" type="submit">Add watchlist</button><button class="btn ghost" type="button" data-cancel="${k}">Cancel</button></div>
    </form>
    <ul class="wl">${st.watch.filter(w => w.kind === k).map(w => `<li><span>${esc(w.name)}<small>${esc(w.official_domains.join(', ') || 'no official domain')}${w.date ? ' · ' + esc(w.date) : ''}</small></span>
      <span class="acts"><button class="mini" data-hunt="${w.id}" title="Lookalikes + newborn + CT">Hunt</button><button class="mini" data-maps="${w.id}" title="Google Maps listings">Maps</button><button class="mini" data-search="${w.id}" title="Google results &amp; ads">Search</button><button class="mini" data-seeds="${w.id}" title="Show generated lookalikes">Seeds</button></span></li>`).join('')}</ul></div>`).join('');
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
  p.querySelectorAll('[data-hunt]').forEach(b => b.onclick = () => runJob(`/api/hunt`, {watch_id: +b.dataset.hunt}, 'Hunt'));
  p.querySelectorAll('[data-maps]').forEach(b => b.onclick = () => runJob(`/api/maps/${b.dataset.maps}`, null, 'Maps check'));
  p.querySelectorAll('[data-search]').forEach(b => b.onclick = () => runJob(`/api/search/${b.dataset.search}`, null, 'Search sweep'));
  p.querySelectorAll('[data-seeds]').forEach(b => b.onclick = () => showSeeds(+b.dataset.seeds));
}
async function showSeeds(wid) {
  const r = await api(`/api/watchlists/${wid}/candidates`);
  const counts = {}; r.candidates.forEach(c => counts[c.technique] = (counts[c.technique] || 0) + 1);
  tab('case');
  $('p-case').innerHTML = `<div class="case"><span class="chip" style="--c:var(--s-domains)">Lookalike seeds</span>
    <h4>${esc(r.watch.name)}</h4><div class="who">${r.candidates.length} lookalike names. Hunt checks each in DNS, the newly-registered list and CT logs.</div>
    <div>${Object.entries(counts).map(([k, v]) => `<span class="chip">${esc(k)} ${v}</span>`).join('')}</div>
    <p class="eyebrow mt">Lure words seeded</p><div>${Object.entries(r.seed_words).map(([l, w]) => `<span class="chip">${esc(l)} · ${langText(w, l)}</span>`).join('') || '<span class="hint">none for these languages</span>'}</div>
    <div class="actions"><button class="btn" id="b-hunt">Hunt now</button></div>
    <ul class="gen">${r.candidates.slice(0, 60).map(c => `<li><span>${esc(c.display)}${c.display !== c.domain ? ' → ' + esc(c.domain) : ''}</span><em>${esc(c.technique)}</em></li>`).join('')}</ul></div>`;
  $('b-hunt').onclick = () => runJob('/api/hunt', {watch_id: wid}, 'Hunt');
}
function alertPane(msg) { tab('case'); $('p-case').innerHTML = `<p class="err">${esc(msg)}</p>`; }

/* ---------- tools ---------- */
function renderTools() {
  $('p-tools').innerHTML = `
  <div class="grp"><div class="eyebrow">Newborn sweep</div><p class="hint">Match every watchlist against the last 3 days of newly registered domains (about 70k a day), then analyse the hits.</p>
    <button class="btn" id="b-newborn">Run newborn sweep</button></div>
  <div class="grp"><div class="eyebrow">Inspect an ad</div>
    <form class="stack" id="f-ad"><label>Ad text<textarea id="ad-text" name="text" placeholder="Paste the ad text in any language"></textarea></label>
    <label>Landing URL<input id="ad-url" name="url" placeholder="https://…"></label>
    <label>Screenshot (needs Claude key)<input id="ad-img" type="file" accept="image/png,image/jpeg,image/webp"></label>
    <button class="btn" type="submit">Inspect ad</button></form></div>
  <div class="grp"><div class="eyebrow">Job &amp; visa posts</div>
    <form class="stack" id="f-jobs"><label>Paste posts (one per blank-line block)<textarea id="jobs-text" name="text" placeholder="Any language: Hindi, Urdu, Malayalam, Tagalog…"></textarea></label>
    <label>Public Telegram channels (comma separated)<input id="jobs-tg" name="tg" placeholder="channelname, another_channel"></label>
    <label style="flex-direction:row;align-items:center;gap:6px"><input type="checkbox" id="jobs-samples" name="samples"> Include the 11 synthetic sample posts</label>
    <button class="btn" type="submit">Score posts</button></form></div>`;
  $('b-newborn').onclick = () => runJob('/api/newborn', null, 'Newborn sweep');
  $('f-ad').onsubmit = async e => {
    e.preventDefault();
    const file = $('ad-img').files[0]; let image_b64 = '', media_type = 'image/png';
    if (file) { image_b64 = await new Promise(res => { const r = new FileReader(); r.onload = () => res(String(r.result).split(',')[1]); r.readAsDataURL(file); }); media_type = file.type; }
    showBusy('Inspecting ad and landing page…');
    try { const c = await api('/api/ads/inspect', {method: 'POST', body: {text: $('ad-text').value, url: $('ad-url').value, image_b64, media_type}}); await refresh(); openCase(c.id); }
    catch (err) { alertPane(err.message); }
    hideBusy();
  };
  $('f-jobs').onsubmit = e => {
    e.preventDefault();
    const texts = $('jobs-text').value.split(/\n\s*\n/).map(s => s.trim()).filter(Boolean);
    const telegram = $('jobs-tg').value.split(',').map(s => s.trim()).filter(Boolean);
    runJob('/api/jobs/scan', {texts, telegram, samples: $('jobs-samples').checked}, 'Job posts');
  };
}

/* ---------- actors ---------- */
async function loadActors() {
  const a = await api('/api/actors');
  $('p-actors').innerHTML = a.length ? `<p class="hint">Sites joined by a shared phishing-kit fingerprint, phone number, Telegram bot, analytics ID or hosting.</p><ul class="gen">${a.map(x =>
    `<li class="link" data-a="${esc(x.actor)}"><span>${esc(x.actor)} · ${x.count} items · ${esc(x.brands.join(', '))}</span><em>${esc(x.sensors.join('/'))} · ${x.max_score}</em></li>`).join('')}</ul>`
    : '<p class="hint">No actors yet. Actors appear when two or more flagged items share a fingerprint.</p>';
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
  st.jobs.add(r.job); showBusy(`${label} started…`);
  if (r.watch_id) loadWatch();
  const tick = async () => {
    let j; try { j = await api('/api/jobs/' + r.job); } catch { setTimeout(tick, 2000); return; }
    const last = (j.progress || []).slice(-1)[0];
    if (last) showBusy(`${label}: ${last.msg}`);
    if (j.status === 'running') { refresh(); setTimeout(tick, 1500); return; }
    st.jobs.delete(r.job); await refresh();
    if (j.status === 'error') alertPane(`${label} failed: ${(j.result || {}).error || 'unknown error'}`);
    else { showBusy(`${label}: ${last ? last.msg : 'done'}`); setTimeout(hideBusy, 6000);
      const best = ((j.result || {}).cases || []).map(id => st.cases.find(c => c.id === id)).filter(Boolean).sort((a, b) => b.score - a.score)[0];
      if (best) openCase(best.id); }
  };
  tick();
}

/* ---------- feed, kpis, pulse, events ---------- */
function renderFeed() {
  const rows = st.cases.filter(visible).slice(0, 40);
  $('feed').innerHTML = rows.length ? rows.map(c => `<li data-id="${c.id}"><time>${new Date(c.created * 1000).toLocaleTimeString('en-GB', {timeZone: 'Asia/Dubai', hour: '2-digit', minute: '2-digit'})}</time>
    <span class="txt"><span class="chip" style="--c:${SENS[c.sensor]?.c}">${esc(SENS[c.sensor]?.name || c.sensor)}</span>${(c.langs || []).slice(0, 2).map(l => `<span class="chip">${esc(l)}</span>`).join('')}<br>${langText(c.title, (c.langs || [])[0])}<small class="small"> · ${esc(c.target || '')}</small></span>
    <span class="sc" style="color:${sev(c.score)}">${c.score}</span></li>`).join('') : '<li><span></span><span class="txt hint">Nothing at this filter yet.</span><span></span></li>';
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
  cx.font = '10px JetBrains Mono, monospace'; cx.strokeStyle = '#13243a'; cx.fillStyle = '#5a6c86';
  for (let i = 0; i <= 6; i++) { const x = 12 + i * (w - 24) / 6; cx.beginPath(); cx.moveTo(x, 8); cx.lineTo(x, h - 18); cx.stroke(); cx.fillText(['-24h', '-20h', '-16h', '-12h', '-8h', '-4h', 'now'][i], x - 12, h - 4); }
  const X = i => 12 + i * (w - 24) / 23, Y = v => h - 20 - (v / max) * (h - 34);
  cx.beginPath(); cx.moveTo(X(0), h - 20); data.forEach((v, i) => cx.lineTo(X(i), Y(v))); cx.lineTo(X(23), h - 20); cx.closePath();
  const g = cx.createLinearGradient(0, 0, 0, h); g.addColorStop(0, 'rgba(180,140,255,.4)'); g.addColorStop(1, 'rgba(76,201,240,.06)'); cx.fillStyle = g; cx.fill();
  cx.beginPath(); data.forEach((v, i) => i ? cx.lineTo(X(i), Y(v)) : cx.moveTo(X(i), Y(v))); cx.strokeStyle = '#4cc9f0'; cx.lineWidth = 1.6; cx.stroke();
  cx.fillStyle = '#ff5470'; cx.beginPath(); cx.arc(X(23), Y(data[23]), 3.5, 0, 7); cx.fill();
  $('pulseval').textContent = `risk volume · now ${data[23]}`;
}
function renderEvents() {
  const today = new Date(); today.setHours(0, 0, 0, 0);
  const ev = st.watch.filter(w => w.date).map(w => ({n: w.name, d: Math.round((new Date(w.date + 'T00:00:00') - today) / 864e5)})).filter(e => e.d >= -1).sort((a, b) => a.d - b.d);
  $('events').innerHTML = ev.length ? ev.map(e => `<span class="ev"><b>${e.d}d</b>${esc(e.n)}</span>`).join('') : '<span class="hint">Add a date to an event watchlist to see its countdown here.</span>';
}
function renderKeys() {
  const k = (st.status || {}).keys || {};
  const row = (on, label) => `<span class="${on ? 'on' : 'off'}">${on ? '●' : '○'} ${label}</span>`;
  $('keys').innerHTML = row(k.claude, 'Claude') + row(k.google_maps, 'Google Maps') + row(k.serpapi, 'SerpAPI') + row(true, 'DNS · RDAP · NRD · CT');
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
  runJob('/api/hunt', {name, official_domain: $('cmddom').value.trim() || null, lure}, `Hunt “${name}”`);
};
function tickClock() {
  const d = new Date();
  $('clock').textContent = d.toLocaleTimeString('en-GB', {timeZone: 'Asia/Dubai'});
  $('clockdate').textContent = d.toLocaleDateString('en-GB', {timeZone: 'Asia/Dubai', day: '2-digit', month: 'short', year: 'numeric'}).toUpperCase() + ' · GST';
}

async function boot() {
  buildRail(); renderTools(); tickClock(); setInterval(tickClock, 1000);
  $('p-case').innerHTML = '<p class="hint">Type an entity in the command bar and press Hunt, or open Watch and run a sensor. Click any pin or feed row to open its case file.</p>';
  fetch('/web/world.json').then(r => r.json()).then(j => { st.geo = j; render(); }).catch(() => {});
  try { st.status = await api('/api/status'); renderKeys(); } catch {}
  await loadWatch(); await refresh();
  setInterval(refresh, 8000);
  addEventListener('resize', drawPulse);
}
boot();
})();
