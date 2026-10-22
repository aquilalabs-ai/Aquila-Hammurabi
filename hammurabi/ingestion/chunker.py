"""Legal chunker — token-aware splitting of legal segments into indexable chunks."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from hammurabi.ingestion.models import LegalChunk, LegalDocument, LegalSegment, NERResult

if TYPE_CHECKING:
    import tiktoken  # noqa: F401

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_ENCODING_NAME = "cl100k_base"
_MAX_TOKENS = 512
_OVERLAP_TOKENS = 50


# ---------------------------------------------------------------------------
# Token helpers
# ---------------------------------------------------------------------------


def _get_encoder() -> Any:
    import tiktoken  # noqa: PLC0415

    return tiktoken.get_encoding(_ENCODING_NAME)


def _count_tokens(text: str, encoder: Any) -> int:
    return len(encoder.encode(text))


def _split_by_tokens(
    text: str,
    encoder: Any,
    max_tokens: int = _MAX_TOKENS,
    overlap: int = _OVERLAP_TOKENS,
) -> list[str]:
    """Split *text* into token-bounded chunks with *overlap* token overlap.

    When the text fits within *max_tokens* it is returned as-is (single chunk).
    Otherwise the token list is sliced with a stride of ``max_tokens - overlap``.
    """
    tokens = encoder.encode(text)
    if len(tokens) <= max_tokens:
        return [text]

    chunks: list[str] = []
    stride = max_tokens - overlap
    start = 0
    while start < len(tokens):
        end = min(start + max_tokens, len(tokens))
        chunk_tokens = tokens[start:end]
        chunks.append(encoder.decode(chunk_tokens))
        if end == len(tokens):
            break
        start += stride

    return chunks


# ---------------------------------------------------------------------------
# Chunker
# ---------------------------------------------------------------------------


class LegalChunker:
    """Produce indexable :class:`~hammurabi.ingestion.models.LegalChunk` objects.

    Each :class:`~hammurabi.ingestion.models.LegalSegment` becomes one or more
    chunks:

    * If the segment text fits within *max_tokens* → one chunk.
    * Otherwise the text is split with *overlap_tokens* token overlap.

    ``NERResult`` (optional) enriches each chunk with tags and the jurisdiction
    detected at document level.

    Parameters
    ----------
    max_tokens:
        Maximum tokens per chunk (default: 512).
    overlap_tokens:
        Token overlap between consecutive chunks from the same segment
        (default: 50).
    """

    def __init__(
        self,
        max_tokens: int = _MAX_TOKENS,
        overlap_tokens: int = _OVERLAP_TOKENS,
    ) -> None:
        self._max_tokens = max_tokens
        self._overlap_tokens = overlap_tokens

    def chunk_document(
        self,
        document: LegalDocument,
        ner_result: NERResult | None = None,
        jurisdiction: str = "FR",
        code: str | None = None,
    ) -> list[LegalChunk]:
        """Chunk all segments in *document* and return flat list of chunks.

        Parameters
        ----------
        document:
            Parsed and segmented document.
        ner_result:
            Optional NER result for the whole document (tags / jurisdiction).
        jurisdiction:
            ISO jurisdiction code to embed in every chunk.
        code:
            Legal code name (e.g. ``"Civil Code"``).
        """
        encoder = _get_encoder()

        # Resolve jurisdiction: NER takes priority when available
        resolved_jurisdiction = jurisdiction
        if ner_result and ner_result.jurisdictions:
            resolved_jurisdiction = ner_result.jurisdictions[0]

        global_tags: list[str] = ner_result.tags if ner_result else []
        effective_date: str | None = ner_result.effective_date if ner_result else None

        all_chunks: list[LegalChunk] = []
        chunk_index = 0

        for segment in document.segments:
            chunks = self._chunk_segment(
                segment=segment,
                encoder=encoder,
                source_type=document.source_type.value,
                jurisdiction=resolved_jurisdiction,
                code=code,
                global_tags=global_tags,
                global_effective_date=effective_date,
                start_index=chunk_index,
            )
            all_chunks.extend(chunks)
            chunk_index += len(chunks)

        # If no segments, chunk raw_text directly
        if not document.segments:
            texts = _split_by_tokens(
                document.raw_text, encoder, self._max_tokens, self._overlap_tokens
            )
            for i, text in enumerate(texts):
                all_chunks.append(
                    LegalChunk(
                        text=text,
                        source_type=document.source_type.value,
                        code=code,
                        article_id=None,
                        jurisdiction=resolved_jurisdiction,
                        effective_date=effective_date,
                        tags=global_tags,
                        chunk_index=chunk_index + i,
                        token_count=_count_tokens(text, encoder),
                    )
                )

        return all_chunks

    def chunk_segment(
        self,
        segment: LegalSegment,
        source_type: str,
        jurisdiction: str = "FR",
        code: str | None = None,
        tags: list[str] | None = None,
        effective_date: str | None = None,
        start_index: int = 0,
    ) -> list[LegalChunk]:
        """Chunk a single segment (useful for incremental processing)."""
        encoder = _get_encoder()
        return self._chunk_segment(
            segment=segment,
            encoder=encoder,
            source_type=source_type,
            jurisdiction=jurisdiction,
            code=code,
            global_tags=tags or [],
            global_effective_date=effective_date,
            start_index=start_index,
        )

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _chunk_segment(
        self,
        segment: LegalSegment,
        encoder: Any,
        source_type: str,
        jurisdiction: str,
        code: str | None,
        global_tags: list[str],
        global_effective_date: str | None,
        start_index: int,
    ) -> list[LegalChunk]:
        texts = _split_by_tokens(segment.text, encoder, self._max_tokens, self._overlap_tokens)

        # Merge segment-level tags with global tags, deduplicated
        seg_tags = list(dict.fromkeys(global_tags + list(segment.metadata.get("tags", []))))
        seg_effective = segment.metadata.get("effective_date", global_effective_date)

        # Build article_id when possible
        article_id: str | None = None
        if segment.article_number and code:
            jur_lower = jurisdiction.lower()
            # Strip common suffixes so "Civil Code" → "civil", "Code Civil" → "civil"
            _STOP = {"code", "loi", "act", "law", "règlement", "regulation"}
            code_parts = [p for p in code.lower().split() if p not in _STOP]
            code_slug = "-".join(code_parts) or code.lower().replace(" ", "-")
            article_id = f"{jur_lower}-{code_slug}-{segment.article_number}"

        # Carry per-segment metadata
        seg_meta: dict[str, Any] = {
            "segment_type": segment.segment_type,
            "heading": segment.heading,
            "hierarchy": segment.hierarchy,
            "cross_references": segment.cross_references,
            **segment.metadata,
        }
        if segment.page_number is not None:
            seg_meta["page_number"] = segment.page_number

        chunks: list[LegalChunk] = []
        for i, text in enumerate(texts):
            chunks.append(
                LegalChunk(
                    text=text,
                    source_type=source_type,
                    code=code,
                    article_id=article_id,
                    jurisdiction=jurisdiction,
                    effective_date=seg_effective,
                    tags=seg_tags,
                    chunk_index=start_index + i,
                    token_count=_count_tokens(text, encoder),
                    metadata=seg_meta if i == 0 else {**seg_meta, "split_part": i},
                )
            )
        return chunks
