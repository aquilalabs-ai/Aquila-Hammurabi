"""PostgreSQL-backed conversation session persistence (30-day TTL)."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from hammurabi.config import settings

# ---------------------------------------------------------------------------
# DDL — run once via ensure_schema()
# ---------------------------------------------------------------------------

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS chat_sessions (
    session_id  TEXT        NOT NULL,
    messages    JSONB       NOT NULL DEFAULT '[]',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (session_id)
);

CREATE INDEX IF NOT EXISTS idx_chat_sessions_updated_at
    ON chat_sessions (updated_at);
"""

_TTL_DAYS = 30

# ---------------------------------------------------------------------------
# Engine — module-level singleton, lazily created
# ---------------------------------------------------------------------------

_engine: AsyncEngine | None = None


def _get_engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        # Replace psycopg (sync) scheme with psycopg+asyncio for SQLAlchemy async
        dsn = settings.postgres_dsn
        if dsn.startswith("postgresql+psycopg://"):
            dsn = dsn.replace("postgresql+psycopg://", "postgresql+psycopg_async://", 1)
        elif dsn.startswith("postgresql://"):
            dsn = dsn.replace("postgresql://", "postgresql+psycopg_async://", 1)
        _engine = create_async_engine(dsn, pool_pre_ping=True)
    return _engine


def _session_factory() -> sessionmaker[AsyncSession]:  # type: ignore[type-arg]
    return sessionmaker(_get_engine(), class_=AsyncSession, expire_on_commit=False)  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def ensure_schema() -> None:
    """Create the chat_sessions table if it does not exist."""
    async with _get_engine().begin() as conn:
        await conn.execute(text(_CREATE_TABLE))


async def load_messages(session_id: str) -> list[dict[str, Any]]:
    """Return stored messages for *session_id*, or [] if the session is new/expired."""
    cutoff = datetime.now(tz=timezone.utc) - timedelta(days=_TTL_DAYS)
    async with _session_factory()() as db:
        row = await db.execute(
            text(
                "SELECT messages FROM chat_sessions "
                "WHERE session_id = :sid AND updated_at >= :cutoff"
            ),
            {"sid": session_id, "cutoff": cutoff},
        )
        result = row.fetchone()
    if result is None:
        return []
    raw: Any = result[0]
    if isinstance(raw, str):
        return json.loads(raw)  # type: ignore[no-any-return]
    return raw  # type: ignore[return-value]


async def save_messages(session_id: str, messages: list[dict[str, Any]]) -> None:
    """Upsert *messages* for *session_id*, refreshing the updated_at timestamp."""
    payload = json.dumps(messages)
    async with _session_factory()() as db:
        await db.execute(
            text(
                """
                INSERT INTO chat_sessions (session_id, messages, updated_at)
                VALUES (:sid, CAST(:msgs AS jsonb), NOW())
                ON CONFLICT (session_id) DO UPDATE
                    SET messages   = EXCLUDED.messages,
                        updated_at = EXCLUDED.updated_at
                """
            ),
            {"sid": session_id, "msgs": payload},
        )
        await db.commit()


async def delete_session(session_id: str) -> None:
    """Permanently delete a session."""
    async with _session_factory()() as db:
        await db.execute(
            text("DELETE FROM chat_sessions WHERE session_id = :sid"),
            {"sid": session_id},
        )
        await db.commit()


async def purge_expired() -> int:
    """Delete all sessions older than TTL. Returns number of rows deleted."""
    cutoff = datetime.now(tz=timezone.utc) - timedelta(days=_TTL_DAYS)
    async with _session_factory()() as db:
        result = await db.execute(
            text("DELETE FROM chat_sessions WHERE updated_at < :cutoff RETURNING session_id"),
            {"cutoff": cutoff},
        )
        await db.commit()
        rows = result.fetchall()
    return len(rows)


async def close_engine() -> None:
    """Dispose the async engine connection pool on shutdown."""
    global _engine
    if _engine is not None:
        await _engine.dispose()
        _engine = None
