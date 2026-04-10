"""StructuredCodeLoader — ingests JSON/XML legal codes (Légifrance, EUR-Lex)."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import TYPE_CHECKING, Any

from hammurabi.ingestion.models import (
    DocumentType,
    LegalDocument,
    LegalSegment,
    RawPage,
    SourceType,
)

if TYPE_CHECKING:
    from lxml import etree  # noqa: F401

# ---------------------------------------------------------------------------
# XML helpers
# ---------------------------------------------------------------------------

# Namespace patterns used by Légifrance / EUR-Lex XML exports
_NS_STRIP = re.compile(r"\{[^}]*\}")


def _tag(element: Any) -> str:
    """Return the local tag name without namespace."""
    return _NS_STRIP.sub("", element.tag)


def _text(element: Any) -> str:
    """Recursively gather all text content from an lxml element."""

    parts: list[str] = []
    if element.text:
        parts.append(element.text.strip())
    for child in element:
        parts.append(_text(child))
        if child.tail:
            parts.append(child.tail.strip())
    return " ".join(p for p in parts if p)


def _load_xml(path: Path) -> list[LegalSegment]:
    """Parse a Légifrance / EUR-Lex style XML file into article segments."""
    from lxml import etree  # noqa: PLC0415

    tree = etree.parse(str(path))
    root = tree.getroot()

    segments: list[LegalSegment] = []
    hierarchy: dict[str, str] = {}

    def _walk(node: Any, depth: int = 0) -> None:
        local = _tag(node)
        attrib: dict[str, str] = dict(node.attrib)

        if local in ("TITRE", "TITRE_TM", "TITRE_TA"):
            hierarchy["title"] = _text(node) or attrib.get("id", "")
        elif local in ("CHAPITRE", "CHAPITRE_TM"):
            hierarchy["chapter"] = _text(node) or attrib.get("id", "")
        elif local in ("SECTION", "SECTION_TA"):
            hierarchy["section"] = _text(node) or attrib.get("id", "")
        elif local in ("ARTICLE", "article"):
            article_num = attrib.get("num") or attrib.get("id") or attrib.get("eId", "")
            # Prefer the child <CONTENU> or <alinea> body if present
            body_nodes = [c for c in node if _tag(c) in ("CONTENU", "alinea", "p", "content")]
            body = " ".join(_text(b) for b in body_nodes) if body_nodes else _text(node)
            heading_node = next((c for c in node if _tag(c) in ("NOTA", "TITRE", "heading")), None)
            heading = _text(heading_node) if heading_node is not None else None

            if body.strip():
                segments.append(
                    LegalSegment(
                        segment_type="article",
                        text=body.strip(),
                        heading=heading,
                        article_number=article_num or None,
                        hierarchy=dict(hierarchy),
                        metadata={"xml_attrib": attrib},
                    )
                )
            return  # don't recurse into article children

        for child in node:
            _walk(child, depth + 1)

    _walk(root)
    return segments


# ---------------------------------------------------------------------------
# JSON helpers
# ---------------------------------------------------------------------------


def _load_json(path: Path) -> list[LegalSegment]:
    """Parse a JSON legal code export into article segments.

    Expected shapes (flexible):
    - list of article objects with keys ``number``/``id``, ``content``/``text``
    - dict with ``articles`` key
    - nested dict with ``titles`` → ``chapters`` → ``articles``
    """
    raw = json.loads(path.read_text(encoding="utf-8"))

    articles: list[dict[str, Any]] = []

    if isinstance(raw, list):
        articles = [a for a in raw if isinstance(a, dict)]
    elif isinstance(raw, dict):
        if "articles" in raw:
            articles = raw["articles"]
        elif "titles" in raw:
            for title in raw["titles"]:
                for chapter in title.get("chapters", []):
                    for section in chapter.get("sections", [chapter]):
                        articles.extend(section.get("articles", []))
        else:
            # Flat dict keyed by article ID
            articles = [{"id": k, "content": v} for k, v in raw.items() if isinstance(v, str)]

    segments: list[LegalSegment] = []
    for art in articles:
        num = str(art.get("number") or art.get("num") or art.get("id") or "")
        text = str(art.get("content") or art.get("text") or art.get("body") or "").strip()
        if not text:
            continue
        segments.append(
            LegalSegment(
                segment_type="article",
                text=text,
                heading=art.get("heading") or art.get("title"),
                article_number=num or None,
                hierarchy={
                    "title": art.get("title_name", ""),
                    "chapter": art.get("chapter_name", ""),
                    "section": art.get("section_name", ""),
                },
                metadata={k: v for k, v in art.items() if k not in ("content", "text", "body")},
            )
        )
    return segments


# ---------------------------------------------------------------------------
# Loader
# ---------------------------------------------------------------------------


class StructuredCodeLoader:
    """Ingest a JSON or XML legal code export and produce article segments.

    Supports:
    - Légifrance XML (``LEGI`` format) and generic EUR-Lex XML
    - JSON exports with articles as top-level list or nested under ``articles``
    """

    def __init__(self, jurisdiction: str = "FR", code_name: str = "") -> None:
        self._jurisdiction = jurisdiction
        self._code_name = code_name

    # ------------------------------------------------------------------
    # LegalSourceLoader interface
    # ------------------------------------------------------------------

    def label(self) -> str:
        return "StructuredCodeLoader"

    def metadata(self, source: str | Path) -> dict[str, Any]:
        path = Path(source)
        return {
            "filename": path.name,
            "suffix": path.suffix.lower(),
            "jurisdiction": self._jurisdiction,
            "code_name": self._code_name,
        }

    def load(self, source: str | Path) -> LegalDocument:
        path = Path(source)
        suffix = path.suffix.lower()

        if suffix in (".xml", ".xhtml"):
            segments = _load_xml(path)
        elif suffix in (".json",):
            segments = _load_json(path)
        else:
            raise ValueError(f"StructuredCodeLoader: unsupported file type '{suffix}'")

        raw_text = "\n\n".join(s.text for s in segments)
        pages = [RawPage(number=1, text=raw_text)]

        return LegalDocument(
            source_type=SourceType.XML if suffix in (".xml", ".xhtml") else SourceType.JSON,
            document_type=DocumentType.STATUTE,
            raw_text=raw_text,
            pages=pages,
            segments=segments,
            metadata=self.metadata(path),
        )
