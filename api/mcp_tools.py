"""Shared MCP tool definitions -- imported by both the HTTP-mounted
server (api.py, for the hosted/remote case) and the stdio server
(mcp_stdio.py, for local Cursor/Cline use). Tools are defined once
here; each entrypoint only differs in how it RUNS this same instance."""

import os
import base64
import tempfile
import urllib.request
from fastmcp import FastMCP
from ragcore import ask, list_sources, delete_source
from ingest import process_pdf

mcp = FastMCP("PaperLens")


@mcp.tool
def ask_papers(question: str, thread_id: str = "default") -> str:
    """Ask a question about the stored papers. thread_id keeps a
    conversation going across calls -- omit it for a one-off question."""
    res = ask(question, thread_id=thread_id)
    return str(res.get("answer", res) if isinstance(res, dict) else res)


@mcp.tool
def list_papers() -> str:
    """Lists every paper currently stored, by filename."""
    papers = list_sources()
    if not papers:
        return "No papers currently stored in the database."
    return "Stored Papers:\n" + "\n".join(f"- {p}" for p in papers)


@mcp.tool
def ingest_paper(
    file_path: str = None, 
    filename: str = None, 
    pdf_base64: str = None,
    url: str = None
) -> str:
    """
    Ingests a PDF paper into PaperLens using one of three strategies:
    1. 'file_path': Local file path (use ONLY when running MCP server locally on stdio).
    2. 'pdf_base64' + 'filename': Raw PDF encoded as base64 (use for remote HTTP connections with local files).
    3. 'url': Public PDF URL e.g. ArXiv (works on both remote HTTP and local stdio).
    """
    # Strategy 1: Ingest via Public URL
    if url:
        target_name = filename or url.split("/")[-1] or "downloaded_paper.pdf"
        if not target_name.lower().endswith(".pdf"):
            target_name += ".pdf"

        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            tmp_path = tmp.name

        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req) as response, open(tmp_path, 'wb') as out_file:
                out_file.write(response.read())
            
            process_pdf(tmp_path, target_name)
            return f"✅ Successfully downloaded and ingested '{target_name}' from URL into Neon Postgres."
        except Exception as e:
            return f"❌ Failed to download or process PDF from URL: {str(e)}"
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    # Strategy 2: Ingest via Local File Path (stdio local mode)
    elif file_path:
        if not os.path.exists(file_path):
            return f"❌ Error: Local file path '{file_path}' does not exist on the server."
        
        target_name = filename or os.path.basename(file_path.replace("\\", "/"))
        try:
            process_pdf(file_path, target_name)
            return f"✅ Successfully ingested '{target_name}' from local filesystem path."
        except Exception as e:
            return f"❌ Ingestion error: {str(e)}"

    # Strategy 3: Ingest via Base64 Payload (remote HTTP mode)
    elif pdf_base64:
        if not filename:
            return "❌ Error: 'filename' is required when passing 'pdf_base64'."

        try:
            pdf_bytes = base64.b64decode(pdf_base64)
            with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
                tmp.write(pdf_bytes)
                tmp_path = tmp.name

            process_pdf(tmp_path, filename)
            return f"✅ Successfully ingested '{filename}' from Base64 payload into Neon Postgres."
        except Exception as e:
            return f"❌ Base64 ingestion error: {str(e)}"
        finally:
            if 'tmp_path' in locals() and os.path.exists(tmp_path):
                os.remove(tmp_path)

    return "❌ Error: You must provide either 'file_path', 'url', or ('filename' + 'pdf_base64')."


@mcp.tool
def delete_paper(filename: str) -> str:
    """Removes a paper and its associated vectors/data completely from PaperLens by filename."""
    try:
        delete_source(filename)
        return f"🗑️ Successfully deleted '{filename}' and purged all associated vectors from Neon Postgres."
    except Exception as e:
        return f"❌ Deletion error: {str(e)}"