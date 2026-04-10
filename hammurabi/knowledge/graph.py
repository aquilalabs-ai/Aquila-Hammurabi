"""Neo4j legal graph client — async MERGE ingestion and graph context queries.

The driver is imported lazily inside each method so that importing this module
does not require ``neo4j`` to be installed (TYPE_CHECKING guard keeps startup
fast and mypy happy in strict mode).

Public API
----------
``LegalGraphClient`` — instantiate once per application; call ``close()``
on shutdown to release the driver connection pool.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from hammurabi.config import settings
from hammurabi.knowledge.models import ArticleContext, CaseContext, CitationChainEntry

if TYPE_CHECKING:
    from neo4j import AsyncDriver  # noqa: F401

# Module-level cached async driver — created on first use.
_DRIVER: Any = None


def _get_driver() -> Any:
    global _DRIVER  # noqa: PLW0603
    if _DRIVER is None:
        from neo4j import AsyncGraphDatabase  # noqa: PLC0415

        _DRIVER = AsyncGraphDatabase.driver(
            settings.neo4j_uri,
            auth=(settings.neo4j_user, settings.neo4j_password),
        )
    return _DRIVER


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------


class LegalGraphClient:
    """Async Neo4j client for the Hammurabi legal knowledge graph.

    All public methods are coroutines.  The class holds no per-instance state
    beyond the shared module-level driver; it is safe to instantiate multiple
    times or use as a singleton.
    """

    async def close(self) -> None:
        """Close the shared Neo4j driver and release its connection pool."""
        global _DRIVER  # noqa: PLW0603
        if _DRIVER is not None:
            await _DRIVER.close()
            _DRIVER = None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _run(self, query: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        """Execute *query* in a fresh session and return all rows as dicts."""
        driver = _get_driver()
        async with driver.session() as session:
            result = await session.run(query, params or {})
            return await result.data()  # type: ignore[no-any-return]

    # ------------------------------------------------------------------
    # Node MERGE helpers
    # ------------------------------------------------------------------

    async def merge_article(
        self,
        *,
        article_id: str,
        article_number: str,
        code: str,
        code_id: str,
        jurisdiction: str,
        content: str,
        heading: str | None = None,
        title: str | None = None,
        chapter: str | None = None,
        effective_date: str | None = None,
        version: str | None = None,
        tags: list[str] | None = None,
        corpus_id: str | None = None,
    ) -> None:
        """MERGE Jurisdiction → LegalCode → Article chain and set properties."""
        await self._run(
            """
            MERGE (j:Jurisdiction {id: $jurisdiction})
            MERGE (lc:LegalCode {id: $code_id})
              ON CREATE SET lc.name = $code, lc.jurisdiction = $jurisdiction
            MERGE (j)-[:HAS_CODE]->(lc)
            MERGE (a:Article {id: $article_id})
              ON CREATE SET
                a.article        = $article_number,
                a.code           = $code,
                a.code_id        = $code_id,
                a.jurisdiction   = $jurisdiction,
                a.content        = $content,
                a.heading        = $heading,
                a.title          = $title,
                a.chapter        = $chapter,
                a.effective_date = $effective_date,
                a.version        = $version,
                a.tags           = $tags,
                a.corpus_id      = $corpus_id,
                a.current        = true
              ON MATCH SET
                a.content  = $content,
                a.tags     = $tags
            MERGE (lc)-[:CONTAINS]->(a)
            """,
            {
                "jurisdiction": jurisdiction,
                "code_id": code_id,
                "code": code,
                "article_id": article_id,
                "article_number": article_number,
                "content": content,
                "heading": heading,
                "title": title,
                "chapter": chapter,
                "effective_date": effective_date,
                "version": version,
                "tags": tags or [],
                "corpus_id": corpus_id,
            },
        )

    async def merge_case(
        self,
        *,
        case_id: str,
        jurisdiction: str,
        text: str,
        court: str | None = None,
        date: str | None = None,
        parties: list[str] | None = None,
        docket: str | None = None,
        summary: str | None = None,
        tags: list[str] | None = None,
        corpus_id: str | None = None,
    ) -> None:
        """MERGE a Case node and set its properties."""
        await self._run(
            """
            MERGE (c:Case {id: $case_id})
              ON CREATE SET
                c.jurisdiction = $jurisdiction,
                c.court        = $court,
                c.date         = $date,
                c.parties      = $parties,
                c.docket       = $docket,
                c.summary      = $summary,
                c.text         = $text,
                c.tags         = $tags,
                c.corpus_id    = $corpus_id
              ON MATCH SET
                c.text = $text,
                c.tags = $tags
            """,
            {
                "case_id": case_id,
                "jurisdiction": jurisdiction,
                "court": court,
                "date": date,
                "parties": parties or [],
                "docket": docket,
                "summary": summary,
                "text": text,
                "tags": tags or [],
                "corpus_id": corpus_id,
            },
        )

    async def merge_amendment(
        self,
        *,
        amendment_id: str,
        article_id: str,
        text: str,
        date: str | None = None,
        current: bool = False,
    ) -> None:
        """MERGE an Amendment node and attach it to its Article."""
        await self._run(
            """
            MERGE (am:Amendment {id: $amendment_id})
              ON CREATE SET am.text = $text, am.date = $date, am.current = $current
            WITH am
            MATCH (a:Article {id: $article_id})
            MERGE (a)-[:AMENDED_BY]->(am)
            """,
            {
                "amendment_id": amendment_id,
                "article_id": article_id,
                "text": text,
                "date": date,
                "current": current,
            },
        )

    async def merge_document(
        self,
        *,
        document_id: str,
        title: str | None = None,
        source_type: str | None = None,
        corpus_id: str | None = None,
    ) -> None:
        """MERGE a user Document node."""
        await self._run(
            """
            MERGE (d:Document {id: $document_id})
              ON CREATE SET
                d.title       = $title,
                d.source_type = $source_type,
                d.corpus_id   = $corpus_id
            """,
            {
                "document_id": document_id,
                "title": title,
                "source_type": source_type,
                "corpus_id": corpus_id,
            },
        )

    async def merge_clause(
        self,
        *,
        clause_id: str,
        document_id: str,
        text: str,
        heading: str | None = None,
        clause_number: str | None = None,
    ) -> None:
        """MERGE a Clause node and attach it to its Document."""
        await self._run(
            """
            MERGE (cl:Clause {id: $clause_id})
              ON CREATE SET
                cl.text          = $text,
                cl.heading       = $heading,
                cl.clause_number = $clause_number
            WITH cl
            MATCH (d:Document {id: $document_id})
            MERGE (d)-[:HAS_CLAUSE]->(cl)
            """,
            {
                "clause_id": clause_id,
                "document_id": document_id,
                "text": text,
                "heading": heading,
                "clause_number": clause_number,
            },
        )

    async def merge_risk_flag(
        self,
        *,
        risk_flag_id: str,
        clause_id: str,
        risk_type: str,
        severity: str,
        explanation: str | None = None,
    ) -> None:
        """MERGE a RiskFlag node and attach it to its Clause."""
        await self._run(
            """
            MERGE (rf:RiskFlag {id: $risk_flag_id})
              ON CREATE SET
                rf.risk_type   = $risk_type,
                rf.severity    = $severity,
                rf.explanation = $explanation
            WITH rf
            MATCH (cl:Clause {id: $clause_id})
            MERGE (cl)-[:RISKS]->(rf)
            """,
            {
                "risk_flag_id": risk_flag_id,
                "clause_id": clause_id,
                "risk_type": risk_type,
                "severity": severity,
                "explanation": explanation,
            },
        )

    # ------------------------------------------------------------------
    # Relationship creation
    # ------------------------------------------------------------------

    async def add_article_reference(self, from_id: str, to_id: str) -> None:
        """Create a REFERENCES edge between two articles (skips if either missing)."""
        await self._run(
            """
            MATCH (a:Article {id: $from_id})
            MATCH (b:Article {id: $to_id})
            MERGE (a)-[:REFERENCES]->(b)
            """,
            {"from_id": from_id, "to_id": to_id},
        )

    async def add_case_cites(self, citing_id: str, cited_id: str) -> None:
        """Create a CITES edge between two Case nodes."""
        await self._run(
            """
            MATCH (a:Case {id: $citing_id})
            MATCH (b:Case {id: $cited_id})
            MERGE (a)-[:CITES]->(b)
            """,
            {"citing_id": citing_id, "cited_id": cited_id},
        )

    async def add_case_applies_article(self, case_id: str, article_id: str) -> None:
        """Create APPLIES and reciprocal INTERPRETED_BY edges."""
        await self._run(
            """
            MATCH (c:Case {id: $case_id})
            MATCH (a:Article {id: $article_id})
            MERGE (c)-[:APPLIES]->(a)
            MERGE (a)-[:INTERPRETED_BY]->(c)
            """,
            {"case_id": case_id, "article_id": article_id},
        )

    async def add_document_governed_by(self, document_id: str, article_id: str) -> None:
        """Create a GOVERNED_BY edge from a Document to an Article."""
        await self._run(
            """
            MATCH (d:Document {id: $document_id})
            MATCH (a:Article {id: $article_id})
            MERGE (d)-[:GOVERNED_BY]->(a)
            """,
            {"document_id": document_id, "article_id": article_id},
        )

    # ------------------------------------------------------------------
    # Graph context queries
    # ------------------------------------------------------------------

    async def get_article_context(self, article_id: str) -> ArticleContext | None:
        """Return the full context for *article_id*: node + amendments + cases + citing articles.

        Returns ``None`` when the article does not exist in the graph.
        """
        rows = await self._run(
            """
            MATCH (a:Article {id: $article_id})
            OPTIONAL MATCH (a)-[:AMENDED_BY]->(am:Amendment)
            OPTIONAL MATCH (a)-[:INTERPRETED_BY]->(c:Case)
            OPTIONAL MATCH (other:Article)-[:REFERENCES]->(a)
            RETURN
              properties(a)                       AS article,
              collect(DISTINCT properties(am))    AS amendments,
              collect(DISTINCT properties(c))     AS cases,
              collect(DISTINCT properties(other)) AS citing_articles
            """,
            {"article_id": article_id},
        )
        if not rows or rows[0].get("article") is None:
            return None
        row = rows[0]
        return ArticleContext(
            article=row["article"],
            amendments=[r for r in row["amendments"] if r],
            interpreting_cases=[r for r in row["cases"] if r],
            citing_articles=[r for r in row["citing_articles"] if r],
        )

    async def get_case_context(self, case_id: str) -> CaseContext | None:
        """Return full context for *case_id*: node + cited articles/cases + subsequent citations.

        Returns ``None`` when the case does not exist in the graph.
        """
        rows = await self._run(
            """
            MATCH (c:Case {id: $case_id})
            OPTIONAL MATCH (c)-[:APPLIES]->(a:Article)
            OPTIONAL MATCH (c)-[:CITES]->(prior:Case)
            OPTIONAL MATCH (subsequent:Case)-[:CITES]->(c)
            RETURN
              properties(c)                           AS case,
              collect(DISTINCT properties(a))         AS cited_articles,
              collect(DISTINCT properties(prior))     AS cited_cases,
              collect(DISTINCT properties(subsequent)) AS subsequent_citations
            """,
            {"case_id": case_id},
        )
        if not rows or rows[0].get("case") is None:
            return None
        row = rows[0]
        return CaseContext(
            case=row["case"],
            cited_articles=[r for r in row["cited_articles"] if r],
            cited_cases=[r for r in row["cited_cases"] if r],
            subsequent_citations=[r for r in row["subsequent_citations"] if r],
        )

    async def get_citation_chain(self, article_id: str, depth: int = 2) -> list[CitationChainEntry]:
        """BFS REFERENCES network up to *depth* hops from *article_id*.

        *depth* is clamped to ``[1, 5]`` to prevent runaway queries.
        Returns one :class:`CitationChainEntry` per reachable path.
        """
        safe_depth = max(1, min(depth, 5))
        rows = await self._run(
            f"""
            MATCH path = (a:Article {{id: $article_id}})-[:REFERENCES*1..{safe_depth}]->(b:Article)
            RETURN
              [n IN nodes(path) | properties(n)] AS nodes,
              length(path)                        AS depth
            ORDER BY depth
            """,
            {"article_id": article_id},
        )
        return [CitationChainEntry(nodes=row["nodes"], depth=row["depth"]) for row in rows]

    # ------------------------------------------------------------------
    # Existence checks
    # ------------------------------------------------------------------

    async def article_exists(self, article_id: str) -> bool:
        """Return True when an Article with *article_id* exists in the graph."""
        rows = await self._run(
            "MATCH (a:Article {id: $article_id}) RETURN count(a) AS cnt",
            {"article_id": article_id},
        )
        return bool(rows and rows[0].get("cnt", 0) > 0)

    async def case_exists(self, case_id: str) -> bool:
        """Return True when a Case with *case_id* exists in the graph."""
        rows = await self._run(
            "MATCH (c:Case {id: $case_id}) RETURN count(c) AS cnt",
            {"case_id": case_id},
        )
        return bool(rows and rows[0].get("cnt", 0) > 0)

    # ------------------------------------------------------------------
    # Deletion
    # ------------------------------------------------------------------

    async def delete_corpus(self, corpus_id: str) -> None:
        """Detach-delete all nodes tagged with *corpus_id* and their relationships."""
        await self._run(
            """
            MATCH (n)
            WHERE n.corpus_id = $corpus_id
            DETACH DELETE n
            """,
            {"corpus_id": corpus_id},
        )
