"""PDF reading helpers."""

from pathlib import Path

import pymupdf


def read_pdf_text(path: Path) -> str:
    with pymupdf.open(str(path)) as doc:
        text = "\n".join(page.get_text() for page in doc)
    return text.strip()