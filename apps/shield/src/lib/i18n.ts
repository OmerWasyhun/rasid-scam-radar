// UI strings: full English and Arabic. Warnings that protect people are in all 12 languages.
export const LANGS: { code: string; name: string; rtl?: boolean; speech: string }[] = [
  { code: 'en', name: 'English', speech: 'en-US' },
  { code: 'ar', name: 'العربية', rtl: true, speech: 'ar-SA' },
  { code: 'hi', name: 'हिन्दी', speech: 'hi-IN' },
  { code: 'ur', name: 'اردو', rtl: true, speech: 'ur-PK' },
  { code: 'ml', name: 'മലയാളം', speech: 'ml-IN' },
  { code: 'ta', name: 'தமிழ்', speech: 'ta-IN' },
  { code: 'si', name: 'සිංහල', speech: 'si-LK' },
  { code: 'tl', name: 'Tagalog', speech: 'fil-PH' },
  { code: 'bn', name: 'বাংলা', speech: 'bn-BD' },
  { code: 'ne', name: 'नेपाली', speech: 'ne-NP' },
  { code: 'ru', name: 'Русский', speech: 'ru-RU' },
  { code: 'zh', name: '中文', speech: 'zh-CN' },
];

export const isRTL = (lang: string) => !!LANGS.find(l => l.code === lang)?.rtl;

const en = {
  appName: 'RASID Shield',
  tagline: 'Abu Dhabi Police anti-fraud shield',
  home: 'Home', check: 'Check', calls: 'Calls', history: 'History', settings: 'Settings',
  protected: 'Protection status',
  checkSomething: 'Check a link, message or number',
  checkHint: 'Paste anything suspicious: a link, an SMS or WhatsApp message, or a phone number.',
  paste: 'Paste', checkNow: 'Check now', checking: 'Checking with RASID…',
  whoIsCalling: 'Who is calling?',
  whoIsCallingHint: 'On a call with someone claiming to be a bank, the police or a company? Check their number now.',
  callerNumber: 'Caller number', theySay: 'They say they are from', askedSensitive: 'They asked for a code, card details or money',
  verify: 'Verify caller', endCall: 'End call', report: 'Report', reported: 'Reported. Thank you for protecting others.',
  screener: 'Call screener', screenerHint: 'RASID answers unknown calls for you, asks who is calling, and only connects people it can verify.',
  testAgent: 'Test the screening agent', recent: 'Recent checks', nothingYet: 'Nothing checked yet.',
  server: 'RASID server address', myPhone: 'My phone number', trusted: 'Trusted contact (emergency alerts)',
  language: 'Language', save: 'Save', saved: 'Saved', testConnection: 'Test connection', connected: 'Connected to RASID',
  continue: 'Continue', getStarted: 'Get started',
  nativeOff: 'Automatic notification and call protection needs the RASID Shield Android build. In this preview, check items by pasting them.',
  nativeOn: 'Automatic protection available',
  notifAccess: 'Read incoming notifications', callRole: 'Screen incoming calls', grant: 'Turn on',
  forwardSetup: 'Forward unanswered calls to RASID', dialCode: 'Dial this code once', cancelCode: 'To stop',
  verdict_scam: 'Scam', verdict_suspicious: 'Suspicious', verdict_unclear: 'Unclear', verdict_safe: 'Looks safe',
  verdict_official: 'Official', verdict_reported: 'Reported', verdict_unknown: 'Unknown number', verdict_checking: 'Being investigated',
  verdict_unreachable: 'Site is down', verdict_pass: 'Connected', verdict_unsure: 'Message taken',
  why: 'Why', screenedCalls: 'Screened calls', transcript: 'Transcript', simulate: 'Run agent',
  callerLines: 'What the caller says (one line per turn)',
  emergency: 'EMERGENCY ALERT', hangUpNow: 'Hang up now',
  dismiss: 'I understand', clear: 'Clear history',
};
type Keys = keyof typeof en;

const ar: Record<Keys, string> = {
  appName: 'راصد درع', tagline: 'درع شرطة أبوظبي ضد الاحتيال',
  home: 'الرئيسية', check: 'فحص', calls: 'المكالمات', history: 'السجل', settings: 'الإعدادات',
  protected: 'حالة الحماية',
  checkSomething: 'افحص رابطاً أو رسالة أو رقماً',
  checkHint: 'الصق أي شيء مشبوه: رابط، رسالة نصية أو واتساب، أو رقم هاتف.',
  paste: 'لصق', checkNow: 'افحص الآن', checking: 'جارٍ الفحص مع راصد…',
  whoIsCalling: 'من المتصل؟',
  whoIsCallingHint: 'هل تتحدث مع شخص يدّعي أنه من بنك أو الشرطة أو شركة؟ افحص رقمه الآن.',
  callerNumber: 'رقم المتصل', theySay: 'يقول إنه من', askedSensitive: 'طلب رمزاً أو بيانات بطاقة أو مالاً',
  verify: 'تحقق من المتصل', endCall: 'إنهاء المكالمة', report: 'إبلاغ', reported: 'تم الإبلاغ. شكراً لحمايتك للآخرين.',
  screener: 'فاحص المكالمات', screenerHint: 'يرد راصد على المكالمات المجهولة نيابةً عنك، ويسأل عن هوية المتصل، ولا يوصل إلا من يتحقق منه.',
  testAgent: 'جرّب وكيل الفحص', recent: 'آخر الفحوصات', nothingYet: 'لم يتم فحص أي شيء بعد.',
  server: 'عنوان خادم راصد', myPhone: 'رقم هاتفي', trusted: 'جهة اتصال موثوقة (تنبيهات الطوارئ)',
  language: 'اللغة', save: 'حفظ', saved: 'تم الحفظ', testConnection: 'اختبار الاتصال', connected: 'متصل بخادم راصد',
  continue: 'متابعة', getStarted: 'ابدأ',
  nativeOff: 'الحماية التلقائية للإشعارات والمكالمات تحتاج نسخة أندرويد من راصد درع. في هذه المعاينة، افحص العناصر بلصقها.',
  nativeOn: 'الحماية التلقائية متاحة',
  notifAccess: 'قراءة الإشعارات الواردة', callRole: 'فحص المكالمات الواردة', grant: 'تفعيل',
  forwardSetup: 'حوّل المكالمات غير المجاب عليها إلى راصد', dialCode: 'اطلب هذا الرمز مرة واحدة', cancelCode: 'للإيقاف',
  verdict_scam: 'احتيال', verdict_suspicious: 'مشبوه', verdict_unclear: 'غير واضح', verdict_safe: 'يبدو آمناً',
  verdict_official: 'رسمي', verdict_reported: 'مُبلَّغ عنه', verdict_unknown: 'رقم غير معروف', verdict_checking: 'قيد التحقيق',
  verdict_unreachable: 'الموقع متوقف', verdict_pass: 'تم التوصيل', verdict_unsure: 'تم أخذ رسالة',
  why: 'السبب', screenedCalls: 'المكالمات المفحوصة', transcript: 'نص المكالمة', simulate: 'شغّل الوكيل',
  callerLines: 'ما يقوله المتصل (سطر لكل دور)',
  emergency: 'تنبيه طوارئ', hangUpNow: 'أنهِ المكالمة الآن',
  dismiss: 'فهمت', clear: 'مسح السجل',
};

const DICTS: Record<string, Record<Keys, string>> = { en, ar };

export function t(lang: string, key: Keys): string {
  return (DICTS[lang] ?? en)[key] ?? en[key];
}

// Protective warnings in every language the shield supports.
const SCAM: Record<string, string> = {
  en: 'Warning: this may be a scam. Do not pay and do not share any code.',
  ar: 'تحذير: قد يكون هذا احتيالاً. لا تدفع ولا تشارك أي رمز.',
  hi: 'चेतावनी: यह धोखाधड़ी हो सकती है। पैसे न भेजें और कोड साझा न करें।',
  ur: 'انتباہ: یہ فراڈ ہو سکتا ہے۔ رقم نہ بھیجیں اور کوڈ شیئر نہ کریں۔',
  ml: 'മുന്നറിയിപ്പ്: ഇത് തട്ടിപ്പാകാം. പണം അയക്കരുത്, കോഡ് പങ്കിടരുത്.',
  ta: 'எச்சரிக்கை: இது மோசடியாக இருக்கலாம். பணம் அனுப்பாதீர்கள், குறியீட்டைப் பகிராதீர்கள்.',
  si: 'අවවාදයයි: මෙය වංචාවක් විය හැක. මුදල් යවන්න එපා, කේත බෙදාගන්න එපා.',
  tl: 'Babala: Posibleng scam ito. Huwag magbayad o magbigay ng code.',
  bn: 'সতর্কতা: এটি প্রতারণা হতে পারে। টাকা পাঠাবেন না এবং কোড শেয়ার করবেন না।',
  ne: 'चेतावनी: यो ठगी हुन सक्छ। पैसा नपठाउनुहोस् र कोड साझा नगर्नुहोस्।',
  ru: 'Внимание: это может быть мошенничество. Не платите и не сообщайте коды.',
  zh: '警告：这可能是诈骗。不要付款，也不要分享验证码。',
};
const NOT_ORG: Record<string, string> = {
  en: 'This number does not belong to {org}. Hang up.',
  ar: 'هذا الرقم لا يتبع {org}. أنهِ المكالمة.',
  hi: 'यह नंबर {org} का नहीं है। कॉल काट दें।',
  ur: 'یہ نمبر {org} کا نہیں ہے۔ کال بند کر دیں۔',
  ml: 'ഈ നമ്പർ {org}-ന്റേതല്ല. കോൾ കട്ട് ചെയ്യുക.',
  ta: 'இந்த எண் {org}-க்கு சொந்தமானது அல்ல. அழைப்பைத் துண்டிக்கவும்.',
  si: 'මෙම අංකය {org} ට අයත් නැත. ඇමතුම විසන්ධි කරන්න.',
  tl: 'Hindi pag-aari ng {org} ang numerong ito. Ibaba ang tawag.',
  bn: 'এই নম্বরটি {org}-এর নয়। কল কেটে দিন।',
  ne: 'यो नम्बर {org} को होइन। कल काट्नुहोस्।',
  ru: 'Этот номер не принадлежит {org}. Положите трубку.',
  zh: '此号码不属于{org}。请挂断电话。',
};
const VERIFIED: Record<string, string> = {
  en: 'Verified: this is an official {org} number.',
  ar: 'موثّق: هذا رقم رسمي لـ {org}.',
};

export const warnScam = (lang: string) => SCAM[lang] ?? SCAM.en;
export const warnNotOrg = (lang: string, org: string) => (NOT_ORG[lang] ?? NOT_ORG.en).replace('{org}', org);
export const verifiedOrg = (lang: string, org: string) => (VERIFIED[lang] ?? VERIFIED.en).replace('{org}', org);
export const speechCode = (lang: string) => LANGS.find(l => l.code === lang)?.speech ?? 'en-US';
