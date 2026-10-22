"""PostgreSQL metadata registry for corpora, documents, drafts, and corpus sessions."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from hammurabi.config import settings

_CREATE_TABLES = """
CREATE TABLE IF NOT EXISTS corpora (
    id            TEXT        NOT NULL PRIMARY KEY,
    name          TEXT        NOT NULL,
    jurisdiction  TEXT        NOT NULL,
    status        TEXT        NOT NULL DEFAULT 'pending',
    article_count INTEGER     NOT NULL DEFAULT 0,
    case_count    INTEGER     NOT NULL DEFAULT 0,
    chunk_count   INTEGER     NOT NULL DEFAULT 0,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS documents (
    id               TEXT        NOT NULL PRIMARY KEY,
    corpus_id        TEXT        REFERENCES corpora(id) ON DELETE SET NULL,
    filename         TEXT        NOT NULL,
    document_type    TEXT        NOT NULL DEFAULT 'contract',
    status           TEXT        NOT NULL DEFAULT 'pending',
    content          TEXT        NOT NULL DEFAULT '',
    jurisdiction     TEXT        NOT NULL DEFAULT 'FR',
    analysis_job_id  TEXT,
    analysis_result  JSONB,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS drafts (
    id            TEXT        NOT NULL PRIMARY KEY,
    document_id   TEXT,
    content       TEXT        NOT NULL DEFAULT '',
    prompt        TEXT        NOT NULL DEFAULT '',
    jurisdiction  TEXT        NOT NULL DEFAULT 'FR',
    template_type TEXT        NOT NULL DEFAULT 'contract',
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS corpus_sessions (
    session_id  TEXT        NOT NULL PRIMARY KEY,
    corpus_id   TEXT        NOT NULL REFERENCES corpora(id) ON DELETE CASCADE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS global_sessions (
    session_id  TEXT        NOT NULL PRIMARY KEY,
    title       TEXT        NOT NULL DEFAULT '',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_documents_corpus_id ON documents (corpus_id);
CREATE INDEX IF NOT EXISTS idx_corpus_sessions_corpus_id ON corpus_sessions (corpus_id);
"""

_engine: AsyncEngine | None = None


def _get_engine() -> AsyncEngine:
    global _engine  # noqa: PLW0603
    if _engine is None:
        dsn = settings.postgres_dsn
        if dsn.startswith("postgresql+psycopg://"):
            dsn = dsn.replace("postgresql+psycopg://", "postgresql+psycopg_async://", 1)
        elif dsn.startswith("postgresql://"):
            dsn = dsn.replace("postgresql://", "postgresql+psycopg_async://", 1)
        _engine = create_async_engine(dsn, pool_pre_ping=True)
    return _engine


def _session_factory() -> sessionmaker[AsyncSession]:  # type: ignore[type-arg]
    return sessionmaker(_get_engine(), class_=AsyncSession, expire_on_commit=False)  # type: ignore[return-value]


async def ensure_schema() -> None:
    async with _get_engine().begin() as conn:
        await conn.execute(text(_CREATE_TABLES))


async def close_engine() -> None:
    global _engine  # noqa: PLW0603
    if _engine is not None:
        await _engine.dispose()
        _engine = None


# ── Corpora ───────────────────────────────────────────────────────────────────


async def create_corpus(name: str, jurisdiction: str) -> dict[str, Any]:
    corpus_id = str(uuid.uuid4())
    now = datetime.now(tz=UTC)
    async with _session_factory()() as db:
        await db.execute(
            text(
                "INSERT INTO corpora (id, name, jurisdiction, created_at) "
                "VALUES (:id, :name, :jurisdiction, :created_at)"
            ),
            {"id": corpus_id, "name": name, "jurisdiction": jurisdiction, "created_at": now},
        )
        await db.commit()
    return {
        "id": corpus_id,
        "name": name,
        "jurisdiction": jurisdiction,
        "status": "pending",
        "article_count": 0,
        "case_count": 0,
        "chunk_count": 0,
        "created_at": now,
    }


async def get_corpus(corpus_id: str) -> dict[str, Any] | None:
    async with _session_factory()() as db:
        result = await db.execute(
            text("SELECT * FROM corpora WHERE id = :id"),
            {"id": corpus_id},
        )
        row = result.mappings().fetchone()
    return dict(row) if row else None


async def list_corpora() -> list[dict[str, Any]]:
    async with _session_factory()() as db:
        result = await db.execute(text("SELECT * FROM corpora ORDER BY created_at DESC"))
        rows = result.mappings().fetchall()
    return [dict(r) for r in rows]


async def update_corpus_status(
    corpus_id: str,
    status: str,
    *,
    article_count: int = 0,
    case_count: int = 0,
    chunk_count: int = 0,
) -> None:
    async with _session_factory()() as db:
        await db.execute(
            text(
                "UPDATE corpora SET status = :status, article_count = :ac, "
                "case_count = :cc, chunk_count = :kc WHERE id = :id"
            ),
            {
                "id": corpus_id,
                "status": status,
                "ac": article_count,
                "cc": case_count,
                "kc": chunk_count,
            },
        )
        await db.commit()


async def delete_corpus_record(corpus_id: str) -> None:
    async with _session_factory()() as db:
        await db.execute(text("DELETE FROM corpora WHERE id = :id"), {"id": corpus_id})
        await db.commit()


# ── Documents ─────────────────────────────────────────────────────────────────


async def create_document(
    filename: str,
    document_type: str,
    content: str,
    corpus_id: str | None,
    jurisdiction: str = "FR",
) -> dict[str, Any]:
    doc_id = str(uuid.uuid4())
    now = datetime.now(tz=UTC)
    async with _session_factory()() as db:
        await db.execute(
            text(
                "INSERT INTO documents "
                "(id, corpus_id, filename, document_type, content, jurisdiction, created_at) "
                "VALUES (:id, :cid, :filename, :dtype, :content, :jurisdiction, :created_at)"
            ),
            {
                "id": doc_id,
                "cid": corpus_id,
                "filename": filename,
                "dtype": document_type,
                "content": content,
                "jurisdiction": jurisdiction,
                "created_at": now,
            },
        )
        await db.commit()
    return {
        "id": doc_id,
        "corpus_id": corpus_id,
        "filename": filename,
        "document_type": document_type,
        "status": "pending",
        "content": content,
        "jurisdiction": jurisdiction,
        "created_at": now,
    }


async def get_document(doc_id: str) -> dict[str, Any] | None:
    async with _session_factory()() as db:
        result = await db.execute(
            text("SELECT * FROM documents WHERE id = :id"), {"id": doc_id}
        )
        row = result.mappings().fetchone()
    return dict(row) if row else None


async def update_document_analysis(
    doc_id: str,
    job_id: str,
    status: str,
    result: dict[str, Any] | None = None,
) -> None:
    async with _session_factory()() as db:
        await db.execute(
            text(
                "UPDATE documents SET status = :status, analysis_job_id = :job_id, "
                "analysis_result = :result WHERE id = :id"
            ),
            {
                "id": doc_id,
                "status": status,
                "job_id": job_id,
                "result": json.dumps(result) if result is not None else None,
            },
        )
        await db.commit()


async def delete_document_record(doc_id: str) -> None:
    async with _session_factory()() as db:
        await db.execute(text("DELETE FROM documents WHERE id = :id"), {"id": doc_id})
        await db.commit()


# ── Drafts ────────────────────────────────────────────────────────────────────


async def create_draft(
    content: str,
    prompt: str,
    jurisdiction: str,
    template_type: str,
    document_id: str | None = None,
) -> dict[str, Any]:
    draft_id = str(uuid.uuid4())
    now = datetime.now(tz=UTC)
    async with _session_factory()() as db:
        await db.execute(
            text(
                "INSERT INTO drafts "
                "(id, document_id, content, prompt, jurisdiction, template_type, created_at) "
                "VALUES (:id, :did, :content, :prompt, :jurisdiction, :ttype, :created_at)"
            ),
            {
                "id": draft_id,
                "did": document_id,
                "content": content,
                "prompt": prompt,
                "jurisdiction": jurisdiction,
                "ttype": template_type,
                "created_at": now,
            },
        )
        await db.commit()
    return {
        "id": draft_id,
        "document_id": document_id,
        "content": content,
        "prompt": prompt,
        "jurisdiction": jurisdiction,
        "template_type": template_type,
        "created_at": now,
    }


async def get_draft(draft_id: str) -> dict[str, Any] | None:
    async with _session_factory()() as db:
        result = await db.execute(
            text("SELECT * FROM drafts WHERE id = :id"), {"id": draft_id}
        )
        row = result.mappings().fetchone()
    return dict(row) if row else None


async def update_draft_content(draft_id: str, content: str) -> None:
    async with _session_factory()() as db:
        await db.execute(
            text("UPDATE drafts SET content = :content WHERE id = :id"),
            {"id": draft_id, "content": content},
        )
        await db.commit()


# ── Corpus sessions ───────────────────────────────────────────────────────────


async def create_corpus_session(corpus_id: str) -> dict[str, Any]:
    session_id = str(uuid.uuid4())
    now = datetime.now(tz=UTC)
    async with _session_factory()() as db:
        await db.execute(
            text(
                "INSERT INTO corpus_sessions (session_id, corpus_id, created_at, updated_at) "
                "VALUES (:sid, :cid, :now, :now)"
            ),
            {"sid": session_id, "cid": corpus_id, "now": now},
        )
        await db.commit()
    return {"session_id": session_id, "corpus_id": corpus_id, "created_at": now, "updated_at": now}


async def list_corpus_sessions(corpus_id: str) -> list[dict[str, Any]]:
    async with _session_factory()() as db:
        result = await db.execute(
            text(
                "SELECT * FROM corpus_sessions WHERE corpus_id = :cid ORDER BY created_at DESC"
            ),
            {"cid": corpus_id},
        )
        rows = result.mappings().fetchall()
    return [dict(r) for r in rows]


async def delete_corpus_session(corpus_id: str, session_id: str) -> None:
    async with _session_factory()() as db:
        await db.execute(
            text(
                "DELETE FROM corpus_sessions WHERE session_id = :sid AND corpus_id = :cid"
            ),
            {"sid": session_id, "cid": corpus_id},
        )
        await db.commit()


# ── Global sessions ───────────────────────────────────────────────────────────


async def create_global_session(title: str = "") -> dict[str, Any]:
    session_id = str(uuid.uuid4())
    now = datetime.now(tz=UTC)
    async with _session_factory()() as db:
        await db.execute(
            text(
                "INSERT INTO global_sessions (session_id, title, created_at, updated_at) "
                "VALUES (:sid, :title, :now, :now)"
            ),
            {"sid": session_id, "title": title, "now": now},
        )
        await db.commit()
    return {"session_id": session_id, "title": title, "created_at": now, "updated_at": now}


async def list_global_sessions() -> list[dict[str, Any]]:
    async with _session_factory()() as db:
        result = await db.execute(
            text("SELECT * FROM global_sessions ORDER BY updated_at DESC")
        )
        rows = result.mappings().fetchall()
    return [dict(r) for r in rows]


async def touch_global_session(session_id: str) -> None:
    """Update updated_at so the session floats to the top of the list."""
    async with _session_factory()() as db:
        await db.execute(
            text(
                "UPDATE global_sessions SET updated_at = NOW() "
                "WHERE session_id = :sid"
            ),
            {"sid": session_id},
        )
        await db.commit()


async def delete_global_session(session_id: str) -> None:
    async with _session_factory()() as db:
        await db.execute(
            text("DELETE FROM global_sessions WHERE session_id = :sid"),
            {"sid": session_id},
        )
        await db.commit()
