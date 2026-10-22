"""Entry point — runs the Hammurabi FastAPI server via uvicorn."""

from __future__ import annotations

import asyncio
import sys


def main() -> None:
    import uvicorn

    from hammurabi.config import settings

    config = uvicorn.Config(
        "hammurabi.api.app:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.debug,
        log_level="debug" if settings.debug else "info",
    )
    server = uvicorn.Server(config)

    if sys.platform == "win32":
        # psycopg async (and other async drivers) require SelectorEventLoop on Windows.
        # ProactorEventLoop is the default on Windows in Python 3.8+, but psycopg rejects it.
        # Passing loop_factory to asyncio.run is the only reliable fix on Python 3.12+
        # because set_event_loop_policy() runs too late once uvicorn has imported asyncio.
        import selectors

        asyncio.run(
            server.serve(),
            loop_factory=lambda: asyncio.SelectorEventLoop(selectors.SelectSelector()),
        )
    else:
        asyncio.run(server.serve())


if __name__ == "__main__":
    main()
