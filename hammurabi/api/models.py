"""Pydantic request/response models for the Hammurabi REST API."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

# ── Jobs ──────────────────────────────────────────────────────────────────────


class JobStatus(BaseModel):
    job_id: str
    type: str
    status: str
    result: dict[str, Any] | None = None
    error: str | None = None
    created_at: datetime
    updated_at: datetime


# ── Corpus ────────────────────────────────────────────────────────────────────


class CorpusSummary(BaseModel):
    id: str
    name: str
    jurisdiction: str
    status: str
    article_count: int
    case_count: int
    chunk_count: int
    created_at: datetime


class CorpusIngestResponse(BaseModel):
    corpus_id: str
    job_id: str
    status: str


class CorpusRegisterRequest(BaseModel):
    name: str
    jurisdiction: str = Field(default="FR")
    article_count: int = Field(default=0)
    case_count: int = Field(default=0)
    chunk_count: int = Field(default=0)


class CorpusStats(BaseModel):
    corpus_id: str
    article_count: int
    case_count: int
    chunk_count: int


# ── Documents ─────────────────────────────────────────────────────────────────


class DocumentSummary(BaseModel):
    id: str
    corpus_id: str | None
    filename: str
    document_type: str
    status: str
    created_at: datetime


class DocumentDetail(BaseModel):
    id: str
    corpus_id: str | None
    filename: str
    document_type: str
    status: str
    content: str
    jurisdiction: str
    created_at: datetime


class AnalyzeRequest(BaseModel):
    jurisdiction: str = Field(default="FR")


class AnalysisStatus(BaseModel):
    document_id: str
    job_id: str | None = None
    status: str
    result: dict[str, Any] | None = None
    error: str | None = None


class RiskFlagItem(BaseModel):
    clause_text: str
    risk_type: str
    severity: str
    explanation: str
    suggested_improvement: str
    governing_articles: list[str]


class RiskReportResponse(BaseModel):
    document_id: str
    jurisdiction: str
    flags: list[RiskFlagItem]


# ── Articles & Cases ──────────────────────────────────────────────────────────


class ArticleResponse(BaseModel):
    article: dict[str, Any]
    amendments: list[dict[str, Any]]
    interpreting_cases: list[dict[str, Any]]
    citing_articles: list[dict[str, Any]]


class ArticleCasesResponse(BaseModel):
    article_id: str
    cases: list[dict[str, Any]]


class CitationNetworkResponse(BaseModel):
    article_id: str
    depth: int
    paths: list[dict[str, Any]]


class CaseResponse(BaseModel):
    case: dict[str, Any]
    cited_articles: list[dict[str, Any]]
    cited_cases: list[dict[str, Any]]
    subsequent_citations: list[dict[str, Any]]


# ── Search ────────────────────────────────────────────────────────────────────


class SearchResultItem(BaseModel):
    text: str
    score: float
    source_type: str
    jurisdiction: str
    article_id: str | None
    case_id: str | None
    tags: list[str]
    payload: dict[str, Any]


class SearchResponse(BaseModel):
    query: str
    total: int
    results: list[SearchResultItem]


# ── Chat / Sessions ───────────────────────────────────────────────────────────


class ChatRequest(BaseModel):
    message: str
    session_id: str | None = None
    jurisdiction: str | None = None
    document_text: str = ""
    stream: bool = False


class ChatResponse(BaseModel):
    session_id: str
    response: str


class CaseSimulationRequest(BaseModel):
    scenario: str = Field(description="Case fact pattern for the LLM to solve using IRAC analysis")
    legal_domain: str | None = Field(
        default=None, description="Optional domain hint, e.g. 'contract law', 'tort'"
    )
    jurisdiction: str | None = None
    session_id: str | None = None
    stream: bool = False


class CaseSimulationResponse(BaseModel):
    session_id: str
    scenario: str
    response: str


class GenerateCaseRequest(BaseModel):
    topic: str = Field(default="", description="Legal domain or topic for the case scenario")
    difficulty: str = Field(default="medium", description="easy | medium | hard")
    jurisdiction: str | None = None


class GenerateCaseResponse(BaseModel):
    scenario: str
    relevant_articles: list[str]
    difficulty: str


class SessionCreate(BaseModel):
    title: str | None = None


class SessionSummary(BaseModel):
    session_id: str
    corpus_id: str
    created_at: datetime
    updated_at: datetime


# ── Drafts ────────────────────────────────────────────────────────────────────


class DraftRequest(BaseModel):
    prompt: str
    template_type: str = Field(default="contract", description="contract | memo | pleading | clause")
    jurisdiction: str = Field(default="FR")
    context: str = ""


class DraftImproveRequest(BaseModel):
    instructions: str
    jurisdiction: str = "FR"


class DraftResponse(BaseModel):
    id: str
    content: str
    prompt: str
    jurisdiction: str
    template_type: str
    created_at: datetime


# ── Report Assistant (Student Mode) ──────────────────────────────────────────


class ReportProblematicRequest(BaseModel):
    topic: str = Field(description="The broad subject given to the student")
    study_level: str = Field(
        default="master",
        description="Academic level: bachelor | master | doctorate | other",
    )
    field: str = Field(default="", description="Academic field, e.g. 'droit', 'informatique'")
    session_id: str | None = None


class ReportPlanRequest(BaseModel):
    topic: str = Field(description="The original broad subject")
    problematic: str = Field(
        description="The confirmed, focused research question to build the plan around"
    )
    study_level: str = Field(
        default="master",
        description="Academic level: bachelor | master | doctorate | other",
    )
    field: str = Field(default="", description="Academic field, e.g. 'droit', 'informatique'")
    constraints: str = Field(
        default="", description="Optional constraints (page limit, required sections, etc.)"
    )
    session_id: str | None = None


class ReportCritiqueRequest(BaseModel):
    plan: str = Field(description="The existing plan text to critique")
    topic: str = Field(default="", description="The topic or problematic the plan addresses")
    study_level: str = Field(default="master", description="Academic level")
    session_id: str | None = None


class ReportCoherenceRequest(BaseModel):
    content: str = Field(description="The ideas, sections, or draft text to check for coherence")
    topic: str = Field(default="", description="The central topic or research question")
    session_id: str | None = None


class ReportResponse(BaseModel):
    session_id: str
    response: str


# ── Graph ─────────────────────────────────────────────────────────────────────


class GraphData(BaseModel):
    corpus_id: str
    nodes: list[dict[str, Any]]
    edges: list[dict[str, Any]]


class GraphStats(BaseModel):
    corpus_id: str
    node_counts: dict[str, int]
    relationship_counts: dict[str, int]


class CypherRequest(BaseModel):
    query: str = Field(description="Read-only Cypher (MATCH / CALL / RETURN / WITH)")


class CypherResult(BaseModel):
    columns: list[str]
    rows: list[dict[str, Any]]
    row_count: int


# ── Health ────────────────────────────────────────────────────────────────────


class HealthResponse(BaseModel):
    status: str


class ReadinessResponse(BaseModel):
    status: str
    neo4j: str
    qdrant: str
