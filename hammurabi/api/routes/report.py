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
)
from hammurabi.reasoning.tools import LegalNewsSearchTool

router = APIRouter(
    prefix="/report",
    tags=["Report Assistant"],
    dependencies=[Depends(require_api_key)],
)

_news_tool = LegalNewsSearchTool()


def _session(requested: str | None) -> str:
    return requested or f"report-{uuid.uuid4()}"


async def _fetch_news(topic: str) -> str:
    """Pre-fetch recent legal news for a topic and return formatted results."""
    # Derive a clean keyword query from the topic
    keyword_query = topic.strip().rstrip(".?!")
    try:
        return await _news_tool._arun(query=keyword_query, max_results=6, timelimit="m")
    except Exception:  # noqa: BLE001
        return ""


@router.post("/problematic", response_model=ReportResponse)
async def suggest_problematics(
    body: ReportProblematicRequest, agent: AgentDep
) -> ReportResponse:
    """Analyse a broad topic and propose 3 focused research questions (problématiques)."""
    level_hint = f" (niveau {body.study_level})" if body.study_level else ""
    field_hint = f" en {body.field}" if body.field else ""

    # Hard-fetch news before the agent runs so results are guaranteed in context.
    news_block = await _fetch_news(body.topic)
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
    response = await agent.invoke(query, session_id=session_id, force_route="report")
    return ReportResponse(session_id=session_id, response=response)


@router.post("/plan", response_model=ReportResponse)
async def generate_plan(body: ReportPlanRequest, agent: AgentDep) -> ReportResponse:
    """Generate a detailed hierarchical plan built around the confirmed problematic."""
    level_hint = f" (niveau {body.study_level})" if body.study_level else ""
    field_hint = f" en {body.field}" if body.field else ""
    constraints_hint = f"\n\nContraintes : {body.constraints}" if body.constraints else ""

    # Search on the problematic (more precise than the raw topic) and the topic in parallel.
    news_on_problematic, news_on_topic = await asyncio.gather(
        _fetch_news(body.problematic),
        _fetch_news(body.topic),
    )
    # Deduplicate: if both return the same block, keep one.
    if news_on_problematic == news_on_topic:
        news_block = news_on_problematic
    else:
        parts = [p for p in (news_on_problematic, news_on_topic) if p]
        news_block = "\n\n---\n\n".join(parts)

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
    response = await agent.invoke(query, session_id=session_id, force_route="report")
    return ReportResponse(session_id=session_id, response=response)


@router.post("/critique", response_model=ReportResponse)
async def critique_plan(body: ReportCritiqueRequest, agent: AgentDep) -> ReportResponse:
    """Critique an existing plan: assess structure, coherence, gaps, and suggest improvements."""
    topic_hint = f" sur le sujet : {body.topic}" if body.topic else ""
    level_hint = f" (niveau {body.study_level})" if body.study_level else ""

    query = (
        f"[PLAN CRITIQUE] Critique le plan suivant d'un mémoire/rapport de fin d'études"
        f"{topic_hint}{level_hint}.\n\nPlan à critiquer :\n{body.plan}"
    )
    session_id = _session(body.session_id)
    response = await agent.invoke(query, session_id=session_id, force_route="report")
    return ReportResponse(session_id=session_id, response=response)


@router.post("/coherence", response_model=ReportResponse)
async def check_coherence(body: ReportCoherenceRequest, agent: AgentDep) -> ReportResponse:
    """Verify the logical coherence of ideas, sections, or a draft passage."""
    topic_hint = f" (sujet : {body.topic})" if body.topic else ""

    query = (
        f"[COHERENCE CHECK] Vérifie la cohérence des idées/sections suivantes"
        f"{topic_hint}.\n\nContenu à analyser :\n{body.content}"
    )
    session_id = _session(body.session_id)
    response = await agent.invoke(query, session_id=session_id, force_route="report")
    return ReportResponse(session_id=session_id, response=response)
