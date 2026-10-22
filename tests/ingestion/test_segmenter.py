"""Tests for the LegalDocumentSegmenter."""

from __future__ import annotations

from hammurabi.ingestion.models import DocumentType, LegalDocument, SourceType
from hammurabi.ingestion.segmenter import LegalDocumentSegmenter

_SEGMENTER = LegalDocumentSegmenter()


# ---------------------------------------------------------------------------
# Statute segmentation
# ---------------------------------------------------------------------------

_STATUTE_TEXT = """\
TITRE III — Des obligations
CHAPITRE I — Dispositions générales

Article 1101 — Définition du contrat
Un contrat est un accord de volontés entre deux ou plusieurs personnes destiné à créer, modifier,
transmettre ou éteindre des obligations.

Article 1102 — Liberté contractuelle
Chacun est libre de contracter ou de ne pas contracter, de choisir son cocontractant et de
déterminer le contenu et la forme du contrat dans les limites fixées par la loi.

Article 1103 — Force obligatoire
Les contrats légalement formés tiennent lieu de loi à ceux qui les ont faits,
conformément à l'article 1102 du code civil.
"""


def test_statute_produces_articles() -> None:
    doc = LegalDocument(
        source_type=SourceType.PDF, document_type=DocumentType.STATUTE, raw_text=_STATUTE_TEXT
    )
    segs = _SEGMENTER.segment(doc)
    article_segs = [s for s in segs if s.segment_type == "article"]
    assert len(article_segs) == 3


def test_statute_article_numbers() -> None:
    doc = LegalDocument(
        source_type=SourceType.PDF, document_type=DocumentType.STATUTE, raw_text=_STATUTE_TEXT
    )
    _SEGMENTER.segment(doc)
    nums = [s.article_number for s in doc.segments if s.article_number]
    assert "1101" in nums
    assert "1102" in nums
    assert "1103" in nums


def test_statute_headings() -> None:
    doc = LegalDocument(
        source_type=SourceType.PDF, document_type=DocumentType.STATUTE, raw_text=_STATUTE_TEXT
    )
    _SEGMENTER.segment(doc)
    headings = [s.heading for s in doc.segments if s.heading]
    assert any("Définition" in h for h in headings)


def test_statute_cross_references() -> None:
    doc = LegalDocument(
        source_type=SourceType.PDF, document_type=DocumentType.STATUTE, raw_text=_STATUTE_TEXT
    )
    _SEGMENTER.segment(doc)
    # Article 1103 references 1102
    seg_1103 = next((s for s in doc.segments if s.article_number == "1103"), None)
    assert seg_1103 is not None
    assert "1102" in seg_1103.cross_references


def test_statute_hierarchy_propagation() -> None:
    doc = LegalDocument(
        source_type=SourceType.PDF, document_type=DocumentType.STATUTE, raw_text=_STATUTE_TEXT
    )
    _SEGMENTER.segment(doc)
    # At least one segment should carry the chapter in its hierarchy
    with_chapter = [s for s in doc.segments if s.hierarchy.get("chapter")]
    assert len(with_chapter) >= 1


# ---------------------------------------------------------------------------
# Contract segmentation
# ---------------------------------------------------------------------------

_CONTRACT_TEXT = """\
SERVICE AGREEMENT

1.1 Scope of Services
The Supplier shall provide legal research services as described in Schedule A.

1.2 Delivery
All deliverables must be submitted within 30 days of execution, pursuant to Article 5 of the
governing framework.

2.1 Payment Terms
The Client shall pay the Supplier the sum of €50,000 within 15 days of invoice.

2.2 Late Payment
Interest at 3% per annum shall accrue on overdue amounts.
"""


def test_contract_produces_clauses() -> None:
    doc = LegalDocument(
        source_type=SourceType.DOCX, document_type=DocumentType.CONTRACT, raw_text=_CONTRACT_TEXT
    )
    segs = _SEGMENTER.segment(doc)
    assert len(segs) >= 2
    assert all(s.segment_type == "clause" for s in segs)


def test_contract_clause_cross_refs() -> None:
    doc = LegalDocument(
        source_type=SourceType.DOCX, document_type=DocumentType.CONTRACT, raw_text=_CONTRACT_TEXT
    )
    _SEGMENTER.segment(doc)
    xrefs = [r for s in doc.segments for r in s.cross_references]
    assert "5" in xrefs


# ---------------------------------------------------------------------------
# Judgment segmentation
# ---------------------------------------------------------------------------

_JUDGMENT_TEXT = """\
ENTRE la société Alpha SA ET la société Beta SARL

FAITS
La société Alpha SA a conclu un contrat de prestation de services avec la société Beta SARL
le 1er janvier 2020.

MOTIFS
Attendu que les parties ont librement consenti au contrat ;
Attendu que la clause litigieuse est contraire à l'ordre public.

PAR CES MOTIFS
La Cour condamne la société Beta SARL à payer la somme de 100 000 euros.
"""


def test_judgment_produces_parts() -> None:
    doc = LegalDocument(
        source_type=SourceType.PDF, document_type=DocumentType.JUDGMENT, raw_text=_JUDGMENT_TEXT
    )
    segs = _SEGMENTER.segment(doc)
    assert len(segs) >= 2
    assert all(s.segment_type == "judgment_part" for s in segs)


def test_judgment_section_headings() -> None:
    doc = LegalDocument(
        source_type=SourceType.PDF, document_type=DocumentType.JUDGMENT, raw_text=_JUDGMENT_TEXT
    )
    _SEGMENTER.segment(doc)
    headings = {s.heading for s in doc.segments if s.heading}
    assert "ratio_decidendi" in headings
    assert "operative_part" in headings


def test_empty_text_fallback() -> None:
    doc = LegalDocument(
        source_type=SourceType.PDF, document_type=DocumentType.STATUTE, raw_text="No articles here."
    )
    segs = _SEGMENTER.segment(doc)
    assert len(segs) == 1
    assert segs[0].segment_type == "section"
