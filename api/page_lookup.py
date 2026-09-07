"""
Turns ONE specific page of an already-saved PDF into an image -- but only
the moment something actually asks for it, not for every page up front.

The original PDF lives in Postgres now (db.py), not local disk -- that's
what survives a free-tier restart. The rendered PNG cache below is still
local disk, on purpose: it's pure derived data, cheap to regenerate, so
losing it on a restart just costs one extra render on the next request,
not a correctness problem.
"""

import os
import base64
import pymupdf as fitz
from db import get_pdf_bytes

rendered_pages = "data/rendered_pages"


def get_page_imageb64(source, page_number):
    cache_path = os.path.join(rendered_pages, f"{source}_page{page_number}.png")
    if os.path.exists(cache_path):
        with open(cache_path, "rb") as f:
            return base64.b64encode(f.read()).decode("utf-8")

    pdf_bytes = get_pdf_bytes(source)
    if pdf_bytes is None:
        return None

    doc = fitz.open(stream=pdf_bytes, filetype="pdf")   # straight from Postgres bytes, no local file needed
    page_index = page_number - 1

    if page_index < 0 or page_index >= len(doc):
        doc.close()
        return None

    pixmap = doc[page_index].get_pixmap(dpi=150)
    os.makedirs(rendered_pages, exist_ok=True)
    pixmap.save(cache_path)
    doc.close()

    with open(cache_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")