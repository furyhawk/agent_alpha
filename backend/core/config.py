"""Application settings loaded from .env via pydantic-settings."""

from __future__ import annotations

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

    llm_base_url: str = "http://localhost:11434/v1"
    llm_model: str = "llama"
    llm_api_key: str = ""
    logfire_token: str = ""

    database_url: str = "postgresql+asyncpg://agent_alpha:agent_alpha@localhost:5432/agent_alpha"
    valkey_url: str = "redis://localhost:6379/0"

    # ── Factories ──────────────────────────────────────────────────────────

    @classmethod
    def create(cls, **overrides: str) -> Settings:
        """Return a Settings instance with selective overrides (useful in tests).

        Example::

            settings = Settings.create(llm_model="test-model")
        """
        return cls(**overrides)


settings = Settings()
