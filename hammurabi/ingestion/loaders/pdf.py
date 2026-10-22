"""PDF loader — pdfplumber-based, preserves page numbers and detects boundaries."""

from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING, Any

from hammurabi.ingestion.models import DocumentType, LegalDocument, RawPage, SourceType

if TYPE_CHECKING:
    import pdfplumber  # noqa: F401

# Patterns that suggest the document is a statute rather than a contract/judgment
_STATUTE_SIGNALS = re.compile(
    r"\b(article|loi|code|décret|règlement|ordonnance|statute|act\b|regulation)",
    re.IGNORECASE,
)
_JUDGMENT_SIGNALS = re.compile(
    r"\b(arrêt|jugement|tribunal|cour|attendu que|par ces motifs|judgment|court|held)\b",
    re.IGNORECASE,
)


def _detect_document_type(text: str) -> DocumentType:
    statute_hits = len(_STATUTE_SIGNALS.findall(text[:2000]))
    judgment_hits = len(_JUDGMENT_SIGNALS.findall(text[:2000]))
    if judgment_hits > statute_hits:
        return DocumentType.JUDGMENT
    if statute_hits > 2:
        return DocumentType.STATUTE
    return DocumentType.CONTRACT


class PDFLoader:
    """Load a PDF file using ``pdfplumber``.

    Page text is extracted verbatim; page numbers are 1-based.  The
    ``document_type`` can be supplied explicitly or is inferred from the
    first 2 000 characters.
    """

    def __init__(self, document_type: DocumentType | None = None) -> None:
        self._document_type = document_type

    # ------------------------------------------------------------------
    # LegalSourceLoader interface
    # ------------------------------------------------------------------

    def label(self) -> str:
        return "PDFLoader"

    def metadata(self, source: str | Path) -> dict[str, Any]:
        import pdfplumber

        path = Path(source)
        with pdfplumber.open(path) as pdf:
            page_count: int = len(pdf.pages)
            info: dict[str, Any] = pdf.metadata or {}
        return {
            "filename": path.name,
            "page_count": page_count,
            **{k: v for k, v in info.items() if isinstance(v, str | int | float)},
        }

    def load(self, source: str | Path) -> LegalDocument:
        import pdfplumber

        path = Path(source)
        pages: list[RawPage] = []

        with pdfplumber.open(path) as pdf:
            for page in pdf.pages:
                text: str = page.extract_text() or ""
                pages.append(RawPage(number=page.page_number, text=text))

        raw_text = "\n".join(p.text for p in pages)
        doc_type = self._document_type or _detect_document_type(raw_text)

        return LegalDocument(
            source_type=SourceType.PDF,
            document_type=doc_type,
            raw_text=raw_text,
            pages=pages,
            metadata=self.metadata(path),
        )
