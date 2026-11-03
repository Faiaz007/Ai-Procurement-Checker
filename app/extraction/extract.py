"""
Field extraction via Groq (groq SDK).

Uses JSON mode (response_format={"type": "json_object"}) so the output is
always valid JSON, then validates it against the SupplierDoc Pydantic schema.
Retries up to 3 times on any exception with backoff on rate limits; returns
(text, None) on persistent failure so the graph routes to human review.
"""
import json
import os
import time
from pathlib import Path

from dotenv import load_dotenv
from groq import Groq

from app.extraction.schema import SupplierDoc
from app.ingestion.pdf_reader import read_pdf_text

load_dotenv(override=True)

# Exact field names the model must emit (kept in sync with SupplierDoc).
EXPECTED_FIELDS = [
    "supplier_name",
    "item_code",
    "description",
    "quantity",
    "unit",
    "unit_price",
    "line_total",
    "subtotal",
    "vat_amount",
    "vat_shown_separately",
    "vat_rate",
    "total",
    "tin",
    "bin",
    "advance_percent",
    "payment_terms_text",
    "payment_days_after_delivery",
    "delivery_value",
    "delivery_unit",
    "has_penalty_clause",
    "penalty_percent_per_week",
    "penalty_text",
    "validity_days",
    "quotes",
]

# Maps model output synonyms -> canonical SupplierDoc field names.
_SYNONYMS = {
    "supplier_tin": "tin",
    "supplier_bin": "bin",
    "items[0].unit_price": "unit_price",
    "items[0].quantity": "quantity",
    "items[0].unit": "unit",
    "items[0].description": "description",
    "items[0].amount": "line_total",
    "payment_terms": "payment_terms_text",
    "penalty_details": "penalty_text",
}


def _make_client() -> Groq:
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise EnvironmentError("GROQ_API_KEY is not set.")
    return Groq(api_key=api_key)


def _normalize_keys(data: dict) -> dict:
    """Remap model-output synonyms to canonical SupplierDoc field names."""
    out = {}
    for k, v in data.items():
        canon = _SYNONYMS.get(k, k)
        # Don't clobber a canonical value that already exists.
        if canon in out:
            continue
        out[canon] = v
    return out


SYSTEM_INSTRUCTION = """\
You are a precise document-data extractor for a garment procurement system.

Output a single raw JSON object with EXACTLY these top-level keys (no others):
supplier_name, item_code, description, quantity, unit, unit_price, line_total,
subtotal, vat_amount, vat_shown_separately, vat_rate, total, tin, bin,
advance_percent, payment_terms_text, payment_days_after_delivery, delivery_value,
delivery_unit, has_penalty_clause, penalty_percent_per_week, penalty_text,
validity_days, quotes.

Rules:
- Extract ONLY values that are explicitly stated in the document.
- Set a field to null if the value is missing, ambiguous, a range, or expressed as
  "as agreed" / "to be confirmed" / "on request".
- For delivery: capture the raw number in delivery_value and the time unit in
  delivery_unit (e.g. delivery_value=4, delivery_unit="weeks").
  Never convert weeks to days yourself.
- For TIN: exactly 12 digits.  For BIN: exactly 9 digits.
  Anything else must be null.
- Set has_penalty_clause to true only when a penalty clause is present,
  false only when the document explicitly says there is none, and null when silent.
- For every non-null field include the exact verbatim substring from the document
  in the 'quotes' dictionary mapping field_name -> substring.
- vat_rate is a percentage number (e.g. 15, not 0.15).
- Never guess or infer.
- Output raw JSON only — no markdown fences, no explanatory text.
"""


def extract_fields(pdf_path: str | Path) -> tuple[str, SupplierDoc | None]:
    """
    Extract structured fields from a supplier PDF.

    Uses Groq JSON mode so the model returns raw JSON without markdown fences.
    The response is key-normalized (synonyms -> canonical names) then validated
    against the SupplierDoc Pydantic schema.

    Returns:
        (raw_text, SupplierDoc) on success.
        (raw_text, None)        on persistent failure (routes to human review).
    """
    text = read_pdf_text(Path(pdf_path))
    client = _make_client()
    model = os.environ.get("GROQ_MODEL", "qwen/qwen3.8-27b")

    last_exc: Exception | None = None
    for attempt in range(3):
        try:
            resp = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": SYSTEM_INSTRUCTION},
                    {
                        "role": "user",
                        "content": f"<document>\n{text}\n</document>",
                    },
                ],
                response_format={"type": "json_object"},
                temperature=0,
            )
            raw = resp.choices[0].message.content
            data = json.loads(raw)
            if isinstance(data, dict):
                data = _normalize_keys(data)
            doc = SupplierDoc.model_validate(data)
            return text, doc
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            msg = str(exc)
            wait = 0
            if "rate_limit_exceeded" in msg or "429" in msg:
                for token in ("retry in ", "try again in "):
                    idx = msg.find(token)
                    if idx != -1:
                        try:
                            wait = float(msg[idx + len(token):].split(",")[0].split(" ")[0])
                        except ValueError:
                            wait = 0
                        break
                wait = max(wait, 5.0)
            print(f"[extract] attempt {attempt + 1}/3 failed: {exc}")
            if wait > 0 and attempt < 2:
                time.sleep(wait)

    print(f"[extract] all retries exhausted for {pdf_path}: {last_exc}")
    return text, None
