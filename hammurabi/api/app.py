"""FastAPI application factory with lifespan, CORS, and Swagger security scheme."""

from __future__ import annotations

import logging
import logging.config
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi

from hammurabi.api import store as meta_store
from hammurabi.api.routes import articles, chat, corpus, docs, draft, graph, health, report, search
from hammurabi.config import settings
from hammurabi.knowledge.service import LegalKnowledgeService
from hammurabi.reasoning.agent import IRACAgent
from hammurabi.reasoning.session import close_engine as close_session_engine
from hammurabi.reasoning.session import ensure_schema as ensure_session_schema

_log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    _log.info("startup: initialising session schema")
    await ensure_session_schema()
    _log.info("startup: initialising meta store schema")
    await meta_store.ensure_schema()

    _log.info("startup: building knowledge service and agent")
    knowledge = LegalKnowledgeService()
    agent = IRACAgent(knowledge)
    app.state.knowledge = knowledge
    app.state.agent = agent
    _log.info("startup: ready")

    yield

    _log.info("shutdown: closing connections")
    await knowledge.close()
    await close_session_engine()
    await meta_store.close_engine()
    _log.info("shutdown: done")


def _configure_langsmith() -> None:
    if settings.langsmith_api_key:
        os.environ["LANGCHAIN_TRACING_V2"] = "true"
        os.environ["LANGCHAIN_API_KEY"] = settings.langsmith_api_key
        os.environ["LANGCHAIN_PROJECT"] = settings.langsmith_project


_configure_langsmith()


def _configure_logging() -> None:
    logging.config.dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "default": {
                    "format": "%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
                    "datefmt": "%H:%M:%S",
                },
            },
            "handlers": {
                "console": {
                    "class": "logging.StreamHandler",
                    "formatter": "default",
                },
            },
            "loggers": {
                "hammurabi": {"level": "DEBUG", "handlers": ["console"], "propagate": False},
            },
            "root": {"level": "WARNING", "handlers": ["console"]},
        }
    )


_configure_logging()


def create_app() -> FastAPI:
    app = FastAPI(
        title="Hammurabi Legal Intelligence API",
        description=(
            "AI-powered legal research, document analysis, and contract drafting. "
            "Pass `X-API-Key` header when `API_KEY` is configured; omit it in open mode."
        ),
        version="0.1.0",
        lifespan=lifespan,
        swagger_ui_parameters={"persistAuthorization": True},
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health.router)
    app.include_router(corpus.router)
    app.include_router(docs.router)
    app.include_router(articles.router)
    app.include_router(search.router)
    app.include_router(chat.router)
    app.include_router(draft.router)
    app.include_router(report.router)
    app.include_router(graph.router)

    # Inject X-API-Key security scheme into OpenAPI spec
    def custom_openapi() -> dict:  # type: ignore[type-arg]
        if app.openapi_schema:
            return app.openapi_schema  # type: ignore[return-value]
        schema = get_openapi(
            title=app.title,
            version=app.version,
            description=app.description,
            routes=app.routes,
        )
        schema.setdefault("components", {}).setdefault("securitySchemes", {})["ApiKeyAuth"] = {
            "type": "apiKey",
            "in": "header",
            "name": "X-API-Key",
        }
        for path_item in schema.get("paths", {}).values():
            for operation in path_item.values():
                if isinstance(operation, dict):
                    operation.setdefault("security", [{"ApiKeyAuth": []}])
        app.openapi_schema = schema
        return schema  # type: ignore[return-value]

    app.openapi = custom_openapi  # type: ignore[method-assign]
    return app


app = create_app()
