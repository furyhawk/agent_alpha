"""Application settings loaded from .env via pydantic-settings."""

from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from .env / environment.

    Usage::

        settings = Settings()               # load from .env / env vars
        settings = Settings(_env_file=".env.test")  # alternate file
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    debug: bool = False

    llm_base_url: str = "http://localhost:11434/v1"
    llm_model: str = "llama"
    llm_api_key: str = ""
    logfire_token: str = ""

    database_url: str = "postgresql+asyncpg://agent_alpha:agent_alpha@localhost:5432/agent_alpha"
    valkey_url: str = "redis://localhost:6379/0"

    # ── Milvus (Vector Database) ───────────────────────────────────────────

    milvus_uri: str = "http://localhost:19530"
    milvus_token: str = ""

    # ── Media & File Storage ───────────────────────────────────────────────

    media_dir: str = "media"
    max_upload_size_mb: int = 50

    # ── RAG Parsing ────────────────────────────────────────────────────────

    pdf_parser: str = "pymupdf"

    # ── Cross-Encoder Reranker ─────────────────────────────────────────────

    cross_encoder_model: str = "cross-encoder/ms-marco-MiniLM-L6-v2"
    hf_token: str = ""
    models_cache_dir: Path = Path.home() / ".cache" / "agent-alpha" / "models"

    # ── Embeddings ─────────────────────────────────────────────────────────

    embedding_base_url: str = ""
    """Base URL for the embedding API. If empty, uses the LLM base URL."""

    embedding_api_key: str = ""
    """API key for the embedding API. If empty, uses the LLM API key."""

    # ── AI Configuration ───────────────────────────────────────────────────

    ai_model: str = "gpt-4o"
    rag_image_description_model: str = ""

    # ── RAG Settings (derived) ────────────────────────────────────────────

    @property
    def rag(self) -> object:
        """Return a ``RAGSettings`` instance configured from application settings.

        Lazy import to avoid circular dependencies at module level.
        """
        from backend.services.rag.config import RAGSettings

        return RAGSettings(
            collection_name="documents",
            chunk_size=512,
            chunk_overlap=50,
            chunking_strategy="recursive",
            enable_hybrid_search=False,
            enable_ocr=False,
            enable_image_description=True,
            image_description_model=self.rag_image_description_model,
        )

    # ── Factories ──────────────────────────────────────────────────────────

    @classmethod
    def create(cls, **overrides: str) -> Settings:
        """Return a Settings instance with selective overrides (useful in tests).

        Example::

            settings = Settings.create(llm_model="test-model")
        """
        return cls(**overrides)


settings = Settings()
