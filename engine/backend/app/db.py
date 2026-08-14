from pathlib import Path

import psycopg
from pgvector.psycopg import register_vector
from psycopg_pool import ConnectionPool

from app.config import settings

SCHEMA_PATH = Path(__file__).resolve().parents[1] / "db" / "schema.sql"

_EMBEDDING_DIM = """
SELECT format_type(atttypid, atttypmod) FROM pg_attribute
WHERE attrelid = 'chunks'::regclass AND attname = 'embedding'
"""


def ensure_schema() -> None:
    schema = SCHEMA_PATH.read_text().replace("__EMBED_DIM__", str(settings.embed_dim))
    with psycopg.connect(settings.database_url, autocommit=True) as conn:
        conn.execute(schema)
        # CREATE TABLE IF NOT EXISTS leaves an existing column alone, so a
        # changed EMBED_MODEL would otherwise surface as a confusing insert
        # error much later. Fail here instead.
        actual = conn.execute(_EMBEDDING_DIM).fetchone()[0]
        if actual != f"vector({settings.embed_dim})":
            raise RuntimeError(
                f"chunks.embedding is {actual} but EMBED_DIM is {settings.embed_dim}: "
                "the embedding model changed — re-embed the corpus into a fresh database"
            )


def connect() -> psycopg.Connection:
    conn = psycopg.connect(settings.database_url)
    register_vector(conn)
    return conn


def create_pool() -> ConnectionPool:
    return ConnectionPool(
        settings.database_url,
        min_size=1,
        max_size=8,
        configure=register_vector,
        open=True,
    )
