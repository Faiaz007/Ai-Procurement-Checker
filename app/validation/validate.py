"""
Quote verification and PR loading helpers.
"""
import csv
import re
from pathlib import Path

# Project root is two levels up from this file (app/validation/validate.py)
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_PR = _PROJECT_ROOT / "data" / "purchase-request.csv"

# Fields that carry a decisive meaning – they must have a supporting quote
# when non-null, otherwise the extraction is considered uncertain.
_DECISIVE_FIELDS = {
    "unit_price",
    "advance_percent",
    "delivery_value",
    "has_penalty_clause",
    "penalty_percent_per_week",
    "tin",
    "bin",
}


def _norm(s: str) -> str:
    """Collapse all whitespace to single spaces for robust substring matching."""
    return " ".join(s.split())


def load_pr(path: Path | str = _DEFAULT_PR) -> dict[str, dict]:
    """Return a dict keyed by Item letter from the purchase-request CSV."""
    with open(path, newline="") as f:
        return {r["Item"]: r for r in csv.DictReader(f)}


def verify_quotes(text: str, doc) -> tuple[bool, str | None]:
    """
    Check that every quote in doc.quotes is present (whitespace-normalised)
    in the extracted text, and that every decisive non-null field has a quote.

    Returns (True, None) on success, or (False, field_name) on the first failure.
    """
    norm_text = _norm(text)

    # 1. Check each quote can be found in the document.
    for field, q in doc.quotes.items():
        if not q:
            continue
        if _norm(q) not in norm_text:
            return False, field

    # 2. Check decisive fields have a supporting quote.
    for field in _DECISIVE_FIELDS:
        value = getattr(doc, field, None)
        if value is not None and field not in doc.quotes:
            return False, f"{field}:missing_quote"

    return True, None


def validate_tin(tin: str | None) -> bool:
    """TIN must be exactly 12 digits."""
    return bool(tin and re.fullmatch(r"\d{12}", tin))


def validate_bin(bin_: str | None) -> bool:
    """BIN must be exactly 9 digits."""
    return bool(bin_ and re.fullmatch(r"\d{9}", bin_))
