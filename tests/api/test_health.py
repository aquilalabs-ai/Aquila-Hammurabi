"""Tests for /health and /health/ready endpoints."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from hammurabi.api.app import create_app


@pytest.fixture
def client() -> TestClient:
    app = create_app()

    knowledge = MagicMock()
    knowledge.graph._run = AsyncMock(return_value=[{"n": 1}])
    knowledge.vector_store._client.get_collections = MagicMock(return_value=MagicMock())

    app.state.knowledge = knowledge
    app.state.agent = MagicMock()
    return TestClient(app, raise_server_exceptions=True)


def test_liveness(client: TestClient) -> None:
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_readiness_ok(client: TestClient) -> None:
    resp = client.get("/health/ready")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] in ("ok", "degraded")
    assert "neo4j" in data
    assert "qdrant" in data
