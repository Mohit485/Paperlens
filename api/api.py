import os
import tempfile
from fastapi import FastAPI, UploadFile, File
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
from fastmcp import FastMCP
 
from ragcore import ask, list_sources, delete_source
from multi_paper import ask
from ingest import process_pdf

mcp = FastMCP("PaperLens")
 
 
@mcp.tool
def ask_papers(question: str) -> dict:
    """
    Ask a question about the research papers currently in the PaperLens
    knowledge base. Mention a specific page number (e.g. "page 4") if
    the question is about a figure, table, or equation on that page --
    this routes to a vision-capable answer instead of plain text search.
    Returns a dict with 'answer' and 'sources'.
    """
    return ask(question)
 
 
@mcp.tool
def list_papers() -> list:
    """Lists every paper currently stored in the PaperLens knowledge base, by filename."""
    return list_sources()
 
 
@mcp.tool
def ingest_paper(file_path: str) -> dict:
    """
    Adds a PDF to the PaperLens knowledge base, given its full local
    file path. The file must already exist on disk -- this takes a
    path (a plain string), not uploaded file content directly, since
    MCP tool calls are plain JSON, not multipart file uploads the way
    the REST /ingest endpoint below is.
    """
    filename = file_path.replace("\\", "/").split("/")[-1]
    process_pdf(file_path, filename)
    return {"status": "success", "filename": filename}

mcp_app = mcp.http_app(path="/", transport="streamable-http", stateless_http= True)


app= FastAPI(title= "VisualRAG", lifespan= mcp_app.lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

class Question(BaseModel):
    question : str

@app.get("/")
def health_check():
    # A simple endpoint just to confirm the server is alive and reachable.
    return {"status": "ok", "message": "VisualRAG is running"}


@app.post("/ingest")
async def ingest_files(file : UploadFile= File(...)):
    """
    Accepts one or more PDFs in a single request (Streamlit's uploader
    will send multiple files this exact way once we build the UI).
    """
    if not file.filename.lower().endswith(".pdf"):
        return {"filename": file.filename, "status": "skipped (not a PDF)"}
 
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        tmp.write(await file.read())
        tmp_path = tmp.name
 
    process_pdf(tmp_path, file.filename)
    os.remove(tmp_path)
 
    return {"filename": file.filename, "status": "success"}

@app.post("/ask")
def ask_question(payload: Question):
    return ask(payload.question)

@app.get("/documents")
def get_documents():
    return {"documents": list_sources()}

@app.delete("/documents/{source}")
def remove_document(source: str):
    delete_source(source)
    return {"status": "success", "message": f"'{source}' and everything derived from it has been removed"}

app.mount("/mcp", mcp_app)