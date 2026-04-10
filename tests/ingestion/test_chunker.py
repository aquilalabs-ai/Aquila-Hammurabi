"""Tests for the LegalChunker."""

from __future__ import annotations

from hammurabi.ingestion.chunker import LegalChunker, _count_tokens, _get_encoder, _split_by_tokens
from hammurabi.ingestion.models import (
    DocumentType,
    LegalChunk,
    LegalDocument,
    LegalSegment,
    NERResult,
    SourceType,
)

_CHUNKER = LegalChunker()


# ---------------------------------------------------------------------------
# Token helpers
# ---------------------------------------------------------------------------


def test_count_tokens_short_text() -> None:
    enc = _get_encoder()
    count = _count_tokens("Hello world", enc)
    assert count > 0


def test_split_short_text_single_chunk() -> None:
    enc = _get_encoder()
    chunks = _split_by_tokens("Short text that fits easily.", enc, max_tokens=512, overlap=50)
    assert len(chunks) == 1
    assert chunks[0] == "Short text that fits easily."


def test_split_long_text_multiple_chunks() -> None:
    enc = _get_encoder()
    # Generate text with ~600 tokens
    long_text = " ".join(["word"] * 600)
    chunks = _split_by_tokens(long_text, enc, max_tokens=512, overlap=50)
    assert len(chunks) >= 2
    # All chunks stay within max_tokens
    for chunk in chunks:
        assert _count_tokens(chunk, enc) <= 512


def test_split_overlap_text_recovered() -> None:
    enc = _get_encoder()
    long_text = " ".join([f"word{i}" for i in range(600)])
    chunks = _split_by_tokens(long_text, enc, max_tokens=100, overlap=20)
    # Every chunk (except last) should share ~20 tokens with the next
    assert len(chunks) >= 2


# ---------------------------------------------------------------------------
# chunk_segment
# ---------------------------------------------------------------------------


def test_chunk_segment_single_article() -> None:
    seg = LegalSegment(
        segment_type="article",
        text="Les contrats légalement formés tiennent lieu de loi.",
        heading="Force obligatoire",
        article_number="1103",
    )
    chunks = _CHUNKER.chunk_segment(seg, source_type="pdf", jurisdiction="FR", code="Civil Code")
    assert len(chunks) == 1
    chunk = chunks[0]
    assert chunk.article_id == "fr-civil-1103"
    assert chunk.jurisdiction == "FR"
    assert chunk.source_type == "pdf"
    assert chunk.token_count > 0


def test_chunk_segment_preserves_metadata() -> None:
    seg = LegalSegment(
        segment_type="article",
        text="Content.",
        article_number="5",
        hierarchy={"title": "Title I"},
    )
    chunks = _CHUNKER.chunk_segment(seg, source_type="xml", jurisdiction="EU", code="GDPR")
    assert chunks[0].metadata["hierarchy"] == {"title": "Title I"}


def test_chunk_segment_no_code_no_article_id() -> None:
    seg = LegalSegment(segment_type="clause", text="Clause content.", article_number="2.1")
    chunks = _CHUNKER.chunk_segment(seg, source_type="docx", jurisdiction="FR", code=None)
    assert chunks[0].article_id is None


def test_chunk_segment_long_text_splits() -> None:
    long_text = " ".join(["word"] * 600)
    seg = LegalSegment(segment_type="article", text=long_text, article_number="999")
    chunks = _CHUNKER.chunk_segment(seg, source_type="pdf", jurisdiction="FR", code="Code")
    assert len(chunks) >= 2
    # chunk_index increments
    assert chunks[0].chunk_index == 0
    assert chunks[1].chunk_index == 1
    # split_part flag on second+ chunks
    assert chunks[1].metadata.get("split_part") == 1


# ---------------------------------------------------------------------------
# chunk_document
# ---------------------------------------------------------------------------


def _make_statute_doc(texts: list[str]) -> LegalDocument:
    doc = LegalDocument(
        source_type=SourceType.XML,
        document_type=DocumentType.STATUTE,
        raw_text="\n".join(texts),
    )
    doc.segments = [
        LegalSegment(
            segment_type="article",
            text=t,
            article_number=str(i + 1),
        )
        for i, t in enumerate(texts)
    ]
    return doc


def test_chunk_document_returns_flat_list() -> None:
    doc = _make_statute_doc(["Article one content.", "Article two content."])
    chunks = _CHUNKER.chunk_document(doc, jurisdiction="FR", code="Civil Code")
    assert len(chunks) == 2
    assert all(isinstance(c, LegalChunk) for c in chunks)


def test_chunk_document_index_continuity() -> None:
    doc = _make_statute_doc(["A.", "B.", "C."])
    chunks = _CHUNKER.chunk_document(doc, jurisdiction="FR", code="Code")
    indices = [c.chunk_index for c in chunks]
    assert indices == list(range(len(chunks)))


def test_chunk_document_ner_overrides_jurisdiction() -> None:
    doc = _make_statute_doc(["Content."])
    ner = NERResult(jurisdictions=["EU"], tags=["regulation"])
    chunks = _CHUNKER.chunk_document(doc, ner_result=ner, jurisdiction="FR", code="GDPR")
    assert chunks[0].jurisdiction == "EU"
    assert "regulation" in chunks[0].tags


def test_chunk_document_no_segments_uses_raw_text() -> None:
    doc = LegalDocument(
        source_type=SourceType.URL,
        document_type=DocumentType.STATUTE,
        raw_text="Some raw content without explicit segments.",
    )
    # segments list is empty
    chunks = _CHUNKER.chunk_document(doc, jurisdiction="FR")
    assert len(chunks) >= 1
    assert "raw content" in chunks[0].text


def test_chunk_document_effective_date_propagated() -> None:
    doc = _make_statute_doc(["Content."])
    ner = NERResult(effective_date="2016-10-01")
    chunks = _CHUNKER.chunk_document(doc, ner_result=ner, jurisdiction="FR")
    assert chunks[0].effective_date == "2016-10-01"
