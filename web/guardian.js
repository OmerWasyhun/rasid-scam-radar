/* RASID Call Guardian listener.
   During a call, the browser turns what it hears into text (Web Speech API),
   sends each line to /voice/listen, and speaks the Guardian's warnings aloud
   (speechSynthesis) in Arabic and English. All text is inserted with textContent. */
(function () {
'use strict';
const $ = id => document.getElementById(id);
const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
const synth = window.speechSynthesis;
const ARABIC = /[؀-ۿ]/;

const ME = t('راصد');   // transcript label for the Guardian's own lines
const VERDICT = {'no scam signs': t('لا توجد علامات احتيال'), 'suspicious': t('مكالمة مشبوهة'), 'likely scam': t('احتيال على الأرجح')};

const st = {ws: null, open: false, mic: false, recog: null, speaking: 0, interim: null, playing: false, voices: []};

// ---------- transcript ----------
function line(text, who, cls) {
  const d = document.createElement('div');
  d.className = 'ln' + (who === ME ? ' rasid' : '') + (cls ? ' ' + cls : '');
  d.dir = ARABIC.test(text) ? 'rtl' : 'ltr';
  const s = document.createElement('small');
  s.textContent = who;
  d.append(s, document.createTextNode(text));
  $('log').append(d);
  $('log').scrollTop = $('log').scrollHeight;
  return d;
}
function interim(text) {
  if (!text) { st.interim?.remove(); st.interim = null; return; }
  if (!st.interim) st.interim = line('', t('يسمع…'), 'interim');
  st.interim.lastChild.textContent = text;
  st.interim.dir = ARABIC.test(text) ? 'rtl' : 'ltr';
}

// ---------- voice out ----------
function loadVoices() {
  st.voices = synth ? synth.getVoices() : [];
  const ar = st.voices.some(v => v.lang.toLowerCase().startsWith('ar'));
  const notes = [];
  if (!SR) notes.push(t('هذا المتصفح لا يدعم التعرّف على الكلام: استخدم Microsoft Edge أو Google Chrome، أو اكتب الأسطر في الأسفل.'));
  if (!synth) notes.push(t('هذا المتصفح لا يستطيع النطق؛ ستظهر التحذيرات نصّاً.'));
  $('envNote').textContent = notes.join(' ');
  $('envNote').className = 'g-note' + (notes.length ? ' bad' : '');
}
function pickVoice(lang) {
  const l = lang.toLowerCase();
  const vs = st.voices.filter(v => v.lang.toLowerCase().replace('_', '-') === l);
  const pref = vs.find(v => /natural|online/i.test(v.name)) || vs[0];
  return pref || st.voices.find(v => v.lang.toLowerCase().startsWith(l.slice(0, 2)));
}
// Recorded voice (Gemini TTS, an urgent police-alert delivery) for the Guardian's fixed lines; any other text,
// such as a warning Claude wrote for this call, is spoken by the browser voice instead.
const RECORDED = {
  'راصد، حارس المكالمات من شرطة أبوظبي، انضم إلى هذه المكالمة للتحقق من علامات الاحتيال. لا يتم تسجيل المكالمة.': 'ar-greeting',
  'RASID Call Guardian from Abu Dhabi Police has joined this call to check for fraud. Nothing is recorded.': 'en-greeting',
  'تنبيه من راصد: في هذه المكالمة علامات احتيال. لا تعطِ أي رمز أو بيانات بطاقة أو كلمة مرور.': 'ar-caution',
  'RASID caution: this call shows warning signs. Do not share any code, card details or password.': 'en-caution',
  'تحذير من راصد: هذه المكالمة تطابق أسلوب احتيال معروف. البنوك والشرطة لا تطلب الرمز أبداً. ننصحك بإنهاء المكالمة الآن.': 'ar-danger',
  'RASID warning: this call matches a known scam. Banks and police never ask for codes. We advise you to hang up now.': 'en-danger',
  'راصد: لا توجد علامات احتيال حتى الآن. ومع ذلك، لا تشارك أي رمز أو بيانات بطاقة.': 'ar-clear',
  'RASID: no scam signs so far. Still, never share codes or card details on a call.': 'en-clear',
  'راصد توقف عن الاستماع. الملخص على الشاشة.': 'ar-leaving',
  'RASID has stopped listening. The summary is on the screen.': 'en-leaving',
  'RASID is now listening in English.': 'en-lang',
  'راصد يستمع الآن باللغة العربية.': 'ar-lang',
};
const clipQ = [];
let clipBusy = false, lastTone = 0, actx = null;
function alertTone() {          // two short tones before a caution or a warning, so nobody misses it
  try {
    actx = actx || new (window.AudioContext || window.webkitAudioContext)();
    const now = actx.currentTime;
    [[880, 0], [660, 0.22]].forEach(([f, at]) => {
      const o = actx.createOscillator(), g = actx.createGain();
      o.type = 'sine'; o.frequency.value = f;
      g.gain.setValueAtTime(0.0001, now + at);
      g.gain.exponentialRampToValueAtTime(0.35, now + at + 0.02);
      g.gain.exponentialRampToValueAtTime(0.0001, now + at + 0.2);
      o.connect(g).connect(actx.destination); o.start(now + at); o.stop(now + at + 0.21);
    });
  } catch (e) { /* no Web Audio: skip the tone */ }
  return new Promise(r => setTimeout(r, 480));
}
async function playNextClip() {
  if (clipBusy || !clipQ.length) return;
  clipBusy = true;
  const item = clipQ.shift();
  if (item.warn && Date.now() - lastTone > 4000) { lastTone = Date.now(); await alertTone(); }
  let done = false;
  const finish = () => {
    if (done) return;
    done = true; clipBusy = false;
    st.speaking = Math.max(0, st.speaking - 1);
    if (!st.speaking) setTimeout(resumeMic, 350);
    micUi(); playNextClip();
  };
  const a = new Audio('/web/voice/' + item.clip + '.wav');
  a.onended = a.onerror = finish;
  setTimeout(finish, 20000);
  a.play().catch(finish);
}
function speak(text, lang) {
  const warn = /RASID (warning|caution)|تحذير|تنبيه/.test(text);
  line(text, ME, warn ? 'warn' : '');
  const clip = RECORDED[(text || '').trim()];
  if (clip) { st.speaking++; pauseMic(); micUi(); clipQ.push({ clip, warn }); playNextClip(); return; }
  if (!synth) return;
  const voice = pickVoice(lang || 'en-US');
  if (!voice && lang && lang.startsWith('ar')) return;   // no Arabic voice: shown only
  const u = new SpeechSynthesisUtterance(text);
  u.lang = lang || 'en-US';
  if (voice) u.voice = voice;
  u.rate = 1;
  // Count it as speaking from the moment it is queued; some browsers never fire onend, so a watchdog
  // releases it after a generous estimate of the speaking time and clears a stuck speech queue.
  let done = false;
  const finish = () => {
    if (done) return;
    done = true;
    st.speaking = Math.max(0, st.speaking - 1);
    if (!st.speaking) { if (synth.speaking && stuck) synth.cancel(); setTimeout(resumeMic, 350); }
    micUi();
  };
  let stuck = false;
  st.speaking++; pauseMic(); micUi();
  u.onend = u.onerror = finish;
  setTimeout(() => { stuck = true; finish(); }, 4000 + text.length * 110 * st.speaking);
  synth.speak(u);
}

// ---------- voice in ----------
function makeRecog() {
  const r = new SR();
  r.continuous = true;
  r.interimResults = true;
  r.lang = $('lang').value;
  r.onresult = e => {
    if (st.speaking) return;                       // ignore our own voice
    let partial = '';
    for (let i = e.resultIndex; i < e.results.length; i++) {
      const res = e.results[i];
      if (res.isFinal) { interim(''); const said = res[0].transcript.trim(); if (said) { line(said, t('مكالمة')); send({type: 'prompt', voicePrompt: said}); } }
      else partial += res[0].transcript;
    }
    if (partial) interim(partial);
  };
  r.onerror = e => {
    if (e.error === 'not-allowed' || e.error === 'service-not-allowed') { note(t('الميكروفون محظور. اسمح به من شريط العنوان، ثم اضغط «استمع» مرة أخرى.')); st.mic = false; }
    else if (e.error === 'network') note(t('يحتاج التعرّف على الكلام إلى اتصال بالإنترنت (خدمة الكلام المجانية في المتصفح). ما زال بإمكانك كتابة الأسطر.'));
  };
  r.onend = () => { st.recogOn = false; if (st.mic && st.open && !st.speaking) resumeMic(); micUi(); };
  return r;
}
function resumeMic() {
  if (!st.mic || !st.open || st.speaking || st.recogOn) return;
  try { st.recog.start(); st.recogOn = true; } catch (_) { /* already running */ }
  micUi();
}
function pauseMic() { if (st.recog && st.recogOn) { try { st.recog.abort(); } catch (_) {} st.recogOn = false; } }
function micUi() {
  const m = $('mic');
  m.className = 'mic' + (st.speaking ? ' speak' : st.recogOn ? ' on' : '');
  $('micTxt').textContent = st.speaking ? t('راصد يتحدث') : st.recogOn ? t('يستمع') : st.open ? t('متصل') : t('لا يستمع');
  document.body.classList.toggle('guardian-live', !!st.open);  // console tab shows LIVE while a call is being guarded
}
function note(t) { $('envNote').textContent = t; $('envNote').className = 'g-note bad'; }

// ---------- connection to the RASID server ----------
function send(m) { if (st.ws && st.ws.readyState === 1) st.ws.send(JSON.stringify(m)); }

async function connect(useMic) {
  const lang = $('lang').value;
  const r = await fetch('/api/v1/guardian/local-session', {method: 'POST', headers: {'Content-Type': 'application/json', 'X-Lang': I18N.lang}, body: JSON.stringify({lang})});
  if (!r.ok) { note((await r.json().catch(() => ({}))).detail || t('تعذّر تشغيل الحارس.')); return false; }
  const {session, ws, claude} = await r.json();
  $('by').textContent = claude ? t('التحليل: القواعد + Claude') : t('التحليل: القواعد فقط (مجاني، دون إنترنت)');
  $('log').replaceChildren(); $('sumCard').hidden = true; $('repMsg').textContent = '';
  state({risk: 0, verdict: 'no scam signs', flags: []});
  return new Promise(resolve => {
    const sock = new WebSocket((location.protocol === 'https:' ? 'wss://' : 'ws://') + location.host + ws + (ws.includes('?') ? '&' : '?') + 'lang=' + I18N.lang);
    st.ws = sock;
    sock.onopen = () => {
      st.open = true;
      sock.send(JSON.stringify({type: 'setup', from: 'local', customParameters: {session}}));
      st.mic = useMic && !!SR;
      if (st.mic) { st.recog = makeRecog(); resumeMic(); }
      ui(); resolve(true);
    };
    sock.onmessage = e => onMsg(JSON.parse(e.data));
    sock.onclose = () => { st.open = false; st.mic = false; pauseMic(); interim(''); ui(); resolve(false); };
  });
}

function onMsg(m) {
  if (m.type === 'text') speak(m.token, m.lang);
  else if (m.type === 'x-state') state(m);
  else if (m.type === 'x-summary') summary(m);
}

function state(m) {
  $('risk').textContent = m.risk;
  const c = m.risk >= 80 ? 'var(--crit)' : m.risk >= 50 ? 'var(--high)' : 'var(--ok)';
  $('risk').style.color = c;
  $('bar').style.width = m.risk + '%'; $('bar').style.background = c;
  $('verdict').textContent = VERDICT[m.verdict] || m.verdict; $('verdict').style.color = c;
  const ul = $('flags'); ul.replaceChildren();
  ((I18N.lang === 'ar' && m.flags_ar && m.flags_ar.length) ? m.flags_ar : (m.flags || [])).slice(0, 6).forEach(f => { const li = document.createElement('li'); li.textContent = f; li.dir = 'auto'; ul.append(li); });
  if (m.analysed_by) $('by').textContent = m.analysed_by === 'claude' ? t('التحليل: القواعد + Claude') : t('التحليل: القواعد فقط (مجاني، دون إنترنت)');
}

// After-call summary in the UI language, built from the structured summary (Arabic fields in Arabic mode,
// falling back to the English ones when empty; English fields in English mode).
function summaryText(s) {
  const ar = I18N.lang !== 'en';
  const head = {'likely scam': t('\u{1F6A8} راصد RASID: مكالمة احتيال على الأرجح'), 'suspicious': t('\u26A0\uFE0F راصد RASID: مكالمة مشبوهة'),
                'no scam signs': t('\u2705 راصد RASID: لا توجد علامات احتيال')}[s.verdict] || t('راصد');
  const parts = [head + ' (' + s.risk + '/100)'];
  const said = ar ? (s.summary_ar || s.summary_en) : s.summary_en;
  if (said) parts.push(said);
  const flags = (ar && s.red_flags_ar && s.red_flags_ar.length) ? s.red_flags_ar : (s.red_flags || []);
  if (flags.length) parts.push(t('العلامات: {f}', {f: flags.slice(0, 3).join(ar ? '\u061B ' : '; ')}));
  if (s.verdict !== 'no scam signs') parts.push(t('لا تشارك الرموز أو بيانات البطاقة أبداً. اضغط «إبلاغ» لإرسال الملخص إلى شرطة أبوظبي.'));
  return parts.join('\n');
}

function summary(m) {
  $('sumCard').hidden = false;
  $('sumText').textContent = m.summary ? summaryText(m.summary) : m.text;
  $('sumText').dir = 'auto';
  $('reportForm').hidden = m.summary.verdict === 'no scam signs';
}

function ui() {
  const b = $('start');
  b.textContent = st.open ? t('إيقاف') : t('استمع');
  b.classList.toggle('stop', st.open);
  $('ask').disabled = !st.open;
  $('lang').disabled = st.open;
  document.querySelectorAll('#samples button').forEach(x => { x.disabled = st.open; });
  micUi();
}

// ---------- controls ----------
$('start').onclick = async () => {
  if (st.open) { st.mic = false; pauseMic(); send({type: 'x-end'}); return; }
  if (synth) synth.cancel();
  await connect(true);
};
$('ask').onclick = () => send({type: 'ask'});
$('typeForm').onsubmit = async e => {
  e.preventDefault();
  const typed = $('typeIn').value.trim();
  if (!typed) return;
  if (!st.open && !(await connect(false))) return;
  line(typed, t('مكالمة (مكتوبة)'));
  send({type: 'prompt', voicePrompt: typed});
  $('typeIn').value = '';
};
$('reportForm').onsubmit = async e => {
  e.preventDefault();
  const r = await fetch('/api/v1/guardian/local-report', {method: 'POST', headers: {'Content-Type': 'application/json', 'X-Lang': I18N.lang}, body: JSON.stringify({number: $('repNum').value})});
  const j = await r.json().catch(() => ({}));
  $('repMsg').textContent = r.ok ? t('سُجّل البلاغ كقضية رقم {n} في وحدة الشرطة (مستشعر حارس المكالمات).', {n: j.case}) : (j.detail || t('تعذّر إرسال البلاغ.'));
  if (r.ok) $('reportForm').hidden = true;
};

const wait = ms => new Promise(r => setTimeout(r, ms));
async function playSample(name, s) {
  if (st.open) return;
  $('lang').value = s.lang;
  if (!(await connect(false))) return;
  await wait(2500);                                   // let the greeting play
  for (const said of s.lines) {
    if (!st.open) return;
    line(said, t('مكالمة (عينة)'));
    send({type: 'prompt', voicePrompt: said});
    await wait(2200);
  }
  for (let i = 0; st.speaking && i < 100; i++) await wait(300);
  await wait(800);
  send({type: 'x-end'});
}

fetch('/api/v1/guardian/samples', {headers: {'X-Lang': I18N.lang}}).then(r => r.json()).then(all => {
  const labels = {bank_otp_ar: t('بنك مزيّف، رمز OTP (عربي)'), police_fine_en: t('مخالفة شرطة مزيّفة (إنجليزي)'), delivery_link_en: t('رابط شحنة (إنجليزي)'),
                  friend_dinner_ar: t('صديق، مكالمة عادية (عربي)'), real_bank_reminder_en: t('تذكير حقيقي من البنك (إنجليزي)')};
  Object.entries(all).forEach(([k, s]) => {
    const b = document.createElement('button');
    b.type = 'button'; b.className = 'btn ghost'; b.textContent = labels[k] || k;
    b.onclick = () => playSample(k, s);
    $('samples').append(b);
  });
}).catch(() => {});

if (synth) { loadVoices(); synth.onvoiceschanged = loadVoices; } else loadVoices();
ui();
})();
