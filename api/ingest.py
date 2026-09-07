"""takes a newly uploaded PDF, saves its bytes permanently in Postgres,
and extracts + embeds its text one page at a time. Does NOT render any
page images here -- that only happens later, on demand (see page_lookup.py).

The permanent copy used to be a local file in data/papers/ -- that folder
gets wiped on every free-tier restart, so Postgres is now the source of
truth, and the PDF is opened straight from memory, never touching disk."""

import os
import io
import re
import pytesseract
import fitz
from PIL import Image
from ragcore import add_text, clear_source_text
from db import save_caption, save_pdf

CAPTION_PATTERN = re.compile(r"^(Fig(?:ure)?\.?|Table)\s+(\d+)\b", re.IGNORECASE | re.MULTILINE)


def extract_captions(page_text):
    captions = []
    for match in CAPTION_PATTERN.finditer(page_text):
        label = match.group(1).lower()
        number = int(match.group(2))
        object_type = "table" if label.startswith("table") else "figure"
        captions.append((object_type, number))
    return captions


def process_pdf(temp_path, original_filename):
    clear_source_text(original_filename)

    with open(temp_path, "rb") as f:
        pdf_bytes = f.read()
    save_pdf(original_filename, pdf_bytes)   # permanent copy now lives in Postgres

    doc = fitz.open(stream=pdf_bytes, filetype="pdf")   # opened straight from memory, no disk round-trip
    print(f"Processing {original_filename} ({len(doc)} pages)...")

    for page_number in range(len(doc)):
        text = doc[page_number].get_text().strip()
        if not text:
            pixmap = doc[page_number].get_pixmap(dpi=150)
            image = Image.open(io.BytesIO(pixmap.tobytes()))
            text = pytesseract.image_to_string(image).strip()
            print(f"[OCR debug] page {page_number + 1}: extracted {len(text)} characters")
            print(f"[OCR debug] preview: {text[:150]!r}")

        if text:
            add_text(text=text, source=original_filename, page=page_number + 1)
            for object_type, number in extract_captions(text):
                save_caption(source=original_filename, object_type=object_type, number=number, page=page_number + 1)

    doc.close()
    print(f"  -> done with {original_filename}")


if __name__ == "__main__":
    BULK_FOLDER = "data/bulk_upload"
    if os.path.isdir(BULK_FOLDER):
        for filename in os.listdir(BULK_FOLDER):
            if filename.lower().endswith(".pdf"):
                process_pdf(os.path.join(BULK_FOLDER, filename), filename)
    else:
        print(f"No {BULK_FOLDER}/ folder found. Nothing to do here -- "
              f"upload PDFs through the API instead (see api.py).")