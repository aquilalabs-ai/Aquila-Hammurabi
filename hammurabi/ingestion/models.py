"""Shared data models for the ingestion layer."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class SourceType(StrEnum):
    PDF = "pdf"
    DOCX = "docx"
    XML = "xml"
    JSON = "json"
    URL = "url"


class DocumentType(StrEnum):
    STATUTE = "statute"
    CONTRACT = "contract"
    JUDGMENT = "judgment"
    REGULATION = "regulation"


@dataclass
class RawPage:
    """A single page extracted from a source document."""

    number: int
    text: str


@dataclass
class LegalSegment:
    """A discrete legal unit extracted during segmentation.

    ``segment_type`` is one of: ``article``, ``clause``, ``title``,
    ``chapter``, ``section``, ``judgment_part``.
    """

    segment_type: str
    text: str
    heading: str | None = None
    article_number: str | None = None
    page_number: int | None = None
    # Ancestor hierarchy — keys: "title", "chapter", "section"
    hierarchy: dict[str, str] = field(default_factory=dict)
    # Article identifiers found in the body text of this segment
    cross_references: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class LegalDocument:
    """Raw parsed document produced by a :class:`LegalSourceLoader`."""

    source_type: SourceType
    document_type: DocumentType
    raw_text: str
    pages: list[RawPage] = field(default_factory=list)
    segments: list[LegalSegment] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class NERResult:
    """Named entity extraction result for a single document or segment."""

    parties: list[str] = field(default_factory=list)
    dates: list[str] = field(default_factory=list)
    jurisdictions: list[str] = field(default_factory=list)
    monetary_amounts: list[str] = field(default_factory=list)
    deadlines: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    # First effective date found (ISO-8601 string when available)
    effective_date: str | None = None
    # Version string (e.g. "2016-02-10") for statute articles
    version: str | None = None


@dataclass
class LegalChunk:
    """Final indexable unit produced by the :class:`LegalChunker`.

    The ``metadata`` dict carries any loader/segmenter fields not captured by
    the named attributes above (e.g. page_number, court, docket, parties).
    """

    text: str
    source_type: str
    code: str | None
    article_id: str | None
    jurisdiction: str
    effective_date: str | None
    tags: list[str]
    chunk_index: int
    token_count: int
    metadata: dict[str, Any] = field(default_factory=dict)
