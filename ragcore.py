import os
import base64
from dotenv import load_dotenv
from groq import Groq, RateLimitError, APIStatusError
from langchain_chroma import Chroma
from langchain_community.embeddings import HuggingFaceEmbeddings
from PIL import Image
import io
import re
from page_lookup import get_page_imageb64, paper_folder, rendered_pages

load_dotenv() #load_dotenv() reads the .env file sitting in this same folder and copies its values (like GROQ_API_KEY) into the environment

#The Embedding Model 
print("Loading text embedding model...")
embedding_fn= HuggingFaceEmbeddings(model_name= "sentence-transformers/all-MiniLM-L6-v2")


# the Vector Database
#ChromaDB's whole job is: store thousands of these number-lists, and when we hand it a new one, quickly tell us which stored ones are the closest match 
chroma_dir= "chroma_db"
vectorstore= Chroma(
    collection_name= "research_companion",
    embedding_function= embedding_fn,
    persist_directory= chroma_dir #persist_directory means Chroma saves everything to a folder on disk
)

# Groq client
groq_client= Groq(api_key= os.environ.get("GROQ_API_KEY"))
TEXT_MODEL = os.environ.get("GROQ_TEXT_MODEL", "openai/gpt-oss-20b")
VISION_MODEL = os.environ.get("GROQ_VISION_MODEL", "qwen/qwen3.6-27b")


MAX_PAGES_PER_ANSWER = int(os.environ.get("MAX_PAGES_PER_ANSWER", 2))
MAX_IMAGE_DIMENSION = int(os.environ.get("MAX_IMAGE_DIMENSION", 768))
MAX_TEXT_CHUNKS = int(os.environ.get("MAX_TEXT_CHUNKS", 3))
MAX_CHARS_PER_CHUNK = int(os.environ.get("MAX_CHARS_PER_CHUNK", 2000))

#Adding text to Knowledge base
def add_text(text, source, page):
    """Saves one chunk of text into the vector database.
 
    text   -> the actual words (e.g. everything written on one PDF page)
    source -> which file this came from (e.g. "paper1.pdf") -- used for citing later
    page   -> which page number, so we can point back to the exact source"""
    vectorstore.add_texts(
        texts=[text],
        metadatas=[{"type": "text", "source": source, "page": str(page)}],
    )


def shrink_image_for_llm(base64_image, max_dimension=MAX_IMAGE_DIMENSION):
    """
    Takes a base64-encoded image (as stored in Chroma) and returns a
    smaller base64-encoded version, capped at max_dimension pixels on its
    longest side."""
    image_bytes = base64.b64decode(base64_image)
    image = Image.open(io.BytesIO(image_bytes))
    image.thumbnail((max_dimension, max_dimension))
 
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode("utf-8")

# What Question is asking for
"""
    Looks for things like "page 4", "pg 4", "p. 4" in a question and
    returns the page numbers found, e.g. [4] or [3, 5].
    """
def extract_page_no(questions):
    """re.findall() scans the whole string for matches of a PATTERN. Our
    pattern means: the word "page" (or "pg"/"p."), optional punctuation/
    spaces, then one or more digits -- the parentheses mark the digits
    as the part we actually want kept ("captured").
    """
    matches= re.findall(r"\bpage\s*(\d+)|\bpg\.?\s*(\d+)|\bp\.\s*(\d+)", questions, re.IGNORECASE)
    page_numbers= []
    for group in matches:
        for value in group:
            if value:
                page_numbers.append(int(value))
    return page_numbers

def find_matching_source(questions, sources):
    if len(sources)== 1:
        return sources[0]
    question_lower= questions.lower()
    for source in sources:
        name_hint= source.lower().replace(".pdf", "").replace("_", " ").replace("-", " ")
        if name_hint in question_lower:
            return source
    return None

#  LOOKING UP ONE SPECIFIC PAGE'S STORED TEXT (not a similarity search)
def get_page_text(source, page_number):
    """
    Unlike search() below, this doesn't ask "what's similar" -- it asks
    "give me exactly this page," using Chroma's .get() with a metadata
    filter instead of similarity_search(). Two different kinds of
    lookup: exact-match vs. nearest-neighbor.
    """
    results= vectorstore.get(where= {"$and": [{"source": source}, {"page": str(page_number)}]})
    documents= results.get("documents", [])
    return documents[0] if documents else ""
    
# SEMANTIC SEARCH -- the "no specific page mentioned" path
def search(query, k=5):
    return vectorstore.similarity_search(query, k=k)

# MAnage what's stored
def list_sources():
    if not os.path.isdir(paper_folder):
        return []
    return sorted(f for f in os.listdir(paper_folder) if f.lower().endswith(".pdf"))

def delete_source(source):
    """
    Removes everything tied to one paper: its text entries in Chroma,
    any cached page images, and the permanent PDF itself.
    """
    matches= vectorstore.get(where={"source": source})
    matching_ids = matches.get("ids", [])
    if matching_ids:
        vectorstore.delete(ids=matching_ids)
 
    if os.path.isdir(rendered_pages):
        for filename in os.listdir(rendered_pages):
            if filename.startswith(f"{source}_page"):
                os.remove(os.path.join(rendered_pages, filename))
 
    pdf_path = os.path.join(paper_folder, source)
    if os.path.exists(pdf_path):
        os.remove(pdf_path)
def clear_source_text(source):
    matches = vectorstore.get(where={"source": source})
    matching_ids = matches.get("ids", [])
    if matching_ids:
        vectorstore.delete(ids=matching_ids)

# 7. ASKING GROQ TO WRITE THE ANSWER
def _call_groq(model, messages, extra_args= None):
    try:
        response= groq_client.chat.completions.create(
            model= model,
            messages= messages,
            temperature= 0.2,
            max_tokens= 800,
            **(extra_args or {}),
        )

        return response.choices[0].message.content
    except RateLimitError:
        return (
            "Groq's free-tier rate limit was hit for this request (too many "
            "tokens sent in the last minute). Wait about a minute and try "
            "again, or ask a narrower question."
        )
    except APIStatusError as error:
        return f"groq returned an error {error}"

# Path A - source context given (specific paper or page identified)
def ask_about_pages(query, source, page_numbers):
    page_numbers= page_numbers[:MAX_PAGES_PER_ANSWER]
    context_text = "\n\n".join(get_page_text(source, p) for p in page_numbers)
    instructions = (
        "You are a research assistant. Carefully examine the page "
        "image(s) below -- including any tables, figures, charts, or "
        "diagrams. Read column headers, row labels, axis labels, and "
        "legends closely before answering. The extracted text is "
        "supporting context, but text pulled from tables can come out "
        "jumbled or misaligned -- for anything about a table's actual "
        "structure or values, trust what you can see in the image over "
        "the extracted text. If it's a math question, work through it "
        "carefully and explain each step. If the answer isn't there, "
        "say so.\n\n"
        f"Text from these pages:\n{context_text}\n\nQuestion: {query}"
    )
    content = [{"type": "text", "text": instructions}]
    sources_used = []
    for page_num in page_numbers:
        image_b64 = get_page_imageb64(source, page_num)
        if image_b64 is None:
            continue
        small_image_b64 = shrink_image_for_llm(image_b64)
        content.append({
            "type": "image_url",
            "image_url": {"url": f"data:image/png;base64,{small_image_b64}"},
        })
        sources_used.append(f"{source} (page {page_num})")
    if not sources_used:
        return {"answer": f"I couldn't find page(s) {page_numbers} in {source}.", "sources": []}

    # reasoning_effort="default" turns on this model's "thinking mode" --
    # Groq's own docs recommend this specifically for math and complex
    # reasoning, which is exactly what a page-lookup formula question is.
    answer = _call_groq(
        VISION_MODEL,
        [{"role": "user", "content": content}],
        extra_args={"reasoning_effort": "default"},
    )
    return {"answer": answer, "sources": sources_used}


# PATH B -- no specific page identified
def ask_semantic(query, k=5):
    results = search(query, k=k)
 
    text_pieces = []
    sources = []
    for doc in results[:MAX_TEXT_CHUNKS]:
        meta = doc.metadata
        text_pieces.append(doc.page_content[:MAX_CHARS_PER_CHUNK])
        sources.append(f"{meta['source']} (page {meta['page']})")
 
    context_text = "\n\n".join(text_pieces) if text_pieces else "(no matches found)"
    instructions = (
        "You are a research assistant. Answer the question using ONLY the "
        "context below. If the answer isn't there, say you don't know "
        "instead of guessing.\n\n"
        f"Context:\n{context_text}\n\nQuestion: {query}"
    )
 
    answer = _call_groq(TEXT_MODEL, [{"role": "user", "content": instructions}])
    return {"answer": answer, "sources": sources}

# THE MAIN ENTRY POINT -- decides which path above to use
def ask(query, k=5):
    page_numbers = extract_page_no(query)
    sources = list_sources()
    print(f"[ask debug] query={query!r}  page_numbers={page_numbers}  sources={sources}")
    if page_numbers:
        matched_source = find_matching_source(query, sources) 
        print(f"[ask debug] matched_source={matched_source!r}")
        if matched_source:
            return ask_about_pages(query, matched_source, page_numbers)
 
        if len(sources) > 1:
            return {
                "answer": (
                    f"You mentioned page {page_numbers[0]}, but there are "
                    f"{len(sources)} papers stored and I can't tell which "
                    f"one you mean. Try naming it, e.g. \"explain the "
                    f"figure on page {page_numbers[0]} of {sources[0]}\"."
                ),
                "sources": [],
            }
    return ask_semantic(query, k=k)