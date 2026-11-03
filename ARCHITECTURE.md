# System Architecture – AI Supplier Document Checker

## 1. High-Level Overview

The system is a **deterministic, step-by-step AI pipeline** built with LangGraph.
It never runs an agent "freely" — every step is a named node with a fixed responsibility.

```mermaid
flowchart TD
    A([📄 Supplier PDF]) --> B[1. Ingestion\nPyMuPDF extracts raw text]
    B --> C[2. Extraction\nGemini 2.0 Flash — structured JSON]
    C -->|SupplierDoc| D[3. Verification\nQuote strings found in PDF?]
    C -->|None — extraction failed| HR([🚨 Human Review Stop])
    D -->|All quotes verified| E[4. Rule Engine\ndecide.py applies company rules]
    D -->|Quote mismatch| HR
    E -->|Approve| AP([✅ Approve])
    E -->|Reject| RJ([❌ Reject])
    E -->|Needs a person| HR
```

---

## 2. LangGraph State Machine

The graph is compiled from a `StateGraph`. Each node receives the full state dict
and returns only the keys it updates — nothing is mutated in place.

```mermaid
stateDiagram-v2
    [*] --> extract
    extract --> verify
    verify --> decide
    decide --> human_review : decision == "Needs a person"
    decide --> [*] : decision == "Approve" or "Reject"
    human_review --> [*]
```

### State schema

```
State
├── pdf_path    : str          – input PDF file path
├── text        : str          – raw extracted text (set by extract)
├── doc         : SupplierDoc? – structured fields (set by extract, None on failure)
├── ok          : bool         – quote verification result (set by verify)
├── fail_field  : str          – first failing field name (set by verify)
├── decision    : str          – Approve / Reject / Needs a person (set by decide)
├── reasons     : list[str]    – human-readable explanations (set by decide)
└── quotes      : list[str]    – supporting evidence strings (set by decide)
```

---

## 3. Component Architecture

```mermaid
flowchart LR
    subgraph ingestion["app/ingestion"]
        PR["pdf_reader.py\nPyMuPDF → plain text"]
    end

    subgraph extraction["app/extraction"]
        SC["schema.py\nPydantic SupplierDoc"]
        EX["extract.py\nGemini client + retries"]
        EX --> SC
    end

    subgraph validation["app/validation"]
        VL["validate.py\nverify_quotes\nvalidate_tin / validate_bin\nload_pr"]
    end

    subgraph rules["app/rules"]
        DC["decide.py\nFinding dataclass\n10 company rules\nDecimal arithmetic"]
    end

    subgraph workflow["app/workflow"]
        GR["graph.py\nStateGraph\n4 nodes + conditional edges"]
    end

    GR --> PR
    GR --> EX
    GR --> VL
    GR --> DC
    PR -->|str| EX
    EX -->|SupplierDoc| VL
    VL -->|bool, field| DC
```

---

## 4. Extraction Sequence

```mermaid
sequenceDiagram
    participant G as graph.py
    participant E as extract.py
    participant P as pdf_reader.py
    participant M as Gemini API

    G->>E: extract_fields(pdf_path)
    E->>P: read_pdf_text(path)
    P-->>E: raw_text (str)
    loop Up to 3 attempts
        E->>M: generate_content(text, schema=SupplierDoc, JSON mode, temp=0)
        alt Success
            M-->>E: JSON conforming to SupplierDoc
            E->>E: model_validate_json(resp.text)
            E-->>G: (text, SupplierDoc)
        else Exception
            M-->>E: error / malformed response
            E->>E: log attempt, retry
        end
    end
    E-->>G: (text, None) — all retries exhausted
```

**Why JSON mode + response_schema?**
Gemini's `response_mime_type="application/json"` forces the model to output valid JSON.
Passing `response_schema=SupplierDoc` additionally constrains the JSON to match the
Pydantic model's shape — field names, types, nullability — so `model_validate_json`
never fails due to a structural mismatch.

---

## 5. Rule Engine Decision Tree

```mermaid
flowchart TD
    START([SupplierDoc + PR row]) --> R1{Unit price?}
    R1 -->|None| REV1[review: price missing]
    R1 -->|above max x 1.03| REJ1[reject: price above 3% cap]
    R1 -->|above max only| REV2[review: price slightly above]
    R1 -->|OK| R2

    R2{Advance percent?} -->|None| REV3[review: advance unclear]
    R2 -->|above 20| REJ2[reject: advance over 20%]
    R2 -->|OK| R3

    R3{Penalty clause?} -->|has_penalty_clause = False| REJ3[reject: no clause]
    R3 -->|None - silent| REV4[review: clause unclear]
    R3 -->|True, rate = None| REV5[review: rate not stated]
    R3 -->|True, rate under 0.5| REJ4[reject: rate too low]
    R3 -->|OK| R4

    R4{TIN valid? BIN valid?} -->|both missing| REJ5[reject: no TIN or BIN]
    R4 -->|one missing| REV6[review: partial ID]
    R4 -->|OK| R5

    R5{Delivery days?} -->|None| REV7[review: unclear]
    R5 -->|above 45| REJ6[reject: too late]
    R5 -->|31 to 45| REV8[review: borderline]
    R5 -->|OK| R6

    R6[Quantity / Payment / VAT\nArithmetic / Validity checks] --> OUTCOME

    OUTCOME{Any reject finding?}
    OUTCOME -->|Yes| REJECT([Reject])
    OUTCOME -->|No, any review finding| REVIEW([Needs a person])
    OUTCOME -->|None| APPROVE([Approve])
```

---

## 6. Full Data Flow

```mermaid
flowchart LR
    PDF[(supplier-pack-N.pdf)] -->|bytes| MuPDF[PyMuPDF]
    MuPDF -->|plain text| Gemini[Gemini 2.0 Flash]
    CSV[(purchase-request.csv)] -->|max_price, qty| RuleEngine[Rule Engine]
    Gemini -->|SupplierDoc JSON| QuoteVerifier[Quote Verifier]
    QuoteVerifier -->|verified doc| RuleEngine
    RuleEngine -->|decision + reasons| Output["results.md / stdout / UI"]
```

---

## 7. Error Handling Architecture

```mermaid
flowchart TD
    A[PDF path] --> B{PDF readable?}
    B -->|No - exception| C[main.py catch: Needs a person]
    B -->|Yes| D{Gemini responds OK?}
    D -->|All 3 retries fail| E[extract returns None: Needs a person]
    D -->|Success| F{Quotes found in PDF text?}
    F -->|Mismatch| G[verify node: Needs a person]
    F -->|OK| H{Rule engine result?}
    H -->|Hard reject rule fires| I[Reject]
    H -->|Uncertain / borderline| J[Needs a person → human_review node]
    H -->|All rules pass| K[Approve]
```

---

## 8. Package Structure

```
Ai_Procuremnet_project/
├── app/
│   ├── __init__.py
│   ├── main.py                  ← CLI entry point
│   ├── extraction/
│   │   ├── schema.py            ← Pydantic SupplierDoc model
│   │   └── extract.py           ← Gemini client, retries, JSON mode
│   ├── ingestion/
│   │   └── pdf_reader.py        ← PyMuPDF wrapper
│   ├── rules/
│   │   └── decide.py            ← business rule engine
│   ├── validation/
│   │   └── validate.py          ← quote verifier, TIN/BIN validators
│   └── workflow/
│       └── graph.py             ← LangGraph StateGraph
├── data/
│   ├── supplier_pdf/            ← 10 sample PDFs
│   ├── purchase-request.csv
│   └── company-rules.md
├── tests/
│   └── test_decisions.py        ← offline parametrised unit tests (36 cases)
├── outputs/                     ← cached JSON extractions (auto-created)
├── evaluate.py                  ← LLM end-to-end evaluation
├── conftest.py                  ← pytest sys.path fix
├── .env / .env.example
├── requirements.txt
├── README.md
├── NOTE.md
├── ARCHITECTURE.md              ← this file
└── IMPLEMENTATION_GUIDE.md
```

---

## 9. Technology Choices Rationale

| Technology | Role | Why chosen |
|---|---|---|
| **LangGraph** | Orchestration | Enforces fixed node order; state is explicit; nodes are auditable |
| **Gemini 2.0 Flash** | Field extraction | Fast, cheap, current model; supports JSON mode + response_schema |
| **google-genai SDK** | Gemini client | Current SDK; `google-generativeai` is deprecated |
| **Pydantic v2** | Schema + validation | `model_validate_json` + `model_json_schema` = zero boilerplate |
| **PyMuPDF** | PDF reading | Fast, no system deps; returns clean per-page text |
| **Decimal** | Price arithmetic | Avoids IEEE 754 rounding errors at the 3% price boundary |
| **pytest + parametrize** | Testing | Each scenario reports independently; completely offline and free |

---

## 10. Deployment Topology

```mermaid
flowchart TD
    subgraph local["Local / Server"]
        CLI["python -m app.main"] --> GR[LangGraph Graph]
        ST["Streamlit UI\nui/app.py"] --> GR
        GR --> GEMINI["Gemini API\nexternal HTTPS"]
        GR --> FS["Local filesystem\nPDFs, outputs/"]
    end

    subgraph ci["CI — GitHub Actions"]
        GH[push trigger] --> PT["pytest — offline only\n36 cases, ~0.05 s"]
    end
```
