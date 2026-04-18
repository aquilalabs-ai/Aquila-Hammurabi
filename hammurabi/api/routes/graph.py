"""Graph visualisation, stats, and read-only Cypher query endpoints."""

from __future__ import annotations

import re

from fastapi import APIRouter, Depends, HTTPException

from hammurabi.api import store
from hammurabi.api.auth import require_api_key
from hammurabi.api.deps import KnowledgeDep
from hammurabi.api.models import CypherRequest, CypherResult, GraphData, GraphStats

router = APIRouter(tags=["Graph"], dependencies=[Depends(require_api_key)])

_ALLOWED_START = re.compile(
    r"^\s*(MATCH|CALL|RETURN|WITH|UNWIND|PROFILE|EXPLAIN)", re.IGNORECASE
)
_WRITE_OPS = re.compile(
    r"\b(CREATE|MERGE|SET|DELETE|DETACH|REMOVE|DROP)\b", re.IGNORECASE
)


def _assert_read_only(query: str) -> None:
    if not _ALLOWED_START.match(query):
        raise HTTPException(
            status_code=400,
            detail="Query must start with MATCH, CALL, RETURN, WITH, or UNWIND",
        )
    if _WRITE_OPS.search(query):
        raise HTTPException(status_code=400, detail="Write operations are not permitted")


@router.get("/corpus/{corpus_id}/graph", response_model=GraphData)
async def get_corpus_graph(corpus_id: str, knowledge: KnowledgeDep) -> GraphData:
    if not await store.get_corpus(corpus_id):
        raise HTTPException(status_code=404, detail="Corpus not found")

    raw_nodes = await knowledge.graph._run(
        "MATCH (n) WHERE n.corpus_id = $cid "
        "RETURN elementId(n) AS neo_id, labels(n) AS labels, properties(n) AS props LIMIT 1000",
        {"cid": corpus_id},
    )
    raw_edges = await knowledge.graph._run(
        "MATCH (a)-[r]->(b) "
        "WHERE a.corpus_id = $cid OR b.corpus_id = $cid "
        "RETURN elementId(a) AS source, elementId(b) AS target, type(r) AS rel_type, "
        "properties(r) AS props LIMIT 2000",
        {"cid": corpus_id},
    )

    nodes = [
        {"id": r["neo_id"], "labels": r["labels"], **r.get("props", {})}
        for r in raw_nodes
    ]
    edges = [
        {
            "source": r["source"],
            "target": r["target"],
            "type": r["rel_type"],
            **r.get("props", {}),
        }
        for r in raw_edges
    ]
    return GraphData(corpus_id=corpus_id, nodes=nodes, edges=edges)


@router.get("/corpus/{corpus_id}/graph/stats", response_model=GraphStats)
async def corpus_graph_stats(corpus_id: str, knowledge: KnowledgeDep) -> GraphStats:
    if not await store.get_corpus(corpus_id):
        raise HTTPException(status_code=404, detail="Corpus not found")

    node_rows = await knowledge.graph._run(
        "MATCH (n) WHERE n.corpus_id = $cid "
        "RETURN labels(n)[0] AS label, count(n) AS cnt",
        {"cid": corpus_id},
    )
    rel_rows = await knowledge.graph._run(
        "MATCH (a)-[r]->(b) "
        "WHERE a.corpus_id = $cid OR b.corpus_id = $cid "
        "RETURN type(r) AS rel_type, count(r) AS cnt",
        {"cid": corpus_id},
    )

    return GraphStats(
        corpus_id=corpus_id,
        node_counts={r["label"]: r["cnt"] for r in node_rows if r.get("label")},
        relationship_counts={r["rel_type"]: r["cnt"] for r in rel_rows},
    )


@router.post("/corpus/{corpus_id}/graph/query", response_model=CypherResult)
async def run_cypher(
    corpus_id: str,
    body: CypherRequest,
    knowledge: KnowledgeDep,
) -> CypherResult:
    if not await store.get_corpus(corpus_id):
        raise HTTPException(status_code=404, detail="Corpus not found")
    _assert_read_only(body.query)

    rows = await knowledge.graph._run(body.query)
    columns = list(rows[0].keys()) if rows else []
    return CypherResult(columns=columns, rows=rows, row_count=len(rows))
