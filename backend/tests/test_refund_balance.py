"""Remaining cancellation refund after a partial admission-fee refund."""
from routes.cancellation import refund_balance


def test_ananya_remainder_after_partial_refund():
    # ₹1,00,000 fee, 100% tier, ₹1,000 processing fee, ₹50,100 already refunded.
    balance = refund_balance(paid_paise=10_000_000, refunded_paise=5_010_000, reserved_paise=5_010_000,
                             refund_percent=100, processing_fee_paise=100_000)
    assert balance["entitlement_paise"] == 9_900_000
    assert balance["already_refunded_paise"] == 5_010_000
    assert balance["refund_paise"] == 4_890_000
    assert balance["deduction_paise"] == 100_000


def test_full_policy_refund_when_nothing_was_returned():
    balance = refund_balance(paid_paise=10_000_000, refunded_paise=0, reserved_paise=0,
                             refund_percent=100, processing_fee_paise=100_000)
    assert balance["refund_paise"] == 9_900_000
    assert balance["already_refunded_paise"] == 0


def test_nothing_due_once_prior_refunds_cover_the_policy():
    balance = refund_balance(paid_paise=10_000_000, refunded_paise=9_900_000, reserved_paise=9_900_000,
                             refund_percent=100, processing_fee_paise=100_000)
    assert balance["refund_paise"] == 0


def test_in_flight_reservation_blocks_a_second_payout():
    balance = refund_balance(paid_paise=10_000_000, refunded_paise=5_010_000, reserved_paise=10_000_000,
                             refund_percent=100, processing_fee_paise=100_000)
    assert balance["refund_paise"] == 0
