# PaperLens

Upload a research paper, ask it questions, get answers grounded in the actual pages — not just extracted text, but the real tables, figures, and equations when that's what the question is actually about.

**Try it:** [your-frontend-url.onrender.com](https://paperlens-frontend.onrender.com/)
**MCP server (remote):** `[https://your-api-url.onrender.com/mcp](https://paperlens-api-ng2t.onrender.com)` — Streamable HTTP, works with any MCP client that supports a remote server.

Built with FastAPI, Streamlit, LangGraph, Postgres + pgvector (hosted on Neon), Groq, and Cohere.

## What it actually does

You upload a PDF. From then on you can ask it almost anything about that paper — or several papers at once — and it figures out on its own how best to answer:

- **Name a figure or table** ("what does figure 4 show") and it goes straight to the right page — a small registry built while ingesting the paper maps captions to pages, so you don't need to know the page number yourself.
- **Name a page directly**, and that page gets rendered as an image on the spot and handed to a vision model that actually looks at it. This matters more than it sounds — text extraction mangles table alignment constantly, and a model that can see the table gets it right where reading the extracted text alone wouldn't.
- **Ask something general**, and it searches the paper's embedded text — rewriting your question into something closer to how the paper itself would phrase it before searching, then reranking what comes back before it answers. Plain similarity search tends to find things that are *close enough*; the extra pass is there to get *actually relevant*.
- **Name two papers**, and it searches each one on its own terms and compares them explicitly, rather than pooling everything into one search where one paper usually just drowns out the other.

It also holds a conversation — ask a follow-up like "what about the next page" or "how does that compare to the other one," and it resolves that against what you actually asked a moment ago, not from scratch every time.

Every question first goes through a small classification step that figures out which of the above it actually is, then routes it down the right path. That routing is a real decision point, not a keyword match — which is most of why figure references, page numbers, and comparisons all just work without you having to phrase things a particular way.

## Where things live

Papers, their embeddings, the figure/table registry, and conversation history all live in Postgres. There's no local database and — beyond a small disposable cache of rendered page images — nothing important sits on local disk. That's deliberate: this runs on infrastructure that doesn't promise a disk survives a restart, so anything that matters lives somewhere that does.

## Project layout

```
api/
  api.py          -- FastAPI app: REST endpoints, plus the MCP server mounted at /mcp
  mcp_tools.py    -- MCP tool definitions, shared by both the HTTP and stdio servers
  mcp_stdio.py    -- local MCP entrypoint, for Cursor / Cline / Claude Desktop
  ragcore.py      -- the actual thinking: intent extraction, routing, retrieval, generation
  ingest.py       -- turns an uploaded PDF into embedded text and a caption registry
  page_lookup.py  -- renders a single page as an image, on demand, cached
  db.py           -- the one place in the whole app that knows how to talk to Postgres
  Dockerfile

frontend/
  app.py          -- the Streamlit UI
  Dockerfile

render.yaml
docker-compose.yml
```

## Running it yourself

```
docker compose up --build
```

You'll need a `.env` at the root with:
```
GROQ_API_KEY=...
COHERE_API_KEY=...
DATABASE_URL=postgresql+psycopg://...
LANGGRAPH_STRICT_MSGPACK=true
```

Then open `http://localhost:8501`.

## Using it from Cursor, Cline, or Claude Desktop

Point your MCP client straight at `mcp_stdio.py` — it talks over stdio, so nothing else needs to be running first:

```json
{
  "mcpServers": {
    "paperlens": {
      "command": "path/to/venv/Scripts/python.exe",
      "args": ["path/to/api/mcp_stdio.py"]
    }
  }
}
```

From there you can just say "ingest the PDF at [path] using paperlens" and start asking about it — no need to touch the web UI at all if you don't want to.

## Limitations, as they actually stand

- The hosted MCP endpoint doesn't enforce any authentication right now. Fine for personal use, not something to hand the link out widely just yet.
- Free-tier hosting means both services go to sleep after around 15 minutes idle — the first request after that takes 30-60 seconds while things wake back up.
- Retrieval is dense/semantic, which is genuinely weak at an exact quote or keyword lookup that isn't tied to a named figure or table — it finds what's conceptually related, not necessarily an exact string match.
- Embeddings run through Cohere's trial tier, capped around 1,000 calls a month. Comfortable for personal use, not built for real traffic.
- OCR quality is only as good as what Tesseract can make of a given scan — a rough scan produces rough extracted text, and nothing downstream can fully fix that.

## What's not built yet

- Authentication on the API and MCP endpoints.
- Real tracing on every model call, not just log lines.
- A test suite and CI around the routing logic specifically — that's where the actual complexity lives.
