"""Unit tests for LegalVectorStore and helpers — Qdrant and HTTP calls are mocked."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from hammurabi.ingestion.models import LegalChunk
from hammurabi.knowledge.vector import (
    COLLECTION_CASES,
    COLLECTION_DOCUMENTS,
    COLLECTION_STATUTES,
    LegalVectorStore,
    _collection_for_chunk,
    _sparse_vector,
)

# ---------------------------------------------------------------------------
# _sparse_vector
# ---------------------------------------------------------------------------


def test_sparse_vector_empty_text() -> None:
    indices, values = _sparse_vector("")
    assert indices == []
    assert values == []


def test_sparse_vector_stopwords_only() -> None:
    indices, values = _sparse_vector("the a an and or but")
    assert indices == []
    assert values == []


def test_sparse_vector_returns_float_weights() -> None:
    indices, values = _sparse_vector("contract obligation binding force")
    assert len(indices) == len(values)
    assert all(isinstance(v, float) for v in values)
    assert all(0.0 < v <= 1.0 for v in values)


def test_sparse_vector_unique_indices() -> None:
    indices, _ = _sparse_vector("contract obligation liability termination indemnification")
    assert len(indices) == len(set(indices)), "Hash collision produced duplicate indices"


def test_sparse_vector_deterministic() -> None:
    text = "pacta sunt servanda binding force contracts"
    i1, v1 = _sparse_vector(text)
    i2, v2 = _sparse_vector(text)
    assert i1 == i2
    assert v1 == v2


# ---------------------------------------------------------------------------
# _collection_for_chunk
# ---------------------------------------------------------------------------


def _make_chunk(**kwargs: Any) -> LegalChunk:
    defaults: dict[str, Any] = {
        "text": "Sample legal text.",
        "source_type": "xml",
        "code": "Civil Code",
        "article_id": None,
        "jurisdiction": "FR",
        "effective_date": None,
        "tags": [],
        "chunk_index": 0,
        "token_count": 5,
        "metadata": {},
    }
    defaults.update(kwargs)
    return LegalChunk(**defaults)


def test_collection_article_chunk() -> None:
    chunk = _make_chunk(article_id="fr-civil-1103")
    assert _collection_for_chunk(chunk) == COLLECTION_STATUTES


def test_collection_judgment_chunk() -> None:
    chunk = _make_chunk(metadata={"segment_type": "judgment_part"})
    assert _collection_for_chunk(chunk) == COLLECTION_CASES


def test_collection_clause_chunk() -> None:
    chunk = _make_chunk(metadata={"segment_type": "clause"})
    assert _collection_for_chunk(chunk) == COLLECTION_DOCUMENTS


def test_collection_default_chunk() -> None:
    chunk = _make_chunk()
    assert _collection_for_chunk(chunk) == COLLECTION_DOCUMENTS


# ---------------------------------------------------------------------------
# LegalVectorStore.upsert_chunks (mocked Qdrant + HTTP)
# ---------------------------------------------------------------------------


def _mock_qdrant_client() -> MagicMock:
    client = MagicMock()
    client.get_collections = AsyncMock(return_value=MagicMock(collections=[]))
    client.create_collection = AsyncMock()
    client.upsert = AsyncMock()
    return client


async def test_upsert_chunks_empty_list() -> None:
    store = LegalVectorStore()
    count = await store.upsert_chunks([], corpus_id="c1")
    assert count == 0


async def test_upsert_chunks_calls_embed_and_upsert() -> None:
    store = LegalVectorStore()
    chunk = _make_chunk(article_id="fr-civil-1103", text="Binding force of contracts.")

    fake_embedding = [0.1] * 768
    mock_qdrant = _mock_qdrant_client()

    with (
        patch("hammurabi.knowledge.vector._get_qdrant", return_value=mock_qdrant),
        patch(
            "hammurabi.knowledge.vector._embed",
            new=AsyncMock(return_value=[fake_embedding]),
        ),
    ):
        count = await store.upsert_chunks([chunk], corpus_id="c1")

    assert count == 1
    mock_qdrant.upsert.assert_awaited_once()
    mock_qdrant.create_collection.assert_awaited_once()


async def test_upsert_chunks_creates_collection_once() -> None:
    """Second upsert to the same collection must not call create_collection again."""
    store = LegalVectorStore()
    chunk = _make_chunk(article_id="fr-civil-1103", text="Text.")
    fake_embedding = [0.0] * 768

    existing_col = MagicMock()
    existing_col.name = COLLECTION_STATUTES
    mock_qdrant = _mock_qdrant_client()
    mock_qdrant.get_collections.return_value = MagicMock(collections=[existing_col])

    with (
        patch("hammurabi.knowledge.vector._get_qdrant", return_value=mock_qdrant),
        patch(
            "hammurabi.knowledge.vector._embed",
            new=AsyncMock(return_value=[fake_embedding]),
        ),
    ):
        await store.upsert_chunks([chunk], corpus_id="c1")
        await store.upsert_chunks([chunk], corpus_id="c1")

    # create_collection should never be called — collection already exists
    mock_qdrant.create_collection.assert_not_awaited()


# ---------------------------------------------------------------------------
# LegalVectorStore.search (mocked)
# ---------------------------------------------------------------------------


async def test_search_returns_empty_when_no_collections() -> None:
    store = LegalVectorStore()
    mock_qdrant = MagicMock()
    mock_qdrant.get_collections = AsyncMock(return_value=MagicMock(collections=[]))

    with (
        patch("hammurabi.knowledge.vector._get_qdrant", return_value=mock_qdrant),
        patch(
            "hammurabi.knowledge.vector._embed",
            new=AsyncMock(return_value=[[0.0] * 768]),
        ),
    ):
        results = await store.search("binding force", jurisdiction="FR")

    assert results == []


async def test_search_filters_by_jurisdiction() -> None:
    """Verify that a jurisdiction filter is included when specified."""
    store = LegalVectorStore()

    existing_col = MagicMock()
    existing_col.name = COLLECTION_STATUTES
    mock_qdrant = MagicMock()
    mock_qdrant.get_collections = AsyncMock(return_value=MagicMock(collections=[existing_col]))

    point = MagicMock()
    point.score = 0.95
    point.payload = {
        "text": "Binding force",
        "source_type": "xml",
        "jurisdiction": "FR",
        "article_id": "fr-civil-1103",
        "case_id": None,
        "tags": ["contract"],
        "effective_date": None,
    }
    mock_qdrant.query_points = AsyncMock(return_value=MagicMock(points=[point]))

    with (
        patch("hammurabi.knowledge.vector._get_qdrant", return_value=mock_qdrant),
        patch(
            "hammurabi.knowledge.vector._embed",
            new=AsyncMock(return_value=[[0.1] * 768]),
        ),
    ):
        results = await store.search("binding force", jurisdiction="FR", top_k=5)

    assert len(results) == 1
    assert results[0].jurisdiction == "FR"
    assert results[0].article_id == "fr-civil-1103"
    assert results[0].score == pytest.approx(0.95)


# ---------------------------------------------------------------------------
# LegalVectorStore.delete_corpus (mocked)
# ---------------------------------------------------------------------------


async def test_delete_corpus_called_for_each_collection() -> None:
    store = LegalVectorStore()

    cols = [MagicMock(name=n) for n in (COLLECTION_STATUTES, COLLECTION_CASES)]
    for col, n in zip(cols, (COLLECTION_STATUTES, COLLECTION_CASES), strict=True):
        col.name = n
    mock_qdrant = MagicMock()
    mock_qdrant.get_collections = AsyncMock(return_value=MagicMock(collections=cols))
    mock_qdrant.delete = AsyncMock()

    with patch("hammurabi.knowledge.vector._get_qdrant", return_value=mock_qdrant):
        await store.delete_corpus("corpus-42")

    # delete called once per existing collection
    assert mock_qdrant.delete.await_count == 2
