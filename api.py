import os
import tempfile
from fastapi import FastAPI, UploadFile, File
from pydantic import BaseModel
 
from ragcore import ask, list_sources, delete_source
from ingest import process_pdf


app= FastAPI(title= "VisualRAG")
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