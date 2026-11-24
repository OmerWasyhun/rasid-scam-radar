"""Call Guardian voice agent: a phone number people add to a call they are unsure about.

How a person uses it: during a call, tap "Add call", dial the Guardian number, tap "Merge". The Guardian joins as a
third party, says that it is listening, and stays quiet while the call is normal. When the call shows scam signs it
speaks a warning into the call (heard by both sides) and texts the person a summary. Saying "RASID" (or "راصد") asks
it for its opinion at any time; "RASID leave" sends it away. After the call the person can reply REPORT by SMS to
file the case in the police console.

Twilio pieces (docs: twilio.com/docs/voice/conversationrelay):
  POST /voice/join    Voice webhook of the Guardian number -> TwiML <Connect><ConversationRelay> to /voice/listen
  WS   /voice/listen  ConversationRelay WebSocket: Twilio sends transcribed speech ("prompt"), we send "text" to speak
  POST /voice/done    <Connect action>: the relay session ended
  POST /voice/sms     Messaging webhook of the Guardian number: REPORT replies
No audio is recorded. The transcript lives in memory for the length of the call only.
"""
import asyncio
import base64
import hashlib
import hmac
import json
import logging
import secrets
import time
from urllib.parse import parse_qsl
from xml.sax.saxutils import escape, quoteattr

import httpx
from fastapi import APIRouter, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import Response
from pydantic import BaseModel, Field

from . import db, guardian
from .config import (GUARDIAN_ALLOWED, GUARDIAN_LANG, GUARDIAN_NUMBER, GUARDIAN_SMS_FROM, PUBLIC_BASE_URL,
                     TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
from .guardian import LEAVE, LINES, WAKE, CallState

log = logging.getLogger("rasid.voice")
router = APIRouter(tags=["call-guardian"])

# Voices and speech recognition per language (Twilio ConversationRelay providers).
VOICES = {
    "ar-AE": {"ttsProvider": "Amazon", "voice": "Hala-Neural", "transcriptionProvider": "Google", "speechModel": "telephony"},
    "en-US": {"ttsProvider": "Amazon", "voice": "Joanna-Neural", "transcriptionProvider": "Google", "speechModel": "telephony"},
}
HINTS = "RASID,راصد,OTP,CVV,AnyDesk,TeamViewer,Emirates ID,IBAN,UAE Pass"

SESSIONS: dict[str, dict] = {}      # one-time relay token -> call info (issued by the signed /voice/join webhook)
PENDING: dict[str, dict] = {}       # person's number -> last call summary, for REPORT replies (kept one hour)
PENDING_TTL = 3600
ACTIVE: set = set()             # live Guardian sessions


# ---------- helpers ----------
def digits(phone: str | None) -> str:
    return "".join(ch for ch in (phone or "") if ch.isdigit())


def twiml(inner: str) -> Response:
    return Response(f'<?xml version="1.0" encoding="UTF-8"?><Response>{inner}</Response>', media_type="application/xml")


def valid_signature(url: str, params: dict, signature: str) -> bool:
    """Twilio request signature (HMAC-SHA1 of URL + sorted params). Skipped in demo mode without an auth token."""
    if not TWILIO_AUTH_TOKEN:
        return True
    data = url + "".join(k + params[k] for k in sorted(params))
    digest = base64.b64encode(hmac.new(TWILIO_AUTH_TOKEN.encode(), data.encode(), hashlib.sha1).digest()).decode()
    return hmac.compare_digest(digest, signature or "")


async def twilio_form(request: Request) -> dict:
    form = dict(parse_qsl((await request.body()).decode("utf-8", "ignore"), keep_blank_values=True))
    url = (PUBLIC_BASE_URL + request.url.path + (("?" + request.url.query) if request.url.query else "")) if PUBLIC_BASE_URL else str(request.url)
    if not valid_signature(url, form, request.headers.get("X-Twilio-Signature", "")):
        raise HTTPException(403, "Bad Twilio signature")
    return form


def _prune() -> None:
    now = time.time()
    for k in [k for k, v in SESSIONS.items() if now - v["created"] > 300]:
        SESSIONS.pop(k, None)
    for k in [k for k, v in PENDING.items() if now - v["at"] > PENDING_TTL]:
        PENDING.pop(k, None)


async def send_sms(to: str, body: str) -> bool:
    """Text the person through Twilio's REST API. Returns False (and logs) when SMS is not configured or fails."""
    if not (TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN and GUARDIAN_SMS_FROM and digits(to)):
        log.info("SMS not sent (Twilio not configured): %s", body.replace("\n", " | "))
        return False
    url = f"https://api.twilio.com/2010-04-01/Accounts/{TWILIO_ACCOUNT_SID}/Messages.json"
    sender = GUARDIAN_SMS_FROM if not digits(GUARDIAN_SMS_FROM) or GUARDIAN_SMS_FROM.startswith("+") else "+" + GUARDIAN_SMS_FROM
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.post(url, auth=(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN),
                             data={"To": "+" + digits(to), "From": sender, "Body": body[:1500]})
        if r.status_code >= 300:
            log.warning("Twilio SMS failed %s: %s", r.status_code, r.text[:300])
        return r.status_code < 300
    except httpx.HTTPError as e:
        log.warning("Twilio SMS error: %s", e)
        return False


# ---------- Twilio voice webhooks ----------
@router.post("/voice/join")
async def join(request: Request):
    """Someone dialled (or merged) the Guardian number into their call."""
    f = await twilio_form(request)
    caller = digits(f.get("From"))
    if GUARDIAN_ALLOWED and caller not in GUARDIAN_ALLOWED:
        return twiml("<Say>Sorry, this number is not enrolled in the RASID Call Guardian pilot.</Say><Hangup/>")
    if not PUBLIC_BASE_URL:
        return twiml("<Say>The RASID Call Guardian is not configured yet.</Say><Hangup/>")
    _prune()
    token = secrets.token_urlsafe(18)
    SESSIONS[token] = {"user": caller, "call_sid": f.get("CallSid", ""), "created": time.time()}
    ws = PUBLIC_BASE_URL.replace("https://", "wss://").replace("http://", "ws://") + "/voice/listen"
    first = GUARDIAN_LANG if GUARDIAN_LANG in VOICES else "ar-AE"
    v = VOICES[first]
    langs = "".join(
        f"<Language code={quoteattr(code)}" + "".join(f" {k}={quoteattr(val)}" for k, val in cfg.items()) + "/>"
        for code, cfg in VOICES.items())
    return twiml(
        f'<Connect action={quoteattr(PUBLIC_BASE_URL + "/voice/done")}>'
        f'<ConversationRelay url={quoteattr(ws)} language={quoteattr(first)} ttsProvider={quoteattr(v["ttsProvider"])} '
        f'voice={quoteattr(v["voice"])} transcriptionProvider={quoteattr(v["transcriptionProvider"])} '
        f'speechModel={quoteattr(v["speechModel"])} interruptible="none" dtmfDetection="true" '
        f'echoPromptFiltering="true" hints={quoteattr(HINTS)}>'
        f'{langs}<Parameter name="session" value={quoteattr(token)}/>'
        f'</ConversationRelay></Connect>')


@router.post("/voice/done")
async def done(request: Request):
    await twilio_form(request)
    return twiml("<Hangup/>")


# ---------- the live session ----------
class Session:
    """One Guardian on one call: hears prompts, scores, speaks, texts."""

    def __init__(self, ws: WebSocket, user: str, local: bool = False, lang: str | None = None):
        self.ws = ws
        self.local = local   # local test page instead of Twilio: also sends x-state / x-summary messages
        lang = lang or GUARDIAN_LANG
        self.state = CallState(user=user, lang=lang if lang in VOICES else "ar-AE")
        self.lock = asyncio.Lock()
        self.dirty = asyncio.Event()
        self.alert_sms_sent = False
        self.ended = False
        self.worker: asyncio.Task | None = None

    async def send(self, msg: dict) -> None:
        async with self.lock:
            if not self.ended:
                await self.ws.send_text(json.dumps(msg, ensure_ascii=False))

    async def say(self, lines: list[tuple[str, str]]) -> None:
        for lang, text in lines:
            await self.send({"type": "text", "token": text, "last": True, "lang": lang, "interruptible": False})

    async def greet(self) -> None:
        g = LINES["greeting"]
        order = [("ar-AE", g["ar"]), ("en-US", g["en"])]
        await self.say(order if self.state.lang.startswith("ar") else order[::-1])

    async def set_lang(self, code: str) -> None:
        self.state.lang = code
        await self.send({"type": "language", "ttsLanguage": code, "transcriptionLanguage": code})
        key = "lang_ar" if code.startswith("ar") else "lang_en"
        await self.say([(code, next(iter(LINES[key].values())))])

    async def push_state(self) -> None:
        """Live risk for the local test page (Twilio would reject unknown message types, so local only)."""
        if self.local:
            st = self.state
            await self.send({"type": "x-state", "risk": st.risk, "level": st.level(),
                             "verdict": ["no scam signs", "suspicious", "likely scam"][st.level()],
                             "flags": (st.ai.red_flags if st.ai else []) or guardian.flags_for(st.rule_hits, "en"),
                             "flags_ar": guardian.flags_for(st.rule_hits, "ar"),
                             "analysed_by": "claude" if st.ai else "rules"})

    async def send_summary(self) -> None:
        if self.local:
            s = self.state.summary()
            await self.send({"type": "x-summary", "summary": s, "sms": guardian.sms_text(s)})

    async def leave(self) -> None:
        g = LINES["leaving"]
        await self.say([("ar-AE", g["ar"]), ("en-US", g["en"])] if self.state.lang.startswith("ar") else [("en-US", g["en"]), ("ar-AE", g["ar"])])
        await self.send_summary()
        await self.send({"type": "end", "handoffData": json.dumps({"reason": "asked to leave"})})
        self.ended = True

    async def on_speech(self, text: str) -> None:
        if LEAVE.search(text):
            await self.leave()
            return
        self.state.hear(text)
        if WAKE.search(text):
            await self.say(self.state.status_lines())
        else:
            await self.maybe_warn()
        await self.push_state()
        self.dirty.set()

    async def on_digit(self, d: str) -> None:
        if d == "1":
            await self.say(self.state.status_lines())
        elif d == "2":
            await self.set_lang("en-US")
        elif d == "3":
            await self.set_lang("ar-AE")
        elif d == "9":
            await self.leave()

    async def maybe_warn(self) -> None:
        lines = self.state.due_warning()
        if lines:
            await self.say(lines)
        if self.state.level() == 2 and not self.alert_sms_sent:
            self.alert_sms_sent = True
            asyncio.create_task(send_sms(self.state.user, guardian.sms_text(self.state.summary())))

    async def analyse_loop(self) -> None:
        """Re-assess with Claude whenever new speech arrived; one request at a time, newest transcript wins."""
        while not self.ended:
            await self.dirty.wait()
            self.dirty.clear()
            try:
                ai = await guardian.assess(self.state.transcript)
            except Exception:  # never let one bad analysis stop the Guardian listening; the rules still run
                log.exception("Guardian analysis failed")
                ai = None
            if ai is not None:
                self.state.ai = ai
                await self.maybe_warn()
                await self.push_state()

    async def finish(self) -> None:
        self.ended = True
        if self.worker:
            self.worker.cancel()
        if not self.state.lines:
            return
        s = self.state.summary()
        PENDING[self.state.user] = {**s, "at": time.time()}
        await send_sms(self.state.user, guardian.sms_text(s))


@router.websocket("/voice/listen")
async def listen(ws: WebSocket):
    await ws.accept()
    sess: Session | None = None
    try:
        while True:
            msg = json.loads(await ws.receive_text())
            t = msg.get("type")
            if t == "setup":
                ctx = SESSIONS.pop((msg.get("customParameters") or {}).get("session", ""), None)
                if not ctx:
                    await ws.close(code=1008)
                    return
                sess = Session(ws, ctx["user"] or digits(msg.get("from")), local=ctx.get("local", False), lang=ctx.get("lang"))
                sess.worker = asyncio.create_task(sess.analyse_loop())
                ACTIVE.add(sess)
                await sess.greet()
            elif sess is None:
                continue
            elif t == "prompt" and msg.get("last", True):
                await sess.on_speech(msg.get("voicePrompt", ""))
            elif t == "dtmf":
                await sess.on_digit(str(msg.get("digit", "")))
            elif t == "x-end" and sess.local:
                await sess.send_summary()
                break
            elif t == "error":
                log.warning("ConversationRelay error: %s", msg.get("description"))
            if sess and sess.ended:
                break
    except WebSocketDisconnect:
        pass
    finally:
        if sess:
            ACTIVE.discard(sess)
            await sess.finish()


# ---------- SMS replies: REPORT ----------
REPORT_WORDS = ("report", "بلاغ", "ابلاغ", "إبلاغ")


def file_report(user: str, summary: dict, scammer: str | None) -> int:
    """Put a reported call into the police console as a case. Only the summary is stored, never a transcript."""
    flags = summary.get("red_flags") or []
    title = f"Phone scam reported via Call Guardian{' — ' + scammer if scammer else ''}"
    return db.upsert_case(
        "calls", f"guardian:{user}:{int(summary['at'])}", title, max(summary["risk"], 50),
        target=summary.get("claimed_identity") or "Phone scam", langs=summary.get("langs") or ["AR"],
        where_txt="Call Guardian (live call)",
        signals=[{"text": f, "points": 20} for f in flags[:6]],
        evidence={"summary_en": summary.get("summary_en"), "summary_ar": summary.get("summary_ar"),
                  "scam_type": summary.get("scam_type"), "asks_for": summary.get("asks_for"),
                  "reporter": ("+" + user) if user.isdigit() else "local test", "minutes": summary.get("minutes"), "analysed_by": summary.get("analysed_by")},
        features={"phone": [scammer]} if scammer else None)


@router.post("/voice/sms")
async def sms(request: Request):
    f = await twilio_form(request)
    user, body = digits(f.get("From")), (f.get("Body") or "").strip()
    _prune()
    if not body.lower().startswith(REPORT_WORDS):
        return twiml("<Message>RASID Call Guardian: during a call, add this number and merge to have the call checked. "
                     "Reply REPORT after a call to send it to Abu Dhabi Police.</Message>")
    s = PENDING.pop(user, None)
    if not s:
        return twiml("<Message>RASID: no recent Guardian call found for this number. You can still call Aman on 8002626.</Message>")
    scammer = digits(body) or None
    cid = file_report(user, s, scammer)
    return twiml(f"<Message>RASID: thank you. Your report is case #{cid} with Abu Dhabi Police. "
                 f"شكراً، تم تسجيل بلاغك برقم {cid}.</Message>")


# ---------- simulator: run a typed call through the same brain (no Twilio needed) ----------
class SimIn(BaseModel):
    lines: list[str] = Field(min_length=1, max_length=60)
    lang: str = "ar-AE"
    use_claude: bool = True


async def simulate_call(lines: list[str], lang: str = "ar-AE", use_claude: bool = True) -> dict:
    st = CallState(user="sim", lang=lang if lang in VOICES else "ar-AE")
    timeline = []
    for line in lines:
        st.hear(line)
        if use_claude:
            ai = await guardian.assess(st.transcript)
            if ai is not None:
                st.ai = ai
        said = st.status_lines() if WAKE.search(line) else st.due_warning(now=time.time() + 60 * len(timeline))
        timeline.append({"heard": line, "risk": st.risk, "rules": st.rule_hits, "guardian_says": [t for _, t in said]})
    s = st.summary()
    return {"timeline": timeline, "summary": s, "sms": guardian.sms_text(s)}


@router.post("/api/v1/guardian/simulate")
async def simulate(body: SimIn):
    return await simulate_call(body.lines, body.lang, body.use_claude)


# ---------- local test mode: the laptop is the Guardian's ear (free, no Twilio) ----------
LOOPBACK = {"127.0.0.1", "::1", "localhost", "testclient"}


class LocalIn(BaseModel):
    lang: str = "ar-AE"


def _local_only(request: Request) -> None:
    if (request.client.host if request.client else "") not in LOOPBACK:
        raise HTTPException(403, "The local Guardian test only runs on this computer (open it via http://localhost)")


@router.post("/api/v1/guardian/local-session")
def local_session(body: LocalIn, request: Request):
    """A one-time token for the test page, which then speaks the same WebSocket protocol as Twilio."""
    _local_only(request)
    _prune()
    token = secrets.token_urlsafe(18)
    SESSIONS[token] = {"user": "local", "local": True, "lang": body.lang, "created": time.time()}
    return {"session": token, "ws": "/voice/listen", "claude": guardian.claude_ready()}


class LocalReport(BaseModel):
    number: str = ""


@router.post("/api/v1/guardian/local-report")
def local_report(body: LocalReport, request: Request):
    _local_only(request)
    s = PENDING.pop("local", None)
    if not s:
        raise HTTPException(404, "No finished test call to report")
    return {"case": file_report("local", s, digits(body.number) or None)}


@router.get("/api/v1/guardian/samples")
def samples():
    """The synthetic sample calls, for the test page's "play a sample" buttons."""
    from .config import ROOT
    data = json.loads((ROOT / "data" / "sample_calls.json").read_text(encoding="utf-8"))
    return {k: v for k, v in data.items() if not k.startswith("_")}


@router.get("/api/v1/guardian/status")
def status():
    return {"number": GUARDIAN_NUMBER or None, "public_url": PUBLIC_BASE_URL or None,
            "twilio": bool(TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN), "claude": guardian.claude_ready(),
            "language": GUARDIAN_LANG, "pilot_allowlist": len(GUARDIAN_ALLOWED), "live_calls": len(ACTIVE)}
