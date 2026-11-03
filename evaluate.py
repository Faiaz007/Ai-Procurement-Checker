"""
evaluate.py – LLM end-to-end evaluation script.

Runs the full LangGraph pipeline on all 10 supplier PDFs, prints a
results table, and saves results.md.

Caching
-------
Each extraction result is cached as JSON in outputs/<pdf_stem>.json.
On a re-run, if the cache file exists the LLM call is skipped.
Delete the relevant file (or the whole outputs/ directory) to re-extract.

Usage
-----
    python evaluate.py           # use cache when available
    python evaluate.py --no-cache  # always call the LLM
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import traceback
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(override=True)

# ── Paths ──────────────────────────────────────────────────────────────────────
_ROOT = Path(__file__).resolve().parent
_PDF_DIR = _ROOT / "data" / "supplier_pdf"
_OUTPUTS_DIR = _ROOT / "outputs"
_RESULTS_MD = _ROOT / "results.md"

_OUTPUTS_DIR.mkdir(exist_ok=True)

# ── Ground truth ───────────────────────────────────────────────────────────────
EXPECTED: dict[str, str] = {
    "supplier-pack-01.pdf": "Approve",
    "supplier-pack-02.pdf": "Approve",
    "supplier-pack-03.pdf": "Reject",
    "supplier-pack-04.pdf": "Needs a person",
    "supplier-pack-05.pdf": "Reject",
    "supplier-pack-06.pdf": "Reject",
    "supplier-pack-07.pdf": "Needs a person",
    "supplier-pack-08.pdf": "Reject",
    "supplier-pack-09.pdf": "Needs a person",
    "supplier-pack-10.pdf": "Reject",
}

LABELS = ["Approve", "Reject", "Needs a person"]


def _cache_path(pdf: Path) -> Path:
    return _OUTPUTS_DIR / f"{pdf.stem}.json"


def _load_cache(pdf: Path) -> dict | None:
    p = _cache_path(pdf)
    if p.exists():
        try:
            return json.loads(p.read_text())
        except Exception:
            return None
    return None


def _save_cache(pdf: Path, result: dict) -> None:
    data = {
        "decision": result["decision"],
        "reasons": result.get("reasons", []),
        "quotes": result.get("quotes", []),
    }
    _cache_path(pdf).write_text(json.dumps(data, indent=2, ensure_ascii=False))


def run_evaluation(no_cache: bool = False) -> None:
    # Import here so dotenv is loaded first
    from app.workflow.graph import build_graph

    graph = build_graph()
    initial_state = {
        "pdf_path": "",
        "text": "",
        "doc": None,
        "ok": True,
        "fail_field": "",
        "decision": "",
        "reasons": [],
        "quotes": [],
    }

    rows: list[dict] = []

    pdfs = sorted(_PDF_DIR.glob("*.pdf"))
    print(f"\nEvaluating {len(pdfs)} PDFs …\n")

    for idx, pdf in enumerate(pdfs):
        name = pdf.name
        expected = EXPECTED.get(name, "?")
        cached = None if no_cache else _load_cache(pdf)

        if cached:
            decision = cached["decision"]
            reasons = cached.get("reasons", [])
            source = "(cached)"
        else:
            try:
                state = dict(initial_state, pdf_path=str(pdf))
                res = graph.invoke(state)
                decision = res["decision"]
                reasons = res.get("reasons", [])
                _save_cache(pdf, res)
                source = "(live)"
            except Exception as exc:  # noqa: BLE001
                decision = "Needs a person"
                reasons = [f"Unhandled error: {exc}"]
                traceback.print_exc()
                source = "(error)"

        correct = decision == expected
        rows.append(
            {
                "name": name,
                "expected": expected,
                "got": decision,
                "correct": correct,
                "reasons": reasons,
                "source": source,
            }
        )
        status = "✓" if correct else "✗"
        print(f"  {status} {name:<30} expected={expected:<16} got={decision} {source}")

        # Cooldown to stay within Groq free-tier rate limits (1000 output
        # tokens/minute).  Each extraction emits large JSON with verbatim
        # quotes (~700-800 output tokens), so we must wait ~60s between calls.
        if idx < len(pdfs) - 1:
            time.sleep(65)

    # ── Score ──────────────────────────────────────────────────────────────────
    correct_count = sum(1 for r in rows if r["correct"])
    total = len(rows)
    score = correct_count / total if total else 0
    print(f"\nScore: {correct_count}/{total}  ({score:.0%})\n")

    # ── Confusion matrix ───────────────────────────────────────────────────────
    # rows = actual, cols = predicted
    matrix: dict[str, dict[str, int]] = {
        lbl: {l: 0 for l in LABELS} for lbl in LABELS
    }
    for r in rows:
        actual = r["expected"]
        predicted = r["got"]
        if actual in matrix and predicted in matrix:
            matrix[actual][predicted] += 1

    # ── Save results.md ───────────────────────────────────────────────────────
    lines: list[str] = [
        "# Evaluation Results\n",
        f"**Score: {correct_count}/{total} ({score:.0%})**\n",
        "## Per-document results\n",
        "| File | Expected | Got | ✓/✗ | Reasons |",
        "|------|----------|-----|-----|---------|",
    ]
    for r in rows:
        mark = "✓" if r["correct"] else "✗"
        reason_text = "; ".join(r["reasons"][:2])  # first 2 to keep table readable
        lines.append(
            f"| {r['name']} | {r['expected']} | {r['got']} | {mark} | {reason_text} |"
        )

    lines += [
        "\n## Confusion matrix\n",
        "Rows = actual label, columns = predicted label.\n",
        "| Actual \\ Predicted | " + " | ".join(LABELS) + " |",
        "|---|" + "---|" * len(LABELS),
    ]
    for actual in LABELS:
        row_vals = " | ".join(str(matrix[actual][pred]) for pred in LABELS)
        lines.append(f"| **{actual}** | {row_vals} |")

    lines += [
        "\n## Wrong predictions\n",
    ]
    wrong = [r for r in rows if not r["correct"]]
    if wrong:
        for r in wrong:
            lines.append(f"- **{r['name']}**: expected `{r['expected']}`, got `{r['got']}`")
            for reason in r["reasons"]:
                lines.append(f"  - {reason}")
    else:
        lines.append("_All predictions correct!_")

    _RESULTS_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Results saved to {_RESULTS_MD}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Evaluate supplier-doc pipeline on 10 PDFs.")
    parser.add_argument(
        "--no-cache",
        action="store_true",
        help="Ignore cached extractions and call the LLM for every PDF.",
    )
    args = parser.parse_args()
    run_evaluation(no_cache=args.no_cache)
