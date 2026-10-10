import asyncio
import os

import stripe

SHARED_KEY_PREFIX = "sk_test_emergent"
EMERGENT_PROXY = "https://integrations.emergentagent.com/stripe"
STRIPE_DEFAULT_BASE = "https://api.stripe.com"


def mode() -> dict:
    key = os.environ["STRIPE_API_KEY"]
    shared = key.startswith(SHARED_KEY_PREFIX)
    return {
        "provider": "stripe",
        "key_type": "shared_test_key" if shared else ("own_live_key" if key.startswith("sk_live") else "own_test_key"),
        "refunds_mode": "MOCKED" if shared else "live_provider",
        "refunds_mocked": shared,
        "webhook_signature_verification": bool(os.environ.get("STRIPE_WEBHOOK_SECRET")),
    }


def _configure():
    key = os.environ["STRIPE_API_KEY"]
    stripe.api_key = key
    stripe.api_base = EMERGENT_PROXY if key.startswith(SHARED_KEY_PREFIX) else STRIPE_DEFAULT_BASE


async def _call(fn, *args, **kwargs):
    def run():
        _configure()
        return fn(*args, **kwargs)
    return await asyncio.to_thread(run)


async def create_checkout(*, order_id: str, order_ref: str, description: str, amount_paise: int, email: str,
                          success_url: str, cancel_url: str, webhook_url: str):
    return await _call(
        stripe.checkout.Session.create,
        mode="payment",
        payment_method_types=["card"],
        line_items=[{"price_data": {"currency": "inr", "product_data": {"name": description},
                                    "unit_amount": amount_paise}, "quantity": 1}],
        success_url=success_url,
        cancel_url=cancel_url,
        client_reference_id=order_id,
        customer_email=email,
        metadata={"order_id": order_id, "order_ref": order_ref, "webhook_url": webhook_url},
        idempotency_key=f"checkout-{order_id}",
    )


async def retrieve_session(session_id: str):
    return await _call(stripe.checkout.Session.retrieve, session_id)


def refunds_mocked() -> bool:
    return os.environ["STRIPE_API_KEY"].startswith(SHARED_KEY_PREFIX)


class MockRefund:
    """MOCKED provider refund: the shared Emergent test key has no refund API."""
    def __init__(self, rid: str):
        self.id, self.status, self.failure_reason = rid, "succeeded", None


async def create_refund(*, payment_intent: str | None, amount_paise: int, refund_id: str, order_id: str):
    if refunds_mocked():
        return MockRefund(f"re_mock_{refund_id}")
    return await _call(stripe.Refund.create, payment_intent=payment_intent, amount=amount_paise,
                       metadata={"refund_id": refund_id, "order_id": order_id},
                       idempotency_key=f"refund-{refund_id}")


async def retrieve_refund(provider_refund_id: str):
    if provider_refund_id.startswith("re_mock_"):
        return MockRefund(provider_refund_id)
    return await _call(stripe.Refund.retrieve, provider_refund_id)


def construct_event(payload: bytes, signature: str):
    return stripe.Webhook.construct_event(payload, signature, os.environ["STRIPE_WEBHOOK_SECRET"])
