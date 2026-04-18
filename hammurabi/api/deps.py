"""FastAPI dependency providers — service singletons stored on app state."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import Depends, Request


def _get_knowledge(request: Request) -> Any:
    return request.app.state.knowledge


def _get_agent(request: Request) -> Any:
    return request.app.state.agent


KnowledgeDep = Annotated[Any, Depends(_get_knowledge)]
AgentDep = Annotated[Any, Depends(_get_agent)]
