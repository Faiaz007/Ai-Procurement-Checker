"""
Field extraction via Gemini (google-genai SDK).

Uses JSON mode with a strict response_schema so the output is always
a valid SupplierDoc.  Retries up to 3 times on any exception; returns
(text, None) on persistent failure so the graph routes to human review.
"""
import os
from pathlib import Path

from dotenv import load_dotenv
from google import genai
from google.genai import types

from app.extraction.schema import SupplierDoc
from app.ingestion.pdf_reader import read_pdf_text

load_dotenv()

SYSTEM_INSTRUCTION = """\
You are a precise document-data extractor for a garment procurement system.

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
  in the 'quotes' dictionary.
- Never guess or infer.
"""


def _make_client() -> genai.Client:
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise EnvironmentError("GEMINI_API_KEY is not set.")
    return genai.Client(api_key=api_key)


def extract_fields(pdf_path: str | Path) -> tuple[str, SupplierDoc | None]:
    """
    Extract structured fields from a supplier PDF.

    Returns:
        (raw_text, SupplierDoc) on success.
        (raw_text, None)        on persistent failure (routes to human review).
    """
    text = read_pdf_text(Path(pdf_path))
    client = _make_client()
    model = os.environ.get("GEMINI_MODEL", "gemini-2.0-flash")

    last_exc: Exception | None = None
    for attempt in range(3):
        try:
            resp = client.models.generate_content(
                model=model,
                contents=f"<document>\n{text}\n</document>",
                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM_INSTRUCTION,
                    temperature=0,
                    response_mime_type="application/json",
                    response_schema=SupplierDoc,
                ),
            )
            doc = SupplierDoc.model_validate_json(resp.text)
            return text, doc
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            print(f"[extract] attempt {attempt + 1}/3 failed: {exc}")

    print(f"[extract] all retries exhausted for {pdf_path}: {last_exc}")
    return text, None
