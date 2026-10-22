"""Unit tests for LegalKnowledgeService — graph and vector clients are mocked."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

from hammurabi.ingestion.models import LegalChunk
from hammurabi.knowledge.models import (
    ArticleContext,
    CaseContext,
    CitationChainEntry,
    SearchResult,
)
from hammurabi.knowledge.service import (
    LegalKnowledgeService,
    _article_number_from_id,
    _hierarchy_val,
    _make_code_id,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_graph() -> MagicMock:
    g = MagicMock()
    g.merge_article = AsyncMock()
    g.merge_case = AsyncMock()
    g.merge_document = AsyncMock()
    g.merge_clause = AsyncMock()
    g.add_article_reference = AsyncMock()
    g.add_case_applies_article = AsyncMock()
    g.article_exists = AsyncMock(return_value=False)
    g.case_exists = AsyncMock(return_value=False)
    g.get_article_context = AsyncMock(return_value=None)
    g.get_case_context = AsyncMock(return_value=None)
    g.get_citation_chain = AsyncMock(return_value=[])
    g.delete_corpus = AsyncMock()
    return g


def _make_vector() -> MagicMock:
    v = MagicMock()
    v.upsert_chunks = AsyncMock(return_value=0)
    v.search = AsyncMock(return_value=[])
    v.delete_corpus = AsyncMock()
    v.close = AsyncMock()
    return v


def _make_chunk(**kwargs: Any) -> LegalChunk:
    defaults: dict[str, Any] = {
        "text": "Sample legal text.",
        "source_type": "xml",
        "code": "Civil Code",
        "article_id": None,
        "jurisdiction": "FR",
        "effective_date": None,
        "tags": ["contract"],
        "chunk_index": 0,
        "token_count": 5,
        "metadata": {},
    }
    defaults.update(kwargs)
    return LegalChunk(**defaults)


def _make_service() -> tuple[LegalKnowledgeService, MagicMock, MagicMock]:
    graph = _make_graph()
    vector = _make_vector()
    svc = LegalKnowledgeService(graph=graph, vector=vector)
    return svc, graph, vector


# ---------------------------------------------------------------------------
# ingest_chunks — statute articles
# ---------------------------------------------------------------------------


async def test_ingest_single_article_chunk() -> None:
    svc, graph, vector = _make_service()
    vector.upsert_chunks.return_value = 1
    chunk = _make_chunk(
        article_id="fr-civil-1103",
        metadata={"segment_type": "article", "heading": "Binding force"},
    )

    summary = await svc.ingest_chunks([chunk], corpus_id="c1")

    graph.merge_article.assert_awaited_once()
    assert summary.articles_merged == 1
    assert summary.chunks_upserted == 1
    assert summary.corpus_id == "c1"
    assert summary.errors == []


async def test_ingest_deduplicates_articles() -> None:
    """Two chunks with the same article_id should produce a single merge_article call."""
    svc, graph, vector = _make_service()
    chunk1 = _make_chunk(article_id="fr-civil-1103", chunk_index=0)
    chunk2 = _make_chunk(article_id="fr-civil-1103", chunk_index=1)

    summary = await svc.ingest_chunks([chunk1, chunk2], corpus_id="c1")

    assert graph.merge_article.await_count == 1
    assert summary.articles_merged == 1


async def test_ingest_creates_references_when_article_exists() -> None:
    svc, graph, vector = _make_service()
    graph.article_exists.return_value = True
    chunk = _make_chunk(
        article_id="fr-civil-1103",
        metadata={
            "segment_type": "article",
            "cross_references": ["fr-civil-1101", "fr-civil-1100"],
        },
    )

    summary = await svc.ingest_chunks([chunk], corpus_id="c1")

    assert graph.add_article_reference.await_count == 2
    assert summary.references_created == 2


async def test_ingest_skips_references_when_target_missing() -> None:
    svc, graph, vector = _make_service()
    graph.article_exists.return_value = False
    chunk = _make_chunk(
        article_id="fr-civil-1103",
        metadata={"cross_references": ["fr-civil-9999"]},
    )

    summary = await svc.ingest_chunks([chunk], corpus_id="c1")

    graph.add_article_reference.assert_not_awaited()
    assert summary.references_created == 0


# ---------------------------------------------------------------------------
# ingest_chunks — case law
# ---------------------------------------------------------------------------


async def test_ingest_judgment_chunk() -> None:
    svc, graph, vector = _make_service()
    chunk = _make_chunk(
        source_type="pdf",
        metadata={
            "segment_type": "judgment_part",
            "case_id": "fr-cassiv-2023-01",
            "court": "Cour de cassation",
            "date": "2023-01-15",
        },
    )

    summary = await svc.ingest_chunks([chunk], corpus_id="c2")

    graph.merge_case.assert_awaited_once()
    call_kwargs = graph.merge_case.call_args.kwargs
    assert call_kwargs["case_id"] == "fr-cassiv-2023-01"
    assert call_kwargs["court"] == "Cour de cassation"
    assert summary.cases_merged == 1


async def test_ingest_judgment_links_applied_article() -> None:
    svc, graph, vector = _make_service()
    graph.article_exists.return_value = True
    chunk = _make_chunk(
        metadata={
            "segment_type": "judgment_part",
            "case_id": "fr-cassiv-2023-01",
            "cross_references": ["fr-civil-1103"],
        },
    )

    await svc.ingest_chunks([chunk], corpus_id="c2")

    graph.add_case_applies_article.assert_awaited_once_with("fr-cassiv-2023-01", "fr-civil-1103")


async def test_ingest_judgment_auto_generates_case_id() -> None:
    """When chunk metadata has no case_id, a synthetic one is generated."""
    svc, graph, vector = _make_service()
    chunk = _make_chunk(metadata={"segment_type": "judgment_part"}, chunk_index=7)

    summary = await svc.ingest_chunks([chunk], corpus_id="c2")

    call_kwargs = graph.merge_case.call_args.kwargs
    assert call_kwargs["case_id"].startswith("case-c2-7")
    assert summary.cases_merged == 1


# ---------------------------------------------------------------------------
# ingest_chunks — auto corpus_id
# ---------------------------------------------------------------------------


async def test_ingest_auto_corpus_id() -> None:
    svc, graph, vector = _make_service()
    chunk = _make_chunk(article_id="fr-civil-1103")

    summary = await svc.ingest_chunks([chunk])

    assert summary.corpus_id != ""
    assert len(summary.corpus_id) == 36  # UUID4


# ---------------------------------------------------------------------------
# ingest_chunks — vector upsert error is captured in summary
# ---------------------------------------------------------------------------


async def test_ingest_captures_vector_error() -> None:
    svc, graph, vector = _make_service()
    vector.upsert_chunks.side_effect = RuntimeError("Qdrant connection refused")
    chunk = _make_chunk(article_id="fr-civil-1103")

    summary = await svc.ingest_chunks([chunk], corpus_id="c1")

    assert any("Qdrant" in e for e in summary.errors)
    assert summary.chunks_upserted == 0


# ---------------------------------------------------------------------------
# search
# ---------------------------------------------------------------------------


async def test_search_delegates_to_vector() -> None:
    svc, graph, vector = _make_service()
    expected = [
        SearchResult(
            text="Binding force",
            score=0.9,
            source_type="xml",
            jurisdiction="FR",
            article_id="fr-civil-1103",
            case_id=None,
            tags=["contract"],
            payload={},
        )
    ]
    vector.search.return_value = expected

    results = await svc.search("binding force", jurisdiction="FR", top_k=5)

    vector.search.assert_awaited_once_with(
        "binding force",
        jurisdiction="FR",
        source_type=None,
        tags=None,
        effective_date_from=None,
        effective_date_to=None,
        top_k=5,
        collections=None,
    )
    assert results == expected


# ---------------------------------------------------------------------------
# get_article / get_case / get_citation_network
# ---------------------------------------------------------------------------


async def test_get_article_delegates_to_graph() -> None:
    svc, graph, vector = _make_service()
    ctx = ArticleContext(
        article={"id": "fr-civil-1103"},
        amendments=[],
        interpreting_cases=[],
        citing_articles=[],
    )
    graph.get_article_context.return_value = ctx

    result = await svc.get_article("fr-civil-1103")

    graph.get_article_context.assert_awaited_once_with("fr-civil-1103")
    assert result is ctx


async def test_get_article_returns_none_when_missing() -> None:
    svc, graph, vector = _make_service()
    graph.get_article_context.return_value = None
    assert await svc.get_article("missing") is None


async def test_get_case_delegates_to_graph() -> None:
    svc, graph, vector = _make_service()
    ctx = CaseContext(
        case={"id": "case-1"},
        cited_articles=[],
        cited_cases=[],
        subsequent_citations=[],
    )
    graph.get_case_context.return_value = ctx

    result = await svc.get_case("case-1")

    graph.get_case_context.assert_awaited_once_with("case-1")
    assert result is ctx


async def test_get_citation_network_delegates_to_graph() -> None:
    svc, graph, vector = _make_service()
    chain = [CitationChainEntry(nodes=[{"id": "fr-civil-1103"}], depth=1)]
    graph.get_citation_chain.return_value = chain

    result = await svc.get_citation_network("fr-civil-1103", depth=2)

    graph.get_citation_chain.assert_awaited_once_with("fr-civil-1103", depth=2)
    assert result == chain


# ---------------------------------------------------------------------------
# delete_corpus
# ---------------------------------------------------------------------------


async def test_delete_corpus_cleans_both_stores() -> None:
    svc, graph, vector = _make_service()
    await svc.delete_corpus("corpus-99")
    graph.delete_corpus.assert_awaited_once_with("corpus-99")
    vector.delete_corpus.assert_awaited_once_with("corpus-99")


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def test_make_code_id_strips_stop_words() -> None:
    assert _make_code_id("FR", "Civil Code") == "fr-civil"
    assert _make_code_id("FR", "Code Civil") == "fr-civil"
    assert _make_code_id("EU", "GDPR Regulation") == "eu-gdpr"


def test_make_code_id_fallback() -> None:
    assert _make_code_id("FR", "code") == "fr-code"


def test_article_number_from_id() -> None:
    assert _article_number_from_id("fr-civil-1103") == "1103"
    # Compound numbers: rsplit("-", 1) returns only the last segment; the service
    # derives the number from segment.article_number in practice, not from the ID.
    assert _article_number_from_id("fr-civil-L123-4") == "4"
    assert _article_number_from_id("standalone") == "standalone"


def test_hierarchy_val_present() -> None:
    chunk = _make_chunk(metadata={"hierarchy": {"title": "Title III", "chapter": "Chapter I"}})
    assert _hierarchy_val(chunk, "title") == "Title III"
    assert _hierarchy_val(chunk, "chapter") == "Chapter I"


def test_hierarchy_val_missing() -> None:
    chunk = _make_chunk(metadata={})
    assert _hierarchy_val(chunk, "title") is None


def test_hierarchy_val_non_dict() -> None:
    chunk = _make_chunk(metadata={"hierarchy": "not-a-dict"})
    assert _hierarchy_val(chunk, "title") is None
