"""CaseLawLoader — ingests judgment text (PDF or structured JSON)."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from hammurabi.ingestion.models import (
    DocumentType,
    LegalDocument,
    LegalSegment,
    RawPage,
    SourceType,
)

# ---------------------------------------------------------------------------
# Header-field regexes for French / English judgments
# ---------------------------------------------------------------------------

_COURT_RE = re.compile(
    r"(?:Cour|Tribunal|Court|Supreme Court|Court of Appeal)[^\n]{0,80}",
    re.IGNORECASE,
)
_DATE_RE = re.compile(r"\b(\d{1,2}[\s/\-]\w+[\s/\-]\d{4}|\d{4}[\-/]\d{2}[\-/]\d{2})\b")
_DOCKET_RE = re.compile(
    r"(?:n[°o]?\s*|No\.?\s*|Docket\s+)(\d[\d\s\-/.]+)",
    re.IGNORECASE,
)

# Judgment structural markers (French + English)
_FLAGS = re.IGNORECASE | re.MULTILINE
_SECTION_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("facts", re.compile(r"^\s*(FAITS|FACTS|EN FAIT|BACKGROUND)\b", _FLAGS)),
    ("ratio_decidendi", re.compile(r"^\s*(MOTIFS|REASONS|ATTENDU QUE|EN DROIT|GROUNDS)\b", _FLAGS)),
    (
        "operative_part",
        re.compile(
            r"^\s*(PAR CES MOTIFS|DISPOSITIF|OPERATIVE PART|IT IS ORDERED)\b",
            _FLAGS,
        ),
    ),
]


def _extract_header(text: str) -> dict[str, str]:
    header: dict[str, str] = {}
    court_m = _COURT_RE.search(text[:500])
    if court_m:
        header["court"] = court_m.group(0).strip()
    date_m = _DATE_RE.search(text[:500])
    if date_m:
        header["date"] = date_m.group(1)
    docket_m = _DOCKET_RE.search(text[:500])
    if docket_m:
        header["docket"] = docket_m.group(1).strip()
    return header


def _split_into_sections(text: str) -> list[LegalSegment]:
    """Split judgment text on structural markers."""
    boundaries: list[tuple[int, str]] = []
    for name, pattern in _SECTION_PATTERNS:
        for m in pattern.finditer(text):
            boundaries.append((m.start(), name))

    if not boundaries:
        return [LegalSegment(segment_type="judgment_part", text=text.strip())]

    boundaries.sort()
    segments: list[LegalSegment] = []

    # Text before first marker → header section
    first_pos = boundaries[0][0]
    if first_pos > 0:
        segments.append(
            LegalSegment(
                segment_type="judgment_part",
                text=text[:first_pos].strip(),
                heading="header",
            )
        )

    for i, (pos, name) in enumerate(boundaries):
        end = boundaries[i + 1][0] if i + 1 < len(boundaries) else len(text)
        segments.append(
            LegalSegment(
                segment_type="judgment_part",
                text=text[pos:end].strip(),
                heading=name,
            )
        )

    return segments


def _load_json_judgment(path: Path) -> tuple[dict[str, Any], list[LegalSegment]]:
    """Parse a structured JSON judgment (CourtListener / custom export)."""
    data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))

    meta: dict[str, Any] = {
        "court": data.get("court") or data.get("court_full_name", ""),
        "date": data.get("date_filed") or data.get("date") or data.get("decision_date", ""),
        "docket": data.get("docket_number") or data.get("docket", ""),
        "parties": data.get("case_name") or data.get("parties", ""),
    }

    # Body text: prefer plain_text, then html_with_citations stripped, then full_text
    body: str = data.get("plain_text") or data.get("text") or data.get("full_text") or ""
    # Strip basic HTML tags when present
    body = re.sub(r"<[^>]+>", " ", body).strip()

    segments = _split_into_sections(body) if body else []
    return meta, segments


class CaseLawLoader:
    """Load judgment text from a PDF or structured JSON file.

    For PDF sources the heavy lifting is delegated to :class:`PDFLoader`.
    For JSON the loader parses CourtListener-style exports directly.
    """

    # ------------------------------------------------------------------
    # LegalSourceLoader interface
    # ------------------------------------------------------------------

    def label(self) -> str:
        return "CaseLawLoader"

    def metadata(self, source: str | Path) -> dict[str, Any]:
        path = Path(source)
        if path.suffix.lower() == ".json":
            data = json.loads(path.read_text(encoding="utf-8"))
            return {
                "filename": path.name,
                "court": data.get("court") or data.get("court_full_name", ""),
                "date": data.get("date_filed") or data.get("date", ""),
                "docket": data.get("docket_number") or data.get("docket", ""),
            }
        return {"filename": path.name}

    def load(self, source: str | Path) -> LegalDocument:
        path = Path(source)
        suffix = path.suffix.lower()

        if suffix == ".json":
            meta, segments = _load_json_judgment(path)
            raw_text = "\n\n".join(s.text for s in segments)
            pages = [RawPage(number=1, text=raw_text)]
            return LegalDocument(
                source_type=SourceType.JSON,
                document_type=DocumentType.JUDGMENT,
                raw_text=raw_text,
                pages=pages,
                segments=segments,
                metadata=meta,
            )

        if suffix == ".pdf":
            # Delegate to PDFLoader then re-segment as a judgment
            from hammurabi.ingestion.loaders.pdf import PDFLoader  # noqa: PLC0415

            base_doc = PDFLoader(document_type=DocumentType.JUDGMENT).load(path)
            header = _extract_header(base_doc.raw_text)
            segments = _split_into_sections(base_doc.raw_text)
            base_doc.segments = segments
            base_doc.metadata.update(header)
            return base_doc

        raise ValueError(f"CaseLawLoader: unsupported file type '{suffix}'")
