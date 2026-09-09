import os

# ragcore.py constructs a Groq client at import time -- a real key isn't
# needed since every test mocks the actual API calls, but *some* string
# has to be present or the import itself crashes (Groq() rejects None).
os.environ.setdefault("GROQ_API_KEY", "test-key-not-real")
os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://test:test@localhost/test")
os.environ.setdefault("COHERE_API_KEY", "test-key-not-real")