"""URLLoader — httpx scraper for public legal databases with rate limiting."""

from __future__ import annotations

import re
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from hammurabi.ingestion.models import (
    DocumentType,
    LegalDocument,
    LegalSegment,
    RawPage,
    SourceType,
)

# Tags whose content is worth keeping (others stripped)
_KEEP_TAGS = re.compile(
    r"<(?:p|div|span|article|section|h[1-6]|li|td|pre|blockquote)[^>]*>([^<]*)</[^>]+>",
    re.IGNORECASE | re.DOTALL,
)
_HTML_TAGS = re.compile(r"<[^>]+>")
_MULTI_WS = re.compile(r"\n{3,}")


def _strip_html(html: str) -> str:
    """Very lightweight HTML → plain-text conversion (no external dep)."""
    # Replace block-level tags with newlines before stripping
    text = re.sub(r"<(?:br|p|div|h[1-6]|li|tr)[^>]*/?>", "\n", html, flags=re.IGNORECASE)
    text = _HTML_TAGS.sub("", text)
    text = _MULTI_WS.sub("\n\n", text)
    return text.strip()


class URLLoader:
    """Fetch a legal document from a URL and return a :class:`LegalDocument`.

    Parameters
    ----------
    rate_limit_seconds:
        Minimum wait between successive requests (default: 1 s).
    timeout:
        HTTP request timeout in seconds (default: 30 s).
    document_type:
        Force a document type; otherwise inferred from content.
    headers:
        Extra HTTP headers (e.g. ``{"Authorization": "Bearer …"}``).
    """

    def __init__(
        self,
        rate_limit_seconds: float = 1.0,
        timeout: float = 30.0,
        document_type: DocumentType | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        self._rate_limit = rate_limit_seconds
        self._timeout = timeout
        self._document_type = document_type
        self._headers = headers or {}
        self._last_request_at: float = 0.0

    # ------------------------------------------------------------------
    # LegalSourceLoader interface
    # ------------------------------------------------------------------

    def label(self) -> str:
        return "URLLoader"

    def metadata(self, source: str | Path) -> dict[str, Any]:
        url = str(source)
        parsed = urlparse(url)
        return {"url": url, "domain": parsed.netloc, "path": parsed.path}

    def load(self, source: str | Path) -> LegalDocument:
        import httpx  # noqa: PLC0415

        url = str(source)
        self._throttle()

        response = httpx.get(
            url,
            headers={"User-Agent": "Hammurabi/0.1 legal-corpus-loader", **self._headers},
            timeout=self._timeout,
            follow_redirects=True,
        )
        response.raise_for_status()
        self._last_request_at = time.monotonic()

        content_type = response.headers.get("content-type", "")
        raw_text: str

        raw_text = response.text if "json" in content_type else _strip_html(response.text)

        # Heuristic document type
        from hammurabi.ingestion.loaders.pdf import _detect_document_type  # noqa: PLC0415

        doc_type = self._document_type or _detect_document_type(raw_text)

        pages = [RawPage(number=1, text=raw_text)]
        segments = [LegalSegment(segment_type="section", text=raw_text)]

        return LegalDocument(
            source_type=SourceType.URL,
            document_type=doc_type,
            raw_text=raw_text,
            pages=pages,
            segments=segments,
            metadata={**self.metadata(url), "status_code": response.status_code},
        )

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _throttle(self) -> None:
        elapsed = time.monotonic() - self._last_request_at
        if elapsed < self._rate_limit:
            time.sleep(self._rate_limit - elapsed)
