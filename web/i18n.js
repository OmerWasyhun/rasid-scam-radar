/* RASID console languages. Arabic (right-to-left) is the default and is what the HTML and scripts are written in;
   English (left-to-right) is chosen with the header toggle and remembered in localStorage.
   t('Arabic text') returns the English original in English mode and the Arabic text otherwise.
   Loaded first, in <head>, so the page direction is right before anything is drawn.
   The console script's own English entries live in /web/i18n-app.js (Object.assign(I18N.EN, {...})). */
(function () {
'use strict';
let lang = 'ar';
try { if (localStorage.getItem('rasid-lang') === 'en') lang = 'en'; } catch (_) { /* storage blocked: Arabic */ }
const LANG = lang;
document.documentElement.lang = LANG;
document.documentElement.dir = LANG === 'en' ? 'ltr' : 'rtl';

const EN = {
  // ---------- page shell (index.html) ----------
  "راصد · رادار الاحتيال": "RASID Scam Radar",
  "شرطة أبوظبي · تعقّب الاحتيال": "Abu Dhabi Police · Fraud Hunt",
  "أدوات راصد": "RASID tools",
  "تعقّب الاحتيال": "Fraud Hunt",
  "حارس المكالمات": "Call Guardian",
  "<": ">",
  "تعقّب جهة…  مثل: الاتحاد للطيران، جائزة أبوظبي الكبرى، تدبير": "hunt an entity…  e.g. Etihad Airways, Abu Dhabi Grand Prix, Tadbeer",
  "تعقّب جهة": "Hunt an entity",
  "النطاق الرسمي (اختياري)": "official domain (optional)",
  "النطاق الرسمي": "Official domain",
  "تعقّب": "Hunt",
  "مواقع ومنشورات حُلّلت": "sites & posts analysed",
  "مُعلَّمة (50 فأكثر)": "flagged (50+)",
  "قائمة الإزالة (80 فأكثر)": "strike queue (80+)",
  "جهات احتيال مُجمَّعة": "actors clustered",
  "المستشعرات": "Sensors",
  "عرض الخريطة": "Map view",
  "العالم": "WORLD",
  "داخل الإمارات": "UAE GROUND",
  "لغة الضحية": "Victim language",
  "أدنى درجة": "Min score",
  "المفاتيح": "Keys",
  "خريطة البنية التحتية للاحتيال المرصودة": "Map of detected scam infrastructure",
  "جارٍ العمل…": "Working…",
  "القضية": "Case",
  "المراقبة": "Watch",
  "الأدوات": "Tools",
  "الجهات": "Actors",
  "نبض التهديد · آخر 24 ساعة": "Threat pulse · last 24h",
  "الرصدات خلال 24 ساعة": "Detections over 24 hours",
  "أحدث الرصدات": "Latest detections",
  "كل اللغات": "all languages",

  // ---------- Call Guardian (index.html) ----------
  "g.step1": "When a call you are unsure about starts, choose the call language and press <b>Listen</b>, then allow the microphone.",
  "g.step2": "RASID hears the call and checks what is being asked for, moment by moment.",
  "g.step3": "If scam signs appear, RASID warns <b>out loud</b> in Arabic and English.",
  "g.step4": "Say <b>“RASID”</b> / <b>“راصد”</b> to ask its opinion, or <b>“RASID leave”</b> / <b>“راصد اطلع”</b> to stop listening. After the call, report it in <b>one click</b>.",
  "لغة المكالمة": "Call language",
  "العربية (ar-AE)": "Arabic (ar-AE)",
  "الإنجليزية (en-US)": "English (en-US)",
  "استمع": "Listen",
  "اسأل راصد": "Ask RASID",
  "لا يستمع": "Not listening",
  "نص المكالمة": "Call transcript",
  "لا يوجد ميكروفون؟ اكتب ما يقوله المتصل واضغط Enter…": "No microphone? Type what the caller says and press Enter…",
  "اكتب سطراً من المكالمة": "Type a line from the call",
  "إرسال": "Send",
  "خطر الاحتيال": "Scam risk",
  "لا توجد علامات احتيال": "no scam signs",
  "جرّب مكالمة تجريبية": "Try a sample call",
  "تُشغّل مكالمة مصطنعة نصّاً عبر الحارس، بلا حاجة إلى ميكروفون.": "Plays a synthetic call through the Guardian as text, no microphone needed.",
  "بعد المكالمة": "After the call",
  "لا يُحفظ إلا هذا الملخص. لا تسجيل صوتي ولا نص للمكالمة.": "Only this summary is kept. No audio, no transcript.",
  "رقم المتصل (اختياري)": "Caller’s number (optional)",
  "رقم المتصل": "Caller’s number",
  "إبلاغ": "Report",

  // ---------- Call Guardian (guardian.js) ----------
  "راصد": "RASID",
  "مكالمة مشبوهة": "suspicious",
  "احتيال على الأرجح": "likely scam",
  "يسمع…": "hearing…",
  "هذا المتصفح لا يدعم التعرّف على الكلام: استخدم Microsoft Edge أو Google Chrome، أو اكتب الأسطر في الأسفل.": "This browser has no speech recognition: use Microsoft Edge or Google Chrome, or type the lines below.",
  "هذا المتصفح لا يستطيع النطق؛ ستظهر التحذيرات نصّاً.": "This browser cannot speak; warnings will be shown as text.",
  "لم يُعثر على صوت عربي، لذا ستظهر التحذيرات العربية نصّاً دون نطق. يوفّر Microsoft Edge أصواتاً عربية مجانية (Fatima، Hamdan).": "No Arabic voice found, so Arabic warnings will be shown but not spoken. Microsoft Edge has free Arabic voices (Fatima, Hamdan).",
  "مكالمة": "call",
  "مكالمة (مكتوبة)": "call (typed)",
  "مكالمة (عينة)": "call (sample)",
  "الميكروفون محظور. اسمح به من شريط العنوان، ثم اضغط «استمع» مرة أخرى.": "Microphone blocked. Allow it in the address bar, then press Listen again.",
  "يحتاج التعرّف على الكلام إلى اتصال بالإنترنت (خدمة الكلام المجانية في المتصفح). ما زال بإمكانك كتابة الأسطر.": "Speech recognition needs an internet connection (the browser’s free speech service). You can still type lines.",
  "راصد يتحدث": "RASID is speaking",
  "يستمع": "Listening",
  "متصل": "Connected",
  "تعذّر تشغيل الحارس.": "Could not start the Guardian.",
  "التحليل: القواعد + Claude": "Analysis: rules + Claude",
  "التحليل: القواعد فقط (مجاني، دون إنترنت)": "Analysis: rules only (free, offline)",
  "إيقاف": "Stop",
  "سُجّل البلاغ كقضية رقم {n} في وحدة الشرطة (مستشعر حارس المكالمات).": "Filed as case #{n} in the police console (Call Guardian sensor).",
  "تعذّر إرسال البلاغ.": "Report failed.",
  "بنك مزيّف، رمز OTP (عربي)": "Fake bank, OTP (Arabic)",
  "مخالفة شرطة مزيّفة (إنجليزي)": "Fake police fine (English)",
  "رابط شحنة (إنجليزي)": "Parcel link (English)",
  "صديق، مكالمة عادية (عربي)": "Friend, normal call (Arabic)",
  "تذكير حقيقي من البنك (إنجليزي)": "Real bank reminder (English)",
  "\u{1F6A8} راصد RASID: مكالمة احتيال على الأرجح": "\u{1F6A8} RASID: likely scam call",
  "⚠️ راصد RASID: مكالمة مشبوهة": "⚠️ RASID: suspicious call",
  "✅ راصد RASID: لا توجد علامات احتيال": "✅ RASID: no scam signs found",
  "العلامات: {f}": "Signs: {f}",
  "لا تشارك الرموز أو بيانات البطاقة أبداً. اضغط «إبلاغ» لإرسال الملخص إلى شرطة أبوظبي.": "Never share codes or card details. Press Report to send this to Abu Dhabi Police.",
};

window.I18N = {lang: LANG, EN};
window.t = function (s, vars) {
  let out = (LANG === 'en' && Object.prototype.hasOwnProperty.call(I18N.EN, s)) ? I18N.EN[s] : s;
  if (vars) out = String(out).replace(/\{(\w+)\}/g, (m, k) => (k in vars ? String(vars[k]) : m));
  return out;
};
window.apiLang = () => LANG;

const ATTRS = ['placeholder', 'title', 'aria-label', 'alt'];
function translateDom(root) {
  if (LANG !== 'en') return;
  const has = k => Object.prototype.hasOwnProperty.call(I18N.EN, k);
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
    acceptNode: n => (!n.parentElement || /^(SCRIPT|STYLE)$/.test(n.parentElement.nodeName) || n.parentElement.closest('[translate=no]'))
      ? NodeFilter.FILTER_REJECT : NodeFilter.FILTER_ACCEPT,   // brand marks use translate="no"
  });
  const nodes = [];
  while (walker.nextNode()) nodes.push(walker.currentNode);
  nodes.forEach(n => {
    const k = n.nodeValue.trim();
    if (k && has(k)) n.nodeValue = n.nodeValue.replace(k, I18N.EN[k]);
  });
  root.querySelectorAll('*').forEach(el => {
    ATTRS.forEach(a => { const v = el.getAttribute(a); if (v && has(v.trim())) el.setAttribute(a, I18N.EN[v.trim()]); });
  });
  // Sentences with markup inside (the Guardian steps) are keyed by name and carry their own trusted markup.
  root.querySelectorAll('[data-i18n]').forEach(el => { const k = el.getAttribute('data-i18n'); if (has(k)) el.innerHTML = I18N.EN[k]; });
}

function addToggle() {
  if (document.getElementById('lang-toggle')) return;
  const b = document.createElement('button');
  b.type = 'button';
  b.id = 'lang-toggle';
  b.className = 'btn ghost';
  b.textContent = LANG === 'en' ? 'العربية' : 'English';
  b.lang = LANG === 'en' ? 'ar' : 'en';
  b.setAttribute('aria-label', LANG === 'en' ? 'التبديل إلى العربية' : 'Switch to English');
  b.onclick = () => {
    try { localStorage.setItem('rasid-lang', LANG === 'en' ? 'ar' : 'en'); } catch (_) { /* cannot remember; reload keeps Arabic */ }
    location.reload();
  };
  const nav = document.querySelector('.c-head .views');
  if (nav) nav.after(b); else document.body.prepend(b);
}

function init() { translateDom(document.documentElement); addToggle(); }
if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init); else init();
})();
