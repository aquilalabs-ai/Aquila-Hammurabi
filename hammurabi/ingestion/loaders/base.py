"""Abstract base class for all legal source loaders."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from hammurabi.ingestion.models import LegalDocument


class LegalSourceLoader(ABC):
    """Uniform interface for all source connectors.

    Subclasses must implement :meth:`load`, :meth:`label`, and
    :meth:`metadata`.  The *source* argument to :meth:`load` and
    :meth:`metadata` is a file path (``str`` or :class:`~pathlib.Path`) for
    file-based loaders, or a URL string for :class:`URLLoader`.
    """

    @abstractmethod
    def load(self, source: str | Path) -> LegalDocument:
        """Parse *source* and return a structured legal document."""

    @abstractmethod
    def label(self) -> str:
        """Human-readable loader name (e.g. ``"PDFLoader"``)."""

    @abstractmethod
    def metadata(self, source: str | Path) -> dict[str, Any]:
        """Return source-level metadata without fully parsing the content."""
