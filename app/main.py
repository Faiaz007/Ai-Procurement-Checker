"""
Entry point: run the supplier-document pipeline on all PDFs in data/supplier_pdf/.
"""
import sys
from pathlib import Path

from dotenv import load_dotenv

from app.workflow.graph import build_graph

load_dotenv()

_PDF_DIR = Path(__file__).resolve().parent.parent / "data" / "supplier_pdf"


def main() -> None:
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
            print(f"\n{pdf.name}  →  {res['decision']}")
            for reason, quote in zip(res["reasons"], res["quotes"]):
                print(f"    • {reason}")
                if quote and quote != "not found in document":
                    print(f"      ↳ \"{quote}\"")
        except Exception as exc:  # noqa: BLE001
            print(f"\n{pdf.name}  →  Needs a person  [unhandled error: {exc}]")


if __name__ == "__main__":
    main()
