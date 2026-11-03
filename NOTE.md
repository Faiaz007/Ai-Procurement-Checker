# NOTE – Supplier Document Checker

## What I built

A four-node LangGraph pipeline that processes supplier quotation PDFs for a garment company:

1. **Extract** – reads the PDF with PyMuPDF and sends the text to Gemini in structured JSON mode. The Pydantic schema is passed as `response_schema` so the LLM output is always a valid object; no markdown-fence parsing is needed.
2. **Verify** – checks that every field's supporting quote can be found (whitespace-normalised) in the original PDF text.
3. **Decide** – applies the ten company rules (price cap, advance payment, penalty clause, TIN/BIN, delivery lead-time, quantity, payment terms, VAT, arithmetic, validity) using Python logic with `Decimal` arithmetic.
4. **Human Review** – a named LangGraph node that prints an alert and (in production) would create a ticket. Every "Needs a person" decision passes through this node explicitly.

## How I tested it

- **Offline unit tests** (`pytest tests/`) – 20+ `pytest.mark.parametrize` cases exercise `decide()` with hand-built `SupplierDoc` objects. These are instant, deterministic, and free.
- **End-to-end evaluation** (`python evaluate.py`) – runs the full pipeline on all 10 PDFs against known ground truth, caches each extraction as JSON in `outputs/`, and writes a score table and confusion matrix to `results.md`.

## Results

Run `python evaluate.py` to see the current score. Results are saved to `results.md`. The cache in `outputs/` means re-runs are cheap – delete a file to re-extract it from the LLM.

## What does not work well

- **Vague delivery terms** such as "30 to 90 days as agreed" (pack 09) correctly produce a null `delivery_value`, which routes to human review. However if a future document uses a non-standard unit (e.g. "fortnights") the converter returns null and falls through to review conservatively.
- **Quote matching is approximate.** Whitespace normalisation removes most false failures, but if the PDF renderer uses special Unicode spaces or ligatures the quote may still not match. A fuzzy matcher (e.g. `rapidfuzz`) would be more robust.
- **TIN/BIN format** – the digit-count rules (12 and 9) are based on the sample PDFs. If the format changes in production the regex needs updating.
- **No confidence score** – the system cannot distinguish a model that was 99% sure from one that was 51% sure. A log-probability signal would let us route low-confidence extractions to review even when the structured output validates.

## What I would do next

1. **Fuzzy quote matching** with `rapidfuzz` to handle OCR noise and Unicode variants.
2. **Streaming / async extraction** – process all 10 PDFs in parallel to cut wall-clock time.
3. **Webhook or queue trigger** – replace the manual CLI run with an S3/GCS event that fires the pipeline when a new PDF is uploaded.
4. **Human-in-the-loop UI** – a simple web page where a reviewer can see the extracted fields and the supporting quotes side-by-side, accept or override the decision, and add it to the training set.
5. **Fine-tuning or few-shot prompting** on validated extractions to reduce the null rate for edge-case fields.
