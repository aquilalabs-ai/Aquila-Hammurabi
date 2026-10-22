"""Knowledge layer — Neo4j legal graph and Qdrant vector store.

Public surface::

    from hammurabi.knowledge import (
        LegalKnowledgeService,
        LegalGraphClient,
        LegalVectorStore,
        SearchResult,
        ArticleContext,
        CaseContext,
        CitationChainEntry,
        IngestionSummary,
        COLLECTION_STATUTES,
        COLLECTION_CASES,
        COLLECTION_DOCUMENTS,
    )
"""

from hammurabi.knowledge.graph import LegalGraphClient
from hammurabi.knowledge.models import (
    ArticleContext,
    CaseContext,
    CitationChainEntry,
    IngestionSummary,
    SearchResult,
)
from hammurabi.knowledge.service import LegalKnowledgeService
from hammurabi.knowledge.vector import (
    COLLECTION_CASES,
    COLLECTION_DOCUMENTS,
    COLLECTION_STATUTES,
    LegalVectorStore,
)

__all__ = [
    # Service (primary entry point)
    "LegalKnowledgeService",
    # Individual clients (advanced use)
    "LegalGraphClient",
    "LegalVectorStore",
    # Models
    "SearchResult",
    "ArticleContext",
    "CaseContext",
    "CitationChainEntry",
    "IngestionSummary",
    # Collection name constants
    "COLLECTION_STATUTES",
    "COLLECTION_CASES",
    "COLLECTION_DOCUMENTS",
]
