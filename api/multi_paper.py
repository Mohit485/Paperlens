import os
from ragcore import (
    vectorstore,
    list_sources,
    _call_groq,
    TEXT_MODEL,
    MAX_CHARS_PER_CHUNK,
    ask as ask_single_or_page,
)

MAX_CHUNKS_PER_PAPER = int(os.environ.get("MAX_CHUNKS_PER_PAPER", 2))

 
def find_matching_sources(question, sources):
    """
    Same idea as ragcore.py's find_matching_source(), but collects
    EVERY paper mentioned by name instead of stopping at the first
    match -- that's the actual signal we need here: not "which one
    paper is this about," but "how many distinct papers were named."
    """
    question_lower = question.lower()
    matched = []
    for source in sources:
        name_hint = source.lower().replace(".pdf", "").replace("_", " ").replace("-", " ")
        words = name_hint.split()
        words_present = sum(1 for word in words if word in question_lower)
        # Require ALL words present, or all but one -- tolerates a
        # natural question dropping a generic trailing word (like
        # "paper") while still requiring the DISTINCTIVE part of the
        # name to genuinely be there, so this doesn't just match
        # anything vaguely close.
        if words_present >= max(1, len(words) - 1):
            matched.append(source)
    return matched


def ask_multi_paper(query, matched_sources):
    """
    Runs one FILTERED search per named paper (via Chroma's `filter`
    argument -- restricts similarity_search to chunks whose "source"
    metadata matches exactly one paper), so every named paper
    contributes real, guaranteed context -- not just whichever one
    happens to score higher in a single pooled search.
    """
    all_text_pieces = []
    all_source_labels = []
 
    for source in matched_sources:
        results = vectorstore.similarity_search(query, k=MAX_CHUNKS_PER_PAPER, filter={"source": source})
        for doc in results:
            meta = doc.metadata
            # Labeling each chunk with which paper it came from --
            # without this, the model has no way to tell the two
            # papers' content apart once it's all pasted into one
            # block of context text.
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
 
    # Reusing ragcore.py's _call_groq() directly -- same rate-limit
    # handling, same error handling, nothing duplicated here.
    answer = _call_groq(TEXT_MODEL, [{"role": "user", "content": instructions}])
    return {"answer": answer, "sources": all_source_labels}

def ask(query, k=5):
    """
    The new main entry point -- api.py should import THIS instead of
    ragcore.py's ask(). Checks for the one new case (2+ papers named)
    first; everything else falls straight through to ragcore.py's
    original ask(), completely unchanged.
    """
    sources = list_sources()
    matched_sources = find_matching_sources(query, sources)
 
    # TEMPORARY DEBUG -- same pattern used elsewhere tonight. Delete
    # once you've confirmed this routes correctly.
    print(f"[multi-paper debug] query={query!r}  matched_sources={matched_sources}")
 
    if len(matched_sources) >= 2:
        return ask_multi_paper(query, matched_sources)
 
    return ask_single_or_page(query, k=k)