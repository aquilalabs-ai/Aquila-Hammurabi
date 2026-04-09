"""Application settings loaded from environment variables / .env file."""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── LLM ──────────────────────────────────────────────────────────────────
    llm_base_url: str = Field(
        default="http://localhost:11434/v1",
        description="Base URL for an OpenAI-compatible LLM endpoint.",
    )
    llm_api_key: str = Field(
        default="ollama",
        description="API key for the LLM provider (use 'ollama' for local Ollama).",
    )
    llm_model: str = Field(
        default="llama3.2",
        description="Model name to use for reasoning.",
    )

    # ── Embeddings ────────────────────────────────────────────────────────────
    embedding_model: str = Field(
        default="nomic-embed-text",
        description="Embedding model name (default: nomic-embed-text via Ollama).",
    )
    embedding_base_url: str = Field(
        default="http://localhost:11434/v1",
        description="Base URL for an OpenAI-compatible embeddings endpoint.",
    )
    embedding_api_key: str = Field(
        default="ollama",
        description="API key for the embeddings provider.",
    )

    # ── Neo4j ─────────────────────────────────────────────────────────────────
    neo4j_uri: str = Field(
        default="bolt://localhost:7688",
        description="Bolt URI for Neo4j (host-mapped port from docker-compose).",
    )
    neo4j_user: str = Field(default="neo4j", description="Neo4j username.")
    neo4j_password: str = Field(default="password", description="Neo4j password.")

    # ── Qdrant ────────────────────────────────────────────────────────────────
    qdrant_host: str = Field(default="localhost", description="Qdrant REST host.")
    qdrant_port: int = Field(
        default=6335, description="Qdrant REST port (host-mapped from docker-compose)."
    )
    qdrant_api_key: str | None = Field(
        default=None, description="Qdrant API key (None for unauthenticated local dev)."
    )

    # ── PostgreSQL ────────────────────────────────────────────────────────────
    postgres_dsn: str = Field(
        default="postgresql+psycopg://aquila:aquila@localhost:5433/aquila",
        description="psycopg3-compatible DSN for PostgreSQL session store.",
    )

    # ── Application ───────────────────────────────────────────────────────────
    default_jurisdiction: str = Field(
        default="FR",
        description="ISO 3166-1 alpha-2 jurisdiction code used when none is specified.",
    )
    api_key: str | None = Field(
        default=None,
        description="X-API-Key value. When None/empty the API runs in open (unauthenticated) mode.",
    )
    debug: bool = Field(default=False, description="Enable debug logging and reload.")

    # ── LangSmith (optional tracing) ──────────────────────────────────────────
    langsmith_api_key: str | None = Field(
        default=None, description="LangSmith API key for tracing and evaluation."
    )
    langsmith_project: str = Field(default="hammurabi", description="LangSmith project name.")


settings = Settings()
