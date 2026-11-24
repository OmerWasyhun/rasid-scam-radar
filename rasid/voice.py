"""Call Guardian listener: the laptop listens to a speakerphone call and warns out loud when it hears a scam.

How a person uses it: put the phone call on speaker next to the laptop, open the Call Guardian tab and press Listen.
The browser turns speech into text (Web Speech API) and sends each line to WS /voice/listen. The Guardian stays
quiet while the call is normal; when it hears scam signs it sends a warning that the browser speaks aloud (the phone
carries it to the caller too). Saying "RASID" / "راصد" asks for its opinion; "RASID leave" ends the session. After the
call, a likely scam can be reported to the police console in one click.

  POST /api/v1/guardian/local-session   one-time token for the listener page
  WS   /voice/listen                    speech lines in, spoken warnings and live risk out
  POST /api/v1/guardian/local-report    file the finished call as a case in the console
  POST /api/v1/guardian/simulate        run a typed call through the same rules (and Claude)
No audio is recorded. The transcript lives in memory for the length of the call only.
"""
import asyncio
import json
import logging
import secrets
import time

from fastapi import APIRouter, HTTPException, Request, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

from . import config, db, guardian
from .config import GUARDIAN_LANG, ROOT
from .guardian import LEAVE, LINES, WAKE, CallState

log = logging.getLogger("rasid.voice")
router = APIRouter(tags=["call-guardian"])

LANGS = ("ar-AE", "en-US")
SESSIONS: dict[str, dict] = {}      # one-time listener token -> session info
PENDING: dict[str, dict] = {}       # last finished call summary, until it is reported (kept one hour)
PENDING_TTL = 3600
LOOPBACK = {"127.0.0.1", "::1", "localhost", "testclient"}


def digits(phone: str | None) -> str:
    return "".join(ch for ch in (phone or "") if ch.isdigit())


def _prune() -> None:
    now = time.time()
    for k in [k for k, v in SESSIONS.items() if now - v["created"] > 300]:
        SESSIONS.pop(k, None)
    for k in [k for k, v in PENDING.items() if now - v["at"] > PENDING_TTL]:
        PENDING.pop(k, None)


def _allowed(host: str) -> bool:
    """Local by default; a hosted demo opens it to signed-in officers (the session token comes from the login-gated API)."""
    return config.GUARDIAN_REMOTE or host in LOOPBACK


def _local_only(request: Request) -> None:
    if not _allowed(request.client.host if request.client else ""):
        raise HTTPException(403, "The Call Guardian listener only runs on this computer (open it via http://localhost)")


# ---------- the live session ----------
class Session:
    """One listening session: hears lines, scores them, speaks warnings, reports live risk."""

    def __init__(self, ws: WebSocket, lang: str | None = None):
        self.ws = ws
        lang = lang or GUARDIAN_LANG
        self.state = CallState(user="local", lang=lang if lang in LANGS else "ar-AE")
        self.lock = asyncio.Lock()
        self.dirty = asyncio.Event()
        self.ended = False
        self.worker: asyncio.Task | None = None

    async def send(self, msg: dict) -> None:
        async with self.lock:
            if not self.ended:
                await self.ws.send_text(json.dumps(msg, ensure_ascii=False))

    async def say(self, lines: list[tuple[str, str]]) -> None:
        for lang, text in lines:
            await self.send({"type": "text", "token": text, "lang": lang})

    def _ordered(self, key: str) -> list[tuple[str, str]]:
        g = LINES[key]
        pair = [("ar-AE", g["ar"]), ("en-US", g["en"])]
        return pair if self.state.lang.startswith("ar") else pair[::-1]

    async def push_state(self) -> None:
        st = self.state
        await self.send({"type": "x-state", "risk": st.risk, "level": st.level(),
                         "verdict": ["no scam signs", "suspicious", "likely scam"][st.level()],
                         "flags": (st.ai.red_flags if st.ai else []) or guardian.flags_for(st.rule_hits, "en"),
                         "flags_ar": guardian.flags_for(st.rule_hits, "ar"),
                         "analysed_by": "claude" if st.ai else "rules"})

    async def send_summary(self) -> None:
        s = self.state.summary()
        await self.send({"type": "x-summary", "summary": s, "text": guardian.summary_text(s)})

    async def leave(self) -> None:
        await self.say(self._ordered("leaving"))
        await self.send_summary()
        await self.send({"type": "end"})
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

    async def maybe_warn(self) -> None:
        lines = self.state.due_warning()
        if lines:
            await self.say(lines)

    async def analyse_loop(self) -> None:
        """Re-assess with Claude whenever new speech arrived; one request at a time, newest transcript wins."""
        while not self.ended:
            await self.dirty.wait()
            self.dirty.clear()
            try:
                ai = await guardian.assess(self.state.transcript)
            except Exception:  # never let one bad analysis stop the listener; the rules still run
                log.exception("Guardian analysis failed")
                ai = None
            if ai is not None:
                self.state.ai = ai
                await self.maybe_warn()
                await self.push_state()

    def finish(self) -> None:
        self.ended = True
        if self.worker:
            self.worker.cancel()
        if self.state.lines:
            PENDING["local"] = {**self.state.summary(), "at": time.time()}


@router.websocket("/voice/listen")
async def listen(ws: WebSocket):
    if not _allowed(ws.client.host if ws.client else ""):
        await ws.close(code=1008)
        return
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
                sess = Session(ws, lang=ctx.get("lang"))
                sess.worker = asyncio.create_task(sess.analyse_loop())
                await sess.say(sess._ordered("greeting"))
            elif sess is None:
                continue
            elif t == "prompt":
                await sess.on_speech(msg.get("voicePrompt", ""))
            elif t == "ask":
                await sess.say(sess.state.status_lines())
            elif t == "x-end":
                await sess.send_summary()
                break
            if sess and sess.ended:
                break
    except WebSocketDisconnect:
        pass
    finally:
        if sess:
            sess.finish()


# ---------- listener endpoints ----------
class LocalIn(BaseModel):
    lang: str = "ar-AE"


@router.post("/api/v1/guardian/local-session")
def local_session(body: LocalIn, request: Request):
    _local_only(request)
    _prune()
    token = secrets.token_urlsafe(18)
    SESSIONS[token] = {"lang": body.lang, "created": time.time()}
    return {"session": token, "ws": "/voice/listen", "claude": guardian.claude_ready()}


def file_report(summary: dict, caller: str | None) -> int:
    """Put a reported call into the police console as a case. Only the summary is stored, never a transcript."""
    flags = summary.get("red_flags") or []
    title = f"Phone scam reported via Call Guardian{' — ' + caller if caller else ''}"
    return db.upsert_case(
        "calls", f"guardian:local:{int(summary['at'])}", title, max(summary["risk"], 50),
        target=summary.get("claimed_identity") or "Phone scam", langs=summary.get("langs") or ["AR"],
        where_txt="Call Guardian (speakerphone listener)",
        signals=[{"text": f, "points": 20} for f in flags[:6]],
        evidence={"summary_en": summary.get("summary_en"), "summary_ar": summary.get("summary_ar"),
                  "scam_type": summary.get("scam_type"), "asks_for": summary.get("asks_for"),
                  "minutes": summary.get("minutes"), "analysed_by": summary.get("analysed_by")},
        features={"phone": [caller]} if caller else None)


class LocalReport(BaseModel):
    number: str = ""


@router.post("/api/v1/guardian/local-report")
def local_report(body: LocalReport, request: Request):
    _local_only(request)
    _prune()
    s = PENDING.pop("local", None)
    if not s:
        raise HTTPException(404, "No finished call to report")
    return {"case": file_report(s, digits(body.number) or None)}


@router.get("/api/v1/guardian/samples")
def samples():
    """The synthetic sample calls, for the page's "play a sample" buttons."""
    data = json.loads((ROOT / "data" / "sample_calls.json").read_text(encoding="utf-8"))
    return {k: v for k, v in data.items() if not k.startswith("_")}


# ---------- simulator: run a typed call through the same brain ----------
class SimIn(BaseModel):
    lines: list[str] = Field(min_length=1, max_length=60)
    lang: str = "ar-AE"
    use_claude: bool = True


async def simulate_call(lines: list[str], lang: str = "ar-AE", use_claude: bool = True) -> dict:
    st = CallState(user="sim", lang=lang if lang in LANGS else "ar-AE")
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
    return {"timeline": timeline, "summary": s, "text": guardian.summary_text(s)}


@router.post("/api/v1/guardian/simulate")
async def simulate(body: SimIn):
    return await simulate_call(body.lines, body.lang, body.use_claude)
