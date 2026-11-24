/* RASID Call Guardian, local test page.
   The browser plays the part Twilio plays on a real call: it turns speech into text (Web Speech API), sends it to
   /voice/listen with the same ConversationRelay messages, and speaks the Guardian's replies (speechSynthesis).
   All text is inserted with textContent. */
(function () {
'use strict';
const $ = id => document.getElementById(id);
const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
const synth = window.speechSynthesis;
const ARABIC = /[؀-ۿ]/;

const st = {ws: null, open: false, mic: false, recog: null, speaking: 0, interim: null, playing: false, voices: []};

// ---------- transcript ----------
function line(text, who, cls) {
  const d = document.createElement('div');
  d.className = 'ln' + (who === 'RASID' ? ' rasid' : '') + (cls ? ' ' + cls : '');
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
  if (!st.interim) st.interim = line('', 'hearing…', 'interim');
  st.interim.lastChild.textContent = text;
  st.interim.dir = ARABIC.test(text) ? 'rtl' : 'ltr';
}

// ---------- voice out ----------
function loadVoices() {
  st.voices = synth ? synth.getVoices() : [];
  const ar = st.voices.some(v => v.lang.toLowerCase().startsWith('ar'));
  const notes = [];
  if (!SR) notes.push('This browser has no speech recognition: use Microsoft Edge or Google Chrome, or type the lines below.');
  if (!synth) notes.push('This browser cannot speak; warnings will be shown as text.');
  else if (st.voices.length && !ar) notes.push('No Arabic voice found, so Arabic warnings will be shown but not spoken. Microsoft Edge has free Arabic voices (Fatima, Hamdan).');
  $('envNote').textContent = notes.join(' ');
  $('envNote').className = 'g-note' + (notes.length ? ' bad' : '');
}
function pickVoice(lang) {
  const l = lang.toLowerCase();
  const vs = st.voices.filter(v => v.lang.toLowerCase().replace('_', '-') === l);
  const pref = vs.find(v => /natural|online/i.test(v.name)) || vs[0];
  return pref || st.voices.find(v => v.lang.toLowerCase().startsWith(l.slice(0, 2)));
}
function speak(text, lang) {
  const warn = /RASID (warning|caution)|تحذير|تنبيه/.test(text);
  line(text, 'RASID', warn ? 'warn' : '');
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
      if (res.isFinal) { interim(''); const t = res[0].transcript.trim(); if (t) { line(t, 'call'); send({type: 'prompt', voicePrompt: t, lang: r.lang, last: true}); } }
      else partial += res[0].transcript;
    }
    if (partial) interim(partial);
  };
  r.onerror = e => {
    if (e.error === 'not-allowed' || e.error === 'service-not-allowed') { note('Microphone blocked. Allow it in the address bar, then press Start again.'); st.mic = false; }
    else if (e.error === 'network') note('Speech recognition needs an internet connection (the browser\'s free speech service). You can still type lines.');
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
  $('micTxt').textContent = st.speaking ? 'RASID is speaking' : st.recogOn ? 'Listening' : st.open ? 'Connected' : 'Not listening';
}
function note(t) { $('envNote').textContent = t; $('envNote').className = 'g-note bad'; }

// ---------- connection (same messages as Twilio ConversationRelay) ----------
function send(m) { if (st.ws && st.ws.readyState === 1) st.ws.send(JSON.stringify(m)); }

async function connect(useMic) {
  const lang = $('lang').value;
  const r = await fetch('/api/v1/guardian/local-session', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({lang})});
  if (!r.ok) { note((await r.json().catch(() => ({}))).detail || 'Could not start the Guardian.'); return false; }
  const {session, ws, claude} = await r.json();
  $('by').textContent = claude ? 'Analysis: rules + Claude' : 'Analysis: rules only (free, offline)';
  $('log').replaceChildren(); $('sumCard').hidden = true; $('repMsg').textContent = '';
  state({risk: 0, verdict: 'no scam signs', flags: []});
  return new Promise(resolve => {
    const sock = new WebSocket((location.protocol === 'https:' ? 'wss://' : 'ws://') + location.host + ws);
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
  else if (m.type === 'language') { $('lang').value = m.transcriptionLanguage; if (st.recog) { st.recog.lang = m.transcriptionLanguage; pauseMic(); setTimeout(resumeMic, 300); } }
  else if (m.type === 'x-state') state(m);
  else if (m.type === 'x-summary') summary(m);
}

function state(m) {
  $('risk').textContent = m.risk;
  const c = m.risk >= 80 ? 'var(--crit)' : m.risk >= 50 ? 'var(--high)' : 'var(--ok)';
  $('risk').style.color = c;
  $('bar').style.width = m.risk + '%'; $('bar').style.background = c;
  $('verdict').textContent = m.verdict; $('verdict').style.color = c;
  const ul = $('flags'); ul.replaceChildren();
  (m.flags || []).slice(0, 6).forEach(f => { const li = document.createElement('li'); li.textContent = f; ul.append(li); });
  if (m.analysed_by) $('by').textContent = 'Analysis: ' + (m.analysed_by === 'claude' ? 'rules + Claude' : 'rules only (free, offline)');
}

function summary(m) {
  $('sumCard').hidden = false;
  $('sms').textContent = m.sms;
  $('sms').dir = 'auto';
  $('reportForm').hidden = m.summary.verdict === 'no scam signs';
}

function ui() {
  const b = $('start');
  b.textContent = st.open ? 'Stop' : 'Start listening';
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
$('ask').onclick = () => send({type: 'dtmf', digit: '1'});
$('typeForm').onsubmit = async e => {
  e.preventDefault();
  const t = $('typeIn').value.trim();
  if (!t) return;
  if (!st.open && !(await connect(false))) return;
  line(t, 'call (typed)');
  send({type: 'prompt', voicePrompt: t, lang: $('lang').value, last: true});
  $('typeIn').value = '';
};
$('reportForm').onsubmit = async e => {
  e.preventDefault();
  const r = await fetch('/api/v1/guardian/local-report', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({number: $('repNum').value})});
  const j = await r.json().catch(() => ({}));
  $('repMsg').textContent = r.ok ? `Filed as case #${j.case} in the police console (Call Guardian sensor).` : (j.detail || 'Report failed.');
  if (r.ok) $('reportForm').hidden = true;
};

const wait = ms => new Promise(r => setTimeout(r, ms));
async function playSample(name, s) {
  if (st.open) return;
  $('lang').value = s.lang;
  if (!(await connect(false))) return;
  await wait(2500);                                   // let the greeting play
  for (const t of s.lines) {
    if (!st.open) return;
    line(t, 'call (sample)');
    send({type: 'prompt', voicePrompt: t, lang: s.lang, last: true});
    await wait(2200);
  }
  for (let i = 0; st.speaking && i < 100; i++) await wait(300);
  await wait(800);
  send({type: 'x-end'});
}

fetch('/api/v1/guardian/samples').then(r => r.json()).then(all => {
  const labels = {bank_otp_ar: 'Fake bank, OTP (Arabic)', police_fine_en: 'Fake police fine (English)', delivery_link_en: 'Parcel link (English)',
                  friend_dinner_ar: 'Friend, normal call (Arabic)', real_bank_reminder_en: 'Real bank reminder (English)'};
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
