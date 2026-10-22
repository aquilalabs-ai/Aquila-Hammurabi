"""Unit tests for LegalGraphClient — all Neo4j I/O is mocked."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

from hammurabi.knowledge.graph import LegalGraphClient
from hammurabi.knowledge.models import ArticleContext, CaseContext, CitationChainEntry

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_client() -> LegalGraphClient:
    return LegalGraphClient()


def _patch_run(client: LegalGraphClient, return_value: list[dict[str, Any]]) -> AsyncMock:
    """Patch ``_run`` on *client* to return *return_value*."""
    mock = AsyncMock(return_value=return_value)
    client._run = mock  # type: ignore[method-assign]
    return mock


# ---------------------------------------------------------------------------
# merge_article
# ---------------------------------------------------------------------------


async def test_merge_article_calls_run() -> None:
    client = _make_client()
    mock = _patch_run(client, [])
    await client.merge_article(
        article_id="fr-civil-1103",
        article_number="1103",
        code="Civil Code",
        code_id="fr-civil",
        jurisdiction="FR",
        content="Contracts lawfully formed…",
        heading="Binding force",
        tags=["contract", "obligation"],
        corpus_id="corpus-1",
    )
    mock.assert_awaited_once()
    # Verify query string contains the expected Cypher landmarks
    query: str = mock.call_args[0][0]
    assert "MERGE (a:Article" in query
    assert "MERGE (j:Jurisdiction" in query
    assert "MERGE (lc:LegalCode" in query


async def test_merge_article_defaults_empty_tags() -> None:
    client = _make_client()
    mock = _patch_run(client, [])
    await client.merge_article(
        article_id="fr-civil-1104",
        article_number="1104",
        code="Civil Code",
        code_id="fr-civil",
        jurisdiction="FR",
        content="Content",
    )
    params: dict[str, Any] = mock.call_args[0][1]
    assert params["tags"] == []


# ---------------------------------------------------------------------------
# merge_case
# ---------------------------------------------------------------------------


async def test_merge_case_calls_run() -> None:
    client = _make_client()
    mock = _patch_run(client, [])
    await client.merge_case(
        case_id="fr-cassiv-2023-01",
        jurisdiction="FR",
        text="The court held that…",
        court="Cour de cassation",
        date="2023-01-15",
        parties=["Claimant SA", "Defendant SARL"],
        tags=["contract"],
        corpus_id="corpus-1",
    )
    mock.assert_awaited_once()
    params: dict[str, Any] = mock.call_args[0][1]
    assert params["case_id"] == "fr-cassiv-2023-01"
    assert params["parties"] == ["Claimant SA", "Defendant SARL"]


# ---------------------------------------------------------------------------
# add_article_reference / add_case_applies_article
# ---------------------------------------------------------------------------


async def test_add_article_reference() -> None:
    client = _make_client()
    mock = _patch_run(client, [])
    await client.add_article_reference("fr-civil-1103", "fr-civil-1101")
    mock.assert_awaited_once()
    query: str = mock.call_args[0][0]
    assert "REFERENCES" in query


async def test_add_case_applies_article() -> None:
    client = _make_client()
    mock = _patch_run(client, [])
    await client.add_case_applies_article("fr-cassiv-2023-01", "fr-civil-1103")
    mock.assert_awaited_once()
    query: str = mock.call_args[0][0]
    assert "APPLIES" in query
    assert "INTERPRETED_BY" in query


# ---------------------------------------------------------------------------
# get_article_context
# ---------------------------------------------------------------------------


async def test_get_article_context_returns_none_when_not_found() -> None:
    client = _make_client()
    _patch_run(client, [{"article": None, "amendments": [], "cases": [], "citing_articles": []}])
    result = await client.get_article_context("fr-civil-9999")
    assert result is None


async def test_get_article_context_returns_dataclass() -> None:
    client = _make_client()
    _patch_run(
        client,
        [
            {
                "article": {"id": "fr-civil-1103", "content": "Contracts…"},
                "amendments": [{"id": "amend-1"}],
                "cases": [{"id": "case-1"}],
                "citing_articles": [],
            }
        ],
    )
    ctx = await client.get_article_context("fr-civil-1103")
    assert isinstance(ctx, ArticleContext)
    assert ctx.article["id"] == "fr-civil-1103"
    assert len(ctx.amendments) == 1
    assert len(ctx.interpreting_cases) == 1
    assert ctx.citing_articles == []


# ---------------------------------------------------------------------------
# get_case_context
# ---------------------------------------------------------------------------


async def test_get_case_context_returns_none_when_not_found() -> None:
    client = _make_client()
    _patch_run(
        client,
        [{"case": None, "cited_articles": [], "cited_cases": [], "subsequent_citations": []}],
    )
    result = await client.get_case_context("missing-case")
    assert result is None


async def test_get_case_context_returns_dataclass() -> None:
    client = _make_client()
    _patch_run(
        client,
        [
            {
                "case": {"id": "fr-cassiv-2023-01"},
                "cited_articles": [{"id": "fr-civil-1103"}],
                "cited_cases": [],
                "subsequent_citations": [{"id": "fr-cassiv-2024-10"}],
            }
        ],
    )
    ctx = await client.get_case_context("fr-cassiv-2023-01")
    assert isinstance(ctx, CaseContext)
    assert ctx.case["id"] == "fr-cassiv-2023-01"
    assert ctx.cited_articles[0]["id"] == "fr-civil-1103"


# ---------------------------------------------------------------------------
# get_citation_chain
# ---------------------------------------------------------------------------


async def test_get_citation_chain_returns_entries() -> None:
    client = _make_client()
    _patch_run(
        client,
        [
            {"nodes": [{"id": "fr-civil-1103"}, {"id": "fr-civil-1101"}], "depth": 1},
            {
                "nodes": [
                    {"id": "fr-civil-1103"},
                    {"id": "fr-civil-1101"},
                    {"id": "fr-civil-1100"},
                ],
                "depth": 2,
            },
        ],
    )
    chain = await client.get_citation_chain("fr-civil-1103", depth=2)
    assert len(chain) == 2
    assert isinstance(chain[0], CitationChainEntry)
    assert chain[0].depth == 1


async def test_get_citation_chain_clamps_depth() -> None:
    """depth > 5 should be silently clamped to 5 (reflected in the query string)."""
    client = _make_client()
    mock = _patch_run(client, [])
    await client.get_citation_chain("fr-civil-1103", depth=99)
    query: str = mock.call_args[0][0]
    # The query should embed depth 5 not 99
    assert "1..5" in query
    assert "1..99" not in query


# ---------------------------------------------------------------------------
# article_exists / case_exists
# ---------------------------------------------------------------------------


async def test_article_exists_true() -> None:
    client = _make_client()
    _patch_run(client, [{"cnt": 1}])
    assert await client.article_exists("fr-civil-1103") is True


async def test_article_exists_false() -> None:
    client = _make_client()
    _patch_run(client, [{"cnt": 0}])
    assert await client.article_exists("fr-civil-9999") is False


async def test_case_exists_true() -> None:
    client = _make_client()
    _patch_run(client, [{"cnt": 2}])
    assert await client.case_exists("fr-cassiv-2023-01") is True


# ---------------------------------------------------------------------------
# delete_corpus
# ---------------------------------------------------------------------------


async def test_delete_corpus_calls_detach_delete() -> None:
    client = _make_client()
    mock = _patch_run(client, [])
    await client.delete_corpus("corpus-1")
    mock.assert_awaited_once()
    query: str = mock.call_args[0][0]
    assert "DETACH DELETE" in query
    params: dict[str, Any] = mock.call_args[0][1]
    assert params["corpus_id"] == "corpus-1"
