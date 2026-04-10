"""Ingestion layer — PDF, DOCX, structured XML/JSON, and URL loaders.

Public surface::

    from hammurabi.ingestion import (
        LegalSourceLoader,
        PDFLoader, DOCXLoader, StructuredCodeLoader, CaseLawLoader, URLLoader,
        LegalDocumentSegmenter,
        LegalNERPipeline,
        LegalChunker,
        LegalChunk, LegalDocument, LegalSegment, NERResult,
        SourceType, DocumentType,
    )
"""

from hammurabi.ingestion.chunker import LegalChunker
from hammurabi.ingestion.loaders import (
    CaseLawLoader,
    DOCXLoader,
    LegalSourceLoader,
    PDFLoader,
    StructuredCodeLoader,
    URLLoader,
)
from hammurabi.ingestion.models import (
    DocumentType,
    LegalChunk,
    LegalDocument,
    LegalSegment,
    NERResult,
    RawPage,
    SourceType,
)
from hammurabi.ingestion.ner import LegalNERPipeline
from hammurabi.ingestion.segmenter import LegalDocumentSegmenter

__all__ = [
    # Loaders
    "LegalSourceLoader",
    "PDFLoader",
    "DOCXLoader",
    "StructuredCodeLoader",
    "CaseLawLoader",
    "URLLoader",
    # Segmenter
    "LegalDocumentSegmenter",
    # NER
    "LegalNERPipeline",
    # Chunker
    "LegalChunker",
    # Models
    "LegalChunk",
    "LegalDocument",
    "LegalSegment",
    "NERResult",
    "RawPage",
    "SourceType",
    "DocumentType",
]
