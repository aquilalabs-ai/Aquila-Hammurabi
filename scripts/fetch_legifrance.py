"""Fetch French legal codes from the Légifrance PISTE API and save as JSON.

The downloaded files are ready to be ingested by scripts/seed_knowledge.py.

Setup
-----
1. Go to https://developer.piste.gouv.fr
2. Sign in → "Mes applications" → create an app → subscribe to "Légifrance" API
3. Copy your Client ID and Client Secret into .env:
      PISTE_CLIENT_ID=your_client_id
      PISTE_CLIENT_SECRET=your_client_secret
4. Run:
      uv run python scripts/fetch_legifrance.py

OAuth flow
----------
PISTE uses OAuth2 Client Credentials:
  POST https://oauth.piste.gouv.fr/api/oauth/token
  grant_type=client_credentials, scope=openid

The access token is then passed as  Authorization: Bearer <token>  on every
API call to https://api.piste.gouv.fr/dila/legifrance/lf-engine-app/

Available codes
---------------
Run with --list to print all codes available in Légifrance, or pass --code
names on the command line.  The default set is the most-used French codes.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import selectors
import sys
import time
from pathlib import Path
from typing import Any

import httpx

# ── Constants ─────────────────────────────────────────────────────────────────

_OAUTH_URL = "https://oauth.piste.gouv.fr/api/oauth/token"
_API_BASE = "https://api.piste.gouv.fr/dila/legifrance/lf-engine-app"

# date used for "fetch the current version" — can be overridden via --date
_TODAY = time.strftime("%Y-%m-%d")

# Default output directory
_OUT_DIR = Path("data/codes")

# Well-known LEGITEXT identifiers for French codes.
# Competition law note: there is no standalone "Code de la concurrence" in France.
# Competition provisions (prix, ententes, abus de position dominante, pratiques
# restrictives) are in Book IV of the Code de commerce — fr-commerce below.
_KNOWN_CODES: dict[str, tuple[str, str]] = {
    # ── Droit privé fondamental ───────────────────────────────────────────────
    "fr-civil":           ("LEGITEXT000006070721", "Code civil"),
    "fr-commerce":        ("LEGITEXT000005634379", "Code de commerce"),          # incl. concurrence
    "fr-cpc":             ("LEGITEXT000006070716", "Code de procédure civile"),
    "fr-conso":           ("LEGITEXT000006069565", "Code de la consommation"),
    "fr-propriete-int":   ("LEGITEXT000006069414", "Code de la propriété intellectuelle"),
    "fr-assurances":      ("LEGITEXT000006073984", "Code des assurances"),

    # ── Droit du travail et protection sociale ────────────────────────────────
    "fr-travail":         ("LEGITEXT000006072050", "Code du travail"),
    "fr-secu-sociale":    ("LEGITEXT000006073189", "Code de la sécurité sociale"),
    "fr-action-sociale":  ("LEGITEXT000006074069", "Code de l'action sociale et des familles"),

    # ── Droit pénal et procédure ──────────────────────────────────────────────
    "fr-penal":           ("LEGITEXT000006070719", "Code pénal"),
    "fr-cpp":             ("LEGITEXT000006071154", "Code de procédure pénale"),

    # ── Droit public et administratif ─────────────────────────────────────────
    "fr-cja":             ("LEGITEXT000006070933", "Code de justice administrative"),
    "fr-commande-pub":    ("LEGITEXT000037701019", "Code de la commande publique"),
    "fr-cgfp":            ("LEGITEXT000044416551", "Code général de la fonction publique"),

    # ── Droit fiscal ──────────────────────────────────────────────────────────
    "fr-cgi":             ("LEGITEXT000006069577", "Code général des impôts"),

    # ── Droit financier et monétaire ──────────────────────────────────────────
    "fr-monetaire-fin":   ("LEGITEXT000006072026", "Code monétaire et financier"),

    # ── Droit de l'environnement et de l'urbanisme ────────────────────────────
    "fr-environnement":   ("LEGITEXT000006074220", "Code de l'environnement"),
    "fr-urbanisme":       ("LEGITEXT000006074075", "Code de l'urbanisme"),
    "fr-construction":    ("LEGITEXT000006074096", "Code de la construction et de l'habitation"),

    # ── Droit des transports ──────────────────────────────────────────────────
    "fr-transports":      ("LEGITEXT000023086525", "Code des transports"),
    "fr-route":           ("LEGITEXT000006074228", "Code de la route"),

    # ── Droit de la santé ─────────────────────────────────────────────────────
    "fr-sante-pub":       ("LEGITEXT000006072665", "Code de la santé publique"),

    # ── Droit rural ───────────────────────────────────────────────────────────
    "fr-rural":           ("LEGITEXT000006071367", "Code rural et de la pêche maritime"),

    # ── Droit de l'éducation ──────────────────────────────────────────────────
    "fr-education":       ("LEGITEXT000006071191", "Code de l'éducation"),
}


# ── OAuth2 token ──────────────────────────────────────────────────────────────

def _get_credentials() -> tuple[str, str]:
    """Read PISTE credentials from environment / .env file."""
    # Try .env file first (same directory as this script's project root)
    env_path = Path(__file__).parent.parent / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            os.environ.setdefault(key.strip(), val.strip())

    client_id = os.environ.get("PISTE_CLIENT_ID", "")
    client_secret = os.environ.get("PISTE_CLIENT_SECRET", "")

    if not client_id or not client_secret:
        print(
            "\nERROR: PISTE credentials not found.\n"
            "Set PISTE_CLIENT_ID and PISTE_CLIENT_SECRET in your .env file.\n"
            "Get them at https://developer.piste.gouv.fr → Mes applications.\n"
        )
        sys.exit(1)

    return client_id, client_secret


def _fetch_token(client_id: str, client_secret: str) -> tuple[str, int]:
    """Obtain a Bearer token via OAuth2 Client Credentials grant.

    Returns (access_token, expires_in_seconds).
    """
    resp = httpx.post(
        _OAUTH_URL,
        data={
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": client_secret,
            "scope": "openid",
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=30,
    )
    resp.raise_for_status()
    payload = resp.json()
    token: str = payload["access_token"]
    expires_in: int = int(payload.get("expires_in", 3600))
    return token, expires_in


# ── API helpers ───────────────────────────────────────────────────────────────

def _raise_api_error(resp: httpx.Response, path: str) -> None:
    """Raise a readable error with the response body for easier debugging."""
    body = ""
    try:
        body = json.dumps(resp.json(), ensure_ascii=False, indent=2)[:600]
    except Exception:
        body = resp.text[:600]

    hint = ""
    if resp.status_code == 403:
        hint = (
            "\n\nHint: 403 Forbidden usually means your PISTE application is not yet "
            "subscribed to the Légifrance API.\n"
            "Fix:\n"
            "  1. Go to https://developer.piste.gouv.fr → sign in\n"
            "  2. Open your application → 'Abonnements aux API'\n"
            "  3. Search for 'Légifrance' and subscribe (the free tier is sufficient)\n"
            "  4. Wait ~5 minutes for the subscription to activate, then retry.\n"
        )
    elif resp.status_code == 401:
        hint = "\n\nHint: 401 Unauthorized — check that PISTE_CLIENT_ID and PISTE_CLIENT_SECRET are correct."

    raise httpx.HTTPStatusError(
        f"{resp.status_code} {resp.reason_phrase} for {path}\nResponse body: {body}{hint}",
        request=resp.request,
        response=resp,
    )


class LegifranceClient:
    """Thin async wrapper around the Légifrance PISTE REST API."""

    # Refresh the token this many seconds before it actually expires.
    _REFRESH_MARGIN = 120

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        token: str,
        expires_in: int,
        date: str = _TODAY,
        delay: float = 0.2,
    ) -> None:
        self._client_id = client_id
        self._client_secret = client_secret
        self._date = date
        self._delay = delay
        self._token_expires_at = time.monotonic() + expires_in - self._REFRESH_MARGIN
        self._client = httpx.AsyncClient(
            base_url=_API_BASE,
            headers=self._build_headers(token),
            timeout=60,
        )

    @staticmethod
    def _build_headers(token: str) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def _refresh_token_if_needed(self) -> None:
        if time.monotonic() >= self._token_expires_at:
            token, expires_in = _fetch_token(self._client_id, self._client_secret)
            self._token_expires_at = time.monotonic() + expires_in - self._REFRESH_MARGIN
            self._client.headers.update(self._build_headers(token))

    async def close(self) -> None:
        await self._client.aclose()

    async def _post(self, path: str, body: dict[str, Any]) -> Any:
        self._refresh_token_if_needed()
        await asyncio.sleep(self._delay)
        resp = await self._client.post(path, json=body)
        if not resp.is_success:
            _raise_api_error(resp, path)
        return resp.json()

    async def _get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        self._refresh_token_if_needed()
        await asyncio.sleep(self._delay)
        resp = await self._client.get(path, params=params or {})
        if not resp.is_success:
            _raise_api_error(resp, path)
        return resp.json()

    # ── High-level helpers ────────────────────────────────────────────────────

    async def list_codes(self) -> list[dict[str, Any]]:
        """Return all codes available in Légifrance (POST + pagination)."""
        all_codes: list[dict[str, Any]] = []
        page = 0
        page_size = 100
        while True:
            data = await self._post(
                "/list/code",
                {"pageSize": page_size, "pageNumber": page, "état": "VIGUEUR"},
            )
            # Response shape varies: list, {"results": [...]}, {"codes": [...]}
            if isinstance(data, list):
                all_codes.extend(data)
                break
            items = data.get("results", data.get("codes", data.get("liste", [])))
            if not items:
                break
            all_codes.extend(items)
            # Stop if we got fewer items than a full page (last page)
            if len(items) < page_size:
                break
            page += 1
        return all_codes

    async def get_toc(self, text_id: str) -> dict[str, Any]:
        """Fetch the table of contents (section tree) for a code."""
        return await self._post(
            "/consult/code/tableMatieres",
            {"date": self._date, "textId": text_id},
        )

    async def get_article(self, article_id: str) -> dict[str, Any]:
        """Fetch a single article by its LEGIARTI identifier."""
        return await self._post(
            "/consult/getArticle",
            {"id": article_id, "date": self._date},
        )

    async def get_section_articles(self, section_id: str, text_id: str) -> list[dict[str, Any]]:
        """Fetch all articles inside a section (may return paginated results)."""
        data = await self._post(
            "/consult/code/sectionId",
            {"date": self._date, "sectionId": section_id, "textId": text_id},
        )
        return data.get("articles", [])


# ── Article extraction ────────────────────────────────────────────────────────

def _collect_article_ids(node: dict[str, Any]) -> list[str]:
    """Recursively collect LEGIARTI article IDs from a TOC node."""
    ids: list[str] = []
    # Articles are leaves with an "id" like "LEGIARTI..."
    node_id: str = node.get("id", "")
    if node_id.startswith("LEGIARTI"):
        ids.append(node_id)
    for child in node.get("articles", []):
        if isinstance(child, dict):
            child_id = child.get("id", "")
            if child_id.startswith("LEGIARTI"):
                ids.append(child_id)
    for section in node.get("sections", []):
        if isinstance(section, dict):
            ids.extend(_collect_article_ids(section))
    return ids


def _collect_section_meta(node: dict[str, Any], path: list[str] | None = None) -> dict[str, list[str]]:
    """Build a map of article_id → [title, chapter, section, ...] hierarchy path."""
    if path is None:
        path = []
    result: dict[str, list[str]] = {}

    title = node.get("title", node.get("intitule", ""))
    current_path = [*path, title] if title else path

    for article in node.get("articles", []):
        if isinstance(article, dict):
            aid = article.get("id", "")
            if aid.startswith("LEGIARTI"):
                result[aid] = current_path

    for section in node.get("sections", []):
        if isinstance(section, dict):
            result.update(_collect_section_meta(section, current_path))

    return result


def _parse_article(raw: dict[str, Any], hierarchy: list[str]) -> dict[str, Any] | None:
    """Extract a clean article dict from the API response."""
    # The API wraps in {"article": {...}} or returns directly
    art = raw.get("article", raw)

    article_id: str = art.get("id", "")
    num: str = art.get("num", art.get("numero", ""))
    content: str = (
        art.get("texteHtml", "")
        or art.get("texte", "")
        or art.get("content", "")
        or art.get("text", "")
    )

    # Strip basic HTML tags from texteHtml
    import re
    content = re.sub(r"<[^>]+>", " ", content)
    content = re.sub(r"\s{2,}", " ", content).strip()

    if not content:
        return None

    h = hierarchy
    return {
        "id": article_id,
        "number": num,
        "content": content,
        "title_name": h[0] if len(h) > 0 else "",
        "chapter_name": h[1] if len(h) > 1 else "",
        "section_name": h[2] if len(h) > 2 else "",
        "heading": art.get("nota", ""),
        "etat": art.get("etat", "VIGUEUR"),
        "date_debut": art.get("dateDebut", ""),
        "date_fin": art.get("dateFin", ""),
    }


# ── Main fetch routine ────────────────────────────────────────────────────────

async def fetch_code(
    client: LegifranceClient,
    corpus_id: str,
    text_id: str,
    code_name: str,
    out_dir: Path,
    *,
    force: bool = False,
) -> Path:
    """Download all articles for one code and write <corpus_id>.json."""
    out_path = out_dir / f"{corpus_id}.json"
    if out_path.exists() and not force:
        print(f"  ✓ {code_name} — already downloaded ({out_path}), skipping (use --force to re-fetch)")
        return out_path

    print(f"  Fetching TOC for {code_name} ({text_id}) …", end="", flush=True)
    try:
        toc = await client.get_toc(text_id)
    except httpx.HTTPStatusError as exc:
        print(f" ERROR {exc.response.status_code}: {exc.response.text[:200]}")
        raise

    # TOC may be nested under a key
    toc_root = toc.get("toc", toc.get("tableMatieres", toc))

    article_ids = _collect_article_ids(toc_root)
    hierarchy_map = _collect_section_meta(toc_root)
    print(f" {len(article_ids)} article IDs found")

    articles: list[dict[str, Any]] = []
    errors = 0

    for i, art_id in enumerate(article_ids, start=1):
        if i % 50 == 0 or i == len(article_ids):
            print(f"    {i}/{len(article_ids)} articles fetched …", end="\r", flush=True)
        try:
            raw = await client.get_article(art_id)
            parsed = _parse_article(raw, hierarchy_map.get(art_id, []))
            if parsed:
                articles.append(parsed)
        except Exception as exc:  # noqa: BLE001
            errors += 1
            if errors <= 5:
                print(f"\n    Warning: could not fetch {art_id}: {exc}")

    print(f"\n    → {len(articles)} articles saved, {errors} errors")

    out_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "corpus_id": corpus_id,
        "code_name": code_name,
        "text_id": text_id,
        "jurisdiction": "FR",
        "fetched_at": _TODAY,
        "articles": articles,
    }
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"    Saved → {out_path}")
    return out_path


# ── CLI ───────────────────────────────────────────────────────────────────────

def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Download French legal codes from the Légifrance PISTE API.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument(
        "--codes",
        nargs="+",
        metavar="ID",
        default=list(_KNOWN_CODES.keys()),
        help=(
            "Corpus IDs to fetch (default: all known codes). "
            "Available: " + " ".join(_KNOWN_CODES.keys())
        ),
    )
    p.add_argument("--list", action="store_true",
                   help="List all codes available in Légifrance and exit")
    p.add_argument("--custom", nargs=2, metavar=("LEGITEXT_ID", "CODE_NAME"), action="append",
                   default=[],
                   help="Fetch a custom code by its LEGITEXT ID, e.g. "
                        "--custom LEGITEXT000006070721 'Code civil'")
    p.add_argument("--date", default=_TODAY,
                   help=f"Fetch the version of the code at this date (default: {_TODAY})")
    p.add_argument("--out", default=str(_OUT_DIR), metavar="DIR",
                   help=f"Output directory (default: {_OUT_DIR})")
    p.add_argument("--delay", type=float, default=0.2,
                   help="Seconds between API requests (default: 0.2)")
    p.add_argument("--force", action="store_true",
                   help="Re-download even if the output file already exists")
    p.add_argument("--then-seed", action="store_true",
                   help="After downloading, immediately run seed_knowledge.py")
    return p.parse_args()


async def _async_main(args: argparse.Namespace) -> None:
    client_id, client_secret = _get_credentials()

    print("Authenticating with PISTE …", end="", flush=True)
    token, expires_in = _fetch_token(client_id, client_secret)
    print(" OK")

    client = LegifranceClient(
        client_id=client_id,
        client_secret=client_secret,
        token=token,
        expires_in=expires_in,
        date=args.date,
        delay=args.delay,
    )

    try:
        if args.list:
            # Try live API first; fall back to hardcoded table if not subscribed yet.
            try:
                print("\nFetching full code list from Légifrance API …")
                codes = await client.list_codes()
                print(f"\n{'LEGITEXT ID':<30}  Title")
                print("-" * 70)
                for c in sorted(codes, key=lambda x: x.get("title", x.get("titre", ""))):
                    cid = c.get("id", c.get("textId", ""))
                    title = c.get("title", c.get("titre", c.get("titrefull", "")))
                    print(f"{cid:<30}  {title}")
            except httpx.HTTPStatusError as exc:
                print(f"\nAPI call failed ({exc.response.status_code}). Showing built-in code list instead.\n")
                print(f"{'Corpus ID':<25}  {'LEGITEXT ID':<30}  Name")
                print("-" * 80)
                for cid, (text_id, name) in _KNOWN_CODES.items():
                    print(f"{cid:<25}  {text_id:<30}  {name}")
                print(
                    "\nTo fetch all Légifrance codes, subscribe your PISTE app to the "
                    "'Légifrance' API at https://developer.piste.gouv.fr"
                )
            return

        out_dir = Path(args.out)

        # Build the work list
        to_fetch: list[tuple[str, str, str]] = []  # (corpus_id, text_id, name)

        for corpus_id in args.codes:
            if corpus_id in _KNOWN_CODES:
                text_id, name = _KNOWN_CODES[corpus_id]
                to_fetch.append((corpus_id, text_id, name))
            else:
                print(f"  Unknown corpus ID '{corpus_id}'. Use --list to see options.")

        for text_id, name in args.custom:
            corpus_slug = name.lower().replace(" ", "-").replace("'", "")
            to_fetch.append((f"fr-{corpus_slug}", text_id, name))

        if not to_fetch:
            print("Nothing to fetch.")
            return

        print(f"\nFetching {len(to_fetch)} code(s) → {out_dir}/\n")
        downloaded: list[Path] = []

        for corpus_id, text_id, name in to_fetch:
            print(f"▶ {name}")
            try:
                path = await fetch_code(
                    client, corpus_id, text_id, name, out_dir, force=args.force
                )
                downloaded.append(path)
            except Exception as exc:  # noqa: BLE001
                print(f"  FAILED: {exc}")

        print(f"\n{'='*60}")
        print(f"Downloaded {len(downloaded)}/{len(to_fetch)} code(s) to {out_dir}/")

        if args.then_seed and downloaded:
            print("\nRunning seed_knowledge.py …\n")
            seed_script = Path(__file__).parent / "seed_knowledge.py"
            for path in downloaded:
                data = json.loads(path.read_text(encoding="utf-8"))
                corpus_id = data.get("corpus_id", path.stem)
                code_name = data.get("code_name", path.stem)
                import subprocess
                subprocess.run(
                    [
                        sys.executable, str(seed_script),
                        "--file", str(path),
                        "--code", code_name,
                        "--jurisdiction", "FR",
                        "--corpus-id", corpus_id,
                    ],
                    check=False,
                )

    finally:
        await client.close()


def main() -> None:
    args = _parse_args()

    if sys.platform == "win32":
        loop = asyncio.SelectorEventLoop(selectors.SelectSelector())
    else:
        loop = asyncio.new_event_loop()

    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(_async_main(args))
    finally:
        loop.close()


if __name__ == "__main__":
    main()
