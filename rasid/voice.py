"""Cloud call screener: Twilio Voice + ConversationRelay.

Flow: a call forwarded to the screener number hits /voice/incoming. Contacts and official numbers are connected at
once, known scam numbers are refused, everyone else talks to the agent over /voice/relay. The agent finds out who
is calling and why, checks the claim against the official registry and the number history, then ends the relay
session with a decision. /voice/after turns that decision into TwiML: connect, take a message, or hang up.

Protocol references (Twilio docs): <Connect action> + <ConversationRelay url="wss://..."> ; WebSocket messages
setup / prompt (voicePrompt, last) from Twilio; text (token, last) and end (handoffData) to Twilio.
"""
import base64
import hashlib
import hmac
import json
import re
import secrets
import time
from urllib.parse import parse_qsl
from xml.sax.saxutils import escape, quoteattr

import anthropic
from fastapi import APIRouter, Depends, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import Response
from pydantic import BaseModel

from . import db, phones
from .citizen import device as device_auth
from .config import (ANTHROPIC_API_KEY, PUBLIC_BASE_URL, SCREENER_DEFAULT_DEVICE, TWILIO_AUTH_TOKEN,
                     TWILIO_SCREENER_NUMBER, VOICE_MODEL)

router = APIRouter(tags=["voice"])
SESSIONS: dict[str, dict] = {}       # relay token -> call context
MAX_TURNS = 4
GREETING = ("Hello. This call is being screened by RASID, Abu Dhabi's anti-fraud service, and may be recorded. "
            "Please tell me your name, the organisation you are calling from, and why you are calling.")
SAY = {
    "ask_org": "Thank you. Are you calling from a company or an organisation? If so, which one?",
    "ask_purpose": "Thank you. What is the reason for your call?",
    "ask_ref": "Can you give me a reference number or the branch you are calling from?",
    "pass": "Thank you. Please hold while I connect you.",
    "unsure": "Thank you. They can't take your call right now. I will pass on your message.",
    "scam": "This call cannot be connected. Goodbye.",
}


# ---------- helpers ----------
def twiml(inner: str) -> Response:
    return Response(f'<?xml version="1.0" encoding="UTF-8"?><Response>{inner}</Response>', media_type="application/xml")


def dial(phone: str) -> str:
    cid = phones.e164(TWILIO_SCREENER_NUMBER)
    attr = f" callerId={quoteattr('+' + cid)}" if cid else ""
    return f'<Say>Connecting a screened call.</Say><Dial answerOnBridge="true"{attr}>+{escape(phones.e164(phone))}</Dial>'


def valid_signature(url: str, params: dict, signature: str) -> bool:
    if not TWILIO_AUTH_TOKEN:
        return True  # demo mode without Twilio credentials
    data = url + "".join(k + params[k] for k in sorted(params))
    digest = base64.b64encode(hmac.new(TWILIO_AUTH_TOKEN.encode(), data.encode(), hashlib.sha1).digest()).decode()
    return hmac.compare_digest(digest, signature or "")


async def twilio_form(request: Request) -> dict:
    form = dict(parse_qsl((await request.body()).decode("utf-8", "ignore"), keep_blank_values=True))
    url = (PUBLIC_BASE_URL + request.url.path + (("?" + request.url.query) if request.url.query else "")) if PUBLIC_BASE_URL else str(request.url)
    if not valid_signature(url, form, request.headers.get("X-Twilio-Signature", "")):
        raise HTTPException(403, "Bad Twilio signature")
    return form


def find_device(forwarded_from: str | None) -> dict | None:
    with db.conn() as c:
        if forwarded_from:
            r = c.execute("SELECT * FROM devices WHERE phone=?", (phones.e164(forwarded_from),)).fetchone()
            if r:
                return db.row(r)
        if SCREENER_DEFAULT_DEVICE:
            r = c.execute("SELECT * FROM devices WHERE id=?", (SCREENER_DEFAULT_DEVICE,)).fetchone()
            if r:
                return db.row(r)
        r = c.execute("SELECT * FROM devices ORDER BY created DESC LIMIT 1").fetchone()
        return db.row(r)


def save_call(sid, device, caller, state, decision, reason, level=0):
    from .citizen import push
    transcript = state.get("transcript", []) if state else []
    with db.conn() as c:
        c.execute(
            "INSERT INTO calls(sid,device_id,caller,claimed_org,caller_name,purpose,decision,reason,transcript,created) "
            "VALUES (?,?,?,?,?,?,?,?,?,?) ON CONFLICT(sid) DO UPDATE SET decision=excluded.decision, reason=excluded.reason, "
            "transcript=excluded.transcript, claimed_org=excluded.claimed_org, caller_name=excluded.caller_name, purpose=excluded.purpose",
            (sid, (device or {}).get("id"), phones.e164(caller), (state or {}).get("org"), (state or {}).get("name"),
             (state or {}).get("purpose"), decision, reason, db.dumps(transcript), time.time()))
    if decision == "scam":
        phones.report(caller, "screener", (state or {}).get("org"), source="screener", force_scam=level >= 2)
        db.upsert_case("calls", f"call:{sid}", f"Call from {phones.pretty(caller)}", 90 if level >= 2 else 80,
                       target=(state or {}).get("org") or "Phone scam", langs=(state or {}).get("langs") or ["EN"],
                       where_txt="Cloud call screener", signals=[{"text": reason, "points": 80}],
                       evidence={"transcript": transcript, "text": " / ".join(t["text"] for t in transcript if t["who"] == "caller")},
                       features={"phone": [phones.e164(caller)[3:] if phones.e164(caller).startswith("971") else phones.e164(caller)]})
    who = (state or {}).get("name") or phones.pretty(caller)
    org = (state or {}).get("org")
    if decision == "scam":
        push(device, "🚨 Scam call blocked", f"{who}{' claiming to be ' + org if org else ''}: {reason}", {"type": "call", "sid": sid, "level": level}, emergency=level >= 2)
    elif decision == "pass":
        push(device, "Screened call: connecting", f"{who}{', ' + org if org else ''}: {reason}", {"type": "call", "sid": sid})
    else:
        push(device, "Screened call: message taken", f"{who}{', ' + org if org else ''}. Tap to read the transcript.", {"type": "call", "sid": sid})


# ---------- the agent ----------
EXTRACT_PROMPT = """You are listening to a phone call screened on behalf of a UAE resident. Read the caller's words so far and \
return JSON only with keys:
caller_name (string or null), claimed_org (one of {orgs}, another organisation name, or null), purpose (short English or null),
asked_sensitive (true if the caller asks for an OTP, PIN, card details, passwords, Emirates ID, bank details, a transfer or a payment),
language (BCP-47 code of the caller's language), summary_en (one sentence in English).
Caller said:
{text}"""

_client = None


def _claude_extract(text: str) -> dict | None:
    global _client
    if not ANTHROPIC_API_KEY:
        return None
    try:
        if _client is None:
            _client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        resp = _client.messages.create(
            model=VOICE_MODEL, max_tokens=800, output_config={"effort": "low"},
            messages=[{"role": "user", "content": EXTRACT_PROMPT.format(orgs=", ".join(phones.ORG_ALIASES), text=text[:3000])}])
        if resp.stop_reason == "refusal":
            return None
        raw = "".join(b.text for b in resp.content if b.type == "text")
        m = re.search(r"\{.*\}", raw, re.S)
        return json.loads(m.group(0)) if m else None
    except (anthropic.APIError, ValueError):
        return None


NAME_RE = re.compile(r"(?:my name is|this is|i am|i'm)\s+([A-Za-z]+)|(?:اسمي|معك|أنا)\s+([؀-ۿ]+)", re.I)
PURPOSE_RE = re.compile(r"(?:about|regarding|calling (?:to|for|about)|بخصوص|بشأن)\s+(.{3,80})", re.I)


def _rules_extract(text: str) -> dict:
    m = NAME_RE.search(text)
    p = PURPOSE_RE.search(text)
    from .lexicon import detect_langs
    return {"caller_name": (m.group(1) or m.group(2)).strip() if m else None, "claimed_org": phones.detect_org(text),
            "purpose": p.group(1).strip() if p else None, "asked_sensitive": bool(phones.SENSITIVE.search(text)),
            "language": None, "langs": detect_langs(text)}


def agent_turn(state: dict, caller_text: str) -> tuple[str, dict | None]:
    """Add the caller's words, update what we know, return (what the agent says, decision or None)."""
    state.setdefault("transcript", []).append({"who": "caller", "text": caller_text, "t": time.time()})
    state["turns"] = state.get("turns", 0) + 1
    heard = " ".join(t["text"] for t in state["transcript"] if t["who"] == "caller")
    info = _claude_extract(heard) or _rules_extract(heard)
    for k_src, k_dst in (("caller_name", "name"), ("claimed_org", "org"), ("purpose", "purpose")):
        if info.get(k_src):
            state[k_dst] = info[k_src]
    state["sensitive"] = state.get("sensitive") or bool(info.get("asked_sensitive"))
    if info.get("langs"):
        state["langs"] = info["langs"]
    if info.get("summary_en"):
        state["summary"] = info["summary_en"]

    caller = state.get("caller", "")
    hist = phones.verdict(caller)
    decision = None
    if hist["verdict"] == "scam":
        decision = {"decision": "scam", "level": 2, "reason": f"Number reported as scam by {hist['reports']} {'person' if hist['reports'] == 1 else 'people'}"}
    elif state.get("org"):
        v = phones.verify_claim(caller, state["org"], state.get("sensitive", False))
        if v["decision"] == "pass":
            decision = {"decision": "pass", "level": 0, "reason": v["reasons"][0]}
        elif v["decision"] == "scam":
            decision = {"decision": "scam", "level": v["level"], "reason": "; ".join(v["reasons"][:3])}
        elif state["turns"] >= 3:
            decision = {"decision": "unsure", "level": v["level"], "reason": "; ".join(v["reasons"][:3])}
        else:
            reply = SAY["ask_ref"] if state.get("purpose") else SAY["ask_purpose"]
    elif state.get("sensitive"):
        decision = {"decision": "scam", "level": 1, "reason": "Unknown caller asked for codes, card details or money"}
    elif state["turns"] >= 2 and state.get("purpose"):
        decision = {"decision": "pass", "level": 0, "reason": "Personal call, no organisation claimed (number not verified)"}
    elif state["turns"] >= MAX_TURNS:
        decision = {"decision": "unsure", "level": 0, "reason": "Caller did not say who they are"}
    else:
        reply = SAY["ask_org"] if state["turns"] == 1 else SAY["ask_purpose"]
    if decision:
        reply = SAY[decision["decision"]]
    state["transcript"].append({"who": "agent", "text": reply, "t": time.time()})
    return reply, decision


# ---------- Twilio webhooks ----------
@router.post("/voice/incoming")
async def incoming(request: Request):
    f = await twilio_form(request)
    caller = f.get("From", "")
    dev = find_device(f.get("ForwardedFrom") or f.get("To"))
    sid = f.get("CallSid", secrets.token_hex(8))
    v = phones.verdict(caller)
    contacts = set((dev or {}).get("contacts") or [])
    user_phone = (dev or {}).get("phone")
    if (phones.phash(caller) in contacts or v["verdict"] == "official") and user_phone:
        label = v.get("org") or "a contact"
        save_call(sid, dev, caller, {"org": v.get("org")}, "pass", f"Verified: {label}")
        return twiml(dial(user_phone))
    if v["verdict"] == "scam":
        save_call(sid, dev, caller, {}, "scam", f"Number reported as scam by {v['reports']} {'person' if v['reports'] == 1 else 'people'}", level=2)
        return twiml(f"<Say>{escape(SAY['scam'])}</Say><Hangup/>")
    if not PUBLIC_BASE_URL:
        return twiml("<Say>The screening service is not configured.</Say><Hangup/>")
    token = secrets.token_urlsafe(16)
    SESSIONS[token] = {"sid": sid, "caller": phones.e164(caller), "device_id": (dev or {}).get("id"), "created": time.time()}
    ws = PUBLIC_BASE_URL.replace("https://", "wss://").replace("http://", "ws://") + "/voice/relay"
    return twiml(
        f'<Connect action={quoteattr(PUBLIC_BASE_URL + "/voice/after")}>'
        f'<ConversationRelay url={quoteattr(ws)} welcomeGreeting={quoteattr(GREETING)} language="en-US">'
        f'<Parameter name="session" value={quoteattr(token)}/></ConversationRelay></Connect>')


@router.websocket("/voice/relay")
async def relay(ws: WebSocket):
    await ws.accept()
    state = None
    try:
        while True:
            msg = json.loads(await ws.receive_text())
            t = msg.get("type")
            if t == "setup":
                token = (msg.get("customParameters") or {}).get("session")
                ctx = SESSIONS.get(token)
                if not ctx:
                    await ws.close(code=1008)
                    return
                state = {**ctx, "transcript": [{"who": "agent", "text": GREETING, "t": time.time()}]}
            elif t == "prompt" and state is not None and msg.get("last", True):
                reply, decision = agent_turn(state, msg.get("voicePrompt", ""))
                await ws.send_text(json.dumps({"type": "text", "token": reply, "last": True}))
                if decision:
                    state["decision"] = decision
                    dev = db.row(_device_row(state["device_id"]))
                    save_call(state["sid"], dev, state["caller"], state, decision["decision"], decision["reason"], decision["level"])
                    await ws.send_text(json.dumps({"type": "end", "handoffData": json.dumps(decision)}))
            elif t == "error":
                break
    except WebSocketDisconnect:
        pass
    finally:
        if state and not state.get("decision"):  # caller hung up mid-screening
            dev = db.row(_device_row(state["device_id"]))
            reason = "Caller hung up during screening" + (" right after the greeting" if state.get("turns", 0) == 0 else "")
            save_call(state["sid"], dev, state["caller"], state, "unsure", reason)


def _device_row(did):
    with db.conn() as c:
        return c.execute("SELECT * FROM devices WHERE id=?", (did,)).fetchone()


@router.post("/voice/after")
async def after(request: Request):
    f = await twilio_form(request)
    if f.get("SessionStatus") != "ended":
        return twiml("<Hangup/>")
    try:
        d = json.loads(f.get("HandoffData") or "{}")
    except ValueError:
        d = {}
    if d.get("decision") == "pass":
        dev = find_device(f.get("ForwardedFrom") or f.get("To"))
        if dev and dev.get("phone"):
            return twiml(dial(dev["phone"]))
    return twiml("<Hangup/>")


# ---------- simulator (no Twilio needed): demo + tests ----------
class SimIn(BaseModel):
    caller: str
    lines: list[str]


@router.post("/api/v1/screener/simulate")
def simulate(s: SimIn, dev=Depends(device_auth)):
    """Run the agent on typed caller lines, exactly as the phone call would, and store the result."""
    state = {"sid": "sim-" + secrets.token_hex(6), "caller": phones.e164(s.caller), "device_id": dev["id"],
             "transcript": [{"who": "agent", "text": GREETING, "t": time.time()}]}
    decision = None
    for line in s.lines[:MAX_TURNS]:
        _, decision = agent_turn(state, line)
        if decision:
            break
    if not decision:
        decision = {"decision": "unsure", "level": 0, "reason": "Caller stopped talking before the agent could decide"}
    save_call(state["sid"], dev, state["caller"], state, decision["decision"], decision["reason"], decision["level"])
    return {"decision": decision, "claimed_org": state.get("org"), "caller_name": state.get("name"),
            "purpose": state.get("purpose"), "transcript": state["transcript"], "sid": state["sid"]}
