from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql://postgres:postgres@localhost:5433/knowledge_base"
    openai_api_key: str = ""

    # Domain pack: prompts, routing signals, UI copy and evaluation topics.
    # Point this at another directory to retarget the system — see app/pack.py.
    pack_dir: Path = Path("packs/eu-ai-act")

    # User-facing generation (answers, document summaries).
    chat_model: str = "gpt-5.4-mini"
    # Internal utility calls (routing, query condensing): small, frequent, on the
    # critical path for latency. Sharing one model across both jobs makes every
    # answer-quality upgrade silently expensive.
    utility_model: str = "gpt-5.4-mini"

    embed_model: str = "text-embedding-3-small"
    # Must match the embedding model's output width: it sizes the pgvector column
    # in db/schema.sql. Changing the model without changing this fails on insert.
    embed_dim: int = 1536

    # Tuned against the evaluation set with passage-level ground truth: for the
    # 15 measured questions the passage holding the answer reached the model
    # 1/15 of the time at k=12/cap=3, and 10/15 at these values.
    #
    # per_doc_cap is 0 on purpose. A cap of 3 was flat in k — raising top_k
    # changed nothing at all — because almost every question is about one act,
    # and the cap throttled that act while its first three chunks were recitals.
    # The starvation it guarded against does not appear at this k: doc-level
    # coverage (tools/retrieval_eval) is 37/38 either way.
    top_k: int = 16
    rrf_pool: int = 80
    per_doc_cap: int = 0  # max chunks per document in the top-k; 0 = no limit
    max_chunk_tokens: int = 512

    # agent path
    # One model on the agent path. Structured and tabular lookups used to buy a
    # larger one; measured on the same nine questions it answered no better —
    # two of them worse — while carrying ~70% of the bill at 6.7x the price per
    # token. See docs/evaluation.md.
    agent_model: str = "gpt-5.4-mini"
    agent_max_tool_calls: int = 12  # soft cap: past it, tools ask the model to conclude
    agent_hard_cap_extra: int = 4  # past soft+extra the run is aborted
    agent_timeout_s: float = 150.0

    raw_dir: Path = Path("data/raw")
    objects_dir: Path = Path("data/objects")
    workspace_dir: Path = Path("data/workspace")
    # Corpus provenance (source_url per document). Never read by ingestion: it
    # only lets the viewer inject <base href> into HTML originals that lack one.
    manifest_path: Path = Path("data/manifest.json")

    ingest_ocr: bool = True

    # Comma-separated; a plain string rather than list[str] because
    # pydantic-settings expects JSON for complex types read from the environment.
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


settings = Settings()
