"""Root Guardian: a rooted Android phone streams the live call audio here; RASID transcribes it locally (Whisper),
scores it with the Call Guardian rules (plus Claude when a key is set) and tells the phone to hang up when the call
is a likely scam. The phone then shows "RASID ended a scam call" and the case is filed in the console.

WebSocket /phone/stream?key=<RASID_PHONE_KEY>
  phone -> server  {"type":"start","caller":"+9715...","rate":16000}   then binary PCM16 mono frames,
                   {"type":"end"} when the call ends
  server -> phone  {"type":"state","risk":..,"level":..,"verdict":..,"heard":".."}
                   {"type":"hangup","risk":..,"reason":"..","flags":[..]}   (phone ends the call)
Audio is never stored: it is transcribed in memory and dropped. Only the verdict and red flags are kept.
"""
import asyncio
import json
import logging
import os
import secrets
import time

import numpy as np
from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect

from . import guardian
from .config import DATA_DIR

log = logging.getLogger("rasid.rootguard")
router = APIRouter(tags=["root-guardian"])

PHONE_KEY = os.getenv("RASID_PHONE_KEY", "").strip()
WHISPER_SIZE = os.getenv("RASID_WHISPER_MODEL", "small").strip() or "small"
CHUNK_SECONDS = 4.0          # transcribe every ~4 s of call audio
MIN_RMS = 120                # skip near-silent chunks (PCM16 units)
HANGUP_LEVEL = 2             # 2 = "likely scam" in the Guardian rules

_model = None
_model_lock = asyncio.Lock()


async def _whisper():
    global _model
    async with _model_lock:
        if _model is None:
            from faster_whisper import WhisperModel
            _model = await asyncio.to_thread(WhisperModel, WHISPER_SIZE, device="cpu", compute_type="int8",
                                             download_root=str(DATA_DIR / "models"))
    return _model


def _to_16k_float(pcm: bytes, rate: int) -> np.ndarray:
    a = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0
    if rate != 16000 and len(a):
        n = int(len(a) * 16000 / rate)
        a = np.interp(np.linspace(0, len(a) - 1, n), np.arange(len(a)), a).astype(np.float32)
    return a


async def transcribe(pcm: bytes, rate: int, lang: str | None) -> tuple[str, str | None]:
    """Text of one chunk and the detected language (ar / en / ...)."""
    model = await _whisper()
    audio = _to_16k_float(pcm, rate)

    def run():
        segs, info = model.transcribe(audio, language=lang, beam_size=1, vad_filter=True,
                                      condition_on_previous_text=False)
        return " ".join(s.text.strip() for s in segs).strip(), info.language

    return await asyncio.to_thread(run)


def _check_key(key: str):
    if not PHONE_KEY or not secrets.compare_digest(key or "", PHONE_KEY):
        raise HTTPException(401, "Wrong or missing phone key")


@router.get("/phone/ping")
async def ping(key: str = ""):
    """The app's connection test."""
    _check_key(key)
    return {"ok": True, "whisper_model": WHISPER_SIZE, "whisper_loaded": _model is not None, "claude": guardian.claude_ready()}


@router.post("/phone/warmup")
async def warmup(key: str = ""):
    """Load the speech model before the first call (takes a few seconds the first time)."""
    _check_key(key)
    await _whisper()
    return {"ok": True}


@router.websocket("/phone/stream")
async def stream(ws: WebSocket):
    if not PHONE_KEY or not secrets.compare_digest(ws.query_params.get("key", ""), PHONE_KEY):
        await ws.close(code=1008)
        return
    await ws.accept()
    st = guardian.CallState(user="root-phone")
    caller, rate, lang = None, 16000, None
    buf = bytearray()
    hung_up = False
    started = time.time()
    try:
        while True:
            msg = await ws.receive()
            if msg.get("type") == "websocket.disconnect":
                break
            if msg.get("text"):
                m = json.loads(msg["text"])
                if m.get("type") == "start":
                    caller = m.get("caller") or None
                    rate = int(m.get("rate") or 16000)
                    lang = {"ar": "ar", "en": "en"}.get(m.get("lang"), None)
                    asyncio.create_task(_whisper())  # make sure the model is loading
                elif m.get("type") == "end":
                    break
                continue
            if msg.get("bytes"):
                buf.extend(msg["bytes"])
                if len(buf) >= int(CHUNK_SECONDS * rate * 2):
                    chunk, buf = bytes(buf), bytearray()
                    samples = np.frombuffer(chunk, dtype=np.int16)
                    if not len(samples) or float(np.sqrt(np.mean(samples.astype(np.float32) ** 2))) < MIN_RMS:
                        continue
                    text, detected = await transcribe(chunk, rate, lang)
                    if detected in ("ar", "en"):
                        st.lang = "ar-AE" if detected == "ar" else "en-US"
                    if text:
                        st.hear(text)
                        if guardian.claude_ready():
                            ai = await guardian.assess(st.transcript)
                            if ai is not None:
                                st.ai = ai
                    lvl = st.level()
                    await ws.send_text(json.dumps({"type": "state", "risk": st.risk, "level": lvl,
                                                   "verdict": ["no scam signs", "suspicious", "likely scam"][lvl],
                                                   "heard": text}, ensure_ascii=False))
                    if lvl >= HANGUP_LEVEL and not hung_up:
                        hung_up = True
                        s = st.summary()
                        flags = s.get("red_flags") or []
                        await ws.send_text(json.dumps({"type": "hangup", "risk": st.risk, "flags": flags[:4],
                                                       "flags_ar": (s.get("red_flags_ar") or [])[:4],
                                                       "reason": "; ".join(flags[:2]) or "likely scam"}, ensure_ascii=False))
                        _file(st, caller)
    except WebSocketDisconnect:
        pass
    finally:
        log.info("Root Guardian call ended after %.0fs, risk %s, hung up: %s", time.time() - started, st.risk, hung_up)


def _file(st: "guardian.CallState", caller: str | None) -> int | None:
    """File the ended scam call in the police console (Call Guardian sensor). Never stores audio or transcript."""
    try:
        from .voice import file_report
        s = {**st.summary(), "at": time.time()}
        return file_report("root-phone", s, caller)
    except Exception:
        log.exception("Could not file the root Guardian case")
        return None
