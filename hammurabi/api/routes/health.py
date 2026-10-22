"""Liveness and readiness health checks."""

from __future__ import annotations

from fastapi import APIRouter

from hammurabi.api.deps import KnowledgeDep
from hammurabi.api.models import HealthResponse, ReadinessResponse

router = APIRouter(prefix="/health", tags=["Health"])


@router.get("", response_model=HealthResponse)
async def liveness() -> HealthResponse:
    return HealthResponse(status="ok")


@router.get("/ready", response_model=ReadinessResponse)
async def readiness(knowledge: KnowledgeDep) -> ReadinessResponse:
    neo4j_ok = True
    qdrant_ok = True

    try:
        await knowledge.graph._run("RETURN 1 AS n")
    except Exception:  # noqa: BLE001
        neo4j_ok = False

    try:
        knowledge.vector_store._client.get_collections()  # sync call
    except Exception:  # noqa: BLE001
        qdrant_ok = False

    overall = "ok" if (neo4j_ok and qdrant_ok) else "degraded"
    return ReadinessResponse(
        status=overall,
        neo4j="ok" if neo4j_ok else "unavailable",
        qdrant="ok" if qdrant_ok else "unavailable",
    )
