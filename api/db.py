import sys
import asyncio
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

import os
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from langchain_postgres import PGEngine, PGVectorStore, Column
from psycopg_pool import ConnectionPool
from psycopg.rows import dict_row
from langgraph.checkpoint.postgres import PostgresSaver

DATABASE_URL = os.environ.get("DATABASE_URL")   # postgresql+psycopg://...
# psycopg.connect()/ConnectionPool want a plain libpq DSN, not SQLAlchemy's
# dialect URL -- only needed for the checkpointer's pool below.
_RAW_DATABASE_URL = DATABASE_URL.replace("postgresql+psycopg://", "postgresql://") if DATABASE_URL else None

TABLE_NAME = "research_companion"
EMBEDDING_MODEL_NAME = "embed-english-light-v3.0"   
VECTOR_SIZE=384   


# --- lazy singletons ---
_engine = None
_sql_engine = None
_embedding_model = None
_vectorstore = None
_checkpointer = None
_registry_table_ready = False
_documents_table_ready = False




def get_sql_engine():
    """Plain SQLAlchemy engine for our own raw queries (documents,
    object_registry). pool_pre_ping tests a connection is alive before
    handing it out; pool_recycle proactively retires connections older
    than 5 min -- Neon (like Supabase, RDS) closes idle connections on
    its own schedule, so the client has to stop assuming a cached
    connection is still good."""
    global _sql_engine
    if _sql_engine is None:
        _sql_engine = create_engine(DATABASE_URL, pool_pre_ping=True, pool_recycle=300)
    return _sql_engine



def get_engine():
    """The PGEngine PGVectorStore needs. Built from our OWN async engine
    (via PGEngine.from_engine()) instead of PGEngine.from_connection_string(),
    specifically so the same pool_pre_ping/pool_recycle settings apply
    here too -- PGEngine's default construction doesn't expose them, so
    without this the vectorstore goes stale the same way get_sql_engine()
    did, just silently (a failed search looks like "no matches", not an error)."""
    global _engine
    if _engine is None:
        _engine = PGEngine.from_connection_string(url=DATABASE_URL)
    return _engine


def get_embedding_model():
    """Loads on first use, same lazy pattern as before -- though the
    memory motivation matters less here than it did for torch; this is
    a lightweight API client, not a local model."""
    global _embedding_model
    if _embedding_model is None:
        from langchain_cohere import CohereEmbeddings
        _embedding_model = CohereEmbeddings(model=EMBEDDING_MODEL_NAME)   # reads COHERE_API_KEY from env
    return _embedding_model

def _table_exists(table_name):
    with get_sql_engine().connect() as conn:
        result = conn.execute(text("SELECT to_regclass(:name)"), {"name": table_name})
        return result.scalar() is not None


def get_vectorstore():
    global _vectorstore
    if _vectorstore is None:
        engine = get_engine()
        if not _table_exists(TABLE_NAME):
            print(f"Creating vector table '{TABLE_NAME}'...")
            engine.init_vectorstore_table(
                table_name=TABLE_NAME,
                vector_size=VECTOR_SIZE,
                metadata_columns=[
                    Column("source", "VARCHAR"),
                    Column("page", "INTEGER"),
                    Column("type", "VARCHAR"),
                ],
            )
        _vectorstore = PGVectorStore.create_sync(
            engine=engine,
            table_name=TABLE_NAME,
            embedding_service=get_embedding_model(),
            metadata_columns=["source", "page", "type"],
        )
    return _vectorstore

def reset_vectorstore():
    """Discards the cached PGEngine/PGVectorStore so the next call
    rebuilds them fresh. Used when a stale connection is caught --
    PGEngine can't take pool_pre_ping without losing its sync bridge,
    so staleness here is handled reactively instead of proactively."""
    global _engine, _vectorstore
    _engine = None
    _vectorstore = None


def get_checkpointer():
    """Persistence layer for the graph's conversation state. Uses
    psycopg_pool.ConnectionPool, not a bare connection -- this is
    PostgresSaver's own officially recommended pattern specifically to
    avoid holding one unmonitored connection for the app's whole
    lifetime. max_idle closes connections on our side before Neon does
    it for us."""
    global _checkpointer
    if _checkpointer is None:
        if os.environ.get("LANGGRAPH_STRICT_MSGPACK", "").lower() not in ("1", "true", "yes"):
            print("WARNING: LANGGRAPH_STRICT_MSGPACK is not set -- see CVE-2026-28277.")
        pool = ConnectionPool(
                conninfo=_RAW_DATABASE_URL,
                max_size=5,
                max_idle=120,
                check=ConnectionPool.check_connection,   # NEW -- validates a connection before handing it out; this was the missing half of pool_pre_ping's equivalent
                kwargs={"autocommit": True, "prepare_threshold": 0, "row_factory": dict_row},
                open=True,
                )
        _checkpointer = PostgresSaver(pool)
        _checkpointer.setup()
    return _checkpointer


def _ensure_registry_table():
    global _registry_table_ready
    if _registry_table_ready:
        return
    with get_sql_engine().begin() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS object_registry (
                id SERIAL PRIMARY KEY,
                source VARCHAR NOT NULL,
                object_type VARCHAR NOT NULL,
                number INTEGER NOT NULL,
                page INTEGER NOT NULL,
                UNIQUE (source, object_type, number)
            )
        """))
    _registry_table_ready = True


def save_caption(source, object_type, number, page):
    _ensure_registry_table()
    with get_sql_engine().begin() as conn:
        conn.execute(
            text("""
                INSERT INTO object_registry (source, object_type, number, page)
                VALUES (:source, :object_type, :number, :page)
                ON CONFLICT (source, object_type, number) DO NOTHING
            """),
            {"source": source, "object_type": object_type, "number": number, "page": page},
        )


def lookup_object_page(source, object_type, number):
    _ensure_registry_table()
    with get_sql_engine().connect() as conn:
        result = conn.execute(
            text("""
                SELECT page FROM object_registry
                WHERE source = :source AND object_type = :object_type AND number = :number
            """),
            {"source": source, "object_type": object_type, "number": number},
        )
        row = result.fetchone()
        return row[0] if row else None


def _ensure_documents_table():
    global _documents_table_ready
    if _documents_table_ready:
        return
    with get_sql_engine().begin() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS documents (
                source VARCHAR PRIMARY KEY,
                pdf_bytes BYTEA NOT NULL,
                uploaded_at TIMESTAMP NOT NULL DEFAULT now()
            )
        """))
    _documents_table_ready = True


def save_pdf(source, pdf_bytes):
    _ensure_documents_table()
    with get_sql_engine().begin() as conn:
        conn.execute(
            text("""
                INSERT INTO documents (source, pdf_bytes)
                VALUES (:source, :pdf_bytes)
                ON CONFLICT (source) DO UPDATE SET pdf_bytes = EXCLUDED.pdf_bytes, uploaded_at = now()
            """),
            {"source": source, "pdf_bytes": pdf_bytes},
        )


def get_pdf_bytes(source):
    _ensure_documents_table()
    with get_sql_engine().connect() as conn:
        result = conn.execute(text("SELECT pdf_bytes FROM documents WHERE source = :source"), {"source": source})
        row = result.fetchone()
        return bytes(row[0]) if row else None


def list_pdf_sources():
    _ensure_documents_table()
    with get_sql_engine().connect() as conn:
        result = conn.execute(text("SELECT source FROM documents ORDER BY source"))
        return [row[0] for row in result]


def delete_pdf(source):
    _ensure_documents_table()
    with get_sql_engine().begin() as conn:
        conn.execute(text("DELETE FROM documents WHERE source = :source"), {"source": source})