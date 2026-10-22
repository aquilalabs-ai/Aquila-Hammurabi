"""Legal document segmenter — extracts structured segments from raw text."""

from __future__ import annotations

import re
from dataclasses import dataclass

from hammurabi.ingestion.models import DocumentType, LegalDocument, LegalSegment

# ---------------------------------------------------------------------------
# Article extraction patterns
# ---------------------------------------------------------------------------

# French statute patterns:  "Article 1103 — Binding force"  /  "ARTICLE L. 123-4"
_ARTICLE_FR = re.compile(
    r"^(?:Article|ARTICLE)\s+(L\.?\s*|R\.?\s*|D\.?\s*)?(\d+(?:[.\-]\d+)*)\s*[-—:–]?\s*(.*)$",
    re.MULTILINE | re.IGNORECASE,
)
# English statute patterns: "Section 12." / "§ 12" / "Art. 5"
_ARTICLE_EN = re.compile(
    r"^(?:Section|Art\.|§)\s*(\d+(?:\.\d+)*)[.\s—\-]*(.*)$",
    re.MULTILINE | re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Clause boundary patterns (contracts)
# ---------------------------------------------------------------------------

# Numbered clause:  "1."  "1.1"  "1.1.2"  at line start
_CLAUSE_NUMBERED = re.compile(
    r"^(\d+(?:\.\d+)+)\s+(.+)$",
    re.MULTILINE,
)
# Lettered sub-clause: "(a)" / "(i)" at line start
_CLAUSE_LETTERED = re.compile(
    r"^\s*\(([a-z]|[ivxlc]+)\)\s+(.+)$",
    re.MULTILINE | re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Heading hierarchy patterns
# ---------------------------------------------------------------------------

_TITLE_RE = re.compile(
    r"^(?:TITRE|TITLE|LIVRE|BOOK)\s+(?:[IVX]+|\d+)[.\s—\-]*(.*)$",
    re.MULTILINE | re.IGNORECASE,
)
_CHAPTER_RE = re.compile(
    r"^(?:CHAPITRE|CHAPTER)\s+(?:[IVX]+|\d+)[.\s—\-]*(.*)$",
    re.MULTILINE | re.IGNORECASE,
)
_SECTION_RE = re.compile(
    r"^(?:SECTION|SOUS-SECTION|SUB-SECTION)\s+(?:[IVX]+|\d+)[.\s—\-]*(.*)$",
    re.MULTILINE | re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Cross-reference patterns
# ---------------------------------------------------------------------------

_XREF_RE = re.compile(
    r"(?:"
    # English connectors — directly precede "Article"
    r"(?:pursuant to|as defined in|in accordance with|referred to in)"
    r"\s+(?:[Aa]rticle|[Aa]rt\.)"
    r"|"
    # French connectors — followed by optional "l'" then "article"
    r"(?:en application de|au sens de|visé(?:e)? à|conformément à)"
    r"(?:\s+l['''])?\s*(?:[Aa]rticle|[Aa]rt\.)"
    r")"
    r"\s+(L\.?\s*|R\.?\s*|D\.?\s*)?(\d+(?:[.\-]\d+)*)",
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Judgment structural markers
# ---------------------------------------------------------------------------

_ML = re.IGNORECASE | re.MULTILINE
_JUDGMENT_SECTIONS: list[tuple[str, re.Pattern[str]]] = [
    ("parties", re.compile(r"^\s*(ENTRE|BETWEEN|IN THE MATTER OF)\b", _ML)),
    ("facts", re.compile(r"^\s*(FAITS|FACTS|EN FAIT|BACKGROUND|EXPOSÉ)\b", _ML)),
    ("ratio_decidendi", re.compile(r"^\s*(MOTIFS|REASONS|ATTENDU QUE|EN DROIT|GROUNDS)\b", _ML)),
    (
        "operative_part",
        re.compile(
            r"^\s*(PAR CES MOTIFS|DISPOSITIF|OPERATIVE PART|IT IS ORDERED|HELD)\b",
            _ML,
        ),
    ),
]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@dataclass
class _HierarchyContext:
    title: str = ""
    chapter: str = ""
    section: str = ""

    def as_dict(self) -> dict[str, str]:
        return {"title": self.title, "chapter": self.chapter, "section": self.section}

    def update_from_line(self, line: str) -> bool:
        """Update context if *line* matches a heading pattern. Returns True on match."""
        m = _TITLE_RE.match(line)
        if m:
            self.title = line.strip()
            self.chapter = ""
            self.section = ""
            return True
        m = _CHAPTER_RE.match(line)
        if m:
            self.chapter = line.strip()
            self.section = ""
            return True
        m = _SECTION_RE.match(line)
        if m:
            self.section = line.strip()
            return True
        return False


def _extract_xrefs(text: str) -> list[str]:
    return [m.group(2) for m in _XREF_RE.finditer(text)]


# ---------------------------------------------------------------------------
# Main segmenter
# ---------------------------------------------------------------------------


class LegalDocumentSegmenter:
    """Extract structured :class:`~hammurabi.ingestion.models.LegalSegment` objects
    from a :class:`~hammurabi.ingestion.models.LegalDocument`.

    The segmentation strategy is chosen based on ``document.document_type``:

    * **STATUTE / REGULATION** → article extraction with heading hierarchy
    * **CONTRACT** → clause boundary detection (numbered + lettered)
    * **JUDGMENT** → judgment-structure extraction (parties / facts / motifs /
      dispositif)
    """

    def segment(self, document: LegalDocument) -> list[LegalSegment]:
        """Run segmentation and attach results to *document.segments*."""
        if document.document_type in (DocumentType.STATUTE, DocumentType.REGULATION):
            segments = self._segment_statute(document.raw_text)
        elif document.document_type == DocumentType.JUDGMENT:
            segments = self._segment_judgment(document.raw_text)
        else:
            segments = self._segment_contract(document.raw_text)

        document.segments = segments
        return segments

    # ------------------------------------------------------------------
    # Statute segmentation
    # ------------------------------------------------------------------

    def _segment_statute(self, text: str) -> list[LegalSegment]:
        segments: list[LegalSegment] = []
        ctx = _HierarchyContext()

        # Find all article boundaries
        matches_fr = list(_ARTICLE_FR.finditer(text))
        matches_en = list(_ARTICLE_EN.finditer(text))
        all_matches = sorted(matches_fr + matches_en, key=lambda m: m.start())

        if not all_matches:
            # No article pattern found — return whole text as one segment
            return [LegalSegment(segment_type="section", text=text.strip())]

        for i, m in enumerate(all_matches):
            # Update heading context from lines between previous match and this one
            preamble = text[all_matches[i - 1].end() if i > 0 else 0 : m.start()]
            for line in preamble.splitlines():
                ctx.update_from_line(line.strip())

            # Determine article body (text until next match)
            body_start = m.end()
            body_end = all_matches[i + 1].start() if i + 1 < len(all_matches) else len(text)
            body = text[body_start:body_end].strip()

            # Groups differ between patterns — normalise
            if m.re is _ARTICLE_FR:
                article_num = (m.group(1) or "") + m.group(2)
                heading = m.group(3).strip() or None
            else:
                article_num = m.group(1)
                heading = m.group(2).strip() or None

            full_text = (heading + "\n" + body if heading else body).strip()
            xrefs = _extract_xrefs(full_text)

            segments.append(
                LegalSegment(
                    segment_type="article",
                    text=full_text,
                    heading=heading,
                    article_number=article_num,
                    hierarchy=ctx.as_dict(),
                    cross_references=xrefs,
                )
            )

        return segments

    # ------------------------------------------------------------------
    # Contract segmentation
    # ------------------------------------------------------------------

    def _segment_contract(self, text: str) -> list[LegalSegment]:
        segments: list[LegalSegment] = []

        numbered = list(_CLAUSE_NUMBERED.finditer(text))
        if not numbered:
            # Fall back to lettered sub-clauses
            numbered = list(_CLAUSE_LETTERED.finditer(text))

        if not numbered:
            return [LegalSegment(segment_type="clause", text=text.strip())]

        for i, m in enumerate(numbered):
            body_end = numbered[i + 1].start() if i + 1 < len(numbered) else len(text)
            body = text[m.start() : body_end].strip()
            xrefs = _extract_xrefs(body)

            # Heading is the first line
            lines = body.splitlines()
            heading: str | None = lines[0].strip() if lines else None

            segments.append(
                LegalSegment(
                    segment_type="clause",
                    text=body,
                    heading=heading,
                    cross_references=xrefs,
                )
            )

        return segments

    # ------------------------------------------------------------------
    # Judgment segmentation
    # ------------------------------------------------------------------

    def _segment_judgment(self, text: str) -> list[LegalSegment]:
        boundaries: list[tuple[int, str]] = []
        for name, pattern in _JUDGMENT_SECTIONS:
            for m in pattern.finditer(text):
                boundaries.append((m.start(), name))

        if not boundaries:
            return [LegalSegment(segment_type="judgment_part", text=text.strip())]

        boundaries.sort()
        segments: list[LegalSegment] = []

        # Pre-header text
        if boundaries[0][0] > 0:
            segments.append(
                LegalSegment(
                    segment_type="judgment_part",
                    text=text[: boundaries[0][0]].strip(),
                    heading="header",
                )
            )

        for i, (pos, name) in enumerate(boundaries):
            end = boundaries[i + 1][0] if i + 1 < len(boundaries) else len(text)
            body = text[pos:end].strip()
            xrefs = _extract_xrefs(body)
            segments.append(
                LegalSegment(
                    segment_type="judgment_part",
                    text=body,
                    heading=name,
                    cross_references=xrefs,
                )
            )

        return segments
