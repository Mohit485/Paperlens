import os
import uuid
import json
import base64
import io
from typing import List, Optional, TypedDict, Dict, Any, Annotated
from page_lookup import get_page_imageb64, rendered_pages 
import operator
from db import get_vectorstore, lookup_object_page, list_pdf_sources, delete_pdf, get_checkpointer, reset_vectorstore

from groq import Groq, RateLimitError, APIStatusError
from pydantic import BaseModel, ValidationError
from PIL import Image
from langgraph.graph import StateGraph, START, END
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

# Groq client
groq_client= Groq(api_key= os.environ.get("GROQ_API_KEY"))
TEXT_MODEL = os.environ.get("GROQ_TEXT_MODEL", "openai/gpt-oss-20b")
VISION_MODEL = os.environ.get("GROQ_VISION_MODEL", "qwen/qwen3.6-27b")


MAX_PAGES_PER_ANSWER = int(os.environ.get("MAX_PAGES_PER_ANSWER", 2))
MAX_IMAGE_DIMENSION = int(os.environ.get("MAX_IMAGE_DIMENSION", 768))
MAX_TEXT_CHUNKS = int(os.environ.get("MAX_TEXT_CHUNKS", 3))
MAX_CHARS_PER_CHUNK = int(os.environ.get("MAX_CHARS_PER_CHUNK", 2000))
MAX_CHUNKS_PER_PAPER = int(os.environ.get("MAX_CHUNKS_PER_PAPER", 2))  # from multi_paper.py


def _vectorstore_call(fn):
    """Runs fn() once; if Neon dropped the connection while idle, this
    catches it, rebuilds the vectorstore, and retries exactly once."""
    try:
        return fn()
    except OperationalError:
        print("Stale vectorstore connection -- reconnecting...")
        reset_vectorstore()
        return fn()

#Adding text to Knowledge base
def add_text(text, source, page):
    _vectorstore_call(lambda: get_vectorstore().add_texts(
        texts=[text], metadatas=[{"source": source, "page": page, "type": "text"}], ids=[str(uuid.uuid4())],
    ))


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

# STRUCTURED-OUTPUT INTENT EXTRACTION
class QueryIntent(BaseModel):
    page_numbers: List[int] = []
    paper_names: List[str] = []
    figure_number: Optional[int] = None
    table_number: Optional[int] = None
    is_comparison: bool = False
# strict:true requires every field in `required` (nullable via a
# ["type","null"] union stands in for "optional") -- this is what
# guarantees the model can't return a malformed shape.
_INTENT_SCHEMA = {
    "type": "json_schema",
    "json_schema": {
        "name": "query_intent",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "page_numbers": {
                    "type": "array", "items": {"type": "integer"},
                    "description": "Page numbers explicitly mentioned, e.g. 'page 4' -> [4]. Empty if none.",
                },
                "paper_names": {
                    "type": "array", "items": {"type": "string"},
                    "description": "Any paper name fragments mentioned. Empty if none.",
                },
                "figure_number": {
                    "type": ["integer", "null"],
                    "description": "Figure number mentioned, e.g. 'figure 7' -> 7. null if none.",
                },
                "table_number": {
                    "type": ["integer", "null"],
                    "description": "Table number mentioned, e.g. 'table 3' -> 3. null if none.",
                },
                "is_comparison": {
                    "type": "boolean",
                    "description": "True if the question asks to compare two or more papers.",
                },
            },
            "required": ["page_numbers", "paper_names", "figure_number", "table_number", "is_comparison"],
            "additionalProperties": False,
        },
    },
}

def extract_intent(question, history=None):
    history_block = ""
    if history:
        recent = history[-3:]   # last few turns only -- keeps the prompt small
        history_block = "\n".join(f"Q: {h['question']}\nA: {h['answer']}" for h in recent)

    messages = [
        {"role": "system", "content": (
            "Extract what the user is asking for from their research-paper "
            "question. Only fill in a field if it's actually mentioned -- "
            "don't guess or invent values. If the question refers back to "
            "something earlier ('that figure', 'the other paper'), use the "
            "conversation history to resolve what it means."
        )},
    ]
    if history_block:
        messages.append({"role": "user", "content": f"Conversation so far:\n{history_block}"})
    messages.append({"role": "user", "content": question})

    try:
        response =  groq_client.chat.completions.create(
                                                            model=TEXT_MODEL,
                                                            messages=messages,
                                                            response_format=_INTENT_SCHEMA,
                                                            temperature=0,
                                                            reasoning_effort="low",
                                                        )
        raw = json.loads(response.choices[0].message.content)
        return QueryIntent(**raw)
    except (RateLimitError, APIStatusError, json.JSONDecodeError, ValidationError, TypeError):
        return QueryIntent()

def _names_match(source, name_fragment):
    hint = source.lower().replace(".pdf", "").replace("_", " ").replace("-", " ")
    return hint in name_fragment.lower() or name_fragment.lower() in hint


def _resolve_single_source(intent, sources):
    if len(sources) == 1:
        return sources[0]
    for name in intent.paper_names:
        for source in sources:
            if _names_match(source, name):
                return source
    return None

#  LOOKING UP ONE SPECIFIC PAGE'S STORED TEXT (not a similarity search)
def get_page_text(source, page_number):
    results = _vectorstore_call(lambda: get_vectorstore().similarity_search(
        source, k=1, filter={"source": source, "page": page_number}
    ))
    return results[0].page_content if results else ""

def _delete_all_chunks(source):
    def _do():
        vectorstore = get_vectorstore()
        matches = vectorstore.similarity_search(source, k=1000, filter={"source": source})
        ids = [doc.id for doc in matches if doc.id]
        if ids:
            vectorstore.delete(ids=ids)
    _vectorstore_call(_do)
    
# SEMANTIC SEARCH -- the "no specific page mentioned" path
def search(query, k=5):
    return _vectorstore_call(lambda: get_vectorstore().similarity_search(query, k=k))


# MAnage what's stored
def list_sources():
    return list_pdf_sources() 

def delete_source(source):
    _delete_all_chunks(source)
    if os.path.isdir(rendered_pages):
        for filename in os.listdir(rendered_pages):
            if filename.startswith(f"{source}_page"):
                os.remove(os.path.join(rendered_pages, filename))
    delete_pdf(source)

def clear_source_text(source):
    """Called by ingest.py before re-processing a paper that's already
    been ingested, so a re-upload replaces old chunks instead of
    duplicating them."""
    _delete_all_chunks(source)

# 7. ASKING GROQ TO WRITE THE ANSWER
def _call_groq(model, messages, extra_args=None):
    try:
        response = groq_client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=0.2,
            max_tokens=2000,   # raised from 800 -- a reasoning model needs real headroom beyond its own thinking
            **(extra_args or {}),
        )
        content = response.choices[0].message.content
        if not content:
            if response.choices[0].finish_reason == "length":
                return ("The model ran out of room to answer -- it spent its whole token "
                        "budget reasoning before writing a response. Try a shorter question.")
            return "The model returned an empty response. Try rephrasing the question."
        return content
    except RateLimitError:
        return (...)
    except APIStatusError as error:
        return f"groq returned an error {error}"


# QUERY REWRITE + RERANK
def rewrite_query(query):
    """One cheap Groq call turning a casual question into vocabulary
    closer to how a paper would actually phrase it -- embeddings match
    on wording, not just meaning, so this narrows that gap before the
    similarity search runs."""
    instructions = (
        "Rewrite the following question as a concise search query, using "
        "vocabulary likely to appear in an academic paper. Return ONLY "
        "the rewritten query, nothing else.\n\n"
        f"Question: {query}"
    )
    rewritten = _call_groq(TEXT_MODEL, [{"role": "user", "content": instructions}])
    return rewritten.strip() if rewritten else query


class RerankResult(BaseModel):
    ranked_indices: List[int] = []


_RERANK_SCHEMA = {
    "type": "json_schema",
    "json_schema": {
        "name": "rerank_result",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "ranked_indices": {
                    "type": "array", "items": {"type": "integer"},
                    "description": "Indices of the passages, most to least relevant to the question. Include every index exactly once.",
                },
            },
            "required": ["ranked_indices"],
            "additionalProperties": False,
        },
    },
}


def rerank_chunks(query, documents):
    """Reorders retrieved chunks via a Groq call rather than a local
    cross-encoder -- the deployment target only has memory budget for
    one local model (the embedding model), so a second one isn't an
    option here. Any failure (rate limit, wrong number of indices back)
    just falls back to the original vector-similarity order -- reranking
    is a quality improvement, not something the answer should break over."""
    if len(documents) <= 1:
        return documents

    numbered = "\n\n".join(
        f"[{i}] {doc.page_content[:MAX_CHARS_PER_CHUNK]}" for i, doc in enumerate(documents)
    )
    instructions = (
        "Below are numbered passages retrieved for a question. Order their "
        "indices from most to least relevant to the question.\n\n"
        f"Question: {query}\n\nPassages:\n{numbered}"
    )
    try:
        response = groq_client.chat.completions.create(
            model=TEXT_MODEL,
            messages=[{"role": "user", "content": instructions}],
            response_format=_RERANK_SCHEMA,
            temperature=0,
            reasoning_effort="low",
        )
        raw = json.loads(response.choices[0].message.content)
        ranking = RerankResult(**raw)
        valid = [i for i in ranking.ranked_indices if 0 <= i < len(documents)]
        if len(valid) == len(documents):
            return [documents[i] for i in valid]
    except (RateLimitError, APIStatusError, json.JSONDecodeError, ValidationError, TypeError):
        pass
    return documents


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
    results = rerank_chunks(query, results)
 
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
 
    answer = _call_groq(TEXT_MODEL, [{"role": "user", "content": instructions}], extra_args={"reasoning_effort": "low"})
    return {"answer": answer, "sources": sources}

# Path C -- two or more papers named (merged in from multi_paper.py)
def ask_multi_paper(query, matched_sources):
    """Runs one FILTERED search per named paper, so every named paper
    contributes real, guaranteed context -- not just whichever one
    happens to score higher in a single pooled search."""
    all_text_pieces = []
    all_source_labels = []

    for source in matched_sources:
        results = _vectorstore_call(lambda: get_vectorstore().similarity_search(
            query, k=MAX_CHUNKS_PER_PAPER, filter={"source": source}
        ))
        for doc in results:
            meta = doc.metadata
            all_text_pieces.append(f"[From {source}, page {meta['page']}]\n{doc.page_content[:MAX_CHARS_PER_CHUNK]}")
            all_source_labels.append(f"{source} (page {meta['page']})")

    context_text = "\n\n".join(all_text_pieces) if all_text_pieces else "(no matches found)"
    instructions = (
        "You are a research assistant comparing multiple papers. Answer "
        "the question using ONLY the context below, which is drawn from "
        f"{len(matched_sources)} different papers, each one clearly "
        "labeled. Address each paper explicitly in your answer -- don't "
        "blend them together. If the answer isn't there, say you don't "
        "know instead of guessing.\n\n"
        f"Context:\n{context_text}\n\nQuestion: {query}"
    )

    answer = _call_groq(TEXT_MODEL, [{"role": "user", "content": instructions}], extra_args={"reasoning_effort": "low"})
    return {"answer": answer, "sources": all_source_labels}


# LANGGRAPH ROUTING (step 4)
# =======================================================================
class GraphState(TypedDict, total=False):
    query: str
    k: int
    sources: List[str]
    intent: QueryIntent
    route: str
    matched_source: str
    matched_sources: List[str]
    page_numbers: List[int]
    result: Dict[str, Any]
    history: Annotated[List[Dict], operator.add]


def classify_node(state):
    """The one decision-making node: extract intent, resolve any
    figure/table reference through the caption registry, resolve which
    paper's being asked about, and decide which of the three answer
    paths handles this. Kept as a single node rather than several tiny
    ones -- the resolution logic below is cheap/local; only the intent
    extraction itself is an actual API call worth isolating, and it's
    still the one thing this node does before anything else."""
    query = state["query"]
    sources = state["sources"]
    intent = extract_intent(query, history=state.get("history", []))

    matched_sources = [s for s in sources for name in intent.paper_names if _names_match(s, name)]
    # Both signals required, not just a name-count -- a genuine
    # refinement over the old regex version, which fired on ANY 2+
    # name matches whether or not the question was actually a comparison.
    if intent.is_comparison and len(matched_sources) >= 2:
        return {"intent": intent, "route": "multi_paper", "matched_sources": matched_sources}

    if intent.figure_number is not None or intent.table_number is not None:
        source = _resolve_single_source(intent, sources)
        if source is None and len(sources) > 1:
            return {"intent": intent, "route": "ambiguous", "page_numbers": []}
        if source:
            obj_type = "table" if intent.table_number is not None else "figure"
            number = intent.table_number if intent.table_number is not None else intent.figure_number
            page = lookup_object_page(source, obj_type, number)
            if page is not None:
                return {"intent": intent, "route": "page_lookup", "matched_source": source, "page_numbers": [page]}
            # Registry never caught this caption -- fall through to semantic,
            # same as if this feature didn't exist.

    if intent.page_numbers:
        source = _resolve_single_source(intent, sources)
        if source is None and len(sources) > 1:
            return {"intent": intent, "route": "ambiguous", "page_numbers": intent.page_numbers}
        if source:
            return {"intent": intent, "route": "page_lookup", "matched_source": source, "page_numbers": intent.page_numbers}

    return {"intent": intent, "route": "semantic"}


def ambiguous_node(state):
    page_numbers = state.get("page_numbers") or []
    sources = state["sources"]
    if page_numbers:
        message = (
            f"You mentioned page {page_numbers[0]}, but there are "
            f"{len(sources)} papers stored and I can't tell which "
            f"one you mean. Try naming it, e.g. \"explain the "
            f"figure on page {page_numbers[0]} of {sources[0]}\"."
        )
    else:
        message = f"There are {len(sources)} papers stored and I can't tell which one you mean -- try naming it directly."
    return {"result": {"answer": message, "sources": []}}


def multi_paper_node(state):
    result = ask_multi_paper(state["query"], state["matched_sources"])
    return {"result": result, "history": [{"question": state["query"], "answer": result["answer"]}]}

def page_lookup_node(state):
    result = ask_about_pages(state["query"], state["matched_source"], state["page_numbers"])
    return {"result": result, "history": [{"question": state["query"], "answer": result["answer"]}]}


def semantic_node(state):
    result = ask_semantic(state["query"], k=state.get("k", 5))
    return {"result": result, "history": [{"question": state["query"], "answer": result["answer"]}]}


_graph_builder = StateGraph(GraphState)
_graph_builder.add_node("classify", classify_node)
_graph_builder.add_node("multi_paper", multi_paper_node)
_graph_builder.add_node("page_lookup", page_lookup_node)
_graph_builder.add_node("semantic", semantic_node)
_graph_builder.add_node("ambiguous", ambiguous_node)

_graph_builder.add_edge(START, "classify")
_graph_builder.add_conditional_edges(
    "classify",
    lambda state: state["route"],
    {"multi_paper": "multi_paper", "page_lookup": "page_lookup", "semantic": "semantic", "ambiguous": "ambiguous"},
)
_graph_builder.add_edge("multi_paper", END)
_graph_builder.add_edge("page_lookup", END)
_graph_builder.add_edge("semantic", END)
_graph_builder.add_edge("ambiguous", END)

# compile with the checkpointer attached:
_compiled_graph = None

def _get_compiled_graph():
    global _compiled_graph
    if _compiled_graph is None:
        _compiled_graph = _graph_builder.compile(checkpointer=get_checkpointer())
    return _compiled_graph

# THE MAIN ENTRY POINT -- decides which path above to use
def ask(query, k=5, thread_id="default"):
    """Public entry point -- same signature and return shape api.py and
    the MCP tool already expect. Runs the graph instead of a manual
    if/else chain."""
    config = {"configurable": {"thread_id": thread_id}}
    final_state = _compiled_graph.invoke({"query": query, "k": k, "sources": list_sources()}, config=config,)
    return final_state["result"]


