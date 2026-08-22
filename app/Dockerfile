# Frontend only -- just Streamlit and requests. Deliberately carries
# NONE of the backend's heavy dependencies (no torch, no chromadb, no
# sentence-transformers) -- this container's whole job is rendering UI
# and making HTTP calls to the api service, nothing more.

FROM python:3.11-slim

WORKDIR /app

COPY requirements-streamlit.txt .
RUN pip install --no-cache-dir -r requirements-streamlit.txt

COPY app.py .

EXPOSE 8501

CMD ["streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0"]
