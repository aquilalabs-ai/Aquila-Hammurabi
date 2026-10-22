"""Tests for hybrid search endpoint."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from hammurabi.api.app import create_app
from hammurabi.knowledge.models import SearchResult


@pytest.fixture
def client() -> TestClient:
    app = create_app()
    app.state.knowledge = MagicMock()
    app.state.agent = MagicMock()
    return TestClient(app, raise_server_exceptions=False)


@patch("hammurabi.api.routes.search.KnowledgeDep")
def test_search_empty_results(client: TestClient) -> None:
    knowledge = MagicMock()
    knowledge.search = AsyncMock(return_value=[])

    with patch.object(client.app.state, "knowledge", knowledge):
        resp = client.get("/search?query=contrat")

    assert resp.status_code == 200
    body = resp.json()
    assert body["query"] == "contrat"
    assert body["total"] == 0
    assert body["results"] == []


def test_search_requires_query(client: TestClient) -> None:
    resp = client.get("/search")
    assert resp.status_code == 422
