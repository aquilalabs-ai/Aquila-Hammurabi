"""In-memory background job registry for corpus ingestion and document analysis."""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class Job:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    type: str = ""
    status: str = "pending"
    result: dict[str, Any] | None = None
    error: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(tz=timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(tz=timezone.utc))


_jobs: dict[str, Job] = {}
_lock: asyncio.Lock | None = None


def _get_lock() -> asyncio.Lock:
    global _lock  # noqa: PLW0603
    if _lock is None:
        _lock = asyncio.Lock()
    return _lock


async def create_job(job_type: str) -> Job:
    async with _get_lock():
        job = Job(type=job_type)
        _jobs[job.id] = job
    return job


async def get_job(job_id: str) -> Job | None:
    return _jobs.get(job_id)


async def update_job(
    job_id: str,
    *,
    status: str,
    result: dict[str, Any] | None = None,
    error: str | None = None,
) -> None:
    async with _get_lock():
        if job := _jobs.get(job_id):
            job.status = status
            job.result = result
            job.error = error
            job.updated_at = datetime.now(tz=timezone.utc)
