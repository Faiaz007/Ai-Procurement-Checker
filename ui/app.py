"""
Streamlit UI for the AI Supplier Document Checker.

Run with:
    streamlit run ui/app.py
"""
from __future__ import annotations

import sys
import tempfile
import time
from pathlib import Path

# Ensure project root is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import streamlit as st
from dotenv import load_dotenv

load_dotenv(override=True)

# ── Page config ────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Supplier Document Checker",
    page_icon="📋",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Custom CSS ─────────────────────────────────────────────────────────────────
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');

    html, body, [class*="css"] {
        font-family: 'Inter', sans-serif;
    }

    .main { background: #0f1117; }

    /* Decision badge */
    .badge {
        display: inline-block;
        padding: 0.4rem 1.2rem;
        border-radius: 999px;
        font-weight: 700;
        font-size: 1.1rem;
        letter-spacing: 0.03em;
    }
    .badge-approve  { background: #14532d; color: #4ade80; border: 1px solid #16a34a; }
    .badge-reject   { background: #450a0a; color: #f87171; border: 1px solid #dc2626; }
    .badge-review   { background: #451a03; color: #fb923c; border: 1px solid #ea580c; }

    /* Finding card */
    .finding-card {
        background: #1e2433;
        border-left: 3px solid #3b82f6;
        border-radius: 6px;
        padding: 0.75rem 1rem;
        margin-bottom: 0.5rem;
    }
    .finding-card.reject-card  { border-left-color: #ef4444; }
    .finding-card.review-card  { border-left-color: #f97316; }
    .finding-card.approve-card { border-left-color: #22c55e; }

    .quote-text {
        font-family: 'Courier New', monospace;
        font-size: 0.8rem;
        color: #94a3b8;
        background: #111827;
        padding: 0.4rem 0.6rem;
        border-radius: 4px;
        margin-top: 0.4rem;
        white-space: pre-wrap;
        word-break: break-word;
    }

    /* Step tracker */
    .step { display: flex; align-items: center; gap: 0.5rem; margin: 0.3rem 0; }
    .step-icon { font-size: 1rem; }
    .step-done { color: #4ade80; }
    .step-spin { color: #60a5fa; }
    .step-wait { color: #475569; }

    /* Field table */
    .field-row { display: flex; border-bottom: 1px solid #1e293b; padding: 0.4rem 0; }
    .field-name { flex: 0 0 200px; color: #64748b; font-size: 0.82rem; }
    .field-val  { color: #e2e8f0; font-size: 0.85rem; font-weight: 500; }

    div[data-testid="stMetricValue"] { font-size: 2rem !important; }
</style>
""", unsafe_allow_html=True)


# ── Helpers ────────────────────────────────────────────────────────────────────

def _decision_badge(decision: str) -> str:
    cls = {
        "Approve": "approve",
        "Reject":  "reject",
        "Needs a person": "review",
    }.get(decision, "review")
    icon = {"approve": "✅", "reject": "❌", "review": "🚨"}.get(cls, "❓")
    return f'<span class="badge badge-{cls}">{icon} {decision}</span>'


def _finding_card(reason: str, quote: str, decision: str) -> str:
    cls = {
        "Approve": "approve-card",
        "Reject":  "reject-card",
        "Needs a person": "review-card",
    }.get(decision, "review-card")
    quote_html = (
        f'<div class="quote-text">"{quote}"</div>'
        if quote and quote != "not found in document"
        else ""
    )
    return (
        f'<div class="finding-card {cls}">'
        f"  <strong>{reason}</strong>"
        f"  {quote_html}"
        f"</div>"
    )


def _field_row(name: str, value) -> str:
    display = str(value) if value is not None else '<span style="color:#475569">—</span>'
    return (
        f'<div class="field-row">'
        f'  <span class="field-name">{name}</span>'
        f'  <span class="field-val">{display}</span>'
        f"</div>"
    )


# ── Sidebar ────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## ⚙️ Settings")
    st.markdown("---")
    show_raw = st.checkbox("Show raw PDF text", value=False)
    show_fields = st.checkbox("Show extracted fields", value=True)
    show_json = st.checkbox("Show extracted JSON", value=False)
    st.markdown("---")
    st.markdown("### About")
    st.markdown(
        "AI pipeline built with **LangGraph** + **Groq**.\n\n"
        "Steps: Extract → Verify → Rules → Decision"
    )
    st.markdown("---")
    st.markdown("### Pipeline nodes")
    for step in ["📄 Ingestion (PyMuPDF)", "🤖 Extraction (Groq)", "🔍 Verification", "⚖️ Rule Engine", "🚨 Human Review (if needed)"]:
        st.markdown(f"- {step}")


# ── Main ───────────────────────────────────────────────────────────────────────
st.markdown("# 📋 Supplier Document Checker")
st.markdown("Upload a supplier quotation PDF and the AI pipeline will check it against company rules.")
st.markdown("---")

col_upload, col_info = st.columns([1, 1])

with col_upload:
    uploaded_files = st.file_uploader(
        "Drop supplier PDF(s) here",
        type=["pdf"],
        accept_multiple_files=True,
        help="Upload one or more supplier-pack-N.pdf files",
    )

with col_info:
    st.markdown("""
    **What the pipeline checks:**
    - 💰 Unit price vs. purchase-request cap (±3%)
    - 💳 Advance payment ≤ 20%
    - ⚠️ Late-delivery penalty clause ≥ 0.5%/week
    - 🪪 TIN (12-digit) or BIN (9-digit)
    - 📅 Delivery ≤ 45 days
    - 📦 Quantity within 5% of PR
    - 🧾 VAT shown separately at 15%
    - ➕ Full arithmetic chain
    - ⏳ Quotation validity ≥ 30 days
    """)

st.markdown("---")

if uploaded_files:
    for uploaded in uploaded_files:
        # Save to temp file
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp.write(uploaded.read())
            tmp_path = tmp.name

        st.markdown(f"### Running pipeline on `{uploaded.name}` …")
        step_placeholder = st.empty()

        def show_steps(done: list[str], current: str, waiting: list[str]):
            html = ""
            for s in done:
                html += f'<div class="step step-done">✅ {s}</div>'
            html += f'<div class="step step-spin">⏳ {current}</div>'
            for s in waiting:
                html += f'<div class="step step-wait">◦ {s}</div>'
            step_placeholder.markdown(html, unsafe_allow_html=True)

        all_steps = ["Ingestion", "Extraction (Groq)", "Verification", "Rule Engine"]

        try:
            # Build graph lazily (cached after first load)
            @st.cache_resource
            def get_graph():
                from app.workflow.graph import build_graph
                return build_graph()

            graph = get_graph()

            show_steps([], "Ingestion", ["Extraction (Groq)", "Verification", "Rule Engine"])
            time.sleep(0.3)

            show_steps(["Ingestion"], "Extraction (Groq)", ["Verification", "Rule Engine"])

            t0 = time.time()
            result = graph.invoke({
                "pdf_path": tmp_path,
                "text": "",
                "doc": None,
                "ok": True,
                "fail_field": "",
                "decision": "",
                "reasons": [],
                "quotes": [],
            })
            elapsed = time.time() - t0

            show_steps(["Ingestion", "Extraction (Groq)", "Verification", "Rule Engine"], "Done ✓", [])
            time.sleep(0.2)
            step_placeholder.empty()

        except Exception as exc:
            step_placeholder.empty()
            st.error(f"Pipeline error: {exc}")
            st.stop()

        decision = result["decision"]
        reasons  = result.get("reasons", [])
        quotes   = result.get("quotes", [])
        doc      = result.get("doc")

        # ── Decision banner ────────────────────────────────────────────────────────
        st.markdown("---")
        st.markdown(f"## Decision: {_decision_badge(decision)}", unsafe_allow_html=True)
        st.caption(f"Pipeline completed in {elapsed:.1f}s")
        st.markdown("")

        # ── Metrics ───────────────────────────────────────────────────────────────
        mc1, mc2, mc3 = st.columns(3)
        mc1.metric("Total findings", len(reasons))
        mc2.metric("Reject findings", sum(1 for r in reasons if "Reject" in decision or "reject" in r.lower()))
        mc3.metric("Review flags", sum(1 for r in reasons if "review" in r.lower() or "unclear" in r.lower() or "missing" in r.lower()))

        st.markdown("---")

        # ── Findings ──────────────────────────────────────────────────────────────
        left, right = st.columns([1.1, 1])

        with left:
            st.markdown("### 📋 Findings")
            if reasons:
                cards_html = ""
                for reason, quote in zip(reasons, quotes):
                    cards_html += _finding_card(reason, quote, decision)
                st.markdown(cards_html, unsafe_allow_html=True)
            else:
                st.success("No issues found — all rules passed.")

        # ── Extracted fields ──────────────────────────────────────────────────────
        with right:
            if show_fields and doc:
                st.markdown("### 🔍 Extracted Fields")
                fields = [
                    ("Supplier name",          doc.supplier_name),
                    ("Item code",              doc.item_code),
                    ("Description",            doc.description),
                    ("Quantity",               doc.quantity),
                    ("Unit",                   doc.unit),
                    ("Unit price (BDT)",       doc.unit_price),
                    ("Line total (BDT)",       doc.line_total),
                    ("Subtotal (BDT)",         doc.subtotal),
                    ("VAT amount (BDT)",       doc.vat_amount),
                    ("VAT shown separately",   doc.vat_shown_separately),
                    ("VAT rate (%)",           doc.vat_rate),
                    ("Total (BDT)",            doc.total),
                    ("TIN",                    doc.tin),
                    ("BIN",                    doc.bin),
                    ("Advance (%)",            doc.advance_percent),
                    ("Payment days",           doc.payment_days_after_delivery),
                    ("Delivery value",         doc.delivery_value),
                    ("Delivery unit",          doc.delivery_unit),
                    ("Has penalty clause",     doc.has_penalty_clause),
                    ("Penalty rate (%/week)",  doc.penalty_percent_per_week),
                    ("Validity (days)",        doc.validity_days),
                ]
                rows_html = "".join(_field_row(n, v) for n, v in fields)
                st.markdown(rows_html, unsafe_allow_html=True)
                if show_json:
                    st.markdown("### 🧾 Extracted JSON")
                    st.json(doc.model_dump())
            elif not doc:
                st.warning("Field extraction failed – document sent to human review.")

        # ── Raw text ──────────────────────────────────────────────────────────────
        if show_raw:
            with st.expander("📄 Raw PDF text"):
                st.code(result.get("text", ""), language=None)

else:
    # Empty state
    st.markdown("""
    <div style="text-align:center; padding: 3rem; color: #475569;">
        <div style="font-size: 4rem; margin-bottom: 1rem;">📂</div>
        <div style="font-size: 1.1rem;">Upload a supplier PDF above to get started</div>
        <div style="font-size: 0.9rem; margin-top: 0.5rem;">
            Try any of the 10 sample packs in <code>data/supplier_pdf/</code>
        </div>
    </div>
    """, unsafe_allow_html=True)
