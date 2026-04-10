"""Knowledge layer data models — returned by graph and vector queries."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class SearchResult:
    """A single ranked result from the hybrid vector search."""

    text: str
    score: float
    source_type: str
    jurisdiction: str
    article_id: str | None
    case_id: str | None
    tags: list[str]
    payload: dict[str, Any]


@dataclass
class ArticleContext:
    """Full context for a legal article — node data + related graph neighbours."""

    article: dict[str, Any]
    amendments: list[dict[str, Any]]
    interpreting_cases: list[dict[str, Any]]
    citing_articles: list[dict[str, Any]]


@dataclass
class CaseContext:
    """Full context for a case — node data + citations in both directions."""

    case: dict[str, Any]
    cited_articles: list[dict[str, Any]]
    cited_cases: list[dict[str, Any]]
    subsequent_citations: list[dict[str, Any]]


@dataclass
class CitationChainEntry:
    """One path in the BFS citation network returned by get_citation_chain."""

    nodes: list[dict[str, Any]]
    depth: int


@dataclass
class IngestionSummary:
    """Counts returned after a corpus ingestion run."""

    articles_merged: int = 0
    cases_merged: int = 0
    references_created: int = 0
    chunks_upserted: int = 0
    corpus_id: str = ""
    errors: list[str] = field(default_factory=list)
