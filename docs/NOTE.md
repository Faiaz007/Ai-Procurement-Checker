# NOTE – Supplier Document Checker

## What I built

A four-node LangGraph pipeline that reads supplier quotation PDFs for a garment company and decides **Approve / Reject / Needs a person**, with a cited reason for every decision.

1. **Extract** – PyMuPDF pulls the text out of the PDF, then Groq returns structured JSON. The Pydantic schema is passed as `response_schema`, so the output is always a valid object; no markdown-fence parsing.
2. **Verify** – every extracted field's supporting quote is checked against the original PDF text (whitespace-normalised).
3. **Decide** – ten company rules (price cap, advance payment, penalty clause, TIN/BIN, delivery lead-time, quantity, payment terms, VAT, arithmetic, validity) are applied with Python logic and `Decimal` arithmetic.
4. **Human Review** – a named LangGraph node that prints an alert and, in production, would create a ticket. Every "Needs a person" decision passes through it explicitly.

## How I tested it

- **Offline unit tests** (`pytest tests/`) – 20+ parametrised cases exercise `decide()` with hand-built `SupplierDoc` objects. Instant, deterministic, free.
- **End-to-end evaluation** (`python evaluate.py`) – runs the full pipeline on all 10 PDFs against known ground truth, caches each extraction as JSON in `outputs/`, and writes a score table and confusion matrix to `results.md`.

## Results

Run `python evaluate.py` to see the current score; results land in `results.md`. The cache in `outputs/` keeps re-runs cheap – delete a file to force a fresh LLM extraction.

## What does not work well

- **Unclear delivery times** – vague phrases like "30 to 90 days as agreed" (pack 09) safely go to human review, but unusual units (like "fortnights") are not converted and also go to review.
- **Quote checking is rough** – matching quotes to the PDF text works most of the time, but odd spacing or special characters can cause a false mismatch.
- **TIN/BIN rules are sample-based** – the 12- and 9-digit checks come from the provided PDFs. Real production formats may need the rules updated.
- **No confidence score** – the system cannot tell a very confident extraction from a shaky one, so borderline cases are not auto-flagged.

## What I would improve next

1. Add OCR support and stronger handling of scanned or complex PDFs.
2. Improve extraction reliability through schema-constrained output and field-level validation.
3. Add persistent processing state and automatic recovery from API failures.
4. Expand automated testing with more supplier document variations.
5. Improve the review interface so procurement staff can inspect evidence and resolve flagged cases more easily.