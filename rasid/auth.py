"""Officer login for the console: one shared password from RASID_PASSWORD, signed session cookie.

Off when RASID_PASSWORD is empty (local development). Replace with the police SSO for a real deployment.
"""
import asyncio
import base64
import hashlib
import hmac
import secrets
import time
from urllib.parse import parse_qsl

from fastapi import Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from . import config

COOKIE = "rasid_session"
TTL = 12 * 3600
_SECRET = (config.SESSION_SECRET or secrets.token_hex(32)).encode()
OPEN_PATHS = ("/login", "/voice/", "/web/app.css", "/web/world.json", "/favicon.ico")


def _sign(payload: str) -> str:
    sig = hmac.new(_SECRET, payload.encode(), hashlib.sha256).hexdigest()[:32]
    return base64.urlsafe_b64encode(f"{payload}|{sig}".encode()).decode()


def _valid(token: str | None) -> bool:
    if not token:
        return False
    try:
        payload, sig = base64.urlsafe_b64decode(token.encode()).decode().rsplit("|", 1)
        if not hmac.compare_digest(sig, hmac.new(_SECRET, payload.encode(), hashlib.sha256).hexdigest()[:32]):
            return False
        return time.time() < float(payload.split(":")[1])
    except (ValueError, IndexError, UnicodeDecodeError):
        return False


async def middleware(request: Request, call_next):
    if not config.RASID_PASSWORD or request.url.path.startswith(OPEN_PATHS) or _valid(request.cookies.get(COOKIE)):
        return await call_next(request)
    if request.url.path.startswith("/api/"):
        return JSONResponse({"detail": "Sign in to the RASID console first"}, status_code=401)
    return RedirectResponse("/login", status_code=303)


LOGIN_PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>RASID sign in</title><link rel="stylesheet" href="/web/app.css"></head>
<body style="display:grid;place-items:center;min-height:100vh">
<form method="post" action="/login" class="loginbox">
  <div class="brand"><svg width="30" height="30" viewBox="0 0 30 30" aria-hidden="true"><circle cx="15" cy="15" r="13" fill="none" stroke="#4cc9f0" stroke-width="1.5"/><path d="M15 15 L26 8" stroke="#4cc9f0" stroke-width="1.6"/><circle cx="21" cy="11.5" r="2" fill="#ff5470"/></svg>
  <div>RASID <span class="ar">راصد</span><small>Abu Dhabi Police · Fraud Hunt</small></div></div>
  <label for="pw">Officer password</label>
  <input id="pw" name="password" type="password" autocomplete="current-password" autofocus required>
  {error}
  <button class="btn" type="submit">Sign in</button>
</form></body></html>"""


async def login_page():
    return HTMLResponse(LOGIN_PAGE.format(error=""))


async def login_submit(request: Request):
    form = dict(parse_qsl((await request.body()).decode("utf-8", "ignore")))
    if config.RASID_PASSWORD and hmac.compare_digest(form.get("password", "").encode(), config.RASID_PASSWORD.encode()):
        resp = RedirectResponse("/", status_code=303)
        resp.set_cookie(COOKIE, _sign(f"officer:{time.time() + TTL}"), max_age=TTL, httponly=True, samesite="lax")
        return resp
    await asyncio.sleep(1)  # slow down guessing
    return HTMLResponse(LOGIN_PAGE.format(error='<p class="err">Wrong password.</p>'), status_code=401)


async def logout():
    resp = RedirectResponse("/login", status_code=303)
    resp.delete_cookie(COOKIE)
    return resp
