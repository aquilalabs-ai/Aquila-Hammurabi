"""Fetch French jurisprudence (case law) from the Légifrance PISTE API and save as JSON.

The downloaded files are ready to be ingested by scripts/seed_knowledge.py.

Setup
-----
Same credentials as fetch_legifrance.py:
  PISTE_CLIENT_ID=your_client_id
  PISTE_CLIENT_SECRET=your_client_secret

Run:
  uv run python scripts/fetch_jurisprudence.py
  uv run python scripts/fetch_jurisprudence.py --courts CASS CE --years 2020 2021 2022
  uv run python scripts/fetch_jurisprudence.py --courts CASS --from-date 2015-01-01 --to-date 2023-12-31

Batching strategy
-----------------
The API caps results at 10 000 per query.  To stay under that limit the script
splits each (court, year) combination into its own request batch.  Use
--batch-size to tune page size (max 100) and --max-per-batch to cap how many
decisions are fetched per (court, year) bucket.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import selectors
import sys
import time
from pathlib import Path
from typing import Any

import httpx

# ── Constants ─────────────────────────────────────────────────────────────────

_OAUTH_URL = "https://oauth.piste.gouv.fr/api/oauth/token"
_API_BASE = "https://api.piste.gouv.fr/dila/legifrance/lf-engine-app"

_TODAY = time.strftime("%Y-%m-%d")
_CURRENT_YEAR = int(time.strftime("%Y"))

_OUT_DIR = Path("data/jurisprudence")

# Court registry.  PISTE routes each court to a different *fond* (corpus),
# not a JURIDICTION filter.  Keys are short slugs used for filenames.
# Values: (fond_code, human_name)
#
# Known fond codes:
#   JURI     – Cour de cassation + most civil/criminal courts
#   CETAT    – Conseil d'État + administrative courts (JADE)
#   CONSTIT  – Conseil constitutionnel
#   KALI     – conventions collectives (not case law, included for completeness)
_KNOWN_COURTS: dict[str, tuple[str, str]] = {
    "CASS":  ("JURI",    "Cour de cassation"),
    "CE":    ("CETAT",   "Conseil d'État"),
    "CC":    ("CONSTIT", "Conseil constitutionnel"),
    "CA":    ("JURI",    "Cours d'appel"),
    "TC":    ("JURI",    "Tribunal des conflits"),
}

# Default courts if none specified (high courts only — most relevant for IRAC)
_DEFAULT_COURTS = ["CASS", "CE", "CC"]

# Default year range for a first fetch (recent 5 years keeps the initial
# download manageable; extend with --from-date / --to-date as needed)
_DEFAULT_YEARS = list(range(_CURRENT_YEAR - 4, _CURRENT_YEAR + 1))


# ── OAuth2 token ──────────────────────────────────────────────────────────────

def _get_credentials() -> tuple[str, str]:
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
    body = ""
    try:
        body = json.dumps(resp.json(), ensure_ascii=False, indent=2)[:600]
    except Exception:
        body = resp.text[:600]

    hint = ""
    if resp.status_code == 403:
        hint = (
            "\n\nHint: 403 Forbidden — check your PISTE app is subscribed to the "
            "Légifrance API at https://developer.piste.gouv.fr"
        )
    elif resp.status_code == 401:
        hint = "\n\nHint: 401 Unauthorized — check PISTE_CLIENT_ID / PISTE_CLIENT_SECRET."

    raise httpx.HTTPStatusError(
        f"{resp.status_code} {resp.reason_phrase} for {path}\nBody: {body}{hint}",
        request=resp.request,
        response=resp,
    )


class LegifranceClient:
    """Thin async wrapper around the Légifrance PISTE REST API."""

    _REFRESH_MARGIN = 120

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        token: str,
        expires_in: int,
        delay: float = 0.25,
    ) -> None:
        self._client_id = client_id
        self._client_secret = client_secret
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

    # ── Jurisprudence helpers ─────────────────────────────────────────────────

    async def search_juri(
        self,
        fond: str,
        from_date: str,
        to_date: str,
        page: int = 0,
        page_size: int = 100,
    ) -> dict[str, Any]:
        """Search jurisprudence decisions for a fond (corpus) and date range.

        Each court maps to a distinct PISTE fond code (JURI / CETAT / CONSTIT).
        The date facet key is DATE_DECISION; champs must be an empty list for
        an unfiltered full-corpus search.
        """
        body: dict[str, Any] = {
            "fond": fond,
            "recherche": {
                "champs": [],
                "filtres": [
                    {
                        "facette": "DATE_DECISION",
                        "dates": {"start": from_date, "end": to_date},
                    },
                ],
                "pageNumber": page,
                "pageSize": page_size,
                "operateur": "ET",
                "sort": "DATE_DESC",
                "typePagination": "DEFAUT",
                "fromAdvancedRecherche": False,
            },
        }
        return await self._post("/search", body)

    async def get_decision(self, decision_id: str) -> dict[str, Any]:
        """Fetch the full text of one jurisprudence decision.

        The PISTE free tier exposes a single /consult/juri endpoint for all
        jurisprudence fonds.  A separate /consult/cetat endpoint exists but
        requires an additional JADE API subscription (403 without it).
        We therefore always use /consult/juri regardless of fond.
        """
        return await self._post("/consult/juri", {"textId": decision_id})


# ── Parsing ───────────────────────────────────────────────────────────────────

_STRIP_TAGS = re.compile(r"<[^>]+>")
_COLLAPSE_WS = re.compile(r"\s{2,}")


def _clean_html(text: str) -> str:
    text = _STRIP_TAGS.sub(" ", text)
    return _COLLAPSE_WS.sub(" ", text).strip()


def _unwrap_decision(raw: dict[str, Any]) -> dict[str, Any]:
    """Unwrap the envelope the API wraps around a decision object.

    Known shapes:
      {"decision": {...}}        ← /consult/juri
      {"text": {...}}            ← some versions
      {"texte": {...}}           ← /consult/cetat variant
      {"juri": {...}}            ← older API versions
      direct object              ← fallback
    """
    for key in ("decision", "text", "texte", "juri"):
        val = raw.get(key)
        if isinstance(val, dict) and val.get("id"):
            return val
    return raw


def _parse_decision(raw: dict[str, Any], *, debug_path: Path | None = None) -> dict[str, Any] | None:
    """Extract a clean case dict from a /consult/juri or /consult/cetat response.

    When *debug_path* is given the raw response is written there the first time
    this function is called — useful for diagnosing unexpected API shapes.
    """
    if debug_path is not None:
        debug_path.write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")

    dec = _unwrap_decision(raw)

    decision_id: str = dec.get("id", "")
    if not decision_id:
        return None

    ecli: str = dec.get("ecli", "")

    date_decision: str = (
        dec.get("dateDecision", "")
        or dec.get("dateTexte", "")
        or dec.get("date", "")
    )

    jur = dec.get("juridiction", "")
    if isinstance(jur, dict):
        jurisdiction: str = jur.get("label", jur.get("code", jur.get("id", "")))
    else:
        jurisdiction = str(jur)

    formation: str = (
        dec.get("formation", "")
        or dec.get("libelleFormation", "")
        or dec.get("chambre", "")
    )

    number: str = (
        dec.get("numero", "")
        or dec.get("numeroPourvoi", "")
        or dec.get("numDecision", "")
        or dec.get("numeroRequete", "")
    )

    solution: str = (
        dec.get("solution", "")
        or dec.get("libelleDecision", "")
        or dec.get("decisionAttaquee", {}).get("solution", "") if isinstance(dec.get("decisionAttaquee"), dict) else ""
    )

    # Full text — PISTE uses different field names across fonds
    texte: str = (
        dec.get("texteHtml", "")
        or dec.get("texteIntegral", "")
        or dec.get("contenu", "")
        or dec.get("texte", "")
        or dec.get("motivation", "")
        or dec.get("corps", "")
    )
    texte = _clean_html(texte)

    # Sommaire — fix operator-precedence: evaluate each branch explicitly
    _raw_sommaire = dec.get("sommaire", "")
    if not _raw_sommaire:
        _raw_sommaire = dec.get("abstract", "")
    if not _raw_sommaire:
        _soms = dec.get("sommaires")
        if isinstance(_soms, list) and _soms:
            first = _soms[0]
            _raw_sommaire = first.get("texte", first) if isinstance(first, dict) else str(first)
    sommaire: str = _clean_html(str(_raw_sommaire))

    # Cited articles / codes
    textes_vises: list[str] = []
    for ref in dec.get("textesVises", dec.get("textesCites", [])):
        if isinstance(ref, dict):
            label = ref.get("titre", ref.get("intitule", ref.get("id", "")))
            if label:
                textes_vises.append(str(label))
        elif isinstance(ref, str):
            textes_vises.append(ref)

    # Cited cases
    cases_cited: list[str] = []
    for ref in dec.get("jurisprudencesCitees", dec.get("casesCited", [])):
        if isinstance(ref, dict):
            ref_id = ref.get("id", ref.get("ecli", ""))
            if ref_id:
                cases_cited.append(str(ref_id))
        elif isinstance(ref, str):
            cases_cited.append(ref)

    if not texte and not sommaire:
        return None

    return {
        "id": decision_id,
        "ecli": ecli,
        "number": number,
        "date": date_decision,
        "jurisdiction": jurisdiction,
        "formation": formation,
        "solution": solution,
        "sommaire": sommaire,
        "texte": texte,
        "textes_vises": textes_vises,
        "cases_cited": cases_cited,
    }


def _parse_search_hit(hit: dict[str, Any]) -> str | None:
    """Extract the text ID from a search result hit.

    Known prefixes: JURITEXT (JURI), CETATEXT (CETAT), CONSTIT* (CONSTIT).
    As a fallback any string of 6+ uppercase-alphanumeric chars is accepted so
    that future or undocumented fonds still work.
    """
    def _accept(tid: str) -> bool:
        if not tid or len(tid) < 6:
            return False
        # Prefer known prefixes to avoid picking up stray numeric IDs
        if tid[:4].isupper():
            return True
        return False

    for key in ("id", "textId", "idTexte"):
        tid = str(hit.get(key, ""))
        if _accept(tid):
            return tid

    for t in hit.get("titles", []):
        if isinstance(t, dict):
            for key in ("id", "textId"):
                tid = str(t.get(key, ""))
                if _accept(tid):
                    return tid

    return None


# ── Main fetch routine ────────────────────────────────────────────────────────

async def fetch_batch(
    client: LegifranceClient,
    court_slug: str,
    fond: str,
    court_name: str,
    from_date: str,
    to_date: str,
    out_dir: Path,
    *,
    page_size: int = 100,
    max_decisions: int = 2000,
    force: bool = False,
    debug_first: bool = False,
) -> Path:
    """Fetch one (court, date-range) batch and write court_slug_YYYY[-MM].json."""
    safe_range = f"{from_date}_{to_date}".replace("-", "")
    out_path = out_dir / f"{court_slug}_{safe_range}.json"

    if out_path.exists() and not force:
        print(
            f"  ✓ {court_name} [{from_date} → {to_date}] — already downloaded "
            f"({out_path}), skipping (use --force to re-fetch)"
        )
        return out_path

    print(f"  Searching {court_name} [{from_date} → {to_date}] …", end="", flush=True)

    # Phase 1 — collect decision IDs via paginated search
    decision_ids: list[str] = []
    page = 0
    total: int | None = None

    while True:
        try:
            data = await client.search_juri(
                fond, from_date, to_date, page=page, page_size=page_size
            )
        except httpx.HTTPStatusError as exc:
            print(f" ERROR {exc.response.status_code}: {exc.response.text[:200]}")
            raise

        if total is None:
            total = int(data.get("totalResultNumber", data.get("total", 0)))

        results = data.get("results", data.get("hits", []))
        if not results:
            break

        for hit in results:
            tid = _parse_search_hit(hit)
            if tid and tid not in decision_ids:
                decision_ids.append(tid)

        if len(decision_ids) >= max_decisions:
            print(f"\n    ⚠ Reached --max-per-batch limit ({max_decisions}); stopping early.")
            decision_ids = decision_ids[:max_decisions]
            break

        if len(results) < page_size or len(decision_ids) >= (total or 0):
            break

        page += 1

    print(f" {len(decision_ids)} IDs (total in API: {total})")

    if not decision_ids:
        print("    No decisions found for this batch.")
        out_dir.mkdir(parents=True, exist_ok=True)
        payload: dict[str, Any] = {
            "court_slug": court_slug,
            "court_name": court_name,
            "from_date": from_date,
            "to_date": to_date,
            "jurisdiction": "FR",
            "fetched_at": _TODAY,
            "cases": [],
        }
        out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return out_path

    # Phase 2 — fetch full text for each decision
    cases: list[dict[str, Any]] = []
    errors = 0
    debug_written = False

    for i, did in enumerate(decision_ids, start=1):
        if i % 50 == 0 or i == len(decision_ids):
            print(f"    {i}/{len(decision_ids)} decisions fetched …", end="\r", flush=True)
        try:
            raw = await client.get_decision(did)
            debug_path: Path | None = None
            if debug_first and not debug_written:
                debug_path = out_dir / f"_debug_{court_slug}.json"
                debug_written = True
            parsed = _parse_decision(raw, debug_path=debug_path)
            if parsed:
                cases.append(parsed)
        except Exception as exc:  # noqa: BLE001
            errors += 1
            if errors <= 5:
                print(f"\n    Warning: could not fetch {did}: {exc}")

    print(f"\n    → {len(cases)} cases saved, {errors} errors")

    out_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "court_slug": court_slug,
        "court_name": court_name,
        "from_date": from_date,
        "to_date": to_date,
        "jurisdiction": "FR",
        "fetched_at": _TODAY,
        "cases": cases,
    }
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"    Saved → {out_path}")
    return out_path


# ── CLI ───────────────────────────────────────────────────────────────────────

def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Download French jurisprudence from the Légifrance PISTE API.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument(
        "--courts",
        nargs="+",
        metavar="SLUG",
        default=_DEFAULT_COURTS,
        help=(
            "Court slugs to fetch (default: CASS CE CC). "
            "Available: " + " ".join(_KNOWN_COURTS.keys())
        ),
    )
    p.add_argument(
        "--years",
        nargs="+",
        type=int,
        metavar="YYYY",
        default=None,
        help="Fetch only these years (mutually exclusive with --from-date/--to-date)",
    )
    p.add_argument(
        "--from-date",
        default=None,
        metavar="YYYY-MM-DD",
        help="Start date for a single date-range fetch (requires --to-date)",
    )
    p.add_argument(
        "--to-date",
        default=None,
        metavar="YYYY-MM-DD",
        help="End date for a single date-range fetch (requires --from-date)",
    )
    p.add_argument(
        "--out",
        default=str(_OUT_DIR),
        metavar="DIR",
        help=f"Output directory (default: {_OUT_DIR})",
    )
    p.add_argument(
        "--page-size",
        type=int,
        default=100,
        metavar="N",
        help="Search page size, max 100 (default: 100)",
    )
    p.add_argument(
        "--max-per-batch",
        type=int,
        default=2000,
        metavar="N",
        help="Maximum decisions fetched per (court, year) bucket (default: 2000)",
    )
    p.add_argument(
        "--delay",
        type=float,
        default=0.25,
        help="Seconds between API requests (default: 0.25)",
    )
    p.add_argument(
        "--force",
        action="store_true",
        help="Re-download even if the output file already exists",
    )
    p.add_argument(
        "--list-courts",
        action="store_true",
        help="Print available court slugs and exit",
    )
    p.add_argument(
        "--debug-first",
        action="store_true",
        help=(
            "Save the raw API response for the first decision in each batch to "
            "data/jurisprudence/_debug_<SLUG>.json — useful when cases save as 0"
        ),
    )
    return p.parse_args()


def _build_batches(args: argparse.Namespace) -> list[tuple[str, str, str, str, str]]:
    """Return list of (court_slug, fond, court_name, from_date, to_date)."""
    courts: list[tuple[str, str, str]] = []
    for slug in args.courts:
        if slug not in _KNOWN_COURTS:
            print(f"  Unknown court slug '{slug}'. Use --list-courts to see options.")
            continue
        fond, name = _KNOWN_COURTS[slug]
        courts.append((slug, fond, name))

    # Resolve date ranges
    if args.from_date and args.to_date:
        ranges = [(args.from_date, args.to_date)]
    elif args.years:
        ranges = [(f"{y}-01-01", f"{y}-12-31") for y in sorted(args.years)]
    else:
        ranges = [(f"{y}-01-01", f"{y}-12-31") for y in _DEFAULT_YEARS]

    return [
        (slug, facet, name, fd, td)
        for slug, facet, name in courts
        for fd, td in ranges
    ]


async def _async_main(args: argparse.Namespace) -> None:
    if args.list_courts:
        print(f"\n{'Slug':<10}  {'Fond code':<12}  Human name")
        print("-" * 50)
        for slug, (fond, name) in _KNOWN_COURTS.items():
            print(f"{slug:<10}  {fond:<12}  {name}")
        return

    client_id, client_secret = _get_credentials()

    print("Authenticating with PISTE …", end="", flush=True)
    token, expires_in = _fetch_token(client_id, client_secret)
    print(" OK")

    client = LegifranceClient(
        client_id=client_id,
        client_secret=client_secret,
        token=token,
        expires_in=expires_in,
        delay=args.delay,
    )

    try:
        batches = _build_batches(args)
        if not batches:
            print("Nothing to fetch.")
            return

        out_dir = Path(args.out)
        print(f"\nFetching {len(batches)} batch(es) → {out_dir}/\n")

        downloaded: list[Path] = []
        for slug, fond, name, fd, td in batches:
            print(f"▶ {name}  [{fd} → {td}]")
            try:
                path = await fetch_batch(
                    client,
                    court_slug=slug,
                    fond=fond,
                    court_name=name,
                    from_date=fd,
                    to_date=td,
                    out_dir=out_dir,
                    page_size=min(args.page_size, 100),
                    max_decisions=args.max_per_batch,
                    force=args.force,
                    debug_first=args.debug_first,
                )
                downloaded.append(path)
            except Exception as exc:  # noqa: BLE001
                print(f"  FAILED: {exc}")

        print(f"\n{'='*60}")
        print(f"Downloaded {len(downloaded)}/{len(batches)} batch(es) to {out_dir}/")

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


# uv run python scripts/fetch_jurisprudence.py --courts CE CC --from-date 2026-01-01 --to-date 2026-04-19 --max-per-batch 6000 --force
if __name__ == "__main__":
    main()