"""
Business-rule engine for supplier quotation decisions.

Outcomes
--------
"Approve"               – all rules pass.
"Reject"                – at least one hard reject rule fires.
"Needs a person"        – uncertain/borderline, no hard reject.

Finding severity
----------------
"reject"  → sets Reject
"review"  → sets Needs a person
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal

from app.extraction.schema import SupplierDoc
from app.validation.validate import validate_bin, validate_tin

# Conversion table for delivery time units → days
_UNIT_TO_DAYS: dict[str, float] = {
    "day": 1,
    "days": 1,
    "week": 7,
    "weeks": 7,
    "month": 30,
    "months": 30,
}

_PRICE_TOLERANCE = Decimal("1.03")  # 3 % above max → reject


@dataclass
class Finding:
    severity: str   # "reject" | "review"
    reason: str
    quote: str


def _delivery_days(doc: SupplierDoc) -> int | None:
    """Convert delivery_value + delivery_unit to calendar days, or None."""
    if doc.delivery_value is None or doc.delivery_unit is None:
        return None
    unit_key = doc.delivery_unit.lower().rstrip(".")
    multiplier = _UNIT_TO_DAYS.get(unit_key)
    if multiplier is None:
        return None
    return int(doc.delivery_value * multiplier)


def _q(doc: SupplierDoc, field: str) -> str:
    """Return the supporting quote for a field, or a human-readable fallback."""
    return doc.quotes.get(field) or "not found in document"


def decide(doc: SupplierDoc, pr_row: dict | None) -> tuple[str, list[str], list[str]]:
    """
    Apply company rules and return (decision, reasons, quotes).

    Parameters
    ----------
    doc     : Extracted SupplierDoc (never None here; caller guards that).
    pr_row  : Row from purchase-request.csv for this item, or None.
    """
    findings: list[Finding] = []

    def add(severity: str, reason: str, quote: str) -> None:
        findings.append(Finding(severity=severity, reason=reason, quote=quote))

    # ── 1. Unit price ────────────────────────────────────────────────────────
    if doc.unit_price is None:
        add("review", "Unit price missing", _q(doc, "unit_price"))
    elif pr_row is None:
        add("review", "Item not found in purchase request", "")
    else:
        max_price = Decimal(str(pr_row["Maximum unit price (BDT)"])).quantize(
            Decimal("0.0001"), rounding=ROUND_HALF_UP
        )
        offered = Decimal(str(doc.unit_price)).quantize(
            Decimal("0.0001"), rounding=ROUND_HALF_UP
        )
        if offered > max_price * _PRICE_TOLERANCE:
            add(
                "reject",
                "Unit price more than 3% above the maximum",
                _q(doc, "unit_price"),
            )
        elif offered > max_price:
            add(
                "review",
                "Unit price above maximum by no more than 3%",
                _q(doc, "unit_price"),
            )

    # ── 2. Advance payment ───────────────────────────────────────────────────
    if doc.advance_percent is None:
        add("review", "Advance payment unclear", _q(doc, "advance_percent"))
    elif doc.advance_percent > 20:
        add(
            "reject",
            "Advance payment more than 20%",
            _q(doc, "advance_percent"),
        )

    # ── 3. Late-delivery penalty clause ─────────────────────────────────────
    #   has_penalty_clause=False  → explicit absence → Reject
    #   has_penalty_clause=None   → silent / unclear → Review
    #   has_penalty_clause=True   → present; check the rate
    if doc.has_penalty_clause is False:
        add("reject", "No late-delivery penalty clause", _q(doc, "has_penalty_clause"))
    elif doc.has_penalty_clause is None:
        add("review", "Penalty clause presence unclear", _q(doc, "penalty_text"))
    else:
        # Clause is present – check the rate
        if doc.penalty_percent_per_week is None:
            add(
                "review",
                "Penalty rate not stated; cannot confirm ≥ 0.5% per week",
                _q(doc, "penalty_text"),
            )
        elif doc.penalty_percent_per_week < 0.5:
            add(
                "reject",
                "Late-delivery penalty is less than 0.5% per week",
                _q(doc, "penalty_percent_per_week"),
            )

    # ── 4. TIN / BIN (company rules say "TIN or BIN" required) ──────────────
    tin_ok = validate_tin(doc.tin)
    bin_ok = validate_bin(doc.bin)
    if not tin_ok and not bin_ok:
        add(
            "reject",
            "Neither TIN nor BIN is present with the correct format",
            _q(doc, "tin"),
        )
    elif not tin_ok:
        add("review", "TIN missing or invalid format (expected 12 digits)", _q(doc, "tin"))
    elif not bin_ok:
        add("review", "BIN missing or invalid format (expected 9 digits)", _q(doc, "bin"))

    # ── 5. Delivery ──────────────────────────────────────────────────────────
    days = _delivery_days(doc)
    if days is None:
        add("review", "Delivery lead-time unclear or a range", _q(doc, "delivery_value"))
    elif days > 45:
        add("reject", "Delivery later than 45 days", _q(doc, "delivery_value"))
    elif 31 <= days <= 45:
        add("review", "Delivery in 31–45 days", _q(doc, "delivery_value"))

    # ── 6. Quantity vs. purchase request ────────────────────────────────────
    if doc.quantity is None:
        add("review", "Quantity unclear", _q(doc, "quantity"))
    elif pr_row is not None:
        req = float(pr_row["Quantity requested"])
        if req > 0 and abs(doc.quantity - req) / req > 0.05:
            add(
                "review",
                "Quantity differs from PR by more than 5%",
                _q(doc, "quantity"),
            )

    # ── 7. Payment terms ─────────────────────────────────────────────────────
    if doc.payment_days_after_delivery is None:
        add("review", "Payment terms unclear", _q(doc, "payment_terms_text"))
    elif not (30 <= doc.payment_days_after_delivery <= 60):
        add(
            "review",
            "Payment terms outside 30–60 days after delivery",
            _q(doc, "payment_terms_text"),
        )

    # ── 8. VAT ───────────────────────────────────────────────────────────────
    if doc.vat_shown_separately is not True or doc.vat_rate != 15:
        add("review", "VAT not shown separately at 15%", _q(doc, "vat_amount"))

    # ── 9. Arithmetic ────────────────────────────────────────────────────────
    def _d(v: float | None) -> Decimal | None:
        return None if v is None else Decimal(str(v))

    qty = _d(doc.quantity)
    up = _d(doc.unit_price)
    lt = _d(doc.line_total)
    sub = _d(doc.subtotal)
    vat = _d(doc.vat_amount)
    tot = _d(doc.total)

    tolerance = Decimal("0.02")  # BDT 0.02 rounding tolerance

    if qty is not None and up is not None and lt is not None:
        if abs(lt - qty * up) > tolerance:
            add("review", "Line total does not match quantity × unit price", _q(doc, "line_total"))

    if sub is not None and lt is not None:
        if abs(sub - lt) > tolerance:
            add("review", "Subtotal does not match line total", _q(doc, "subtotal"))

    if sub is not None and vat is not None and doc.vat_rate == 15:
        expected_vat = (sub * Decimal("0.15")).quantize(Decimal("0.01"), ROUND_HALF_UP)
        if abs(vat - expected_vat) > tolerance:
            add("review", "VAT amount does not equal 15% of subtotal", _q(doc, "vat_amount"))

    if sub is not None and vat is not None and tot is not None:
        if abs(tot - (sub + vat)) > tolerance:
            add("review", "Total does not equal subtotal + VAT", _q(doc, "total"))

    # ── 10. Quotation validity ───────────────────────────────────────────────
    if doc.validity_days is None:
        add("review", "Quotation validity period unclear", _q(doc, "validity_days"))
    elif doc.validity_days < 30:
        add("review", "Quotation valid for less than 30 days", _q(doc, "validity_days"))

    # ── 11. Required fields present ─────────────────────────────────────────
    for fname in ("supplier_name", "item_code", "unit", "total"):
        if getattr(doc, fname) is None:
            add("review", f"'{fname}' field missing", "not found in document")

    # ── Decision ─────────────────────────────────────────────────────────────
    has_reject = any(f.severity == "reject" for f in findings)
    has_review = any(f.severity == "review" for f in findings)

    if has_reject:
        decision = "Reject"
    elif has_review:
        decision = "Needs a person"
    else:
        decision = "Approve"

    reasons = [f.reason for f in findings]
    quotes = [f.quote for f in findings]
    return decision, reasons, quotes
