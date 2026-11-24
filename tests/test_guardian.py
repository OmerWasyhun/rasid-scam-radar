"""Offline tests for the Call Guardian: rule scoring on the synthetic sample calls and the full Twilio
ConversationRelay WebSocket flow (Claude switched off, no network)."""
import asyncio
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from rasid import guardian, voice  # noqa: E402
from rasid.guardian import CallState, rule_scan  # noqa: E402

SAMPLES = {k: v for k, v in json.loads((ROOT / "data" / "sample_calls.json").read_text(encoding="utf-8")).items()
           if not k.startswith("_")}


@pytest.fixture(autouse=True)
def no_claude(monkeypatch):
    monkeypatch.setattr(guardian, "claude_ready", lambda: False)
    sent = []

    async def fake_sms(to, body):
        sent.append((to, body))
        return True
    monkeypatch.setattr(voice, "send_sms", fake_sms)
    return sent


@pytest.mark.parametrize("name", list(SAMPLES))
def test_sample_calls_rules_only(name):
    s = SAMPLES[name]
    out = asyncio.run(voice.simulate_call(s["lines"], s["lang"], use_claude=False))
    assert out["summary"]["verdict"] == s["expect"], (name, out["summary"])


def test_otp_request_from_bank_is_danger():
    score, hits = rule_scan("I'm calling from your bank, please read me the code we just sent")
    assert score >= guardian.DANGER and {"otp", "claim"} <= set(hits)


def test_genuine_reassurance_is_not_flagged():
    score, _ = rule_scan("This is your bank. We will never ask you for your PIN or a code on the phone.")
    assert score < guardian.CAUTION


def test_warning_spoken_once_per_level():
    st = CallState(lang="ar-AE")
    st.hear("معك من البنك، اقرأ لي رمز التحقق")
    first = st.due_warning(now=1000)
    assert first and first[0][0] == "ar-AE"          # heard language first
    assert st.due_warning(now=1100) == []             # not repeated


def test_summary_keeps_no_transcript():
    st = CallState()
    st.hear("send the money by gift card now, don't tell anyone")
    s = st.summary()
    assert "send the money" not in json.dumps(s)


def test_twilio_flow(monkeypatch, no_claude):
    from rasid.api import app
    monkeypatch.setattr(voice, "PUBLIC_BASE_URL", "https://guardian.example.test")
    cases = []
    monkeypatch.setattr(voice.db, "upsert_case", lambda *a, **k: cases.append((a, k)) or 42)
    c = TestClient(app)
    r = c.post("/voice/join", data={"From": "+971501112233", "CallSid": "CA1"})
    assert r.status_code == 200 and "<ConversationRelay" in r.text and 'interruptible="none"' in r.text
    token = re.search(r'name="session" value="([^"]+)"', r.text).group(1)

    with c.websocket_connect("/voice/listen") as ws:
        ws.send_text(json.dumps({"type": "setup", "from": "+971501112233", "customParameters": {"session": token}}))
        greet = [json.loads(ws.receive_text()) for _ in range(2)]
        assert all(m["type"] == "text" for m in greet) and greet[0]["lang"] == "ar-AE"
        ws.send_text(json.dumps({"type": "prompt", "voicePrompt": "السلام عليكم معك أحمد من البنك", "last": True}))
        ws.send_text(json.dumps({"type": "prompt", "voicePrompt": "اقرأ لي رمز التحقق اللي وصلك فوراً", "last": True}))
        warn = [json.loads(ws.receive_text()) for _ in range(2)]
        assert warn[0]["type"] == "text" and "راصد" in warn[0]["token"] and warn[0]["interruptible"] is False
        ws.send_text(json.dumps({"type": "prompt", "voicePrompt": "راصد اطلع", "last": True}))
        bye = [json.loads(ws.receive_text()) for _ in range(3)]
        assert bye[-1]["type"] == "end"

    assert any("971501112233" in to and "likely scam" in body for to, body in no_claude)
    assert "971501112233" in voice.PENDING

    r = c.post("/voice/sms", data={"From": "+971501112233", "Body": "REPORT 0509998877"})
    assert "case #42" in r.text and cases[0][1]["features"] == {"phone": ["0509998877"]}
    assert "971501112233" not in voice.PENDING


def test_join_refuses_unknown_session_token():
    from rasid.api import app
    c = TestClient(app)
    with c.websocket_connect("/voice/listen") as ws:
        ws.send_text(json.dumps({"type": "setup", "customParameters": {"session": "nope"}}))
        with pytest.raises(Exception):
            ws.receive_text()


def test_local_test_mode(monkeypatch):
    """The free local page: same WebSocket, plus live risk (x-state) and the summary (x-summary)."""
    from rasid.api import app
    cases = []
    monkeypatch.setattr(voice.db, "upsert_case", lambda *a, **k: cases.append((a, k)) or 7)
    c = TestClient(app)
    assert c.get("/guardian").status_code == 200
    assert "bank_otp_ar" in c.get("/api/v1/guardian/samples").json()
    tok = c.post("/api/v1/guardian/local-session", json={"lang": "en-US"}).json()["session"]
    with c.websocket_connect("/voice/listen") as ws:
        ws.send_text(json.dumps({"type": "setup", "from": "local", "customParameters": {"session": tok}}))
        greet = [json.loads(ws.receive_text()) for _ in range(2)]
        assert greet[0]["lang"] == "en-US"
        ws.send_text(json.dumps({"type": "prompt", "voicePrompt": "This is the police, pay the fine by gift card now", "last": True}))
        msgs = []
        while not any(m["type"] == "x-state" for m in msgs):
            msgs.append(json.loads(ws.receive_text()))
        state = [m for m in msgs if m["type"] == "x-state"][-1]
        assert state["risk"] >= guardian.CAUTION and state["flags"]
        ws.send_text(json.dumps({"type": "x-end"}))
        while True:
            m = json.loads(ws.receive_text())
            if m["type"] == "x-summary":
                break
        assert m["summary"]["verdict"] != "no scam signs" and "RASID" in m["sms"]
    r = c.post("/api/v1/guardian/local-report", json={"number": "050 111 2222"})
    assert r.json() == {"case": 7} and cases[0][1]["features"] == {"phone": ["0501112222"]}
