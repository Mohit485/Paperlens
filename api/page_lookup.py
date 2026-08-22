"""
Turns ONE specific page of an already-saved PDF into an image -- but only
the moment something actually asks for it, not for every page up front.
"""

import os
import base64
import fitz #pyMuPDF

paper_folder= "data/papers"
rendered_pages= "data/rendered_pages"

def get_page_imageb64(source, page_number):
    """
    Returns one page as a base64-encoded PNG string (ready to hand
    straight to Groq's vision model), or None if the paper or page
    doesn't exist.
 
    source      -- the PDF's saved filename, e.g. "depth_anything.pdf"
    page_number -- 1-based, the way a human says it ("page 1" = the
                   FIRST page of the document)
    """
    cache_path= os.path.join(rendered_pages, f"{source}_page{page_number}.png")
    if os .path.exists(cache_path):
        with open(cache_path, "rb") as f:
            return base64.b64encode(f.read()).decode("utf-8")
    pdf_path= os.path.join(paper_folder, source)
    if not os.path.exists(pdf_path):
        return None
    

    doc= fitz.open(pdf_path)
    page_index= page_number-1 # PyMuPDF counts pages from 0; humans count from 1

    if page_index < 0 or page_index >= len(doc):
        doc.close()
        return None
    

    # dpi=150 balances sharpness (readable small text/equations) against
    # file size (keeps the cached PNG and the token cost reasonable).
    pixmap= doc[page_index].get_pixmap(dpi= 150)
    os.makedirs(rendered_pages, exist_ok= True)
    pixmap.save(cache_path)
    doc.close()

    with open(cache_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")
    