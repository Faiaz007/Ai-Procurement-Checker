# Loom Narration Script — Supplier Document Checker

Use this while recording. Read aloud; the bracketed notes are for you (don't read them).

---

## 0:00 — Title / Intro

"Hi, this is the AI Supplier Document Checker. It reads supplier quotation PDFs, extracts the key fields with an LLM, verifies the quotes against the PDF text, and then applies company rules to return one of three decisions: Approve, Reject, or Needs a Person — each with a cited reason."

Show: the project folder + README.

---

## 0:20 — How it works (architecture)

"The pipeline is built with LangGraph as a fixed sequence of four nodes:

1. **Ingestion** — PyMuPDF extracts raw text from the PDF.
2. **Extraction** — Groq (in JSON mode) fills a Pydantic schema, so output always conforms — no markdown-fence parsing issues.
3. **Verification** — the extracted quotes are checked against the actual PDF text, and TIN/BIN identifiers are regex-validated.
4. **Rule engine** — company rules are applied: unit price vs. purchase-request cap, advance payment %, penalty clause, delivery time, VAT, arithmetic chain, and validity period."

Show: the workflow/graph.py node diagram or the README diagram.

---

## 0:55 — Setup

"To run it:

1. Clone the repo and create a virtual environment.
2. `pip install -r requirements.txt`
3. Copy `.env.example` to `.env` and add your GROQ_API_KEY."

(Show the commands quickly.)

---

## 1:15 — Running the CLI backend

"From the project root, the backend runs with:

`python -m app.main`

It processes all PDFs in `data/supplier_pdf/` and prints each decision plus the reasons and the supporting quotes from the document."

(Open a terminal, run it, scroll through output.)

"Add `--json` for machine-readable output. Extractions are cached in `outputs/` so re-runs are cheap — use `--no-cache` on evaluate.py to force fresh LLM calls."

---

## 1:40 — Running the Streamlit UI

"The UI is in `ui/app.py`. Run it with:

`streamlit run ui/app.py`

Upload any supplier PDF — it runs the same pipeline live, shows a step tracker, the decision badge, findings with cited quotes, and the extracted fields."

(Open the UI, upload a sample PDF, show the result.)

---

## 2:15 — Testing / evaluation

"Unit tests in `tests/` are fully offline — they use hand-built objects and never call the LLM. Run them with `pytest tests/ -v`.

`python evaluate.py` runs the full pipeline end-to-end against all 10 sample PDFs and writes an accuracy table plus confusion matrix to `results.md`."

(Show results.md briefly.)

---

## 2:35 — Key design decisions

"A few decisions worth calling out:

- **Groq SDK + JSON mode** eliminates markdown-fence crashes; the response always matches the Pydantic schema.
- **Separate `delivery_value` + `delivery_unit`** so the LLM can't silently convert '4 weeks' into 28 days.
- **`has_penalty_clause: Optional[bool]`** distinguishes an absent clause (→ Reject) from an unsure model (→ Review).
- **Decimal arithmetic** avoids float rounding misjudging the 3% price boundary.
- **3-retry loop with fallback** so one bad LLM response never crashes the run."

---

## 3:00 — Outro

"That's the project. Clone it, add your Groq key, and you're ready to check supplier quotes. Thanks for watching — questions welcome in the comments."

---

## Recording checklist

- [ ] Screen: terminal + app windows, dark theme if possible
- [ ] Mouse pointer visible / highlighted during clicks
- [ ] Speak clearly, ~1.0–1.25x speed
- [ ] Keep total under 4 minutes
- [ ] End screen: repo link + "Thanks for watching"