# Backend only -- FastAPI, ChromaDB, the embedding model, Groq, and the
# MCP server mounted at /mcp. This is the heavy container (torch,
# sentence-transformers) -- kept completely separate from the frontend
# container so the frontend never has to carry that weight, and so
# each service can be rebuilt, redeployed, or scaled independently --
# the actual point of splitting services in the first place.

FROM python:3.11-slim

WORKDIR /app

# System-level dependency (not a pip package) for OCR -- see ingest.py.
RUN apt-get update && apt-get install -y tesseract-ocr && rm -rf /var/lib/apt/lists/*

COPY requirements-api.txt .
RUN pip install --no-cache-dir -r requirements-api.txt

# Only the files this container actually needs -- not app.py, not
# streamlit_app.py, not requirements-streamlit.txt. Listing files
# explicitly like this (rather than "COPY . .") keeps the image lean
# and makes it obvious at a glance what this service depends on.
COPY ragcore.py ingest.py page_lookup.py multi_paper.py api.py ./

EXPOSE 8000

CMD ["uvicorn", "api:app", "--host", "0.0.0.0", "--port", "8000"]
