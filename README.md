# Supplier Document Checker

An AI pipeline that reads supplier quotes, extracts key fields, and decides
**Approve / Reject / Needs a person** – with a cited reason for every decision.

Built for BIAI AI Engineer Round 2 (Task 1).

---

## How it works

```
PDF ──► [Extract fields via Gemini]
           │
           ▼
       [Verify quotes in PDF text]
           │
           ▼
       [Apply company rules]
           │
        ┌──┴──────────────────┐
     Approve / Reject    Needs a person
                              │
                         [Human-review stop]
                         (prints alert, could
                          create a ticket)
```

The graph is built with **LangGraph** as a fixed sequence of nodes.
Extraction uses **Gemini** (via `google-genai`) in structured JSON mode
so the output always conforms to the Pydantic schema – no markdown-fence
crashes, no parsing guesswork.

---

## Setup

### 1. Clone & create a virtual environment

```bash
git clone <your-repo-url>
cd Ai_Procuremnet_project
python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure your API key

```bash
cp .env.example .env
# Edit .env and add your GEMINI_API_KEY from https://aistudio.google.com/
```

---

## Run

### Process all 10 supplier PDFs

```bash
python -m app.main
```

### Evaluate accuracy (X/10 score + results.md)

```bash
python evaluate.py
```

On re-runs, cached extractions in `outputs/` are reused to avoid API calls.
To force a fresh LLM call: `python evaluate.py --no-cache`

---

## Tests

The unit tests are **fully offline** – they use hand-built `SupplierDoc`
objects and never call the LLM.

```bash
pytest tests/ -v
```

---

## Project structure

```
app/
  extraction/
    schema.py        Pydantic model for supplier documents
    extract.py       Gemini extraction with retries + JSON mode
  ingestion/
    pdf_reader.py    PyMuPDF text extraction
  rules/
    decide.py        Business-rule engine (Approve/Reject/Review)
  validation/
    validate.py      Quote verification + TIN/BIN validators
  workflow/
    graph.py         LangGraph pipeline (4 nodes)
  main.py            CLI entry point
data/
  supplier_pdf/      10 sample PDFs
  purchase-request.csv
  company-rules.md
tests/
  test_decisions.py  Offline parametrised unit tests
evaluate.py          LLM end-to-end evaluation + results.md
outputs/             Cached JSON extractions (created at runtime)
results.md           Accuracy table + confusion matrix (created by evaluate.py)
```

---

## Design decisions

| Decision | Rationale |
|---|---|
| `google-genai` + JSON mode | Eliminates markdown-fence crashes; response always matches the Pydantic schema |
| `delivery_value` + `delivery_unit` | Prevents the LLM from silently converting "4 weeks" → 28 days wrong |
| `has_penalty_clause: Optional[bool]` | Distinguishes "clause absent" (→ Reject) from "model unsure" (→ Review) |
| TIN/BIN regex validation | Prevents "Registration on request" strings from passing as valid identifiers |
| Decimal arithmetic | Avoids float rounding misjudging the 3% price boundary |
| 3-retry loop + `(text, None)` fallback | One bad LLM response never crashes the run |
| Named `human_review` node | Satisfies requirement #5 as a visible, auditable stop |
| Extraction cache in `outputs/` | Re-runs are cheap; cache can be cleared per-file for debugging |

---

## What does not work well / what I would do next

See [NOTE.md](NOTE.md).
