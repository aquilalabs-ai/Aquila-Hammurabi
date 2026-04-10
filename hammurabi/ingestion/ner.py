"""Legal NER pipeline — named entity extraction with spaCy + regex fallback."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from hammurabi.ingestion.models import NERResult

if TYPE_CHECKING:
    import spacy  # noqa: F401
    from spacy.language import Language  # noqa: F401

# ---------------------------------------------------------------------------
# Jurisdiction keyword map
# ---------------------------------------------------------------------------

_JURISDICTION_KEYWORDS: dict[str, list[str]] = {
    "FR": ["france", "français", "française", "code civil", "legifrance", "droit français"],
    "EU": ["european union", "eur-lex", "directive", "regulation (eu)", "union européenne", "cjeu"],
    "EN-UK": ["united kingdom", "england", "wales", "uk law", "english law", "companies act"],
    "EN-US": ["united states", "u.s.", "federal", "usc", "state of", "american law"],
    "DE": ["deutschland", "bundesrepublik", "bürgerliches gesetzbuch", "bgb"],
    "BE": ["belgique", "belgium", "droit belge"],
    "CH": ["suisse", "switzerland", "code des obligations"],
}

# ---------------------------------------------------------------------------
# Tag / canonical label mapping
# ---------------------------------------------------------------------------

_TAG_KEYWORDS: dict[str, list[str]] = {
    "contract": ["contract", "agreement", "convention", "contrat", "accord"],
    "obligation": ["obligation", "duty", "shall", "must", "doit", "tenu de"],
    "liability": ["liability", "liable", "responsabilité", "responsable", "damages"],
    "termination": ["termination", "résiliation", "résolution", "expiry", "extinction"],
    "indemnification": ["indemnification", "indemnify", "indemnité", "compensation"],
    "penalty": ["penalty", "pénalité", "clause pénale", "liquidated damages"],
    "force_majeure": ["force majeure", "cas de force", "act of god"],
    "governing_law": ["governing law", "loi applicable", "droit applicable", "jurisdiction"],
    "arbitration": ["arbitration", "arbitrage", "arbitral", "adr"],
    "ip_transfer": [
        "intellectual property",
        "propriété intellectuelle",
        "copyright",
        "patent",
        "trademark",
    ],
    "non_compete": ["non-compete", "non-competition", "non concurrence", "exclusivity"],
    "confidentiality": [
        "confidentiality",
        "confidential",
        "confidentialité",
        "nda",
        "trade secret",
    ],
}

# ---------------------------------------------------------------------------
# Regex patterns (fallback when spaCy unavailable)
# ---------------------------------------------------------------------------

# Dates: "1 janvier 2020", "01/01/2020", "2020-01-01", "January 1, 2020"
_DATE_RE = re.compile(
    r"\b(\d{1,2}[\s/\-](?:\w+)[\s/\-]\d{4}"
    r"|\d{4}[\-/]\d{2}[\-/]\d{2}"
    r"|(?:january|february|march|april|may|june|july|august|september|october|november|december)"
    r"\s+\d{1,2},?\s+\d{4}"
    r"|(?:janvier|février|mars|avril|mai|juin|juillet|août|septembre|octobre|novembre|décembre)"
    r"\s+\d{4})\b",
    re.IGNORECASE,
)

# Monetary amounts: "€ 1,000", "1 000 €", "USD 5,000", "$1,000.00"
_MONEY_RE = re.compile(
    r"(?:€|EUR|USD|\$|£|GBP)\s*[\d][\d\s,']*"
    r"|[\d][\d\s,']*\s*(?:€|EUR|USD|dollars?|euros?|pounds?)\b",
    re.IGNORECASE,
)

# Parties in French contracts: "ENTRE … ET …"
_PARTIES_FR = re.compile(
    r"(?:ENTRE|ENTRE LES SOUSSIGNÉS)\s*[:\-]?\s*(.+?)\s*(?:ET|D'UNE PART)",
    re.IGNORECASE | re.DOTALL,
)
# English: "BETWEEN … AND …"
_PARTIES_EN = re.compile(
    r"BETWEEN\s*[:\-]?\s*(.+?)\s+AND\s+(.+?)(?:\s*\(the\s+[\"']?\w+[\"']?\))?[,\n]",
    re.IGNORECASE | re.DOTALL,
)

# Version / "entrée en vigueur" date
_DATE_FRAGMENT = r"(\d{4}[-/]\d{2}[-/]\d{2}|\d{1,2}[\s/\-]\w+[\s/\-]\d{4})"
_VERSION_RE = re.compile(
    r"(?:version|modifiée?|modified|amended|en vigueur|in force)"
    r"\s+(?:le|le\s+)?" + _DATE_FRAGMENT,
    re.IGNORECASE,
)
_EFFECTIVE_RE = re.compile(
    r"(?:effectif|effective|en vigueur|applicable|in force)"
    r"\s+(?:as of|from|à compter du|depuis le)?\s*" + _DATE_FRAGMENT,
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Regex-based NER (always available)
# ---------------------------------------------------------------------------


def _regex_ner(text: str) -> NERResult:
    result = NERResult()

    # Dates
    result.dates = [m.group(0).strip() for m in _DATE_RE.finditer(text)][:20]

    # Monetary amounts
    result.monetary_amounts = [m.group(0).strip() for m in _MONEY_RE.finditer(text)][:20]

    # Parties
    parties: list[str] = []
    for m in _PARTIES_FR.finditer(text[:1000]):
        parties.append(m.group(1).strip()[:120])
    for m in _PARTIES_EN.finditer(text[:1000]):
        parties.extend([m.group(1).strip()[:120], m.group(2).strip()[:120]])
    result.parties = parties[:10]

    # Jurisdictions
    text_lower = text.lower()
    result.jurisdictions = [
        code
        for code, keywords in _JURISDICTION_KEYWORDS.items()
        if any(kw in text_lower for kw in keywords)
    ]

    # Effective date and version
    eff_m = _EFFECTIVE_RE.search(text)
    result.effective_date = eff_m.group(1) if eff_m else None

    ver_m = _VERSION_RE.search(text)
    result.version = ver_m.group(1) if ver_m else None

    # Tags
    result.tags = [
        tag for tag, keywords in _TAG_KEYWORDS.items() if any(kw in text_lower for kw in keywords)
    ]

    return result


# ---------------------------------------------------------------------------
# spaCy-enhanced NER
# ---------------------------------------------------------------------------

_SPACY_MODEL: Any = None  # cached model instance
_SPACY_AVAILABLE: bool | None = None  # None = not yet probed


def _try_load_spacy(model_name: str) -> Any:
    """Attempt to load a spaCy model; return None on failure."""
    global _SPACY_AVAILABLE, _SPACY_MODEL  # noqa: PLW0603
    if _SPACY_AVAILABLE is False:
        return None
    if _SPACY_MODEL is not None:
        return _SPACY_MODEL
    try:
        import spacy  # noqa: PLC0415

        _SPACY_MODEL = spacy.load(model_name)
        _SPACY_AVAILABLE = True
    except (ImportError, OSError):
        _SPACY_AVAILABLE = False
        _SPACY_MODEL = None
    return _SPACY_MODEL


def _spacy_ner(text: str, nlp: Any) -> NERResult:
    """Run spaCy NER over *text* and merge with regex results."""
    result = _regex_ner(text)

    # Only process first 10 000 chars to stay within memory limits
    doc = nlp(text[:10_000])

    spacy_parties: list[str] = []
    spacy_dates: list[str] = []
    spacy_money: list[str] = []

    for ent in doc.ents:
        if ent.label_ in ("PER", "ORG"):
            spacy_parties.append(ent.text.strip())
        elif ent.label_ == "DATE":
            spacy_dates.append(ent.text.strip())
        elif ent.label_ == "MONEY":
            spacy_money.append(ent.text.strip())

    # Merge — spaCy results take precedence when non-empty
    if spacy_parties:
        result.parties = list(dict.fromkeys(spacy_parties + result.parties))[:10]
    if spacy_dates:
        result.dates = list(dict.fromkeys(spacy_dates + result.dates))[:20]
    if spacy_money:
        result.monetary_amounts = list(dict.fromkeys(spacy_money + result.monetary_amounts))[:20]

    return result


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


class LegalNERPipeline:
    """Extract named entities from legal text.

    Uses ``spaCy`` with the ``fr_core_news_lg`` model when available; falls
    back to pure-regex extraction when the model is not installed.

    Parameters
    ----------
    spacy_model:
        spaCy model name (default: ``"fr_core_news_lg"``).
    """

    def __init__(self, spacy_model: str = "fr_core_news_lg") -> None:
        self._spacy_model = spacy_model

    def extract(self, text: str) -> NERResult:
        """Run NER on *text* and return a :class:`~hammurabi.ingestion.models.NERResult`."""
        nlp = _try_load_spacy(self._spacy_model)
        if nlp is not None:
            return _spacy_ner(text, nlp)
        return _regex_ner(text)

    def detect_jurisdiction(self, text: str) -> str | None:
        """Return the most likely jurisdiction code (``"FR"``, ``"EU"``, …) or ``None``."""
        result = self.extract(text)
        return result.jurisdictions[0] if result.jurisdictions else None

    @staticmethod
    def normalize_tags(raw_tags: list[str]) -> list[str]:
        """Map free-form entity strings to canonical tag labels."""
        out: set[str] = set()
        for tag in raw_tags:
            tag_lower = tag.lower()
            for canonical, keywords in _TAG_KEYWORDS.items():
                if any(kw in tag_lower for kw in keywords):
                    out.add(canonical)
        return sorted(out)
