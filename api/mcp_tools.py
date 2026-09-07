"""Shared MCP tool definitions -- imported by both the HTTP-mounted
server (api.py, for the hosted/remote case) and the stdio server
(mcp_stdio.py, for local Cursor/Cline use). Tools are defined once
here; each entrypoint only differs in how it RUNS this same instance."""

import os
import base64
import tempfile
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
def ingest_paper_from_path(file_path: str) -> dict:
    """
    Adds a PDF given a path on THIS SERVER's own filesystem. Only
    works when client and server share a filesystem -- i.e. a local
    stdio setup, where the client launched this server as a subprocess
    on your own machine. For a remotely-hosted server, this path won't
    resolve -- use ingest_paper_from_bytes instead.
    """
    filename = file_path.replace("\\", "/").split("/")[-1]
    process_pdf(file_path, filename)
    return {"status": "success", "filename": filename}


@mcp.tool
def ingest_paper_from_bytes(filename: str, pdf_base64: str) -> dict:
    """
    Adds a PDF given its raw bytes, base64-encoded. Works identically
    whether this server is local or remote, since it doesn't depend on
    the client and server sharing a filesystem. Use this for a
    remotely-hosted PaperLens instance.
    """
    pdf_bytes = base64.b64decode(pdf_base64)
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        tmp.write(pdf_bytes)
        tmp_path = tmp.name
    try:
        process_pdf(tmp_path, filename)
    finally:
        os.remove(tmp_path)
    return {"status": "success", "filename": filename}