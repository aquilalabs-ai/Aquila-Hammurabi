"""Tests for ingestion data models."""

from __future__ import annotations

from hammurabi.ingestion.models import (
    DocumentType,
    LegalChunk,
    LegalDocument,
    LegalSegment,
    NERResult,
    RawPage,
    SourceType,
)


def test_raw_page_fields() -> None:
    page = RawPage(number=3, text="some content")
    assert page.number == 3
    assert page.text == "some content"


def test_legal_segment_defaults() -> None:
    seg = LegalSegment(segment_type="article", text="Les contrats...")
    assert seg.heading is None
    assert seg.article_number is None
    assert seg.page_number is None
    assert seg.hierarchy == {}
    assert seg.cross_references == []
    assert seg.metadata == {}


def test_legal_segment_full() -> None:
    seg = LegalSegment(
        segment_type="article",
        text="Content.",
        heading="Binding force",
        article_number="1103",
        page_number=5,
        hierarchy={"title": "Title III", "chapter": "Chapter I"},
        cross_references=["1102", "1104"],
        metadata={"effective_date": "2016-10-01"},
    )
    assert seg.article_number == "1103"
    assert "1102" in seg.cross_references


def test_legal_document_defaults() -> None:
    doc = LegalDocument(
        source_type=SourceType.PDF,
        document_type=DocumentType.CONTRACT,
        raw_text="text",
    )
    assert doc.pages == []
    assert doc.segments == []
    assert doc.metadata == {}


def test_ner_result_defaults() -> None:
    r = NERResult()
    assert r.parties == []
    assert r.dates == []
    assert r.jurisdictions == []
    assert r.monetary_amounts == []
    assert r.deadlines == []
    assert r.tags == []
    assert r.effective_date is None
    assert r.version is None


def test_legal_chunk_fields() -> None:
    chunk = LegalChunk(
        text="Article content",
        source_type="pdf",
        code="Civil Code",
        article_id="fr-civil-1103",
        jurisdiction="FR",
        effective_date="2016-10-01",
        tags=["contract", "obligation"],
        chunk_index=0,
        token_count=42,
    )
    assert chunk.article_id == "fr-civil-1103"
    assert chunk.jurisdiction == "FR"
    assert chunk.token_count == 42
    assert chunk.metadata == {}


def test_source_type_values() -> None:
    assert SourceType.PDF == "pdf"
    assert SourceType.DOCX == "docx"
    assert SourceType.XML == "xml"
    assert SourceType.JSON == "json"
    assert SourceType.URL == "url"


def test_document_type_values() -> None:
    assert DocumentType.STATUTE == "statute"
    assert DocumentType.CONTRACT == "contract"
    assert DocumentType.JUDGMENT == "judgment"
    assert DocumentType.REGULATION == "regulation"
