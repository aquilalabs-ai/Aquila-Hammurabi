"""Seed the permanent knowledge base with legal codes.

Usage
-----
# Ingest a local Légifrance XML file:
uv run python scripts/seed_knowledge.py --file path/to/code_civil.xml --code "Code civil" --jurisdiction FR

# Ingest multiple files:
uv run python scripts/seed_knowledge.py \\
    --file data/code_civil.xml      --code "Code civil"      --jurisdiction FR \\
    --file data/code_travail.xml    --code "Code du travail" --jurisdiction FR \\
    --file data/code_commerce.json  --code "Code de commerce" --jurisdiction FR

# Ingest directly from a URL (HTML page — basic extraction):
uv run python scripts/seed_knowledge.py --url https://... --code "Code civil" --jurisdiction FR

# List what is already ingested:
uv run python scripts/seed_knowledge.py --list

Supported formats
-----------------
- Légifrance XML  (.xml / .xhtml) — LEGI format from legifrance.gouv.fr open data
- EUR-Lex XML     (.xml)          — AKN/Formex format
- JSON            (.json)         — flat list, {"articles": [...]} or nested titles structure
- Plain text      (.txt)          — one article per non-blank paragraph

Where to get French legal code XML
------------------------------------
1. data.gouv.fr  — search "LEGI" for the full Légifrance XML dump (free, updated daily)
2. Légifrance PISTE API — https://api.piste.gouv.fr (free registration required)
3. EUR-Lex bulk download — https://eur-lex.europa.eu/statistics/legislative-observatory
"""

from __future__ import annotations

import argparse
import asyncio
import json
import selectors
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


# ── Windows event loop ────────────────────────────────────────────────────────

def _make_loop() -> asyncio.AbstractEventLoop:
    if sys.platform == "win32":
        return asyncio.SelectorEventLoop(selectors.SelectSelector())
    return asyncio.new_event_loop()


# ── CLI definition ─────────────────────────────────────────────────────────────

@dataclass
class CorpusSpec:
    source: str       # file path or URL
    source_type: str  # xml | json | txt | url | pdf | docx
    code: str         # human-readable code name, e.g. "Code civil"
    jurisdiction: str # ISO 3166-1, e.g. "FR"
    corpus_id: str    # stable ID used in Neo4j/Qdrant, e.g. "fr-civil"


def _infer_source_type(source: str) -> str:
    if source.startswith("http://") or source.startswith("https://"):
        return "url"
    suffix = Path(source).suffix.lower()
    return {
        ".xml": "xml", ".xhtml": "xml",
        ".json": "json",
        ".pdf": "pdf",
        ".docx": "docx",
        ".txt": "txt",
    }.get(suffix, "txt")


def _make_corpus_id(jurisdiction: str, code: str) -> str:
    slug = code.lower()
    for word in ("code", "du", "de", "la", "le", "les", "des", "l'", "d'"):
        slug = slug.replace(word, "")
    slug = "-".join(p for p in slug.split() if p)
    return f"{jurisdiction.lower()}-{slug or 'corpus'}"


# ── Ingestion ─────────────────────────────────────────────────────────────────

def _load_txt(path: Path, jurisdiction: str, code: str) -> Any:
    """Parse a plain-text code file: one article per non-blank paragraph."""
    from hammurabi.ingestion.models import (
        DocumentType, LegalDocument, LegalSegment, RawPage, SourceType
    )

    raw = path.read_text(encoding="utf-8")
    paragraphs = [p.strip() for p in raw.split("\n\n") if p.strip()]

    segments = []
    for i, para in enumerate(paragraphs, start=1):
        # Try to detect article number at the start: "Article 1234" or "Art. 1234"
        first_line = para.split("\n")[0]
        import re
        m = re.match(r"(?:Article|Art\.?)\s+(\S+)", first_line, re.IGNORECASE)
        num = m.group(1) if m else str(i)
        segments.append(
            LegalSegment(
                segment_type="article",
                text=para,
                article_number=num,
                hierarchy={"code": code},
                metadata={"code_name": code},
            )
        )

    return LegalDocument(
        source_type=SourceType.XML,
        document_type=DocumentType.STATUTE,
        raw_text=raw,
        pages=[RawPage(number=1, text=raw)],
        segments=segments,
        metadata={"code_name": code, "jurisdiction": jurisdiction},
    )


def _load_source(spec: CorpusSpec) -> Any:
    if spec.source_type == "xml":
        from hammurabi.ingestion.loaders import StructuredCodeLoader
        loader = StructuredCodeLoader(jurisdiction=spec.jurisdiction, code_name=spec.code)
        return loader.load(spec.source)
    elif spec.source_type == "json":
        from hammurabi.ingestion.loaders import StructuredCodeLoader
        loader = StructuredCodeLoader(jurisdiction=spec.jurisdiction, code_name=spec.code)
        return loader.load(spec.source)
    elif spec.source_type == "pdf":
        from hammurabi.ingestion.loaders import PDFLoader
        return PDFLoader().load(spec.source)
    elif spec.source_type == "docx":
        from hammurabi.ingestion.loaders import DOCXLoader
        return DOCXLoader().load(spec.source)
    elif spec.source_type == "url":
        from hammurabi.ingestion.loaders import URLLoader
        return URLLoader().load(spec.source)
    else:
        return _load_txt(Path(spec.source), spec.jurisdiction, spec.code)


async def _ingest_one(spec: CorpusSpec, quiet: bool = False) -> None:
    from hammurabi.ingestion.chunker import LegalChunker
    from hammurabi.ingestion.ner import LegalNERPipeline
    from hammurabi.ingestion.segmenter import LegalDocumentSegmenter
    from hammurabi.knowledge.service import LegalKnowledgeService

    print(f"\n{'='*60}")
    print(f"  Corpus : {spec.code}")
    print(f"  Source : {spec.source}")
    print(f"  ID     : {spec.corpus_id}")
    print(f"{'='*60}")

    print("  [1/5] Loading …", end="", flush=True)
    doc = await asyncio.to_thread(_load_source, spec)
    print(f" {len(doc.pages)} page(s), {len(doc.segments)} raw segment(s)")

    print("  [2/5] Segmenting …", end="", flush=True)
    # Structured/JSON loaders already produce article-level segments — skip re-segmentation.
    if not doc.segments:
        segmenter = LegalDocumentSegmenter()
        doc.segments = await asyncio.to_thread(segmenter.segment, doc)
    print(f" {len(doc.segments)} segment(s)")

    print("  [3/5] Chunking …", end="", flush=True)
    chunker = LegalChunker()
    chunks = await asyncio.to_thread(
        chunker.chunk_document, doc, None, spec.jurisdiction, spec.code
    )
    print(f" {len(chunks)} chunk(s)")

    print("  [4/5] NER tagging …", end="", flush=True)
    ner = LegalNERPipeline()
    for chunk in chunks:
        result = ner.extract(chunk.text)
        chunk.tags = list(set(chunk.tags + result.tags))
        if not chunk.code:
            chunk.code = spec.code
    print(" done")

    print("  [5/5] Ingesting into Neo4j + Qdrant …", end="", flush=True)
    svc = LegalKnowledgeService()
    try:
        summary = await svc.ingest_chunks(chunks, corpus_id=spec.corpus_id)
    finally:
        await svc.close()

    print(" done")
    print()
    print(f"  Articles merged : {summary.articles_merged}")
    print(f"  Cases merged    : {summary.cases_merged}")
    print(f"  Chunks upserted : {summary.chunks_upserted}")
    if summary.errors:
        print(f"  Warnings        : {len(summary.errors)}")
        if not quiet:
            for e in summary.errors[:10]:
                print(f"    - {e}")


async def _list_corpora() -> None:
    """Print corpora currently known to the metadata store."""
    from hammurabi.api.store import ensure_schema, list_corpora

    await ensure_schema()
    rows = await list_corpora()
    if not rows:
        print("No corpora in the metadata store yet.")
        print("(Neo4j/Qdrant may still contain data seeded without the API.)")
        return
    print(f"\n{'ID':<36}  {'Name':<30}  {'Juris':<6}  Status")
    print("-" * 80)
    for r in rows:
        print(f"{r['id']:<36}  {r['name']:<30}  {r['jurisdiction']:<6}  {r['status']}")


# ── Entry point ───────────────────────────────────────────────────────────────

def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Seed the Hammurabi knowledge base with legal codes.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument("--file", metavar="PATH", action="append", dest="files", default=[],
                   help="Path to a local XML/JSON/TXT file (repeatable)")
    p.add_argument("--url", metavar="URL", action="append", dest="urls", default=[],
                   help="URL to fetch and ingest (repeatable)")
    p.add_argument("--code", metavar="NAME",
                   help="Human-readable code name (e.g. 'Code civil')")
    p.add_argument("--jurisdiction", metavar="CODE", default="FR",
                   help="ISO 3166-1 jurisdiction code (default: FR)")
    p.add_argument("--corpus-id", metavar="ID",
                   help="Override the auto-generated corpus ID")
    p.add_argument("--batch", metavar="JSON",
                   help="Path to a JSON file with a list of corpus specs "
                        '[{"source": "...", "code": "...", "jurisdiction": "FR"}, ...]')
    p.add_argument("--list", action="store_true",
                   help="List existing corpora and exit")
    p.add_argument("--quiet", action="store_true",
                   help="Suppress per-warning output")
    return p.parse_args()


def main() -> None:
    args = _parse_args()

    loop = _make_loop()

    if args.list:
        loop.run_until_complete(_list_corpora())
        return

    specs: list[CorpusSpec] = []

    # --batch JSON file
    if args.batch:
        raw: list[dict[str, Any]] = json.loads(Path(args.batch).read_text())
        for item in raw:
            source = item["source"]
            code = item.get("code", Path(source).stem)
            jurisdiction = item.get("jurisdiction", "FR")
            corpus_id = item.get("corpus_id") or _make_corpus_id(jurisdiction, code)
            specs.append(CorpusSpec(
                source=source,
                source_type=item.get("source_type") or _infer_source_type(source),
                code=code,
                jurisdiction=jurisdiction,
                corpus_id=corpus_id,
            ))

    # --file / --url flags
    for path in args.files:
        code = args.code or Path(path).stem.replace("_", " ").replace("-", " ").title()
        jurisdiction = args.jurisdiction
        corpus_id = args.corpus_id or _make_corpus_id(jurisdiction, code)
        specs.append(CorpusSpec(
            source=path,
            source_type=_infer_source_type(path),
            code=code,
            jurisdiction=jurisdiction,
            corpus_id=corpus_id,
        ))

    for url in args.urls:
        code = args.code or "Web corpus"
        jurisdiction = args.jurisdiction
        corpus_id = args.corpus_id or _make_corpus_id(jurisdiction, code)
        specs.append(CorpusSpec(
            source=url,
            source_type="url",
            code=code,
            jurisdiction=jurisdiction,
            corpus_id=corpus_id,
        ))

    if not specs:
        print("Nothing to ingest. Pass --file, --url, or --batch. Use --list to inspect existing data.")
        sys.exit(1)

    for spec in specs:
        loop.run_until_complete(_ingest_one(spec, quiet=args.quiet))

    print("\nAll done. The knowledge base is permanently stored in Neo4j + Qdrant.")


if __name__ == "__main__":
    main()
