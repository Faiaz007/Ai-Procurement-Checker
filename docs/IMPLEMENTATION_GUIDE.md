# Implementation Guide – AI Supplier Document Checker

A deep-dive into every code decision: the theory behind it, how it is implemented,
why each approach was chosen over the alternatives.

---

## Table of Contents

1. [The Core Problem](#1-the-core-problem)
2. [Why LangGraph?](#2-why-langgraph)
3. [Extraction – The Hardest Part](#3-extraction--the-hardest-part)
4. [Pydantic Schema Design](#4-pydantic-schema-design)
5. [Quote Verification](#5-quote-verification)
6. [The Rule Engine](#6-the-rule-engine)
7. [Arithmetic Safety with Decimal](#7-arithmetic-safety-with-decimal)
8. [Testing Strategy](#8-testing-strategy)
9. [Frontend: Streamlit vs Next.js](#9-frontend-streamlit-vs-nextjs)
10. [What I Would Do with More Time](#10-what-i-would-do-with-more-time)

---

## 1. The Core Problem

Procurement documents are **semi-structured natural language**.
The same fact can appear as:

- `"Delivery: 30 days"` → 30 days
- `"Lead time: 4 weeks"` → 28 days
- `"Delivery: 30 to 90 days as agreed"` → **null** (range, not a single value)
- `"Delivery as per negotiation"` → **null**

A naive LLM prompt will happily pick `30` from the last example.
A system that trusts that extraction will silently produce a wrong decision.

**Key insight:** the LLM's job is _extraction_, not _interpretation_.
Every conversion, comparison, and arithmetic check happens in deterministic Python code.

---

## 2. Why LangGraph?

### Theory

LangGraph models a pipeline as a directed graph of nodes, where:
- Each node is a **pure function** `(State) → dict` (partial state update).
- Edges define execution order — including **conditional edges** that branch on runtime values.
- The compiled graph is a `Runnable`, invocable with a single `graph.invoke(state)`.

### Why not a single LLM call?

| Approach | Problem |
|---|---|
| One prompt: "read this PDF and tell me approve/reject" | Unauditable. Wrong answers have no traceable reason. |
| ReAct agent with tools | Agent can loop, hallucinate tool calls, go off-script. Not allowed by the brief. |
| **LangGraph fixed graph** | Every step is named, logged, and auditable. Errors are caught per-node. ✓ |

### The four nodes

```python
# graph.py
g = StateGraph(State)
g.add_node("extract",      node_extract)       # PDF → SupplierDoc
g.add_node("verify",       node_verify)        # quotes in PDF?
g.add_node("decide",       node_decide)        # apply rules
g.add_node("human_review", node_human_review)  # named stop
g.set_entry_point("extract")
g.add_edge("extract", "verify")
g.add_edge("verify",  "decide")
g.add_conditional_edges("decide", _route_after_decide, {
    "human_review": "human_review",
    END: END,
})
g.add_edge("human_review", END)
```

The `human_review` node is required by the brief:
> "When it is not sure, stop and ask a person."

This node is where you would, in production, create a Jira ticket, send a Slack alert,
or open a review queue item.

---

## 3. Extraction – The Hardest Part

### Why the old code broke

```python
# OLD — broken 4 ways
import google.generativeai as genai          # deprecated SDK
model = genai.GenerativeModel("Groq-1.5-flash")  # retired model
resp = model.generate_content(SYSTEM + text)
data = json.loads(resp.text)                 # crashes on ```json ... ```
doc = SupplierDoc(**data)                    # crashes on wrong types
```

### The fix — JSON mode with response_schema

```python
# NEW — extract.py
from google import genai
from google.genai import types

resp = client.models.generate_content(
    model=os.environ.get("Groq_MODEL", "Groq-2.0-flash"),
    contents=f"<document>\n{text}\n</document>",
    config=types.GenerateContentConfig(
        system_instruction=SYSTEM_INSTRUCTION,
        temperature=0,                            # deterministic
        response_mime_type="application/json",    # no markdown fences
        response_schema=SupplierDoc,              # shape-constrained
    ),
)
doc = SupplierDoc.model_validate_json(resp.text)
```

**`temperature=0`** – makes the model pick the single most probable token at every step.
For extraction (not creative writing) this means consistent, repeatable results.

**`response_mime_type="application/json"`** – the model is forbidden from wrapping
its answer in markdown fences. `resp.text` is always a raw JSON string.

**`response_schema=SupplierDoc`** – Groq reads the Pydantic model's JSON schema
and constrains its output to match. Field names, types (`str | null`, `float | null`, etc.)
are all enforced by the model's constrained decoding, not by post-hoc parsing.

### Retry logic

```python
for attempt in range(3):
    try:
        resp = client.models.generate_content(...)
        doc = SupplierDoc.model_validate_json(resp.text)
        return text, doc
    except Exception as exc:
        last_exc = exc
        print(f"[extract] attempt {attempt + 1}/3 failed: {exc}")

return text, None   # caller routes to human review
```

A transient network error, a rate-limit 429, or a malformed response all raise an
exception. Three attempts cover the vast majority of transient failures.
If all three fail, `None` is returned and the graph routes to human review —
**the run never crashes**.

### System instruction design

```
You are a precise document-data extractor for a garment procurement system.

Rules:
- Extract ONLY values explicitly stated in the document.
- Set null if: missing, ambiguous, a range, "as agreed" / "on request".
- For delivery: capture delivery_value (number) and delivery_unit (string).
  Never convert weeks to days yourself.
- TIN: exactly 12 digits. BIN: exactly 9 digits. Anything else → null.
- has_penalty_clause: true/false/null — never guess.
- For every non-null field include the exact verbatim substring in 'quotes'.
- Never guess or infer.
```

The instruction tells the model what to do with every known ambiguity pattern.
The schema's `Field(description=...)` annotations reinforce this at the type level.

---

## 4. Pydantic Schema Design

### Theory

Pydantic v2 models are both a **validation layer** and a **documentation layer**.
When used as a `response_schema`, Groq reads the model's JSON schema —
including field descriptions — to guide its output.

### The delivery split

**Problem:** `delivery_days: int` forces the model to convert `"4 weeks"` to `28`.
This is implicit reasoning the model can get wrong.

```python
# OLD — dangerous
delivery_days: Optional[int] = None
# Model sees "4 weeks" and might write 28, or 4, or null — unpredictable
```

**Fix:** capture the raw value and unit separately, convert in Python.

```python
# NEW — safe
delivery_value: Optional[float] = Field(
    default=None,
    description='Numeric part of the delivery lead-time (e.g. 4 for "4 weeks").'
)
delivery_unit: Optional[str] = Field(
    default=None,
    description='Time unit: "days", "weeks", "months". Null if delivery_value is null.'
)
```

```python
# decide.py — deterministic conversion
_UNIT_TO_DAYS = {"day": 1, "days": 1, "week": 7, "weeks": 7, "month": 30, "months": 30}

def _delivery_days(doc: SupplierDoc) -> int | None:
    if doc.delivery_value is None or doc.delivery_unit is None:
        return None
    multiplier = _UNIT_TO_DAYS.get(doc.delivery_unit.lower().rstrip("."))
    if multiplier is None:
        return None   # unknown unit → human review
    return int(doc.delivery_value * multiplier)
```

### The penalty clause split

**Problem:** `not doc.penalty_text` treats both "model couldn't find it" and "document
explicitly says no penalty" as the same thing — and rejects both.

```python
# OLD — wrong
if not doc.penalty_text:
    reject = True    # null AND explicit-false both rejected
```

**Fix:** add a tristate boolean.

```python
# NEW — correct
has_penalty_clause: Optional[bool] = Field(
    description="True if clause present. False if explicitly absent. Null if silent."
)
```

```python
# decide.py
if doc.has_penalty_clause is False:
    add("reject", "No late-delivery penalty clause", ...)   # explicit → Reject
elif doc.has_penalty_clause is None:
    add("review", "Penalty clause presence unclear", ...)   # unknown → Review
else:
    # clause is present — check the rate
    if doc.penalty_percent_per_week is None:
        add("review", "Penalty rate not stated", ...)
    elif doc.penalty_percent_per_week < 0.5:
        add("reject", "Penalty rate less than 0.5% per week", ...)
```

### TIN / BIN format validation

The company rules say "TIN or BIN required". The old code:
1. Required **both** (wrong reading of the rules).
2. Accepted any non-null string as a valid TIN/BIN.
   `"Registration available on request"` would have passed.

```python
# validate.py
import re

def validate_tin(tin: str | None) -> bool:
    """TIN must be exactly 12 digits."""
    return bool(tin and re.fullmatch(r"\d{12}", tin))

def validate_bin(bin_: str | None) -> bool:
    """BIN must be exactly 9 digits."""
    return bool(bin_ and re.fullmatch(r"\d{9}", bin_))
```

```python
# decide.py — "TIN or BIN" means either is enough
tin_ok = validate_tin(doc.tin)
bin_ok = validate_bin(doc.bin)
if not tin_ok and not bin_ok:
    add("reject", "Neither TIN nor BIN present with correct format", ...)
elif not tin_ok:
    add("review", "TIN missing or invalid (expected 12 digits)", ...)
elif not bin_ok:
    add("review", "BIN missing or invalid (expected 9 digits)", ...)
```

---

## 5. Quote Verification

### Theory

The LLM is asked to cite the exact document substring that supports each field.
Verifying these citations serves two purposes:

1. **Hallucination detection** – if the model invented a value, the quote won't be in
   the PDF.
2. **Auditability** – every decision traces to a source string the evaluator can find
   in the original document.

### The line-break problem

PyMuPDF joins text blocks with `\n`. The model sees continuous text in its context
window (no newlines), so its quotes never contain `\n`. Direct substring search fails.

```python
# OLD — false failures
if q not in text:
    return False, field
```

```python
# NEW — whitespace-normalised
def _norm(s: str) -> str:
    return " ".join(s.split())  # collapses \n, \t, multiple spaces

def verify_quotes(text, doc):
    norm_text = _norm(text)
    for field, q in doc.quotes.items():
        if not q:
            continue
        if _norm(q) not in norm_text:
            return False, field
    return True, None
```

### Decisive-field check

Some fields are important enough that a non-null value _must_ have a supporting quote.
If the model sets `unit_price = 470.0` but has no quote for it, something is wrong.

```python
_DECISIVE_FIELDS = {"unit_price", "advance_percent", "delivery_value",
                    "has_penalty_clause", "penalty_percent_per_week", "tin", "bin"}

for field in _DECISIVE_FIELDS:
    value = getattr(doc, field, None)
    if value is not None and field not in doc.quotes:
        return False, f"{field}:missing_quote"
```

---

## 6. The Rule Engine

### Theory

The old `add()` helper was supposed to set `reject`/`review` flags but didn't —
the `nonlocal` declaration was present but the function body only appended to lists.
The flags were set manually by the caller, which meant any caller that forgot to set
the flag produced a silent miss.

### The fix: Finding dataclass + derive at the end

```python
@dataclass
class Finding:
    severity: str   # "reject" | "review"
    reason: str
    quote: str

findings: list[Finding] = []

def add(severity, reason, quote):
    findings.append(Finding(severity=severity, reason=reason, quote=quote))

# ... all rules call add() ...

# Derive at the end — no flag management needed
has_reject = any(f.severity == "reject" for f in findings)
has_review = any(f.severity == "review" for f in findings)

decision = "Reject" if has_reject else ("Needs a person" if has_review else "Approve")
```

This is the **collect-then-decide** pattern: gather all findings first, then derive the
outcome. It eliminates the class of bugs where a flag is set but later overwritten or
missed.

### Complete arithmetic chain

The old code only checked `qty × unit_price == line_total`.
The brief says "the numbers do not add up" covers the whole chain.

```python
# All four checks
if qty and up and lt:
    if abs(lt - qty * up) > tolerance:
        add("review", "Line total ≠ qty × unit price", ...)

if sub and lt:
    if abs(sub - lt) > tolerance:
        add("review", "Subtotal ≠ line total", ...)

if sub and vat and doc.vat_rate == 15:
    expected_vat = (sub * Decimal("0.15")).quantize(Decimal("0.01"), ROUND_HALF_UP)
    if abs(vat - expected_vat) > tolerance:
        add("review", "VAT ≠ 15% of subtotal", ...)

if sub and vat and tot:
    if abs(tot - (sub + vat)) > tolerance:
        add("review", "Total ≠ subtotal + VAT", ...)
```

---

## 7. Arithmetic Safety with Decimal

### The float problem

IEEE 754 floating-point arithmetic can produce results like `1.03 * 480 = 494.40000000000003`.
A price of exactly `494.40` would then be evaluated as `494.40 < 494.40000000000003`
and wrongly classified as within the cap.

```python
# OLD — risky
if doc.unit_price > maxp * 1.03:
    reject = True
```

### The fix

```python
# NEW — exact
_PRICE_TOLERANCE = Decimal("1.03")

max_price = Decimal(str(pr_row["Maximum unit price (BDT)"])).quantize(
    Decimal("0.0001"), rounding=ROUND_HALF_UP
)
offered = Decimal(str(doc.unit_price)).quantize(
    Decimal("0.0001"), rounding=ROUND_HALF_UP
)
if offered > max_price * _PRICE_TOLERANCE:
    add("reject", "Unit price more than 3% above max", ...)
```

`Decimal("1.03")` is exact. `Decimal(str(float_val))` avoids the precision-loss of
`Decimal(float_val)` directly. The arithmetic is exact up to the precision you specify.

---

## 8. Testing Strategy

### Theory: two test tiers

| Tier | Tool | LLM calls | Speed | Purpose |
|---|---|---|---|---|
| Unit tests | `pytest` | 0 | ~0.05 s | Verify rule logic is correct |
| E2E evaluation | `evaluate.py` | 10 (cached) | ~30 s | Verify LLM + full pipeline |

### Offline unit tests

Each test builds a `SupplierDoc` in memory and calls `decide()` directly.

```python
@pytest.mark.parametrize("label,doc,pr_row,expected", [
    ("approve_clean",        _base_doc(),                _pr(), "Approve"),
    ("reject_price_too_high", _base_doc(unit_price=500), _pr(), "Reject"),
    # ... 20 more cases
])
def test_decide(label, doc, pr_row, expected):
    decision, reasons, _ = decide(doc, pr_row)
    assert decision == expected, f"[{label}] got={decision}, reasons={reasons}"
```

`pytest.mark.parametrize` reports each case as a separate test item in the output,
so you see exactly which scenario failed — not just "test_all_decisions FAILED".

### Evaluation caching

```python
# evaluate.py
def _load_cache(pdf):
    p = _cache_path(pdf)
    if p.exists():
        return json.loads(p.read_text())
    return None

def _save_cache(pdf, result):
    _cache_path(pdf).write_text(json.dumps({
        "decision": result["decision"],
        "reasons":  result.get("reasons", []),
    }, indent=2))
```

Each PDF's extraction result is cached as `outputs/supplier-pack-N.json`.
Re-runs skip the API call entirely. Delete the file to re-extract. `--no-cache` flag
forces a fresh call for all files.

---

## 9. Frontend: Streamlit vs Next.js

### The recommendation: **Streamlit**

For this project — a polished BIAI demo that ships fast — **Streamlit is the right
choice**. Here is the full analysis:

#### Streamlit

| Criterion | Assessment |
|---|---|
| **Setup time** | < 30 minutes from zero to running UI |
| **Language** | Pure Python — same language as the whole project |
| **LangGraph integration** | Direct import; call `graph.invoke()` in-process |
| **PDF upload** | `st.file_uploader` built in |
| **Streaming output** | `st.write_stream` works with LangGraph event streams |
| **Polish** | Good with custom CSS injected via `st.markdown` |
| **Deploy** | `streamlit run ui/app.py` — one command |
| **Hosting** | Free on Streamlit Community Cloud (shareable URL) |

**Verdict for this use case:** You can have a live, shareable demo URL in an afternoon.
Evaluators can upload a PDF and watch the pipeline run in real time.

#### Next.js

| Criterion | Assessment |
|---|---|
| **Setup time** | 1–2 days minimum (Next.js app + FastAPI backend + CORS) |
| **Language** | TypeScript frontend + Python backend (two codebases) |
| **LangGraph integration** | Requires a REST or WebSocket API layer |
| **PDF upload** | Custom implementation needed |
| **Streaming** | Server-Sent Events or WebSockets — significant extra work |
| **Polish** | Excellent — pixel-perfect control |
| **Deploy** | Vercel (frontend) + Railway/Fly.io (backend) — two deployments |

**Verdict for this use case:** Great for a production product.
Overkill for a 72-hour demo where the evaluator just wants to see it work.

#### The "both" path (recommended)

Build Streamlit first to nail the demo. Structure the backend so it can trivially
become a FastAPI API later:

```python
# ui/app.py — Streamlit
import streamlit as st
from app.workflow.graph import build_graph

graph = build_graph()

st.title("Supplier Document Checker")
pdf_file = st.file_uploader("Upload a supplier PDF", type="pdf")

if pdf_file and st.button("Analyse"):
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp.write(pdf_file.read())
        tmp_path = tmp.name

    with st.spinner("Running pipeline…"):
        result = graph.invoke({
            "pdf_path": tmp_path, "text": "", "doc": None,
            "ok": True, "fail_field": "", "decision": "",
            "reasons": [], "quotes": [],
        })

    decision = result["decision"]
    colour = {"Approve": "green", "Reject": "red"}.get(decision, "orange")
    st.markdown(f"## Decision: :{colour}[{decision}]")

    for reason, quote in zip(result["reasons"], result["quotes"]):
        with st.expander(reason):
            st.code(quote)
```

That is a complete, working Streamlit UI — about 30 lines.

---

## 10. What I Would Do with More Time

### Short term (hours)

- **Fuzzy quote matching** with `rapidfuzz` — handle OCR noise and Unicode ligatures.
- **Async extraction** — process all 10 PDFs in parallel with `asyncio.gather`.
- **Streamlit UI** with file upload, per-field highlight, and side-by-side PDF viewer.

### Medium term (days)

- **FastAPI backend** so the Streamlit UI becomes a lightweight React/Next.js frontend
  if the company wants a branded product.
- **Human-review queue** — the `human_review` node writes to a database; a reviewer
  dashboard shows the queue with one-click approve/reject.
- **Feedback loop** — reviewer decisions are stored as labelled examples.
  Few-shot prompts are updated automatically when the labelled set grows.

### Long term (weeks)

- **Fine-tune a small model** (Gemma 3 or Qwen 2.5) on validated extractions to remove
  the Groq API dependency for privacy-sensitive deployments.
- **Multi-language support** — many supplier documents in Bangladesh are mixed Bangla/English.
  The extraction prompt and schema would need Bangla-aware field descriptions.
- **Confidence scores** — use log-probabilities or ensemble multiple calls to estimate
  extraction certainty, routing low-confidence fields to review even when structured
  output validates.
