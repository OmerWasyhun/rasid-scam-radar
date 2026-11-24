"""Brand-agnostic checks for a single pasted link (the "Check a link" path and POST /api/check).

Watchlists cover UAE brands in depth. A pasted link can impersonate anyone, so this adds what holds for any brand:
the page or its address claims a well-known brand on a domain that brand does not own, the page asks for a password
or card, or it sits on a free site builder where phishing kits are often hosted.
"""
import re
from urllib.parse import unquote, urlparse

from bs4 import BeautifulSoup

from .generator import registrable

# Well-known brands phished worldwide and in the UAE -> the registrable domains they own.
BRANDS = {
    "Instagram": {"instagram.com", "facebook.com", "meta.com"},
    "Facebook": {"facebook.com", "fb.com", "meta.com"},
    "WhatsApp": {"whatsapp.com", "whatsapp.net", "facebook.com"},
    "Netflix": {"netflix.com"},
    "Microsoft": {"microsoft.com", "microsoftonline.com", "live.com", "office.com", "office365.com", "outlook.com", "sharepoint.com", "onedrive.com", "msn.com", "bing.com"},
    "Outlook": {"outlook.com", "live.com", "office.com", "microsoft.com", "microsoftonline.com"},
    "Office 365": {"office.com", "office365.com", "microsoft.com", "microsoftonline.com"},
    "OneDrive": {"onedrive.com", "live.com", "microsoft.com", "sharepoint.com"},
    "Apple": {"apple.com", "icloud.com"},
    "iCloud": {"icloud.com", "apple.com"},
    "Google": {"google.com", "google.ae", "gmail.com", "youtube.com", "goo.gl"},
    "Gmail": {"gmail.com", "google.com"},
    "PayPal": {"paypal.com", "paypal.me"},
    "Amazon": {"amazon.com", "amazon.ae", "amazon.sa", "amazon.co.uk", "amazon.de"},
    "DHL": {"dhl.com", "dhl.ae", "dhl.de"},
    "FedEx": {"fedex.com"},
    "Aramex": {"aramex.com"},
    "Emirates Post": {"emiratespost.ae", "epg.gov.ae"},
    "Telekom": {"telekom.de", "telekom.hu", "telekom.com", "t-mobile.com"},
    "Etisalat": {"etisalat.ae", "eand.com"},
    "Binance": {"binance.com"},
    "Coinbase": {"coinbase.com"},
    "MetaMask": {"metamask.io"},
    "Roblox": {"roblox.com"},
    "LinkedIn": {"linkedin.com"},
    "Dropbox": {"dropbox.com"},
    "DocuSign": {"docusign.com", "docusign.net"},
    "Adobe": {"adobe.com"},
    "Wells Fargo": {"wellsfargo.com"},
    "HSBC": {"hsbc.com", "hsbc.ae", "hsbc.co.uk"},
    "Emirates NBD": {"emiratesnbd.com"},
    "ADCB": {"adcb.com"},
    "UAE PASS": {"uaepass.ae", "u.ae"},
    "TAMM": {"tamm.abudhabi", "abudhabi.ae"},
    "Salik": {"salik.ae"},
}
_BRAND_RX = {b: re.compile(r"(?<![a-z0-9])" + re.escape(b.lower()).replace(r"\ ", r"[\s_-]?") + r"(?![a-z])", re.I) for b in BRANDS}
# In a hostname or path the brand is often glued to other words: instagramloginpassword, netflix_gt
_GLUED_RX = {b: re.compile(re.escape(b.lower().replace(" ", ""))) for b in BRANDS if len(b.replace(" ", "")) >= 5}

# Free site builders and app hosts: anyone can publish a page on a subdomain in minutes.
FREE_HOSTS = {"github.io", "blogspot.com", "netlify.app", "vercel.app", "pages.dev", "workers.dev", "web.app",
              "firebaseapp.com", "weebly.com", "wixsite.com", "000webhostapp.com", "glitch.me", "herokuapp.com",
              "onrender.com", "repl.co", "replit.app", "webflow.io", "framer.app", "framer.website", "surge.sh",
              "r2.dev", "square.site", "godaddysites.com", "mystrikingly.com", "wordpress.com", "carrd.co",
              "ngrok-free.app", "ngrok.io", "trycloudflare.com", "azurewebsites.net", "appspot.com", "translate.goog",
              "ipfs.io", "dweb.link", "gitbook.io", "notion.site", "jimdosite.com", "site123.me", "tilda.ws"}
LOGIN_WORDS = re.compile(r"\b(log ?in|sign ?in|verify|verification|account|password|wallet|belépés|iniciar sesi[oó]n|"
                         r"entrar|connexion|anmelden|giri[sş])\b|تسجيل الدخول|تحقق|كلمة المرور", re.I)


def free_host(host: str) -> str | None:
    host = host.lower()
    return next((f for f in FREE_HOSTS if host == f or host.endswith("." + f)), None)


def no_age_credit(host: str) -> bool:
    """An old registrable domain says nothing about a page on one of its subdomains (shared or free hosting)."""
    host = host.lower()
    reg = registrable(host)
    return bool(free_host(host)) or host not in (reg, "www." + reg)


def claimed_brands(title: str, url: str) -> list[str]:
    """Brands named in the page title, or glued into the hostname/path of the link."""
    parsed = urlparse(url)
    where = unquote((parsed.hostname or "") + " " + parsed.path).lower()
    out = []
    for b, rx in _BRAND_RX.items():
        if rx.search(title or "") or rx.search(where) or (b in _GLUED_RX and _GLUED_RX[b].search(where)):
            out.append(b)
    return out


def check(url: str, final_url: str, title: str, html: str) -> list[dict]:
    """Signals for one link. url: what was pasted; final_url/title/html: the page it landed on (rendered if possible)."""
    host = (urlparse(final_url or url).hostname or "").lower()
    reg = registrable(host)
    soup = BeautifulSoup(html or "", "html.parser")
    password = bool(soup.find("input", {"type": re.compile("^password$", re.I)}))
    login_text = bool(LOGIN_WORDS.search(title or ""))
    sig = []
    fh = free_host(host)
    if fh:
        sig.append({"text": f"Hosted on a free site builder ({fh}), where anyone can publish a page in minutes", "points": 10})
    fake = [b for b in claimed_brands(title, final_url or url) + claimed_brands("", url) if reg not in BRANDS[b]]
    fake = list(dict.fromkeys(fake))
    if fake:
        b = fake[0]
        sig.append({"text": f"Claims to be {b} but is on {reg}, a domain {b} does not own", "points": 20, "brand": b})
        if password or login_text:
            what = "asks for a password" if password else "shows a sign-in or verification page"
            sig.append({"text": f"Fake {b} page: {what} on a domain {b} does not own", "points": 30, "kind": "content"})
        elif fh:
            sig.append({"text": f"Uses the {b} name on a free-hosted page", "points": 15, "kind": "content"})
    elif password and fh:
        sig.append({"text": "Password form on a free-hosted page", "points": 15, "kind": "content"})
    return sig
