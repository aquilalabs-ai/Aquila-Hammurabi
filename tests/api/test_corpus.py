"""Tests for corpus management endpoints."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from hammurabi.api.app import create_app


@pytest.fixture
def client() -> TestClient:
    app = create_app()
    app.state.knowledge = MagicMock()
    app.state.agent = MagicMock()
    return TestClient(app, raise_server_exceptions=False)


@patch("hammurabi.api.routes.corpus.store")
@patch("hammurabi.api.routes.corpus.job_store")
def test_list_corpora_empty(mock_jobs: MagicMock, mock_store: MagicMock, client: TestClient) -> None:
    mock_store.list_corpora = AsyncMock(return_value=[])
    resp = client.get("/corpus")
    assert resp.status_code == 200
    assert resp.json() == []


@patch("hammurabi.api.routes.corpus.store")
def test_corpus_stats_not_found(mock_store: MagicMock, client: TestClient) -> None:
    mock_store.get_corpus = AsyncMock(return_value=None)
    resp = client.get("/corpus/nonexistent/stats")
    assert resp.status_code == 404
