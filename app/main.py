"""
Entry point: run the supplier-document pipeline on all PDFs in data/supplier_pdf/.
"""
import argparse
import json
import sys
from pathlib import Path

from dotenv import load_dotenv

from app.workflow.graph import build_graph

load_dotenv(override=True)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

_PDF_DIR = Path(__file__).resolve().parent.parent / "data" / "supplier_pdf"


def main(json_output: bool = False) -> None:
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

    pdfs = sorted(_PDF_DIR.glob("*.pdf"))
    if not pdfs:
        print(f"No PDFs found in {_PDF_DIR}", file=sys.stderr)
        return

    for pdf in pdfs:
        try:
            state = dict(initial_state, pdf_path=str(pdf))
            res = graph.invoke(state)
            doc = res.get("doc")
            if json_output:
                payload = {
                    "file": pdf.name,
                    "extraction": doc.model_dump() if doc is not None else None,
                    "decision": res["decision"],
                    "reasons": res["reasons"],
                    "quotes": res["quotes"],
                }
                print(json.dumps(payload, indent=2, ensure_ascii=False))
                continue
            print(f"\n{pdf.name}  →  {res['decision']}")
            for reason, quote in zip(res["reasons"], res["quotes"]):
                print(f"    • {reason}")
                if quote and quote != "not found in document":
                    print(f"      ↳ \"{quote}\"")
        except Exception as exc:  # noqa: BLE001
            print(f"\n{pdf.name}  →  Needs a person  [unhandled error: {exc}]")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the supplier-document pipeline.")
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print the extracted fields and decision as formatted JSON.",
    )
    main(json_output=parser.parse_args().json)
