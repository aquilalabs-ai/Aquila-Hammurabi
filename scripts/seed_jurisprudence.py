"""Ingest jurisprudence JSON files (produced by fetch_jurisprudence.py) into
Neo4j and Qdrant.

Usage
-----
# Ingest all files in the default directory:
uv run python scripts/seed_jurisprudence.py

# Ingest specific files:
uv run python scripts/seed_jurisprudence.py --file data/jurisprudence/CASS_20260401_20260419.json

# Use a custom directory:
uv run python scripts/seed_jurisprudence.py --dir data/jurisprudence

What this does
--------------
1. Neo4j  — MERGE a :Case node for every decision (id, ecli, court, date,
            formation, solution, summary, full text, tags, corpus_id).
2. Qdrant — Embed + upsert each case into the ``hammurabi_cases`` collection
            (dense cosine + sparse BM25; hybrid RRF search ready).
3. CITES  — After all cases in a file are merged, add Case→Case CITES edges
            from the ``cases_cited`` field (only if the cited case is already
            in the graph — safe to re-run as MERGE is idempotent).
4. APPLIES — Best-effort: tries to resolve ``textes_vises`` article refs to
             existing Article nodes and create Case→Article APPLIES edges.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import selectors
import sys
from pathlib import Path
from typing import Any

from hammurabi.ingestion.models import LegalChunk


# ── Windows event-loop fix ─────────────────────────────────────────────────────

def _make_loop() -> asyncio.AbstractEventLoop:
    if sys.platform == "win32":
        return asyncio.SelectorEventLoop(selectors.SelectSelector())
    return asyncio.new_event_loop()


# ── Article-ID resolver ────────────────────────────────────────────────────────

import re as _re

# Patterns like "article 1240", "art. L. 1235-3", "L. 442-6", "1382" etc.
_ART_NUM_RE = _re.compile(
    r"\b(?:articles?\s*|art\.\s*)?([LRD]\.\s*\d[\d\-]*|\d[\d\-]*(?:-\d+)*)\b",
    _re.IGNORECASE,
)


def _candidate_article_ids(textes_vises: list[str], jurisdiction: str) -> list[str]:
    """Heuristically extract article IDs from textes_vises strings.

    The API returns strings like "Code civil - Article 1240".  We extract the
    article number and build candidate IDs to look up in the graph.  These are
    best-effort — unresolvable refs are silently skipped.
    """
    candidates: list[str] = []
    j = jurisdiction.lower()
    for ref in textes_vises:
        for m in _ART_NUM_RE.finditer(ref):
            num = m.group(1).replace(" ", "").replace(".", "")
            # Try a few common code slugs
            for slug in ("civil", "commerce", "travail", "penal", "cpc", "cpp"):
                candidates.append(f"{j}-{slug}-{num}")
    return candidates


# ── Core ingestion ─────────────────────────────────────────────────────────────

async def _ingest_file(path: Path, *, batch_size: int = 50, quiet: bool = False) -> None:
    from hammurabi.knowledge.graph import LegalGraphClient
    from hammurabi.knowledge.service import LegalKnowledgeService

    data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    cases: list[dict[str, Any]] = data.get("cases", [])
    court_slug: str = data.get("court_slug", path.stem)
    court_name: str = data.get("court_name", court_slug)
    jurisdiction: str = data.get("jurisdiction", "FR")
    corpus_id = f"juri-{court_slug}"

    print(f"\n{'='*60}")
    print(f"  File       : {path}")
    print(f"  Court      : {court_name}")
    print(f"  Cases      : {len(cases)}")
    print(f"  Corpus ID  : {corpus_id}")
    print(f"{'='*60}")

    if not cases:
        print("  No cases — skipping.")
        return

    svc = LegalKnowledgeService()
    graph: LegalGraphClient = svc.graph
    total_merged = total_vectors = total_cites = total_applies = 0
    errors: list[str] = []

    # ── Phase 1: MERGE cases + embed into Qdrant ───────────────────────────────
    print(f"  [1/3] Ingesting {len(cases)} cases in batches of {batch_size} …")

    for batch_start in range(0, len(cases), batch_size):
        batch = cases[batch_start : batch_start + batch_size]
        chunks: list[LegalChunk] = []

        for i, case in enumerate(batch):
            decision_id: str = case.get("id", "")
            if not decision_id:
                continue

            sommaire: str = case.get("sommaire", "")
            texte: str = case.get("texte", "")

            # Use sommaire as the primary searchable text; fall back to full text
            # truncated to 4 000 chars so embeddings stay within model limits.
            search_text = sommaire or texte[:4000]
            if not search_text:
                continue

            chunks.append(
                LegalChunk(
                    text=search_text,
                    source_type="jurisprudence",
                    code=None,
                    article_id=None,
                    jurisdiction=jurisdiction,
                    effective_date=case.get("date") or None,
                    tags=[court_slug, "jurisprudence", jurisdiction.lower()],
                    chunk_index=batch_start + i,
                    token_count=len(search_text.split()),
                    metadata={
                        "segment_type": "judgment_part",
                        "case_id": decision_id,
                        "court": court_name,
                        "date": case.get("date", ""),
                        "docket": case.get("number", ""),
                        "summary": sommaire[:500] if sommaire else "",
                        "ecli": case.get("ecli", ""),
                        "formation": case.get("formation", ""),
                        "solution": case.get("solution", ""),
                    },
                )
            )

        if not chunks:
            continue

        try:
            summary = await svc.ingest_chunks(chunks, corpus_id=corpus_id)
            total_merged += summary.cases_merged
            total_vectors += summary.chunks_upserted
            errors.extend(summary.errors)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"Batch {batch_start}: {exc}")

        done = min(batch_start + batch_size, len(cases))
        print(f"    {done}/{len(cases)} …", end="\r", flush=True)

    print(f"\n    → {total_merged} cases merged, {total_vectors} vectors upserted")

    # ── Phase 2: CITES edges ───────────────────────────────────────────────────
    print("  [2/3] Wiring Case → Case CITES edges …")

    for case in cases:
        citing_id: str = case.get("id", "")
        if not citing_id:
            continue
        for cited_id in case.get("cases_cited", []):
            if not cited_id:
                continue
            try:
                if await graph.case_exists(cited_id):
                    await graph.add_case_cites(citing_id, cited_id)
                    total_cites += 1
            except Exception as exc:  # noqa: BLE001
                errors.append(f"CITES {citing_id}->{cited_id}: {exc}")

    print(f"    → {total_cites} CITES edge(s) created")

    # ── Phase 3: APPLIES edges (best-effort article resolution) ───────────────
    print("  [3/3] Wiring Case → Article APPLIES edges (best-effort) …")

    for case in cases:
        case_id: str = case.get("id", "")
        if not case_id:
            continue
        textes_vises: list[str] = case.get("textes_vises", [])
        if not textes_vises:
            continue

        for candidate_id in _candidate_article_ids(textes_vises, jurisdiction):
            try:
                if await graph.article_exists(candidate_id):
                    await graph.add_case_applies_article(case_id, candidate_id)
                    total_applies += 1
            except Exception as exc:  # noqa: BLE001
                errors.append(f"APPLIES {case_id}->{candidate_id}: {exc}")

    print(f"    → {total_applies} APPLIES edge(s) created")

    await svc.close()

    if errors and not quiet:
        print(f"\n  Warnings ({len(errors)}):")
        for e in errors[:10]:
            print(f"    - {e}")
        if len(errors) > 10:
            print(f"    … and {len(errors) - 10} more")


# ── CLI ───────────────────────────────────────────────────────────────────────

def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Seed Neo4j + Qdrant with jurisprudence from fetch_jurisprudence.py output.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument(
        "--file",
        metavar="PATH",
        action="append",
        dest="files",
        default=[],
        help="Path to a jurisprudence JSON file (repeatable). Defaults to all files in --dir.",
    )
    p.add_argument(
        "--dir",
        default="data/jurisprudence",
        metavar="DIR",
        help="Directory of jurisprudence JSON files (default: data/jurisprudence)",
    )
    p.add_argument(
        "--batch-size",
        type=int,
        default=50,
        metavar="N",
        help="Cases per embedding/ingestion batch (default: 50)",
    )
    p.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress per-warning output",
    )
    return p.parse_args()


async def _async_main(args: argparse.Namespace) -> None:
    paths: list[Path] = []

    if args.files:
        paths = [Path(f) for f in args.files]
    else:
        d = Path(args.dir)
        if not d.exists():
            print(f"Directory not found: {d}")
            sys.exit(1)
        paths = sorted(d.glob("*.json"))
        if not paths:
            print(f"No JSON files found in {d}")
            sys.exit(1)

    print(f"Seeding {len(paths)} file(s) …")
    for path in paths:
        await _ingest_file(path, batch_size=args.batch_size, quiet=args.quiet)

    print("\nDone. Cases are now searchable in Neo4j and Qdrant.")


def main() -> None:
    args = _parse_args()
    loop = _make_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(_async_main(args))
    finally:
        loop.close()


if __name__ == "__main__":
    main()