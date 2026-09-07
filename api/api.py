import os
import tempfile
from fastapi import FastAPI, UploadFile, File
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware

from ragcore import ask, list_sources, delete_source
from ingest import process_pdf
from mcp_tools import mcp
from starlette.responses import JSONResponse



mcp_app = mcp.http_app(path="/", transport="streamable-http", stateless_http=True)
app = FastAPI(title="PaperLens", lifespan=mcp_app.lifespan, show_banner=False)


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

class Question(BaseModel):
    question: str
    thread_id: str = "default"


@app.get("/")
def health_check():
    return {"status": "ok", "message": "PaperLens is running"}


@app.post("/ingest")
async def ingest_files(file: UploadFile = File(...)):
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
    return ask(payload.question, thread_id=payload.thread_id)


@app.get("/documents")
def get_documents():
    return {"documents": list_sources()}


@app.delete("/documents/{source}")
def remove_document(source: str):
    delete_source(source)
    return {"status": "success", "message": f"'{source}' and everything derived from it has been removed"}


app.mount("/mcp", mcp_app)