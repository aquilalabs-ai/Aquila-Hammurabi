"""Smoke tests for Settings — validates defaults and env-var overrides."""

from __future__ import annotations

import pytest

from hammurabi.config import Settings


def test_defaults() -> None:
    s = Settings()
    assert s.default_jurisdiction == "FR"
    assert s.neo4j_uri == "bolt://localhost:7688"
    assert s.qdrant_host == "localhost"
    assert s.qdrant_port == 6335
    assert s.api_key is None
    assert s.debug is False
    assert s.langsmith_api_key is None


def test_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEFAULT_JURISDICTION", "EU")
    monkeypatch.setenv("NEO4J_URI", "bolt://neo4j:7687")
    monkeypatch.setenv("QDRANT_PORT", "6333")
    monkeypatch.setenv("DEBUG", "true")

    s = Settings()

    assert s.default_jurisdiction == "EU"
    assert s.neo4j_uri == "bolt://neo4j:7687"
    assert s.qdrant_port == 6333
    assert s.debug is True


def test_optional_secrets_none_by_default() -> None:
    s = Settings()
    assert s.qdrant_api_key is None
    assert s.langsmith_api_key is None
    assert s.api_key is None
