"""
Offline unit tests for the decide() function.

These tests are deterministic and instant – they use hand-built SupplierDoc
objects and never call the LLM.  Each pack scenario is tested independently
via pytest.mark.parametrize.

To run the LLM end-to-end evaluation, use:
    python evaluate.py
"""
import pytest

from app.extraction.schema import SupplierDoc
from app.rules.decide import decide

# ── Helpers ───────────────────────────────────────────────────────────────────

def _pr(unit_price: float = 480.0, quantity: float = 12000.0) -> dict:
    """Minimal PR row."""
    return {
        "Item": "A",
        "Description": "Cotton twill fabric, 280 gsm",
        "Unit": "metre",
        "Quantity requested": str(quantity),
        "Maximum unit price (BDT)": str(unit_price),
    }


def _base_doc(**overrides) -> SupplierDoc:
    """A fully valid SupplierDoc that should produce 'Approve'."""
    base = dict(
        supplier_name="Test Supplier Ltd",
        item_code="A",
        description="Cotton twill fabric, 280 gsm",
        quantity=12000.0,
        unit="metre",
        unit_price=470.0,
        line_total=5640000.0,
        subtotal=5640000.0,
        vat_amount=846000.0,
        vat_shown_separately=True,
        vat_rate=15.0,
        total=6486000.0,
        tin="123456789012",   # 12 digits
        bin="123456789",      # 9 digits
        advance_percent=10.0,
        payment_terms_text="Net 45 days after delivery",
        payment_days_after_delivery=45,
        delivery_value=30.0,
        delivery_unit="days",
        has_penalty_clause=True,
        penalty_percent_per_week=1.0,
        penalty_text="1% of order value per week of delay",
        validity_days=60,
        quotes={
            "unit_price": "BDT 470.00 per metre",
            "advance_percent": "10% advance",
            "delivery_value": "30 days",
            "has_penalty_clause": "1% of order value per week of delay",
            "penalty_percent_per_week": "1% of order value per week of delay",
            "tin": "123456789012",
            "bin": "123456789",
        },
    )
    base.update(overrides)
    return SupplierDoc(**base)


# ── Parametrised test cases ────────────────────────────────────────────────────

@pytest.mark.parametrize("label,doc,pr_row,expected", [
    # ── Approve ────────────────────────────────────────────────────────────────
    (
        "approve_clean",
        _base_doc(),
        _pr(),
        "Approve",
    ),

    # ── Reject: price > 3% above max ──────────────────────────────────────────
    (
        "reject_price_above_3pct",
        _base_doc(unit_price=500.0),  # 480 * 1.03 = 494.4, 500 > 494.4
        _pr(unit_price=480.0),
        "Reject",
    ),

    # ── Review: price between max and max*1.03 ─────────────────────────────────
    (
        "review_price_slightly_above",
        _base_doc(unit_price=490.0),  # 480 < 490 < 494.4
        _pr(unit_price=480.0),
        "Needs a person",
    ),

    # ── Reject: advance > 20% ─────────────────────────────────────────────────
    (
        "reject_advance_too_high",
        _base_doc(advance_percent=30.0),
        _pr(),
        "Reject",
    ),

    # ── Reject: explicit no penalty clause ────────────────────────────────────
    (
        "reject_no_penalty_clause",
        _base_doc(has_penalty_clause=False, penalty_percent_per_week=None, penalty_text=None),
        _pr(),
        "Reject",
    ),

    # ── Review: penalty clause presence unknown (None) ────────────────────────
    (
        "review_penalty_unknown",
        _base_doc(has_penalty_clause=None, penalty_percent_per_week=None, penalty_text=None),
        _pr(),
        "Needs a person",
    ),

    # ── Reject: penalty rate too low ──────────────────────────────────────────
    (
        "reject_penalty_too_low",
        _base_doc(penalty_percent_per_week=0.25),
        _pr(),
        "Reject",
    ),

    # ── Reject: neither TIN nor BIN ───────────────────────────────────────────
    (
        "reject_no_tin_no_bin",
        _base_doc(tin=None, bin=None),
        _pr(),
        "Reject",
    ),

    # ── Review: only TIN present (BIN missing) ────────────────────────────────
    (
        "review_tin_only",
        _base_doc(bin=None),
        _pr(),
        "Needs a person",
    ),

    # ── Review: only BIN present (TIN missing) ────────────────────────────────
    (
        "review_bin_only",
        _base_doc(tin=None),
        _pr(),
        "Needs a person",
    ),

    # ── Reject: delivery > 45 days ────────────────────────────────────────────
    (
        "reject_delivery_too_late",
        _base_doc(delivery_value=7.0, delivery_unit="weeks"),  # 49 days
        _pr(),
        "Reject",
    ),

    # ── Reject: delivery > 45 days via "6 weeks" ──────────────────────────────
    (
        "reject_delivery_6_weeks",
        _base_doc(delivery_value=6.0, delivery_unit="weeks"),  # 42 days → should be review
        _pr(),
        "Needs a person",  # 42 days falls in 31–45 range
    ),

    # ── Review: delivery in 31–45 days ────────────────────────────────────────
    (
        "review_delivery_31_to_45",
        _base_doc(delivery_value=40.0, delivery_unit="days"),
        _pr(),
        "Needs a person",
    ),

    # ── Review: delivery unclear (None) ───────────────────────────────────────
    (
        "review_delivery_unclear",
        _base_doc(delivery_value=None, delivery_unit=None),
        _pr(),
        "Needs a person",
    ),

    # ── Review: quantity differs > 5% ─────────────────────────────────────────
    (
        "review_quantity_differs",
        _base_doc(quantity=14000.0),  # 16.7% above 12000
        _pr(quantity=12000.0),
        "Needs a person",
    ),

    # ── Review: payment terms outside 30–60 days ──────────────────────────────
    (
        "review_payment_terms_outside",
        _base_doc(payment_days_after_delivery=90),
        _pr(),
        "Needs a person",
    ),

    # ── Review: VAT not shown separately ──────────────────────────────────────
    (
        "review_vat_not_separate",
        _base_doc(vat_shown_separately=False),
        _pr(),
        "Needs a person",
    ),

    # ── Review: arithmetic wrong (line total mismatch) ────────────────────────
    (
        "review_line_total_wrong",
        _base_doc(line_total=9999999.0),
        _pr(),
        "Needs a person",
    ),

    # ── Review: arithmetic wrong (VAT mismatch) ───────────────────────────────
    (
        "review_vat_amount_wrong",
        _base_doc(vat_amount=500000.0),   # should be 846000
        _pr(),
        "Needs a person",
    ),

    # ── Review: validity < 30 days ────────────────────────────────────────────
    (
        "review_validity_too_short",
        _base_doc(validity_days=14),
        _pr(),
        "Needs a person",
    ),

    # ── Review: unit price missing ────────────────────────────────────────────
    (
        "review_unit_price_missing",
        _base_doc(unit_price=None),
        _pr(),
        "Needs a person",
    ),

    # ── Reject takes priority over review ────────────────────────────────────
    (
        "reject_beats_review",
        _base_doc(unit_price=500.0, validity_days=14),  # both reject and review
        _pr(unit_price=480.0),
        "Reject",
    ),
])
def test_decide(label, doc, pr_row, expected):
    decision, reasons, _ = decide(doc, pr_row)
    assert decision == expected, (
        f"[{label}] expected={expected!r}, got={decision!r}, reasons={reasons}"
    )


# ── Delivery conversion tests ─────────────────────────────────────────────────

@pytest.mark.parametrize("value,unit,expected_days", [
    (30, "days", 30),
    (4,  "weeks", 28),
    (1,  "month", 30),
    (2,  "months", 60),
    (1,  "week", 7),
])
def test_delivery_conversion(value, unit, expected_days):
    from app.rules.decide import _delivery_days
    doc = _base_doc(delivery_value=float(value), delivery_unit=unit)
    assert _delivery_days(doc) == expected_days


# ── TIN / BIN validation ──────────────────────────────────────────────────────

@pytest.mark.parametrize("tin,expected", [
    ("123456789012", True),   # 12 digits ✓
    ("12345678901",  False),  # 11 digits ✗
    ("1234567890123", False), # 13 digits ✗
    ("12345678901A", False),  # non-digit ✗
    (None,           False),
])
def test_validate_tin(tin, expected):
    from app.validation.validate import validate_tin
    assert validate_tin(tin) == expected


@pytest.mark.parametrize("bin_,expected", [
    ("123456789", True),   # 9 digits ✓
    ("12345678",  False),  # 8 digits ✗
    ("1234567890", False), # 10 digits ✗
    (None,        False),
])
def test_validate_bin(bin_, expected):
    from app.validation.validate import validate_bin
    assert validate_bin(bin_) == expected
