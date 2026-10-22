"""LangChain tools for the IRAC reasoning agent."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

import httpx
from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field

from hammurabi.config import settings
from hammurabi.reasoning.risk import ClauseRiskScorer

if TYPE_CHECKING:
    from hammurabi.knowledge import LegalKnowledgeService


# ---------------------------------------------------------------------------
# Input schemas
# ---------------------------------------------------------------------------


class ArticleIdInput(BaseModel):
    article_id: str = Field(
        ...,
        description="Article ID in format {jurisdiction}-{code}-{number}, e.g. fr-civil-1103",
    )


class SemanticSearchInput(BaseModel):
    query: str = Field(..., description="Natural-language search query")
    jurisdiction: str | None = Field(None, description="ISO jurisdiction code, e.g. FR")
    source_type: str | None = Field(
        None, description="Filter: 'statute', 'contract', or 'judgment'"
    )
    top_k: int = Field(5, description="Number of results to return (1-20)", ge=1, le=20)


class CaseLawInput(BaseModel):
    query: str = Field(
        ..., description="Legal principle or article ID to find interpreting cases for"
    )
    jurisdiction: str | None = Field(None, description="ISO jurisdiction code, e.g. FR")
    top_k: int = Field(5, ge=1, le=20)


class CitationGraphInput(BaseModel):
    article_id: str = Field(..., description="Article ID to trace citations from")
    depth: int = Field(2, description="BFS depth (1-5)", ge=1, le=5)


class DocumentAnalysisInput(BaseModel):
    text: str = Field(..., description="Full text of the document to analyse")
    jurisdiction: str | None = Field(None, description="ISO jurisdiction code, e.g. FR")


class RiskFlagInput(BaseModel):
    clause_text: str = Field(..., description="Text of the clause to assess for risk")
    jurisdiction: str | None = Field(None, description="ISO jurisdiction code, e.g. FR")


class DraftingInput(BaseModel):
    instruction: str = Field(
        ...,
        description="What to draft — e.g. 'a limitation of liability clause capped at €500k'",
    )
    context: str | None = Field(
        None, description="Existing clause text to improve, if any"
    )
    jurisdiction: str | None = Field(None, description="ISO jurisdiction code, e.g. FR")


class SummaryInput(BaseModel):
    text: str = Field(..., description="Statute article or judgment text to summarise")
    audience: str = Field(
        "general", description="Target audience: 'general', 'student', or 'expert'"
    )


class QuizInput(BaseModel):
    topic: str = Field(..., description="Legal concept or article to generate questions about")
    count: int = Field(3, description="Number of questions to generate (1-10)", ge=1, le=10)
    difficulty: str = Field(
        "intermediate", description="Difficulty: 'beginner', 'intermediate', or 'advanced'"
    )


class CypherInput(BaseModel):
    query: str = Field(..., description="Read-only Cypher query to execute on the legal graph")


class LegalNewsSearchInput(BaseModel):
    query: str = Field(
        ...,
        description=(
            "Legal topic or keywords to search for in French legal news "
            "(e.g. 'intelligence artificielle responsabilité contrat')"
        ),
    )
    max_results: int = Field(
        6, description="Maximum number of news articles to return (1-10)", ge=1, le=10
    )
    timelimit: str = Field(
        "m",
        description=(
            "Recency filter: 'd' = last day, 'w' = last week, 'm' = last month, "
            "'y' = last year. Default 'm' keeps results fresh."
        ),
    )


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


class StatuteLookupTool(BaseTool):
    """Retrieve full context of a specific legal article from the knowledge graph."""

    name: str = "statute_lookup"
    description: str = (
        "Look up a specific legal article by its ID. "
        "Returns the article text, amendments, interpreting cases, and citing articles. "
        "Use when you know the exact article ID (e.g. fr-civil-1103)."
    )
    args_schema: type[BaseModel] = ArticleIdInput
    knowledge: Any  # LegalKnowledgeService — Any avoids circular import at class level

    async def _arun(self, article_id: str) -> str:
        ctx = await self.knowledge.get_article(article_id)
        if ctx is None:
            return f"Article '{article_id}' not found in the knowledge graph."
        article = ctx.article
        parts: list[str] = [
            f"## Article {article_id}",
            f"Code: {article.get('code', 'N/A')}",
            f"Jurisdiction: {article.get('jurisdiction', 'N/A')}",
        ]
        if article.get("heading"):
            parts.append(f"Heading: {article['heading']}")
        if article.get("content"):
            parts.append(f"\n{article['content']}")
        if ctx.amendments:
            parts.append(f"\n### Amendments ({len(ctx.amendments)})")
            for am in ctx.amendments[:3]:
                parts.append(f"- {am.get('amendment_id', '')}: {am.get('description', '')}")
        if ctx.interpreting_cases:
            parts.append(f"\n### Interpreting Cases ({len(ctx.interpreting_cases)})")
            for c in ctx.interpreting_cases[:5]:
                parts.append(f"- [{c.get('case_id', '')}] {c.get('court', '')} ({c.get('date', '')})")
        if ctx.citing_articles:
            ids = [a.get("article_id", "") for a in ctx.citing_articles[:5]]
            parts.append(f"\n### Cited by: {', '.join(ids)}")
        return "\n".join(parts)

    def _run(self, article_id: str) -> str:
        raise NotImplementedError("Use _arun")


class SemanticSearchTool(BaseTool):
    """Hybrid semantic + keyword search over the legal corpus."""

    name: str = "semantic_search"
    description: str = (
        "Search the legal corpus using a natural-language query. "
        "Returns relevant statutes, cases, and document clauses ranked by relevance. "
        "Use when you don't know the exact article ID or need broad context."
    )
    args_schema: type[BaseModel] = SemanticSearchInput
    knowledge: Any

    async def _arun(
        self,
        query: str,
        jurisdiction: str | None = None,
        source_type: str | None = None,
        top_k: int = 5,
    ) -> str:
        jur = jurisdiction or settings.default_jurisdiction
        results = await self.knowledge.search(
            query, jurisdiction=jur, source_type=source_type, top_k=top_k
        )
        if not results:
            return "No results found for the given query."
        lines: list[str] = [f"## Search Results for '{query}' (jurisdiction={jur})\n"]
        for i, r in enumerate(results, 1):
            label = r.article_id or r.case_id or "document"
            lines.append(f"**[{i}] {label}** (score={r.score:.3f}, type={r.source_type})")
            lines.append(r.text[:400] + ("…" if len(r.text) > 400 else ""))
            lines.append("")
        return "\n".join(lines)

    def _run(self, **kwargs: Any) -> str:
        raise NotImplementedError("Use _arun")


class CaseLawSearchTool(BaseTool):
    """Find cases that interpret a given article or legal principle."""

    name: str = "case_law_search"
    description: str = (
        "Search for case law that interprets a legal article or addresses a legal principle. "
        "Returns case summaries with docket numbers and courts."
    )
    args_schema: type[BaseModel] = CaseLawInput
    knowledge: Any

    async def _arun(
        self,
        query: str,
        jurisdiction: str | None = None,
        top_k: int = 5,
    ) -> str:
        jur = jurisdiction or settings.default_jurisdiction
        results = await self.knowledge.search(
            query, jurisdiction=jur, source_type="judgment", top_k=top_k
        )
        if not results:
            return "No case law found."
        lines: list[str] = [f"## Case Law Results for '{query}'\n"]
        for i, r in enumerate(results, 1):
            case_id = r.case_id or "unknown"
            court = r.payload.get("court", "")
            date = r.payload.get("date", "")
            lines.append(f"**[{i}] [{case_id}]** {court} {date}")
            lines.append(r.text[:500] + ("…" if len(r.text) > 500 else ""))
            lines.append("")
        return "\n".join(lines)

    def _run(self, **kwargs: Any) -> str:
        raise NotImplementedError("Use _arun")


class CitationGraphTool(BaseTool):
    """Explore the citation network (REFERENCES / CITES) from a given article."""

    name: str = "citation_graph"
    description: str = (
        "Explore which articles and cases reference a given article, and which it references. "
        "Useful for understanding doctrine evolution and legal precedent chains."
    )
    args_schema: type[BaseModel] = CitationGraphInput
    knowledge: Any

    async def _arun(self, article_id: str, depth: int = 2) -> str:
        chains = await self.knowledge.get_citation_network(article_id, depth=depth)
        if not chains:
            return f"No citation network found for '{article_id}'."
        lines: list[str] = [f"## Citation Network for {article_id} (depth={depth})\n"]
        for chain in chains[:20]:
            node_ids = [n.get("article_id") or n.get("case_id") or str(n) for n in chain.nodes]
            lines.append(f"Path (depth {chain.depth}): {' → '.join(node_ids)}")
        return "\n".join(lines)

    def _run(self, **kwargs: Any) -> str:
        raise NotImplementedError("Use _arun")


class DocumentAnalysisTool(BaseTool):
    """Extract clauses and structural metadata from a document."""

    name: str = "document_analysis"
    description: str = (
        "Extract and structure clauses, obligations, and parties from a document text. "
        "Returns a structured list of clauses with headings and clause numbers."
    )
    args_schema: type[BaseModel] = DocumentAnalysisInput
    knowledge: Any

    async def _arun(self, text: str, jurisdiction: str | None = None) -> str:
        from hammurabi.ingestion.segmenter import LegalDocumentSegmenter
        from hammurabi.ingestion.models import DocumentType

        segmenter = LegalDocumentSegmenter()
        segments = segmenter.segment(text, DocumentType.CONTRACT)
        if not segments:
            return "No clauses extracted from the document."
        lines: list[str] = [f"## Extracted Clauses ({len(segments)})\n"]
        for seg in segments:
            heading = seg.heading or f"Clause {seg.article_number or ''}"
            preview = seg.text[:300] + ("…" if len(seg.text) > 300 else "")
            lines.append(f"**{heading}**")
            lines.append(preview)
            lines.append("")
        return "\n".join(lines)

    def _run(self, **kwargs: Any) -> str:
        raise NotImplementedError("Use _arun")


class RiskFlagTool(BaseTool):
    """Identify risks in a single contract clause with severity scoring."""

    name: str = "risk_flag"
    description: str = (
        "Analyse a contract clause for legal risks. "
        "Returns risk type, severity (LOW/MEDIUM/HIGH/CRITICAL), explanation, "
        "suggested improvement, and applicable article IDs."
    )
    args_schema: type[BaseModel] = RiskFlagInput

    async def _arun(self, clause_text: str, jurisdiction: str | None = None) -> str:
        jur = (jurisdiction or settings.default_jurisdiction).upper()
        scorer = ClauseRiskScorer(jurisdiction=jur)
        reports = scorer.score(clause_text)
        if not reports:
            return "No significant legal risks detected in this clause."
        lines: list[str] = [f"## Risk Analysis ({len(reports)} risk(s) detected)\n"]
        for r in reports:
            lines.append(f"**{r.severity.value} — {r.risk_type.value.upper()}**")
            lines.append(f"Explanation: {r.explanation}")
            lines.append(f"Suggestion: {r.suggested_improvement}")
            if r.governing_articles:
                lines.append(f"Governing articles: {', '.join(r.governing_articles)}")
            lines.append("")
        return "\n".join(lines)

    def _run(self, **kwargs: Any) -> str:
        raise NotImplementedError("Use _arun")


class DraftingTool(BaseTool):
    """Generate or improve a legal clause using the LLM."""

    name: str = "drafting"
    description: str = (
        "Generate or improve a legal clause, contract section, memo, or pleading fragment. "
        "Produces formal legal language. Provide instruction and optionally existing text to improve."
    )
    args_schema: type[BaseModel] = DraftingInput
    llm: Any  # ChatOpenAI

    async def _arun(
        self,
        instruction: str,
        context: str | None = None,
        jurisdiction: str | None = None,
    ) -> str:
        jur = jurisdiction or settings.default_jurisdiction
        prompt = (
            f"You are an expert legal drafter. Jurisdiction: {jur}.\n\n"
            f"Task: {instruction}\n"
        )
        if context:
            prompt += f"\nExisting text to improve:\n{context}\n"
        prompt += "\nProduce the drafted legal text only, without explanation."
        from langchain_core.messages import HumanMessage

        response = await self.llm.ainvoke([HumanMessage(content=prompt)])
        return str(response.content)

    def _run(self, **kwargs: Any) -> str:
        raise NotImplementedError("Use _arun")


class SummaryTool(BaseTool):
    """Summarise a statute article or judgment in plain language."""

    name: str = "summary"
    description: str = (
        "Summarise a legal text (statute article or judgment) in plain language. "
        "Adjust complexity based on audience: 'general', 'student', or 'expert'."
    )
    args_schema: type[BaseModel] = SummaryInput
    llm: Any

    async def _arun(self, text: str, audience: str = "general") -> str:
        audience_map = {
            "general": "a general audience with no legal background",
            "student": "a first-year law student",
            "expert": "an experienced lawyer",
        }
        target = audience_map.get(audience, audience_map["general"])
        prompt = (
            f"Summarise the following legal text for {target}. "
            "Be concise and accurate. Use plain language where possible.\n\n"
            f"Text:\n{text}"
        )
        from langchain_core.messages import HumanMessage

        response = await self.llm.ainvoke([HumanMessage(content=prompt)])
        return str(response.content)

    def _run(self, **kwargs: Any) -> str:
        raise NotImplementedError("Use _arun")


class QuizTool(BaseTool):
    """Generate exam questions and model answers on a legal concept."""

    name: str = "quiz"
    description: str = (
        "Generate exam questions with model answers on a legal concept. "
        "Useful in student/learning mode."
    )
    args_schema: type[BaseModel] = QuizInput
    llm: Any

    async def _arun(
        self, topic: str, count: int = 3, difficulty: str = "intermediate"
    ) -> str:
        prompt = (
            f"Generate {count} {difficulty}-level legal exam questions about: {topic}.\n\n"
            "For each question provide:\n"
            "1. The question\n"
            "2. A model answer (3-5 sentences)\n\n"
            "Format as Q1: ... A1: ... Q2: ... A2: ..."
        )
        from langchain_core.messages import HumanMessage

        response = await self.llm.ainvoke([HumanMessage(content=prompt)])
        return str(response.content)

    def _run(self, **kwargs: Any) -> str:
        raise NotImplementedError("Use _arun")


# Curated French legal domains split into two tiers.
# Tier 1 — official/institutional (highest authority)
_FR_LEGAL_DOMAINS_OFFICIAL = [
    "legifrance.gouv.fr",
    "courdecassation.fr",
    "conseil-etat.fr",
    "conseil-constitutionnel.fr",
    "vie-publique.fr",
    "senat.fr",
    "assemblee-nationale.fr",
]

# Tier 2 — professional publishers and legal-news outlets
_FR_LEGAL_DOMAINS_PRESS = [
    "dalloz-actualite.fr",
    "lexbase.fr",
    "village-justice.com",
    "actu-juridique.fr",
    "leclubdesjuristes.com",
    "lefebvre-dalloz.fr",
    "net-iris.fr",
    "lgdj.fr",
    "doctrine.fr",
    "legavox.fr",
    "lagazettedescommunes.com",
    "revuegeneraledudroit.eu",
]

_ALL_FR_LEGAL_DOMAINS = _FR_LEGAL_DOMAINS_OFFICIAL + _FR_LEGAL_DOMAINS_PRESS


def _site_filter(domains: list[str]) -> str:
    return " OR ".join(f"site:{d}" for d in domains)


class LegalNewsSearchTool(BaseTool):
    """Search recent French legal news via DuckDuckGo (free, no API key)."""

    name: str = "legal_news_search"
    description: str = (
        "Search for recent French legal news and jurisprudential developments from trusted sources "
        "(Légifrance, Cour de cassation, Conseil d'État, Dalloz Actualité, LexBase, etc.). "
        "ONLY use this tool for report / mémoire / thesis tasks where current legal debates matter. "
        "Do NOT call this for standard legal research, IRAC analysis, or knowledge-base queries — "
        "use semantic_search or statute_lookup instead."
    )
    args_schema: type[BaseModel] = LegalNewsSearchInput

    _TIMEOUT_S: float = 12.0  # DuckDuckGo calls can stall; hard-kill after this

    async def _arun(self, query: str, max_results: int = 6, timelimit: str = "m") -> str:
        import asyncio

        from ddgs import DDGS

        # site: operators work reliably with ddgs.text() but NOT with ddgs.news().
        # Strategy: run two searches in parallel —
        #   A) ddgs.text() with site: filter → domain-pinpointed results
        #   B) ddgs.news() without site: filter → genuinely recent items
        # Then merge and deduplicate by URL, capping at max_results.

        official_query = f"{query} ({_site_filter(_FR_LEGAL_DOMAINS_OFFICIAL)})"
        press_query = f"{query} ({_site_filter(_FR_LEGAL_DOMAINS_PRESS)})"
        news_query = f"{query} actualité juridique droit France"

        # Pass a native HTTP timeout so each thread exits on its own if the
        # network stalls — asyncio.wait_for alone cannot interrupt a running thread.
        http_timeout = max(5, int(self._TIMEOUT_S) - 2)

        def _text(q: str, n: int) -> list[dict[str, str]]:
            try:
                with DDGS(timeout=http_timeout) as ddgs:
                    print("Running ddgs.text() with query:", q)
                    return list(ddgs.text(q, max_results=n, region="fr-fr", timelimit=timelimit))
            except Exception:  # noqa: BLE001
                return []

        def _news(q: str, n: int) -> list[dict[str, str]]:
            try:
                with DDGS(timeout=http_timeout) as ddgs:
                    print("Running ddgs.news() with query:", q)
                    return list(ddgs.news(q, max_results=n, region="fr-fr", timelimit=timelimit))
            except Exception:  # noqa: BLE001
                return []

        try:
            official_res, press_res, news_res = await asyncio.wait_for(
                asyncio.gather(
                    asyncio.to_thread(_text, official_query, max_results),
                    asyncio.to_thread(_text, press_query, max_results),
                    asyncio.to_thread(_news, news_query, max_results),
                ),
                timeout=self._TIMEOUT_S,
            )
        except (asyncio.TimeoutError, Exception):  # noqa: BLE001
            return "La recherche d'actualités juridiques a expiré (timeout). Veuillez réessayer."

        # Merge: official first (highest authority), then press, then news.
        seen_urls: set[str] = set()
        merged: list[dict[str, str]] = []
        for r in [*official_res, *press_res, *news_res]:
            url = r.get("href", r.get("url", ""))
            if url and url not in seen_urls:
                seen_urls.add(url)
                merged.append(r)
            if len(merged) >= max_results:
                break

        if not merged:
            return "No recent French legal news found for this query."

        lines: list[str] = [f"## Actualités juridiques récentes : « {query} »\n"]
        for i, r in enumerate(merged, 1):
            title = r.get("title", "Sans titre")
            url = r.get("href", r.get("url", ""))
            body = r.get("body", "")
            published = r.get("date", r.get("published", ""))
            source = r.get("source", "")
            # Derive source label from URL when the field is missing
            if not source and url:
                source = url.split("/")[2].removeprefix("www.")
            lines.append(f"**[{i}] {title}**")
            if published:
                lines.append(f"Date : {published}")
            if source:
                lines.append(f"Source : {source}")
            if url:
                lines.append(f"Lien : {url}")
            if body:
                lines.append(body[:600] + ("…" if len(body) > 600 else ""))
            lines.append("")
        return "\n".join(lines)

    def _run(self, **kwargs: Any) -> str:
        raise NotImplementedError("Use _arun")


# ---------------------------------------------------------------------------
# MCP tools — call the Neo4j MCP server at http://localhost:8081
# ---------------------------------------------------------------------------


class _MCPClient:
    """Minimal JSON-RPC 2.0 client for the Neo4j MCP server."""

    def __init__(self, base_url: str = "http://localhost:8081") -> None:
        self._base_url = base_url.rstrip("/")
        self._id = 0

    async def call(self, tool_name: str, params: dict[str, Any] | None = None) -> Any:
        self._id += 1
        payload = {
            "jsonrpc": "2.0",
            "id": self._id,
            "method": "tools/call",
            "params": {"name": tool_name, "arguments": params or {}},
        }
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(f"{self._base_url}/mcp", json=payload)
            resp.raise_for_status()
            data = resp.json()
        if "error" in data:
            raise RuntimeError(f"MCP error: {data['error']}")
        result: Any = data.get("result", {})
        content = result.get("content", [])
        if content and isinstance(content, list):
            return content[0].get("text", "")
        return json.dumps(result)


_mcp_client = _MCPClient()


class GetSchemaTool(BaseTool):
    """Return the Neo4j graph schema (node labels, relationship types, properties)."""

    name: str = "get_schema"
    description: str = (
        "Return the Neo4j graph schema: node labels, relationship types, and property keys. "
        "Call this once at the start of any Cypher-based workflow."
    )

    async def _arun(self) -> str:
        return str(await _mcp_client.call("get-schema"))

    def _run(self) -> str:
        raise NotImplementedError("Use _arun")


class ReadCypherTool(BaseTool):
    """Execute a read-only Cypher query against the Neo4j graph."""

    name: str = "read_cypher"
    description: str = (
        "Execute a read-only Cypher query against the legal knowledge graph. "
        "Use get_schema first to understand available node labels and relationships."
    )
    args_schema: type[BaseModel] = CypherInput

    async def _arun(self, query: str) -> str:
        return str(await _mcp_client.call("read-cypher", {"query": query}))

    def _run(self, **kwargs: Any) -> str:
        raise NotImplementedError("Use _arun")


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def build_tools(knowledge: Any, llm: Any) -> list[BaseTool]:
    """Instantiate all agent tools, injecting shared dependencies."""
    return [
        StatuteLookupTool(knowledge=knowledge),
        SemanticSearchTool(knowledge=knowledge),
        CaseLawSearchTool(knowledge=knowledge),
        CitationGraphTool(knowledge=knowledge),
        DocumentAnalysisTool(knowledge=knowledge),
        RiskFlagTool(),
        DraftingTool(llm=llm),
        SummaryTool(llm=llm),
        QuizTool(llm=llm),
        LegalNewsSearchTool(),
        GetSchemaTool(),
        ReadCypherTool(),
    ]
