"""Qdrant vector store — async embed + hybrid dense/sparse search with RRF.

Architecture
------------
* Three collections, one per document class:
  - ``hammurabi_statutes``  — statute articles
  - ``hammurabi_cases``     — case law chunks
  - ``hammurabi_documents`` — user-uploaded contracts / regulations

* Each collection carries two named vector spaces:
  - ``"dense"``  — cosine embedding from the configured embedding model
  - ``"sparse"`` — term-frequency sparse vector (BM25-like, no external model)

* Hybrid search uses Qdrant's ``Prefetch`` + ``FusionQuery(Fusion.RRF)`` to
  merge ranked lists from both spaces in a single server-side pass.

Imports of ``qdrant_client`` types are guarded behind ``TYPE_CHECKING`` so that
importing this module never triggers the driver at startup.
"""

from __future__ import annotations

import hashlib
import re
import uuid
from collections import Counter
from datetime import date, datetime
from typing import TYPE_CHECKING, Any

import httpx

from hammurabi.config import settings
from hammurabi.ingestion.models import LegalChunk
from hammurabi.knowledge.models import SearchResult

if TYPE_CHECKING:
    from qdrant_client import AsyncQdrantClient  # noqa: F401
    from qdrant_client.http.models import (  # noqa: F401
        Distance,
        Filter,
        PointStruct,
        Prefetch,
        SparseIndexParams,
        SparseVector,
        SparseVectorParams,
        VectorParams,
    )

# ---------------------------------------------------------------------------
# Collection names
# ---------------------------------------------------------------------------

COLLECTION_STATUTES = "hammurabi_statutes"
COLLECTION_CASES = "hammurabi_cases"
COLLECTION_DOCUMENTS = "hammurabi_documents"

# Map segment_type → collection name
_SEGMENT_TO_COLLECTION: dict[str, str] = {
    "article": COLLECTION_STATUTES,
    "judgment_part": COLLECTION_CASES,
}


def _collection_for_chunk(chunk: LegalChunk) -> str:
    if chunk.article_id:
        return COLLECTION_STATUTES
    seg_type: str = chunk.metadata.get("segment_type", "")
    return _SEGMENT_TO_COLLECTION.get(seg_type, COLLECTION_DOCUMENTS)


# ---------------------------------------------------------------------------
# Sparse vector (BM25-style TF tokeniser — no external model required)
# ---------------------------------------------------------------------------

_STOPWORDS: frozenset[str] = frozenset(
    {
        "the",
        "a",
        "an",
        "and",
        "or",
        "but",
        "in",
        "on",
        "at",
        "to",
        "for",
        "of",
        "with",
        "by",
        "from",
        "as",
        "is",
        "was",
        "are",
        "were",
        "be",
        "been",
        "being",
        "have",
        "has",
        "had",
        "do",
        "does",
        "did",
        "will",
        "would",
        "could",
        "should",
        "may",
        "might",
        "shall",
        "can",
        "not",
        "no",
        "nor",
        "so",
        "yet",
        "both",
        "either",
        "neither",
        "each",
        "le",
        "la",
        "les",
        "de",
        "du",
        "des",
        "et",
        "en",
        "un",
        "une",
        "que",
        "qui",
        "ce",
        "se",
        "sa",
        "son",
        "ses",
        "au",
        "aux",
    }
)

_TOKEN_RE = re.compile(r"\b[a-zA-Zàáâãäåæçèéêëìíîïðñòóôõöùúûüýþÿ]{3,}\b")


def _sparse_vector(text: str) -> tuple[list[int], list[float]]:
    """Convert *text* to a sparse TF vector suitable for Qdrant.

    Each unique token is hashed to a 23-bit index (≤ 8 388 608 buckets).
    Weights are normalised term frequencies in [0, 1].
    """
    tokens = [t for t in _TOKEN_RE.findall(text.lower()) if t not in _STOPWORDS]
    if not tokens:
        return [], []

    tf = Counter(tokens)
    total = len(tokens)
    # Accumulate weight per bucket (handles rare hash collisions gracefully)
    bucket: dict[int, float] = {}
    for token, count in tf.items():
        idx = int(hashlib.md5(token.encode()).hexdigest(), 16) % (2**23)
        bucket[idx] = bucket.get(idx, 0.0) + count / total

    indices = list(bucket.keys())
    values = [bucket[i] for i in indices]
    return indices, values


# ---------------------------------------------------------------------------
# Date helper
# ---------------------------------------------------------------------------


def _parse_date(iso: str | None) -> date | None:
    """Parse an ISO-8601 date string (``"2016-10-01"``) to a :class:`date` object."""
    if iso is None:
        return None
    try:
        return datetime.fromisoformat(iso).date()
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Embedding helper
# ---------------------------------------------------------------------------


async def _embed(texts: list[str]) -> list[list[float]]:
    """Call the configured OpenAI-compatible embeddings endpoint for *texts*."""
    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(
            f"{settings.embedding_base_url}/embeddings",
            headers={"Authorization": f"Bearer {settings.embedding_api_key}"},
            json={"model": settings.embedding_model, "input": texts},
        )
        resp.raise_for_status()
    data: list[dict[str, Any]] = resp.json()["data"]
    # Sort by index to preserve input order
    data.sort(key=lambda x: x["index"])
    return [item["embedding"] for item in data]


# ---------------------------------------------------------------------------
# Qdrant client singleton
# ---------------------------------------------------------------------------

_QDRANT: Any = None


def _get_qdrant() -> Any:
    global _QDRANT  # noqa: PLW0603
    if _QDRANT is None:
        from qdrant_client import AsyncQdrantClient  # noqa: PLC0415

        _QDRANT = AsyncQdrantClient(
            host=settings.qdrant_host,
            port=settings.qdrant_port,
            api_key=settings.qdrant_api_key,
        )
    return _QDRANT


# ---------------------------------------------------------------------------
# Vector store client
# ---------------------------------------------------------------------------


class LegalVectorStore:
    """Async Qdrant client for the Hammurabi legal vector store.

    Collections are created lazily on first upsert; no manual setup required
    beyond having Qdrant running.
    """

    def __init__(self) -> None:
        self._initialised: set[str] = set()

    async def close(self) -> None:
        """Close the shared Qdrant client."""
        global _QDRANT  # noqa: PLW0603
        if _QDRANT is not None:
            await _QDRANT.close()
            _QDRANT = None
        self._initialised.clear()

    # ------------------------------------------------------------------
    # Collection management
    # ------------------------------------------------------------------

    async def _ensure_collection(self, name: str) -> None:
        """Create *name* collection with dense + sparse vector spaces if absent."""
        if name in self._initialised:
            return

        from qdrant_client.http.models import (  # noqa: PLC0415
            Distance,
            SparseIndexParams,
            SparseVectorParams,
            VectorParams,
        )

        client = _get_qdrant()
        existing = {c.name for c in (await client.get_collections()).collections}
        if name not in existing:
            await client.create_collection(
                collection_name=name,
                vectors_config={
                    "dense": VectorParams(
                        size=settings.embedding_dim,
                        distance=Distance.COSINE,
                    )
                },
                sparse_vectors_config={
                    "sparse": SparseVectorParams(index=SparseIndexParams(on_disk=False))
                },
            )
        self._initialised.add(name)

    # ------------------------------------------------------------------
    # Upsert
    # ------------------------------------------------------------------

    async def upsert_chunks(
        self,
        chunks: list[LegalChunk],
        corpus_id: str,
        batch_size: int = 32,
    ) -> int:
        """Embed and upsert *chunks* into the appropriate Qdrant collections.

        Returns the number of points upserted.
        """
        from qdrant_client.http.models import PointStruct, SparseVector  # noqa: PLC0415

        if not chunks:
            return 0

        # Group chunks by target collection
        by_collection: dict[str, list[LegalChunk]] = {}
        for chunk in chunks:
            col = _collection_for_chunk(chunk)
            by_collection.setdefault(col, []).append(chunk)

        total = 0
        for collection, col_chunks in by_collection.items():
            await self._ensure_collection(collection)
            client = _get_qdrant()

            # Process in batches to respect memory / API limits
            for i in range(0, len(col_chunks), batch_size):
                batch = col_chunks[i : i + batch_size]
                embeddings = await _embed([c.text for c in batch])

                points: list[Any] = []
                for chunk, dense_vec in zip(batch, embeddings, strict=True):
                    sp_indices, sp_values = _sparse_vector(chunk.text)
                    payload: dict[str, Any] = {
                        "text": chunk.text,
                        "source_type": chunk.source_type,
                        "jurisdiction": chunk.jurisdiction,
                        "code": chunk.code,
                        "article_id": chunk.article_id,
                        "case_id": chunk.metadata.get("case_id"),
                        "tags": chunk.tags,
                        "effective_date": chunk.effective_date,
                        "chunk_index": chunk.chunk_index,
                        "corpus_id": corpus_id,
                        **{
                            k: v
                            for k, v in chunk.metadata.items()
                            if k
                            in {
                                "heading",
                                "segment_type",
                                "court",
                                "date",
                                "docket",
                                "parties",
                                "page_number",
                            }
                        },
                    }
                    points.append(
                        PointStruct(
                            id=str(uuid.uuid4()),
                            vector={
                                "dense": dense_vec,
                                "sparse": SparseVector(
                                    indices=sp_indices,
                                    values=sp_values,
                                ),
                            },
                            payload=payload,
                        )
                    )

                await client.upsert(collection_name=collection, points=points)
                total += len(points)

        return total

    # ------------------------------------------------------------------
    # Hybrid search
    # ------------------------------------------------------------------

    async def search(
        self,
        query: str,
        *,
        jurisdiction: str | None = None,
        source_type: str | None = None,
        tags: list[str] | None = None,
        effective_date_from: str | None = None,
        effective_date_to: str | None = None,
        top_k: int = 10,
        collections: list[str] | None = None,
    ) -> list[SearchResult]:
        """Hybrid dense + sparse search with RRF merging across collections.

        Parameters
        ----------
        query:
            Natural-language search query.
        jurisdiction:
            ISO jurisdiction filter (e.g. ``"FR"``).
        source_type:
            Payload ``source_type`` filter (e.g. ``"xml"``).
        tags:
            At least one tag must be present in the chunk's tag list.
        effective_date_from / effective_date_to:
            ISO-8601 date strings for date-range filtering on ``effective_date``.
        top_k:
            Number of results to return per collection.
        collections:
            Explicit list of collection names to search; defaults to all three.
        """
        from qdrant_client.http.models import (  # noqa: PLC0415
            DatetimeRange,
            FieldCondition,
            Filter,
            FusionQuery,
            MatchValue,
            Prefetch,
            SparseVector,
        )
        from qdrant_client.models import Fusion  # noqa: PLC0415

        target_collections = collections or [
            COLLECTION_STATUTES,
            COLLECTION_CASES,
            COLLECTION_DOCUMENTS,
        ]

        # Embed query
        dense_vec = (await _embed([query]))[0]
        sp_indices, sp_values = _sparse_vector(query)

        # Build filter
        must_conditions: list[Any] = []
        if jurisdiction:
            must_conditions.append(
                FieldCondition(key="jurisdiction", match=MatchValue(value=jurisdiction))
            )
        if source_type:
            must_conditions.append(
                FieldCondition(key="source_type", match=MatchValue(value=source_type))
            )
        if tags:
            must_conditions.append(FieldCondition(key="tags", match=MatchValue(value=tags[0])))
        if effective_date_from or effective_date_to:
            must_conditions.append(
                FieldCondition(
                    key="effective_date",
                    range=DatetimeRange(
                        gte=_parse_date(effective_date_from),
                        lte=_parse_date(effective_date_to),
                    ),
                )
            )
        qdrant_filter: Any = Filter(must=must_conditions) if must_conditions else None

        client = _get_qdrant()
        results: list[SearchResult] = []

        for collection in target_collections:
            existing = {c.name for c in (await client.get_collections()).collections}
            if collection not in existing:
                continue

            response = await client.query_points(
                collection_name=collection,
                prefetch=[
                    Prefetch(
                        query=dense_vec,
                        using="dense",
                        limit=top_k * 2,
                    ),
                    Prefetch(
                        query=SparseVector(
                            indices=sp_indices,
                            values=sp_values,
                        ),
                        using="sparse",
                        limit=top_k * 2,
                    ),
                ],
                query=FusionQuery(fusion=Fusion.RRF),
                limit=top_k,
                query_filter=qdrant_filter,
                with_payload=True,
            )

            for point in response.points:
                payload: dict[str, Any] = dict(point.payload or {})
                results.append(
                    SearchResult(
                        text=payload.get("text", ""),
                        score=point.score,
                        source_type=payload.get("source_type", ""),
                        jurisdiction=payload.get("jurisdiction", ""),
                        article_id=payload.get("article_id"),
                        case_id=payload.get("case_id"),
                        tags=payload.get("tags", []),
                        payload=payload,
                    )
                )

        # Re-rank across collections by score (descending)
        results.sort(key=lambda r: r.score, reverse=True)
        return results[:top_k]

    # ------------------------------------------------------------------
    # Deletion
    # ------------------------------------------------------------------

    async def delete_corpus(self, corpus_id: str) -> None:
        """Delete all points tagged with *corpus_id* from every collection."""
        from qdrant_client.http.models import FieldCondition, Filter, MatchValue  # noqa: PLC0415

        client = _get_qdrant()
        for collection in (COLLECTION_STATUTES, COLLECTION_CASES, COLLECTION_DOCUMENTS):
            existing = {c.name for c in (await client.get_collections()).collections}
            if collection not in existing:
                continue
            await client.delete(
                collection_name=collection,
                points_selector=Filter(
                    must=[FieldCondition(key="corpus_id", match=MatchValue(value=corpus_id))]
                ),
            )
