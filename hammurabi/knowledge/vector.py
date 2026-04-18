"""Qdrant vector store — async hybrid dense + sparse search with RRF.

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

import asyncio
import hashlib
import logging
import re
import uuid
from collections import Counter
from datetime import date, datetime
from typing import TYPE_CHECKING, Any

from hammurabi.config import settings
from hammurabi.ingestion.models import LegalChunk
from hammurabi.knowledge.models import SearchResult

if TYPE_CHECKING:
    from openai import AsyncOpenAI
    from qdrant_client import AsyncQdrantClient
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

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Collection names
# ---------------------------------------------------------------------------

COLLECTION_STATUTES = "hammurabi_statutes"
COLLECTION_CASES = "hammurabi_cases"
COLLECTION_DOCUMENTS = "hammurabi_documents"

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
        "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for",
        "of", "with", "by", "from", "as", "is", "was", "are", "were", "be",
        "been", "being", "have", "has", "had", "do", "does", "did", "will",
        "would", "could", "should", "may", "might", "shall", "can", "not",
        "no", "nor", "so", "yet", "both", "either", "neither", "each",
        "le", "la", "les", "de", "du", "des", "et", "en", "un", "une",
        "que", "qui", "ce", "se", "sa", "son", "ses", "au", "aux",
    }
)

_TOKEN_RE = re.compile(r"\b[a-zA-Zàáâãäåæçèéêëìíîïðñòóôõöùúûüýþÿ]{3,}\b")


def _sparse_vector(text: str) -> tuple[list[int], list[float]]:
    """Convert *text* to a sparse TF vector suitable for Qdrant."""
    tokens = [t for t in _TOKEN_RE.findall(text.lower()) if t not in _STOPWORDS]
    if not tokens:
        return [], []

    tf = Counter(tokens)
    total = len(tokens)
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
    if iso is None:
        return None
    try:
        return datetime.fromisoformat(iso).date()
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Singletons
# ---------------------------------------------------------------------------

_QDRANT: Any = None
_OPENAI: Any = None


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


def _get_openai() -> Any:
    global _OPENAI  # noqa: PLW0603
    if _OPENAI is None:
        from openai import AsyncOpenAI  # noqa: PLC0415

        _OPENAI = AsyncOpenAI(
            base_url=settings.embedding_base_url,
            api_key=settings.embedding_api_key,
        )
    return _OPENAI


# ---------------------------------------------------------------------------
# Embedding helper — OpenAI SDK with exponential-backoff retry
# ---------------------------------------------------------------------------


_EMBED_BATCH_MAX = 25


async def _embed_batch(texts: list[str], retries: int = 3) -> list[list[float]]:
    """Embed a single batch (≤ _EMBED_BATCH_MAX) with retry."""
    client = _get_openai()
    last_exc: Exception | None = None

    for attempt in range(retries):
        try:
            response = await client.embeddings.create(
                model=settings.embedding_model,
                input=texts,
            )
            return [item.embedding for item in response.data]
        except Exception as exc:
            last_exc = exc
            if attempt < retries - 1:
                wait = 2**attempt
                logger.warning(
                    "embed attempt %d/%d failed (%s) — retrying in %ds",
                    attempt + 1, retries, exc, wait,
                )
                await asyncio.sleep(wait)

    raise RuntimeError(f"Embedding failed after {retries} attempts") from last_exc


async def _embed(texts: list[str]) -> list[list[float]]:
    """Embed *texts*, splitting into provider-safe sub-batches automatically."""
    results: list[list[float]] = []
    for i in range(0, len(texts), _EMBED_BATCH_MAX):
        results.extend(await _embed_batch(texts[i : i + _EMBED_BATCH_MAX]))
    return results


# ---------------------------------------------------------------------------
# Vector store
# ---------------------------------------------------------------------------


class LegalVectorStore:
    """Async Qdrant client for the Hammurabi legal vector store."""

    def __init__(self) -> None:
        self._initialised: set[str] = set()

    async def close(self) -> None:
        global _QDRANT, _OPENAI  # noqa: PLW0603
        if _QDRANT is not None:
            await _QDRANT.close()
            _QDRANT = None
        if _OPENAI is not None:
            await _OPENAI.close()
            _OPENAI = None
        self._initialised.clear()

    # ------------------------------------------------------------------
    # Collection management
    # ------------------------------------------------------------------

    async def _ensure_collection(self, name: str) -> None:
        """Create *name* with dense + sparse vector spaces if absent.

        Raises :class:`ValueError` if the collection exists with a mismatched
        dense vector dimension — prevents silent garbage results.
        """
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

        if name in existing:
            info = await client.get_collection(name)
            existing_size = info.config.params.vectors["dense"].size  # type: ignore[index]
            if existing_size != settings.embedding_dim:
                raise ValueError(
                    f"Collection '{name}' exists with dense size {existing_size} but "
                    f"EMBEDDING_DIM={settings.embedding_dim}. Drop the collection or "
                    "update EMBEDDING_DIM to match."
                )
        else:
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
        """Embed and upsert *chunks* into the appropriate Qdrant collections."""
        from qdrant_client.http.models import PointStruct, SparseVector  # noqa: PLC0415

        if not chunks:
            return 0

        by_collection: dict[str, list[LegalChunk]] = {}
        for chunk in chunks:
            col = _collection_for_chunk(chunk)
            by_collection.setdefault(col, []).append(chunk)

        total = 0
        for collection, col_chunks in by_collection.items():
            await self._ensure_collection(collection)
            client = _get_qdrant()

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
                            if k in {
                                "heading", "segment_type", "court", "date",
                                "docket", "parties", "page_number",
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
        """Hybrid dense + sparse search with server-side RRF across collections."""
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

        dense_vec = (await _embed([query]))[0]
        sp_indices, sp_values = _sparse_vector(query)

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
                    Prefetch(query=dense_vec, using="dense", limit=top_k * 2),
                    Prefetch(
                        query=SparseVector(indices=sp_indices, values=sp_values),
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
