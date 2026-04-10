"""DOCX loader — python-docx; heading hierarchy maps to section tree."""

from __future__ import annotations

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
    import docx  # noqa: F401

# python-docx heading style names (Heading 1 … Heading 6)
_HEADING_LEVEL: dict[str, int] = {f"heading {i}": i for i in range(1, 7)}

# Map heading depth to our hierarchy key
_LEVEL_TO_KEY: dict[int, str] = {
    1: "title",
    2: "chapter",
    3: "section",
    4: "article",
}


def _style_level(style_name: str) -> int | None:
    """Return the heading depth (1-based) or None for body paragraphs."""
    return _HEADING_LEVEL.get(style_name.lower())


class DOCXLoader:
    """Load a ``.docx`` file and convert the heading hierarchy to segments.

    Heading 1 → Title, Heading 2 → Chapter, Heading 3 → Section,
    Heading 4+ → Article/Clause.  Body paragraphs below a heading are
    attached to the nearest ancestor segment as ``text``.
    """

    def __init__(self, document_type: DocumentType = DocumentType.CONTRACT) -> None:
        self._document_type = document_type

    # ------------------------------------------------------------------
    # LegalSourceLoader interface
    # ------------------------------------------------------------------

    def label(self) -> str:
        return "DOCXLoader"

    def metadata(self, source: str | Path) -> dict[str, Any]:
        import docx

        path = Path(source)
        doc = docx.Document(str(path))
        core = doc.core_properties
        return {
            "filename": path.name,
            "author": core.author or "",
            "title": core.title or "",
            "created": str(core.created) if core.created else "",
            "modified": str(core.modified) if core.modified else "",
        }

    def load(self, source: str | Path) -> LegalDocument:
        import docx

        path = Path(source)
        document = docx.Document(str(path))

        segments: list[LegalSegment] = []
        # Current ancestor context
        hierarchy: dict[str, str] = {}
        current_heading: str | None = None
        current_level: int | None = None
        body_lines: list[str] = []

        def _flush(heading: str | None, level: int | None, lines: list[str]) -> None:
            if not lines and heading is None:
                return
            seg_type = _LEVEL_TO_KEY.get(level or 0, "section") if level else "clause"
            segments.append(
                LegalSegment(
                    segment_type=seg_type,
                    text="\n".join(lines).strip(),
                    heading=heading,
                    hierarchy=dict(hierarchy),
                )
            )

        all_lines: list[str] = []

        for para in document.paragraphs:
            text = para.text.strip()
            if not text:
                continue

            style_name = para.style.name if para.style else ""
            level = _style_level(style_name)
            all_lines.append(text)

            if level is not None:
                # Flush previous segment
                _flush(current_heading, current_level, body_lines)
                body_lines = []

                # Update hierarchy context — drop descendants of the current level
                key = _LEVEL_TO_KEY.get(level, "section")
                # _LEVEL_TO_KEY keys are ordered 1..4; drop any key with depth >= level
                hierarchy = {
                    k: v
                    for k, v in hierarchy.items()
                    for k_depth in [next((d for d, n in _LEVEL_TO_KEY.items() if n == k), 99)]
                    if k_depth < level
                }
                hierarchy[key] = text

                current_heading = text
                current_level = level
            else:
                body_lines.append(text)

        _flush(current_heading, current_level, body_lines)

        raw_text = "\n".join(all_lines)
        # Single synthetic "page" since DOCX has no pages
        pages = [RawPage(number=1, text=raw_text)]

        return LegalDocument(
            source_type=SourceType.DOCX,
            document_type=self._document_type,
            raw_text=raw_text,
            pages=pages,
            segments=segments,
            metadata=self.metadata(path),
        )
