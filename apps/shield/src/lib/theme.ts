// RASID Shield: one deliberate dark look, matching the police console.
export const C = {
  ink: '#060b14',
  panel: '#0b1422',
  panel2: '#0f1b2d',
  line: '#1a2a41',
  line2: '#24395a',
  text: '#dbe5f2',
  muted: '#8395ae',
  faint: '#5a6c86',
  accent: '#4cc9f0',
  ok: '#5ee0a0',
  warn: '#ff9f43',
  crit: '#ff5470',
  white: '#f1f6fc',
};

export const verdictColor = (v?: string) =>
  v === 'scam' ? C.crit : v === 'suspicious' || v === 'reported' || v === 'unsure' || v === 'unverified' || v === 'mismatch' ? C.warn
    : v === 'official' || v === 'safe' || v === 'pass' || v === 'match' ? C.ok : C.muted;

export const mono = { fontFamily: 'monospace' as const };
