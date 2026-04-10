"""Source connector loaders for the ingestion layer."""

from hammurabi.ingestion.loaders.base import LegalSourceLoader
from hammurabi.ingestion.loaders.caselaw import CaseLawLoader
from hammurabi.ingestion.loaders.docx import DOCXLoader
from hammurabi.ingestion.loaders.pdf import PDFLoader
from hammurabi.ingestion.loaders.structured import StructuredCodeLoader
from hammurabi.ingestion.loaders.url import URLLoader

__all__ = [
    "LegalSourceLoader",
    "PDFLoader",
    "DOCXLoader",
    "StructuredCodeLoader",
    "CaseLawLoader",
    "URLLoader",
]
