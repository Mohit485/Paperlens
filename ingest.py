"""takes a newly uploaded PDF, saves a PERMANENT copy, and
extracts + embeds its text one page at a time. Does NOT render any page
images here -- that only happens later, on demand, the first time a
question actually asks about a specific page (see page_lookup.py)."""

import os
import fitz # pdf rendering python library
import shutil
from ragcore import add_text, clear_source_text 
from page_lookup import paper_folder

def process_pdf(temp_path, original_filename):
    """
    temp_path         -- where the uploaded file is currently sitting
                          (a temporary location the caller gave us)
    original_filename -- the name we want to remember this paper by,
                          e.g. "depth_anything.pdf"
    """
    clear_source_text(original_filename)
    # If this exact paper was already ingested before (e.g. you're re-uploading it), clear out its OLD text chunks first. Without this, every re-upload would just add more copies on top of the existing ones 
    os.makedirs(paper_folder, exist_ok=True)
    permanent_path= os.path.join(paper_folder, original_filename)
    shutil.copy(temp_path, permanent_path)

    doc = fitz.open(permanent_path)
    print(f"Processing {original_filename} ({len(doc)} pages)...")

    for page_number in range(len(doc)):
        text= doc[page_number].get_text().strip()
        if text:  # skip essentially blank pages (e.g. a title page with just a logo)
            add_text(text=text, source=original_filename, page=page_number + 1)

    doc.close()
    print(f"  -> done with {original_filename}")

if __name__ == "__main__":
    # This is now a secondary path -- normal usage is uploading through
    # the API/website, which calls process_pdf() directly per file.
    BULK_FOLDER = "data/bulk_upload"
    if os.path.isdir(BULK_FOLDER):
        for filename in os.listdir(BULK_FOLDER):
            if filename.lower().endswith(".pdf"):
                process_pdf(os.path.join(BULK_FOLDER, filename), filename)
    else:
        print(f"No {BULK_FOLDER}/ folder found. Nothing to do here -- "
              f"upload PDFs through the API instead (see api.py).")