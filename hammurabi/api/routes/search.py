"""Hybrid semantic search across the full legal corpus."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from hammurabi.api.auth import require_api_key
from hammurabi.api.deps import KnowledgeDep
from hammurabi.api.models import SearchResponse, SearchResultItem

router = APIRouter(tags=["Search"], dependencies=[Depends(require_api_key)])


@router.get("/search", response_model=SearchResponse)
async def search(
    q: str,
    knowledge: KnowledgeDep,
    jurisdiction: str | None = None,
    source_type: str | None = None,
    tags: str | None = None,
    top_k: int = 10,
) -> SearchResponse:
    tag_list = [t.strip() for t in tags.split(",")] if tags else None
    results = await knowledge.search(
        q,
        jurisdiction=jurisdiction,
        source_type=source_type,
        tags=tag_list,
        top_k=min(top_k, 50),
    )
    items = [
        SearchResultItem(
            text=r.text,
            score=r.score,
            source_type=r.source_type,
            jurisdiction=r.jurisdiction,
            article_id=r.article_id,
            case_id=r.case_id,
            tags=r.tags,
            payload=r.payload,
        )
        for r in results
    ]
    return SearchResponse(query=q, total=len(items), results=items)
