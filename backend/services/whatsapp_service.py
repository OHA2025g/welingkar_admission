import asyncio
import json
import logging
import os
import secrets

from twilio.base.exceptions import TwilioRestException
from twilio.rest import Client

logger = logging.getLogger(__name__)

REQUIRED_VARS = ("TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN", "TWILIO_WHATSAPP_FROM")


class WhatsAppDeliveryError(Exception):
    pass


def missing_vars() -> list[str]:
    return [v for v in REQUIRED_VARS if not os.environ.get(v)]


def is_configured() -> bool:
    return not missing_vars()


def _client() -> Client:
    return Client(os.environ["TWILIO_ACCOUNT_SID"], os.environ["TWILIO_AUTH_TOKEN"])


def _send_sync(to_e164: str, code: str, ttl_min: int):
    kwargs = {"from_": os.environ["TWILIO_WHATSAPP_FROM"], "to": f"whatsapp:{to_e164}"}
    content_sid = os.environ.get("TWILIO_WHATSAPP_CONTENT_SID")
    if content_sid:
        kwargs.update(content_sid=content_sid, content_variables=json.dumps({"1": code}))
    else:
        kwargs["body"] = (f"Your WeSchool Admissions verification code is {code}. "
                          f"It expires in {ttl_min} minutes. Do not share this code with anyone.")
    return _client().messages.create(**kwargs)


def is_mocked() -> bool:
    """MOCKED delivery when no approved template SID is set (Twilio trial blocks free-form text)."""
    return not os.environ.get("TWILIO_WHATSAPP_CONTENT_SID")


async def send_whatsapp_otp(to_e164: str, code: str, ttl_min: int) -> tuple[str, str]:
    if is_mocked():
        return f"wa_mock_{secrets.token_hex(8)}", "mocked"
    try:
        msg = await asyncio.to_thread(_send_sync, to_e164, code, ttl_min)
        return msg.sid, msg.status
    except TwilioRestException as e:
        logger.error(f"Twilio error {e.status} code={e.code}")
        hint = " (approved template required: set TWILIO_WHATSAPP_CONTENT_SID)" if e.code == 21654 else ""
        raise WhatsAppDeliveryError(f"Twilio error {e.code}: {e.msg}{hint}")
    except Exception as e:
        logger.error(f"Twilio unreachable: {type(e).__name__}")
        raise WhatsAppDeliveryError("Twilio unreachable")


async def fetch_status(sid: str) -> tuple[str, str | None]:
    msg = await asyncio.to_thread(lambda: _client().messages(sid).fetch())
    err = f"{msg.error_code}: {msg.error_message}" if msg.error_code else None
    return msg.status, err
