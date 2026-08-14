-- __EMBED_DIM__ is substituted from settings.embed_dim by app/db.py, so the
-- vector column always matches the configured embedding model.
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS documents (
    doc_id       text PRIMARY KEY,
    filename     text NOT NULL,
    format       text NOT NULL,
    sha256       text NOT NULL,
    status       text NOT NULL DEFAULT 'RECEIVED'
        CHECK (status IN ('RECEIVED', 'PARSED', 'FAILED', 'PUBLISHED')),
    error        text,
    storage_path text,
    title        text,
    page_count   integer,
    chunk_count  integer,
    table_count  integer,
    ingested_at  timestamptz NOT NULL DEFAULT now(),
    published_at timestamptz
);

CREATE TABLE IF NOT EXISTS chunks (
    chunk_id   text PRIMARY KEY,
    doc_id     text NOT NULL REFERENCES documents(doc_id) ON DELETE CASCADE,
    seq        integer NOT NULL,
    kind       text NOT NULL DEFAULT 'text' CHECK (kind IN ('text', 'table')),
    text       text NOT NULL,
    page       integer,
    bbox       jsonb,
    bboxes     jsonb,
    char_start integer,
    char_end   integer,
    headings   text[] NOT NULL DEFAULT '{}',
    embedding  vector(__EMBED_DIM__) NOT NULL,
    tsv        tsvector GENERATED ALWAYS AS (to_tsvector('simple'::regconfig, text)) STORED
);

CREATE INDEX IF NOT EXISTS chunks_doc_idx ON chunks (doc_id);
CREATE INDEX IF NOT EXISTS chunks_tsv_idx ON chunks USING gin (tsv);
CREATE INDEX IF NOT EXISTS chunks_embedding_idx ON chunks USING hnsw (embedding vector_cosine_ops);
