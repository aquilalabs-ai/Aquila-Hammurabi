"""Legal article and case retrieval endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from hammurabi.api.auth import require_api_key
from hammurabi.api.deps import KnowledgeDep
from hammurabi.api.models import (
    ArticleCasesResponse,
    ArticleResponse,
    CaseResponse,
    CitationNetworkResponse,
)

router = APIRouter(tags=["Legal Research"], dependencies=[Depends(require_api_key)])


@router.get("/articles/autocomplete")
async def autocomplete_articles(
    q: str,
    knowledge: KnowledgeDep,
    limit: int = 20,
) -> list[dict]:
    """Substring search on article IDs for typeahead suggestions."""
    if len(q) < 2:
        return []
    return await knowledge.search_article_ids(q, limit=min(limit, 50))


@router.get(
    "/articles/{jurisdiction}/{code}/{article_id}",
    response_model=ArticleResponse,
)
async def get_article(
    jurisdiction: str,
    code: str,
    article_id: str,
    knowledge: KnowledgeDep,
) -> ArticleResponse:
    full_id = f"{jurisdiction.lower()}-{code.lower()}-{article_id}"
    ctx = await knowledge.get_article(full_id)
    if not ctx:
        raise HTTPException(status_code=404, detail="Article not found")
    return ArticleResponse(
        article=ctx.article,
        amendments=ctx.amendments,
        interpreting_cases=ctx.interpreting_cases,
        citing_articles=ctx.citing_articles,
    )


@router.get(
    "/articles/{jurisdiction}/{code}/{article_id}/cases",
    response_model=ArticleCasesResponse,
)
async def get_article_cases(
    jurisdiction: str,
    code: str,
    article_id: str,
    knowledge: KnowledgeDep,
) -> ArticleCasesResponse:
    full_id = f"{jurisdiction.lower()}-{code.lower()}-{article_id}"
    ctx = await knowledge.get_article(full_id)
    if not ctx:
        raise HTTPException(status_code=404, detail="Article not found")
    return ArticleCasesResponse(article_id=full_id, cases=ctx.interpreting_cases)


@router.get(
    "/articles/{jurisdiction}/{code}/{article_id}/citations",
    response_model=CitationNetworkResponse,
)
async def get_article_citations(
    jurisdiction: str,
    code: str,
    article_id: str,
    knowledge: KnowledgeDep,
    depth: int = 2,
) -> CitationNetworkResponse:
    full_id = f"{jurisdiction.lower()}-{code.lower()}-{article_id}"
    depth = max(1, min(depth, 5))
    chain = await knowledge.get_citation_network(full_id, depth=depth)
    return CitationNetworkResponse(
        article_id=full_id,
        depth=depth,
        paths=[{"nodes": e.nodes, "depth": e.depth} for e in chain],
    )


@router.get("/cases/{case_id}", response_model=CaseResponse)
async def get_case(case_id: str, knowledge: KnowledgeDep) -> CaseResponse:
    ctx = await knowledge.get_case(case_id)
    if not ctx:
        raise HTTPException(status_code=404, detail="Case not found")
    return CaseResponse(
        case=ctx.case,
        cited_articles=ctx.cited_articles,
        cited_cases=ctx.cited_cases,
        subsequent_citations=ctx.subsequent_citations,
    )
