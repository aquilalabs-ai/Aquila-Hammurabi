"""End-of-studies report / thesis assistant endpoints (student mode)."""

from __future__ import annotations

import asyncio
import uuid

from fastapi import APIRouter, Depends

from hammurabi.api.auth import require_api_key
from hammurabi.api.deps import AgentDep
from hammurabi.api.models import (
    ReportCoherenceRequest,
    ReportCritiqueRequest,
    ReportPlanRequest,
    ReportProblematicRequest,
    ReportResponse,
    ReportSourceItem,
)
from hammurabi.reasoning.sources import extract_kb_sources, parse_news_sources
from hammurabi.reasoning.tools import LegalNewsSearchTool

router = APIRouter(
    prefix="/report",
    tags=["Report Assistant"],
    dependencies=[Depends(require_api_key)],
)

_news_tool = LegalNewsSearchTool()


def _session(requested: str | None) -> str:
    return requested or f"report-{uuid.uuid4()}"


async def _fetch_news(topic: str) -> tuple[str, list[ReportSourceItem]]:
    """Pre-fetch recent legal news. Returns (formatted_text, structured_sources)."""
    keyword_query = topic.strip().rstrip(".?!")
    try:
        text = await _news_tool._arun(query=keyword_query, max_results=6, timelimit="m")
        return text, parse_news_sources(text)
    except Exception:  # noqa: BLE001
        return "", []


def _merge_sources(
    *source_lists: list[ReportSourceItem],
) -> list[ReportSourceItem]:
    """Deduplicate and merge source lists (web by URL, KB by article_id)."""
    seen_urls: set[str] = set()
    seen_ids: set[str] = set()
    merged: list[ReportSourceItem] = []
    for sources in source_lists:
        for s in sources:
            if s.type == "web":
                if s.url and s.url not in seen_urls:
                    seen_urls.add(s.url)
                    merged.append(s)
            else:
                if s.article_id and s.article_id not in seen_ids:
                    seen_ids.add(s.article_id)
                    merged.append(s)
    return merged


@router.post("/problematic", response_model=ReportResponse)
async def suggest_problematics(
    body: ReportProblematicRequest, agent: AgentDep
) -> ReportResponse:
    """Analyse a broad topic and propose 3 focused research questions (problématiques)."""
    print("\nGENERATING PROBLEMATIC\n")
    level_hint = f" (niveau {body.study_level})" if body.study_level else ""
    field_hint = f" en {body.field}" if body.field else ""

    news_block, web_sources = await _fetch_news(body.topic)
    news_section = (
        f"\n\n## Actualités juridiques récentes (pré-chargées)\n{news_block}"
        if news_block
        else "\n\n## Actualités juridiques récentes\nAucun résultat trouvé."
    )

    query = (
        f"[PROBLEMATIC GENERATION] Le sujet donné à l'étudiant est : « {body.topic} »."
        f" Analyse ce sujet{field_hint}{level_hint} et propose 3 problématiques focalisées."
        f"{news_section}"
        f"\n\nLes actualités ci-dessus sont déjà chargées — utilise-les directement. "
        "Lance uniquement `semantic_search` et `statute_lookup` pour compléter avec les sources KB."
    )
    session_id = _session(body.session_id)
    response, messages = await agent.invoke_with_sources(
        query, session_id=session_id, force_route="report_problematic"
    )
    sources = _merge_sources(web_sources, extract_kb_sources(messages))
    return ReportResponse(session_id=session_id, response=response, sources=sources)


@router.post("/plan", response_model=ReportResponse)
async def generate_plan(body: ReportPlanRequest, agent: AgentDep) -> ReportResponse:
    """Generate a detailed hierarchical plan built around the confirmed problematic."""
    print("\nGENERATING PLAN\n")
    level_hint = f" (niveau {body.study_level})" if body.study_level else ""
    field_hint = f" en {body.field}" if body.field else ""
    constraints_hint = f"\n\nContraintes : {body.constraints}" if body.constraints else ""

    (news_prob, web_prob), (news_topic, web_topic) = await asyncio.gather(
        _fetch_news(body.problematic),
        _fetch_news(body.topic),
    )
    # Deduplicate text blocks
    if news_prob == news_topic:
        news_block = news_prob
        web_sources = web_prob
    else:
        parts = [p for p in (news_prob, news_topic) if p]
        news_block = "\n\n---\n\n".join(parts)
        web_sources = _merge_sources(web_prob, web_topic)

    news_section = (
        f"\n\n## Actualités juridiques récentes (pré-chargées)\n{news_block}"
        if news_block
        else "\n\n## Actualités juridiques récentes\nAucun résultat trouvé."
    )

    query = (
        f"[PLAN GENERATION] Sujet : « {body.topic} »{field_hint}{level_hint}.\n"
        f"Problématique retenue : « {body.problematic} ».\n"
        f"Génère un plan détaillé centré sur cette problématique.{constraints_hint}"
        f"{news_section}"
        f"\n\nLes actualités ci-dessus sont déjà chargées — utilise-les directement. "
        "Lance uniquement `semantic_search` et `statute_lookup` pour les sources KB."
    )
    session_id = _session(body.session_id)
    response, messages = await agent.invoke_with_sources(
        query, session_id=session_id, force_route="report_plan"
    )
    sources = _merge_sources(web_sources, extract_kb_sources(messages))
    return ReportResponse(session_id=session_id, response=response, sources=sources)


@router.post("/critique", response_model=ReportResponse)
async def critique_plan(body: ReportCritiqueRequest, agent: AgentDep) -> ReportResponse:
    """Critique an existing plan: assess structure, coherence, gaps, and suggest improvements."""
    print("\nGENERATING PLAN CRITIQUE\n")
    topic_hint = f" sur le sujet : {body.topic}" if body.topic else ""
    level_hint = f" (niveau {body.study_level})" if body.study_level else ""

    query = (
        f"[PLAN CRITIQUE] Critique le plan suivant d'un mémoire/rapport de fin d'études"
        f"{topic_hint}{level_hint}.\n\nPlan à critiquer :\n{body.plan}"
    )
    session_id = _session(body.session_id)
    response, messages = await agent.invoke_with_sources(
        query, session_id=session_id, force_route="report_critique"
    )
    sources = _merge_sources(extract_kb_sources(messages))
    return ReportResponse(session_id=session_id, response=response, sources=sources)


@router.post("/coherence", response_model=ReportResponse)
async def check_coherence(body: ReportCoherenceRequest, agent: AgentDep) -> ReportResponse:
    """Verify the logical coherence of ideas, sections, or a draft passage."""
    print("\nGENERATING COHERENCE CHECK\n")
    topic_hint = f" (sujet : {body.topic})" if body.topic else ""

    query = (
        f"[COHERENCE CHECK] Vérifie la cohérence des idées/sections suivantes"
        f"{topic_hint}.\n\nContenu à analyser :\n{body.content}"
    )
    session_id = _session(body.session_id)
    response, messages = await agent.invoke_with_sources(
        query, session_id=session_id, force_route="report_coherence"
    )
    sources = _merge_sources(extract_kb_sources(messages))
    return ReportResponse(session_id=session_id, response=response, sources=sources)
