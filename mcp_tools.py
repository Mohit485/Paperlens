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
def ask_papers(question: str, thread_id: str = "default") -> dict:
    """Ask a question about the stored papers. thread_id keeps a
    conversation going across calls -- omit it for a one-off question."""
    return ask(question, thread_id=thread_id)


@mcp.tool
def list_papers() -> list:
    """Lists every paper currently stored, by filename."""
    return list_sources()


@mcp.tool
def ingest_paper(
    file_path: str = None, 
    filename: str = None, 
    pdf_base64: str = None,
    url: str = None
) -> dict:
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
            return {"status": "success", "filename": target_name, "source": "url"}
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    # Strategy 2: Ingest via Local File Path (stdio local mode)
    elif file_path:
        if not os.path.exists(file_path):
            return {"status": "error", "message": f"Local path '{file_path}' does not exist on server."}
        
        target_name = filename or os.path.basename(file_path.replace("\\", "/"))
        process_pdf(file_path, target_name)
        return {"status": "success", "filename": target_name, "source": "file_path"}

    # Strategy 3: Ingest via Base64 Payload (remote HTTP mode)
    elif pdf_base64:
        if not filename:
            return {"status": "error", "message": "'filename' is required when passing 'pdf_base64'."}

        pdf_bytes = base64.b64decode(pdf_base64)
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            tmp.write(pdf_bytes)
            tmp_path = tmp.name

        try:
            process_pdf(tmp_path, filename)
            return {"status": "success", "filename": filename, "source": "base64"}
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    return {"status": "error", "message": "Provide either 'file_path', 'url', or ('filename' + 'pdf_base64')."}


@mcp.tool
def delete_paper(filename: str) -> dict:
    """Removes a paper and its associated vectors/data completely from PaperLens by filename."""
    try:
        delete_source(filename)
        return {"status": "success", "message": f"Deleted '{filename}' successfully."}
    except Exception as e:
        return {"status": "error", "message": str(e)}