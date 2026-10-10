import ipaddress
import logging
import os
import re
from html import escape
from html.parser import HTMLParser
from urllib.parse import urlparse

import httpx

logger = logging.getLogger(__name__)

EMAIL_BASE_URL = "https://integrations.emergentagent.com"
EMAIL_KEY = os.environ.get("EMERGENT_EMAIL_KEY") or None
CONSOLE_MODE = EMAIL_KEY is None
EMAIL_FROM_NAME = os.environ["EMAIL_FROM_NAME"]
EMAIL_REPLY_TO = os.environ.get("EMAIL_REPLY_TO")


class EmailDeliveryError(Exception):
    pass


_SHORTENERS = ("bit.ly", "tinyurl.com", "t.co", "is.gd", "cutt.ly", "goo.gl", "rebrand.ly")
_CRED_ASK = ("reply with your password", "reply with the code", "send your password", "cvv",
             "send us your password", "enter your password below", "confirm your card number",
             "your full card number", "seed phrase", "recovery phrase", "verify your card",
             "social security number", "confirm your bank details")
_HOSTISH = re.compile(r"\b(?:https?://)?((?:[a-z0-9-]+\.)+[a-z]{2,})", re.I)


def _host_ok(host: str) -> bool:
    if not host or "xn--" in host:
        return False
    try:
        ipaddress.ip_address(host)
        return False
    except ValueError:
        pass
    return not any(host == s or host.endswith("." + s) for s in _SHORTENERS)


def _same_site(shown: str, real: str) -> bool:
    return shown == real or real.endswith("." + shown) or shown.endswith("." + real)


class _EmailScan(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tags, self.urls, self.anchors = set(), [], []
        self._href, self._text = None, []

    def handle_starttag(self, tag, attrs):
        self.tags.add(tag.lower())
        self.urls += [v for k, v in attrs if k.lower() in ("href", "src") and v]
        if tag.lower() == "a":
            self._href = dict((k.lower(), v) for k, v in attrs).get("href")
            self._text = []

    def handle_data(self, data):
        if self._href is not None:
            self._text.append(data)

    def handle_endtag(self, tag):
        if tag.lower() == "a" and self._href is not None:
            self.anchors.append((self._href, "".join(self._text)))
            self._href, self._text = None, []


def _assert_safe_email(subject: str, html: str) -> None:
    scan = _EmailScan()
    scan.feed(html)
    if scan.tags & {"form", "input", "textarea", "select"}:
        raise ValueError("No forms or input fields in email (G2)")
    body = f"{subject}\n{html}".lower()
    for p in _CRED_ASK:
        if p in body:
            raise ValueError(f"Email asks the recipient for credentials: {p!r} (G2)")
    for url in scan.urls:
        low = url.strip().lower()
        if low.startswith(("mailto:", "tel:", "cid:", "#")):
            continue
        if not low.startswith("https://"):
            raise ValueError(f"Email links/assets must be absolute https: {url!r} (G3)")
        host = urlparse(low).hostname or ""
        if not _host_ok(host) or urlparse(low).username is not None:
            raise ValueError(f"Shortened, numeric-host or credential-bearing URL: {url!r} (G3)")
    for href, text in scan.anchors:
        real = urlparse(href.strip().lower()).hostname or ""
        if not real:
            continue
        for m in _HOSTISH.finditer(text):
            if not _same_site(m.group(1).lower(), real):
                raise ValueError(f"Anchor text {m.group(1)!r} != real link host {real!r} (G3)")


async def send_email(*, to: str, subject: str, html: str) -> str:
    _assert_safe_email(subject, html)
    if CONSOLE_MODE:
        logger.warning(f"LOCAL CONSOLE EMAIL (no EMERGENT_EMAIL_KEY) to={to} subject={subject!r}\n{html}")
        return "local-console"
    payload = {"to": [to], "subject": subject, "html": html, "from_name": EMAIL_FROM_NAME}
    if EMAIL_REPLY_TO:
        payload["contact_email"] = EMAIL_REPLY_TO
    try:
        async with httpx.AsyncClient(timeout=30) as c:
            resp = await c.post(f"{EMAIL_BASE_URL}/api/v1/email/send",
                                headers={"X-Email-Key": EMAIL_KEY}, json=payload)
        resp.raise_for_status()
        return resp.json().get("id")
    except httpx.HTTPStatusError as e:
        logger.error(f"Email send failed: {e.response.status_code} {e.response.text}")
        raise EmailDeliveryError(f"Email provider returned {e.response.status_code}")
    except Exception as e:
        logger.error(f"Email send error: {e}")
        raise EmailDeliveryError("Email provider unreachable")


PURPOSE_LABEL = {"registration": "registration", "login": "sign-in", "recovery": "password recovery"}


def otp_email(code: str, purpose: str, ttl_min: int) -> tuple[str, str]:
    label = PURPOSE_LABEL.get(purpose, "verification")
    brand = escape(EMAIL_FROM_NAME)
    subject = f"{EMAIL_FROM_NAME}: your {label} code"
    html = (
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f4f1ea">'
        '<tr><td align="left" style="padding:32px 24px;font-family:Arial,sans-serif;color:#1a1a1a">'
        f'<p style="font-size:12px;letter-spacing:2px;text-transform:uppercase;color:#8a1c1c;margin:0 0 16px">{brand}</p>'
        f'<p style="font-size:16px;margin:0 0 12px">Use this one-time code to continue your {escape(label)}:</p>'
        f'<p style="font-size:34px;font-weight:bold;letter-spacing:8px;margin:0 0 16px;font-family:Courier,monospace">{escape(code)}</p>'
        f'<p style="font-size:14px;color:#444;margin:0 0 8px">The code expires in {ttl_min} minutes and works once.</p>'
        '<p style="font-size:14px;color:#444;margin:0 0 24px">If you did not request it, you can ignore this email.</p>'
        f'<p style="font-size:12px;color:#888;margin:0">Sent by {brand}. We never ask for your password or payment '
        'details by email.</p></td></tr></table>'
    )
    return subject, html
