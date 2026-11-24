"""RASID's own headless browser (Playwright + Chromium): renders suspect pages, takes screenshots, records network calls.

Safety: a fresh incognito context per page, JavaScript on (phishing pages are often built by JS) but downloads,
permissions, popups and service workers off; requests to private/internal addresses are blocked; forms are never
filled or submitted; every page gets a hard time limit.
"""
import asyncio
import concurrent.futures as cf
import hashlib
import ipaddress
import socket
import threading
import time
from urllib.parse import urlparse

from .config import DATA_DIR, DESKTOP_UA, LOW_MEMORY

SHOTS = DATA_DIR / "shots"
VIEWPORT = {"width": 1366, "height": 900}
PAGE_TIMEOUT_MS = 20000
SETTLE_MS = 2500
CONCURRENCY = 4


def _public(host: str) -> bool:
    try:
        for info in socket.getaddrinfo(host, None):
            ip = ipaddress.ip_address(info[4][0])
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
                return False
        return True
    except (socket.gaierror, ValueError, UnicodeError):
        return False


class _Pool:
    """One Chromium instance on its own event-loop thread; callers submit URLs from any thread."""

    def __init__(self):
        self.loop = None
        self.browser = None
        self.sem = None
        self.ready = threading.Event()
        self.error = None
        self._pw = None

    def start(self):
        if self.ready.is_set() and self.browser:
            return
        threading.Thread(target=self._run, daemon=True, name="rasid-browser").start()
        self.ready.wait(60)
        if self.error:
            raise RuntimeError(self.error)

    def _run(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        try:
            self.loop.run_until_complete(self._launch())
        except Exception as e:
            self.error = f"Headless browser unavailable: {e}"
            self.ready.set()
            return
        self.ready.set()
        self.loop.run_forever()

    async def _launch(self):
        from playwright.async_api import async_playwright
        self._pw = await async_playwright().start()
        args = ["--disable-dev-shm-usage", "--no-first-run"]
        if LOW_MEMORY:  # small hosting plans (512 MB): one renderer, capped JS heap
            args += ["--disable-gpu", "--no-zygote", "--renderer-process-limit=1", "--js-flags=--max-old-space-size=160"]
        self.browser = await self._pw.chromium.launch(headless=True, args=args)
        self.sem = asyncio.Semaphore(CONCURRENCY)

    async def _render(self, url: str, shot_name: str) -> dict:
        async with self.sem:
            ctx = await self.browser.new_context(
                viewport=VIEWPORT, user_agent=DESKTOP_UA, locale="en-AE", timezone_id="Asia/Dubai",
                accept_downloads=False, ignore_https_errors=True, java_script_enabled=True,
                service_workers="block", permissions=[])
            requests, blocked = [], []

            async def guard(route):
                req = route.request
                host = (urlparse(req.url).hostname or "").lower()
                if req.url.startswith(("http://", "https://")) and host and not _public(host):
                    blocked.append(host)
                    return await route.abort()
                await route.continue_()

            await ctx.route("**/*", guard)
            page = await ctx.new_page()
            page.on("popup", lambda p: asyncio.ensure_future(p.close()))
            page.on("request", lambda r: requests.append({"url": r.url[:300], "method": r.method, "type": r.resource_type}))
            out = {"url": url, "ok": False}
            try:
                resp = await page.goto(url, wait_until="domcontentloaded", timeout=PAGE_TIMEOUT_MS)
                try:
                    await page.wait_for_load_state("networkidle", timeout=6000)
                except Exception:
                    pass
                await page.wait_for_timeout(SETTLE_MS)
                SHOTS.mkdir(parents=True, exist_ok=True)
                path = SHOTS / f"{shot_name}.png"
                await page.screenshot(path=str(path), full_page=False)
                full = SHOTS / f"{shot_name}-full.jpg"
                try:
                    await page.screenshot(path=str(full), full_page=True, type="jpeg", quality=60, timeout=8000)
                except Exception:
                    full = None
                out.update({
                    "ok": True, "status": resp.status if resp else None, "final_url": page.url,
                    "title": (await page.title())[:200], "html": (await page.content())[:2_000_000],
                    "screenshot": path.name, "screenshot_full": full.name if full else None,
                })
            except Exception as e:
                out["error"] = str(e).split("\n")[0][:200]
            finally:
                out["requests"] = requests[:400]
                out["blocked_private"] = sorted(set(blocked))
                await ctx.close()
            return out

    def render(self, url: str, shot_name: str, timeout: float = 45) -> dict:
        self.start()
        fut = asyncio.run_coroutine_threadsafe(self._render(url, shot_name), self.loop)
        try:
            return fut.result(timeout)
        except cf.TimeoutError:
            fut.cancel()
            return {"url": url, "ok": False, "error": "Page took too long to render"}


_pool = _Pool()


def available() -> tuple[bool, str]:
    try:
        _pool.start()
        return True, ""
    except Exception as e:
        return False, str(e)


def shot_name(url: str, tag: str = "") -> str:
    return hashlib.sha1(f"{url}|{tag}|{int(time.time() // 3600)}".encode()).hexdigest()[:16]


def render(url: str, tag: str = "") -> dict:
    """Render a page and save its screenshot. Returns html, final_url, title, screenshot file name and network requests."""
    host = (urlparse(url).hostname or "").lower()
    if not host or not _public(host):
        return {"url": url, "ok": False, "error": "Refused: not a public address"}
    try:
        return _pool.render(url, shot_name(url, tag))
    except RuntimeError as e:
        return {"url": url, "ok": False, "error": str(e)}
