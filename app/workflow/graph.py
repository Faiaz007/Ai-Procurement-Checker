"""
LangGraph workflow for supplier document checking.

Nodes
-----
extract      – read PDF and call Groq; produces SupplierDoc or None.
verify       – check all quotes appear verbatim in the PDF text.
decide       – apply company rules.
human_review – named terminal node for documents that need a person.
"""
from pathlib import Path
from typing import TypedDict

from langgraph.graph import END, StateGraph

from app.extraction.extract import extract_fields
from app.rules.decide import decide
from app.validation.validate import find_pr_row, load_pr, verify_quotes

# Absolute path to the PR CSV so the graph works regardless of CWD
_PR_PATH = Path(__file__).resolve().parents[2] / "data" / "purchase-request.csv"


class State(TypedDict):
    pdf_path: str
    text: str
    doc: object          # SupplierDoc | None
    ok: bool
    fail_field: str
    decision: str
    reasons: list
    quotes: list


# ── Nodes ─────────────────────────────────────────────────────────────────────

def node_extract(state: State) -> dict:
    text, doc = extract_fields(state["pdf_path"])
    if doc is not None and not doc.item_code:
        # Deterministic fallback: infer the item code from the description/unit
        # when the LLM returns null for the first table column.
        row = find_pr_row(load_pr(_PR_PATH), doc)
        if row is not None:
            doc.item_code = row["Item"]
    return {"text": text, "doc": doc}


def node_verify(state: State) -> dict:
    doc = state["doc"]
    if doc is None:
        # Extraction failed → skip verify, go straight to human review
        return {"ok": False, "fail_field": "extraction_failed"}
    ok, field = verify_quotes(state["text"], doc)
    return {"ok": ok, "fail_field": field or ""}


def node_decide(state: State) -> dict:
    if not state["ok"]:
        reason = (
            "LLM extraction failed after 3 retries"
            if state["fail_field"] == "extraction_failed"
            else f"Quote not found in PDF: {state['fail_field']}"
        )
        return {
            "decision": "Needs a person",
            "reasons": [reason],
            "quotes": ["not found in document"],
        }
    pr = load_pr(_PR_PATH)
    row = find_pr_row(pr, state["doc"])
    decision, reasons, quotes = decide(state["doc"], row)
    return {"decision": decision, "reasons": reasons, "quotes": quotes}


def node_human_review(state: State) -> dict:
    """
    Explicit human-review stop.  In a production system this node would
    create a ticket, send a notification, etc.
    This implementation simply marks the decision and returns.
    """
    decision = state.get("decision", "Needs a person")
    print(
        f"[HUMAN REVIEW REQUIRED] {state['pdf_path']}: "
        + "; ".join(state.get("reasons", []))
    )
    return {"decision": decision}


# ── Routing ───────────────────────────────────────────────────────────────────

def _route_after_decide(state: State) -> str:
    if state["decision"] == "Needs a person":
        return "human_review"
    return END


# ── Graph ─────────────────────────────────────────────────────────────────────

def build_graph():
    g = StateGraph(State)

    g.add_node("extract", node_extract)
    g.add_node("verify", node_verify)
    g.add_node("decide", node_decide)
    g.add_node("human_review", node_human_review)

    g.set_entry_point("extract")
    g.add_edge("extract", "verify")
    g.add_edge("verify", "decide")
    g.add_conditional_edges("decide", _route_after_decide, {
        "human_review": "human_review",
        END: END,
    })
    g.add_edge("human_review", END)

    return g.compile()
