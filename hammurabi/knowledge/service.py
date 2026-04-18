"""Unified LegalKnowledgeService — facade over Neo4j graph + Qdrant vector store.

Usage
-----
::

    from hammurabi.knowledge import LegalKnowledgeService

    svc = LegalKnowledgeService()
    summary = await svc.ingest_chunks(chunks, corpus_id="my-corpus")
    results = await svc.search("pacta sunt servanda", jurisdiction="FR")
    ctx     = await svc.get_article("fr-civil-1103")
    await svc.delete_corpus("my-corpus")
    await svc.close()
"""

from __future__ import annotations

import uuid
from typing import Any

from hammurabi.ingestion.models import LegalChunk
from hammurabi.knowledge.graph import LegalGraphClient
from hammurabi.knowledge.models import (
    ArticleContext,
    CaseContext,
    CitationChainEntry,
    IngestionSummary,
    SearchResult,
)
from hammurabi.knowledge.vector import LegalVectorStore


class LegalKnowledgeService:
    """Unified facade wrapping the Neo4j graph and Qdrant vector store.

    Instantiate once per application; inject into route handlers or agents.
    Always call :meth:`close` on shutdown.
    """

    def __init__(
        self,
        graph: LegalGraphClient | None = None,
        vector: LegalVectorStore | None = None,
    ) -> None:
        self._graph = graph or LegalGraphClient()
        self._vector = vector or LegalVectorStore()

    async def close(self) -> None:
        """Release Neo4j driver and Qdrant client connection pools."""
        await self._graph.close()
        await self._vector.close()

    # ------------------------------------------------------------------
    # Ingestion pipeline
    # ------------------------------------------------------------------

    async def ingest_chunks(
        self,
        chunks: list[LegalChunk],
        corpus_id: str | None = None,
        document_id: str | None = None,
    ) -> IngestionSummary:
        """Write *chunks* to both Neo4j (graph nodes) and Qdrant (vector index).

        Parameters
        ----------
        chunks:
            Flat list of :class:`~hammurabi.ingestion.models.LegalChunk` objects
            produced by the ingestion layer.
        corpus_id:
            Logical corpus identifier (auto-generated UUID when omitted).
        document_id:
            Optional document node ID for user-uploaded contracts.  When set,
            a ``Document`` node is merged and clause chunks are attached to it.

        Returns
        -------
        :class:`IngestionSummary` with counts of merged/created graph nodes and
        upserted vector points.
        """
        resolved_corpus_id = corpus_id or str(uuid.uuid4())
        summary = IngestionSummary(corpus_id=resolved_corpus_id)

        # ── 1. Graph ingestion ─────────────────────────────────────────────────
        seen_articles: set[str] = set()
        seen_cases: set[str] = set()

        # Optionally create a Document node for contract/regulation uploads
        doc_node_id: str | None = None
        has_clause_chunks = any(
            c.metadata.get("segment_type") in ("clause", "section") for c in chunks
        )
        if document_id and has_clause_chunks:
            doc_node_id = document_id
            await self._graph.merge_document(
                document_id=doc_node_id,
                source_type=chunks[0].source_type if chunks else None,
                corpus_id=resolved_corpus_id,
            )

        for chunk in chunks:
            seg_type: str = chunk.metadata.get("segment_type", "")

            # ── Statute article ────────────────────────────────────────────────
            if chunk.article_id and chunk.article_id not in seen_articles:
                seen_articles.add(chunk.article_id)
                code = chunk.code or "Unknown Code"
                code_id = _make_code_id(chunk.jurisdiction, code)
                article_number = _article_number_from_id(chunk.article_id)

                try:
                    await self._graph.merge_article(
                        article_id=chunk.article_id,
                        article_number=article_number,
                        code=code,
                        code_id=code_id,
                        jurisdiction=chunk.jurisdiction,
                        content=chunk.text,
                        heading=chunk.metadata.get("heading"),
                        title=_hierarchy_val(chunk, "title"),
                        chapter=_hierarchy_val(chunk, "chapter"),
                        effective_date=chunk.effective_date,
                        version=chunk.metadata.get("version"),
                        tags=chunk.tags,
                        corpus_id=resolved_corpus_id,
                    )
                    summary.articles_merged += 1
                except Exception as exc:  # noqa: BLE001
                    summary.errors.append(f"Article {chunk.article_id}: {exc}")

                # Create REFERENCES edges to already-existing articles
                for ref_id in chunk.metadata.get("cross_references", []):
                    try:
                        if await self._graph.article_exists(ref_id):
                            await self._graph.add_article_reference(chunk.article_id, ref_id)
                            summary.references_created += 1
                    except Exception as exc:  # noqa: BLE001
                        summary.errors.append(f"Ref {chunk.article_id}->{ref_id}: {exc}")

            # ── Case law judgment ──────────────────────────────────────────────
            elif seg_type == "judgment_part":
                raw_case_id: Any = chunk.metadata.get("case_id")
                case_id: str = (
                    str(raw_case_id)
                    if raw_case_id
                    else f"case-{resolved_corpus_id}-{chunk.chunk_index}"
                )
                if case_id not in seen_cases:
                    seen_cases.add(case_id)
                    try:
                        raw_parties: Any = chunk.metadata.get("parties", [])
                        parties: list[str] = list(raw_parties) if raw_parties else []
                        await self._graph.merge_case(
                            case_id=case_id,
                            jurisdiction=chunk.jurisdiction,
                            text=chunk.text,
                            court=chunk.metadata.get("court"),
                            date=chunk.metadata.get("date"),
                            parties=parties,
                            docket=chunk.metadata.get("docket"),
                            tags=chunk.tags,
                            corpus_id=resolved_corpus_id,
                        )
                        summary.cases_merged += 1
                    except Exception as exc:  # noqa: BLE001
                        summary.errors.append(f"Case {case_id}: {exc}")

                # Wire case → applied articles referenced in cross_references
                for ref_id in chunk.metadata.get("cross_references", []):
                    try:
                        if await self._graph.article_exists(ref_id):
                            await self._graph.add_case_applies_article(case_id, ref_id)
                    except Exception as exc:  # noqa: BLE001
                        summary.errors.append(f"Applies {case_id}->{ref_id}: {exc}")

            # ── Contract clause ────────────────────────────────────────────────
            elif seg_type in ("clause", "section") and doc_node_id:
                clause_id = chunk.metadata.get("clause_id") or str(uuid.uuid4())
                try:
                    await self._graph.merge_clause(
                        clause_id=clause_id,
                        document_id=doc_node_id,
                        text=chunk.text,
                        heading=chunk.metadata.get("heading"),
                        clause_number=chunk.metadata.get("article_number"),
                    )
                except Exception as exc:  # noqa: BLE001
                    summary.errors.append(f"Clause {clause_id}: {exc}")

        # ── 2. Vector upsert ───────────────────────────────────────────────────
        try:
            summary.chunks_upserted = await self._vector.upsert_chunks(
                chunks, corpus_id=resolved_corpus_id
            )
        except Exception as exc:  # noqa: BLE001
            summary.errors.append(f"Vector upsert: {exc}")

        return summary

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    async def search(
        self,
        query: str,
        jurisdiction: str | None = None,
        source_type: str | None = None,
        tags: list[str] | None = None,
        effective_date_from: str | None = None,
        effective_date_to: str | None = None,
        top_k: int = 10,
        collections: list[str] | None = None,
    ) -> list[SearchResult]:
        """Hybrid semantic search over the legal corpus.

        When *jurisdiction* is not supplied, ``settings.default_jurisdiction``
        is **not** automatically injected — callers may pass ``None`` to search
        across all jurisdictions.

        Returns a list of :class:`SearchResult` ranked by RRF score descending.
        """
        return await self._vector.search(
            query,
            jurisdiction=jurisdiction,
            source_type=source_type,
            tags=tags,
            effective_date_from=effective_date_from,
            effective_date_to=effective_date_to,
            top_k=top_k,
            collections=collections,
        )

    # ------------------------------------------------------------------
    # Graph retrieval
    # ------------------------------------------------------------------

    async def search_article_ids(self, q: str, limit: int = 20) -> list[dict[str, Any]]:
        """Substring search on article IDs — used for autocomplete."""
        return await self._graph.search_article_ids(q, limit=limit)

    async def get_article(self, article_id: str) -> ArticleContext | None:
        """Retrieve full article context: node properties + amendments + cases + citing articles.

        Returns ``None`` when *article_id* is not in the graph.
        """
        return await self._graph.get_article_context(article_id)

    async def get_case(self, case_id: str) -> CaseContext | None:
        """Retrieve full case context: node properties + cited articles/cases + subsequent cites.

        Returns ``None`` when *case_id* is not in the graph.
        """
        return await self._graph.get_case_context(case_id)

    async def get_citation_network(
        self, article_id: str, depth: int = 2
    ) -> list[CitationChainEntry]:
        """BFS REFERENCES citation network up to *depth* hops from *article_id*.

        *depth* is silently clamped to ``[1, 5]`` by the graph client.
        Returns one :class:`CitationChainEntry` per reachable path (may be empty
        when the article has no outgoing REFERENCES edges).
        """
        return await self._graph.get_citation_chain(article_id, depth=depth)

    # ------------------------------------------------------------------
    # Deletion
    # ------------------------------------------------------------------

    async def delete_corpus(self, corpus_id: str) -> None:
        """Purge all graph nodes and vector points tagged with *corpus_id*.

        Both stores are cleaned in parallel (graph then vector — order does not
        matter since they are independent).
        """
        await self._graph.delete_corpus(corpus_id)
        await self._vector.delete_corpus(corpus_id)

    # ------------------------------------------------------------------
    # Convenience accessors (expose underlying clients for advanced use)
    # ------------------------------------------------------------------

    @property
    def graph(self) -> LegalGraphClient:
        """Direct access to the :class:`LegalGraphClient` for advanced Cypher."""
        return self._graph

    @property
    def vector_store(self) -> LegalVectorStore:
        """Direct access to the :class:`LegalVectorStore` for collection management."""
        return self._vector


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _make_code_id(jurisdiction: str, code: str) -> str:
    """Build a canonical LegalCode id like ``"fr-civil"``."""
    _STOP = {"code", "loi", "act", "law", "règlement", "regulation"}
    parts = [p for p in code.lower().split() if p not in _STOP]
    slug = "-".join(parts) or code.lower().replace(" ", "-")
    return f"{jurisdiction.lower()}-{slug}"


def _article_number_from_id(article_id: str) -> str:
    """Extract article number from id like ``"fr-civil-1103"`` → ``"1103"``."""
    parts = article_id.rsplit("-", 1)
    return parts[-1] if len(parts) > 1 else article_id


def _hierarchy_val(chunk: LegalChunk, key: str) -> str | None:
    hierarchy: Any = chunk.metadata.get("hierarchy", {})
    if isinstance(hierarchy, dict):
        val = hierarchy.get(key)
        return str(val) if val is not None else None
    return None
