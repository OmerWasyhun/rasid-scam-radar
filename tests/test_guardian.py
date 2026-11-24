"""Offline tests for the Call Guardian listener: rule scoring on the synthetic sample calls and the full
WebSocket session the console tab uses (Claude switched off, no network)."""
import asyncio
import json
import pathlib
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

    async def no_assess(_):
        return None
    monkeypatch.setattr(guardian, "assess", no_assess)


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
    assert "send the money" not in json.dumps(st.summary())


def test_listener_refuses_unknown_session_token():
    from rasid.api import app
    with TestClient(app).websocket_connect("/voice/listen") as ws:
        ws.send_text(json.dumps({"type": "setup", "customParameters": {"session": "nope"}}))
        with pytest.raises(Exception):
            ws.receive_text()


def test_listener_session_and_report(monkeypatch):
    """Press Listen -> speech lines -> spoken warning and live risk -> stop -> summary -> Report files a case."""
    from rasid.api import app
    cases = []
    monkeypatch.setattr(voice.db, "upsert_case", lambda *a, **k: cases.append((a, k)) or 7)
    c = TestClient(app)
    assert "bank_otp_ar" in c.get("/api/v1/guardian/samples").json()
    tok = c.post("/api/v1/guardian/local-session", json={"lang": "en-US"}).json()["session"]
    with c.websocket_connect("/voice/listen") as ws:
        ws.send_text(json.dumps({"type": "setup", "customParameters": {"session": tok}}))
        greet = [json.loads(ws.receive_text()) for _ in range(2)]
        assert greet[0]["type"] == "text" and greet[0]["lang"] == "en-US"
        ws.send_text(json.dumps({"type": "prompt", "voicePrompt": "This is the police, pay the fine by gift card now"}))
        msgs = []
        while not any(m["type"] == "x-state" for m in msgs):
            msgs.append(json.loads(ws.receive_text()))
        assert any(m["type"] == "text" and "RASID" in m["token"] for m in msgs)    # warning spoken aloud
        state = [m for m in msgs if m["type"] == "x-state"][-1]
        assert state["risk"] >= guardian.CAUTION and state["flags"]
        ws.send_text(json.dumps({"type": "x-end"}))
        while (m := json.loads(ws.receive_text()))["type"] != "x-summary":
            pass
        assert m["summary"]["verdict"] != "no scam signs" and "RASID" in m["text"]
    r = c.post("/api/v1/guardian/local-report", json={"number": "050 111 2222"})
    assert r.json() == {"case": 7} and cases[0][1]["features"] == {"phone": ["0501112222"]}
    assert c.post("/api/v1/guardian/local-report", json={}).status_code == 404     # reported once only


def test_guardian_link_opens_console_tab():
    from rasid.api import app
    r = TestClient(app).get("/guardian", follow_redirects=False)
    assert r.status_code in (302, 307) and r.headers["location"] == "/#guardian"
