"""Risk scoring engine for legal clause analysis."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class RiskType(str, Enum):
    LIABILITY = "liability"
    TERMINATION = "termination"
    INDEMNIFICATION = "indemnification"
    IP_TRANSFER = "ip_transfer"
    NON_COMPETE = "non_compete"
    GOVERNING_LAW = "governing_law"
    ARBITRATION = "arbitration"
    FORCE_MAJEURE = "force_majeure"


class Severity(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


@dataclass
class RiskReport:
    """Structured risk assessment for a single clause."""

    clause_text: str
    risk_type: RiskType
    severity: Severity
    explanation: str
    suggested_improvement: str
    governing_articles: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Keyword taxonomy — maps risk type to (keyword_patterns, base_severity)
# ---------------------------------------------------------------------------

_TAXONOMY: list[tuple[RiskType, list[str], Severity]] = [
    (
        RiskType.LIABILITY,
        [
            r"\bliabilit",
            r"\bindemnif",
            r"\bresponsabilit",
            r"\bresponsabl",
            r"\blimit(?:ation)?\s+of\s+liabilit",
            r"\bexclusion\s+of\s+liabilit",
            r"\bdommages",
            r"\bpréjudice",
        ],
        Severity.HIGH,
    ),
    (
        RiskType.TERMINATION,
        [
            r"\btermination\b",
            r"\bresiliation\b",
            r"\brésiliat",
            r"\bterminate\b",
            r"\bbreach\b",
            r"\bmanquement\b",
            r"\bdefault\b",
        ],
        Severity.MEDIUM,
    ),
    (
        RiskType.INDEMNIFICATION,
        [
            r"\bindemnif",
            r"\bhold\s+harmless\b",
            r"\bindemnit",
            r"\bgarantir\b",
            r"\bgarantie\b",
        ],
        Severity.HIGH,
    ),
    (
        RiskType.IP_TRANSFER,
        [
            r"\bintellectual\s+propert",
            r"\bpropriété\s+intellectuelle\b",
            r"\bcopyright\b",
            r"\bassign(?:ment)?\b",
            r"\bcession\b",
            r"\btransfer\s+of\s+(?:ownership|rights)\b",
            r"\bdroit(?:s)?\s+d'auteur\b",
        ],
        Severity.HIGH,
    ),
    (
        RiskType.NON_COMPETE,
        [
            r"\bnon[- ]compet",
            r"\bnon[- ]solicitat",
            r"\bconcurrence\b",
            r"\brestrictive\s+covenant\b",
            r"\bclause\s+de\s+non[- ]concurrence\b",
        ],
        Severity.HIGH,
    ),
    (
        RiskType.GOVERNING_LAW,
        [
            r"\bgoverning\s+law\b",
            r"\bchoice\s+of\s+law\b",
            r"\bdroit\s+applicable\b",
            r"\bloi\s+applicable\b",
            r"\bjurisdiction\b",
            r"\bcompétence\b",
        ],
        Severity.MEDIUM,
    ),
    (
        RiskType.ARBITRATION,
        [
            r"\barbitrat",
            r"\bdispute\s+resolution\b",
            r"\brèglement\s+des\s+litiges\b",
            r"\bmediat",
            r"\bconciliat",
            r"\btribunal\b",
        ],
        Severity.MEDIUM,
    ),
    (
        RiskType.FORCE_MAJEURE,
        [
            r"\bforce\s+majeure\b",
            r"\bact\s+of\s+god\b",
            r"\bunforeseeable\b",
            r"\bimpossibilit",
            r"\bcas\s+de\s+force\s+majeure\b",
        ],
        Severity.LOW,
    ),
]

# Patterns that escalate severity to CRITICAL
_CRITICAL_ESCALATORS: list[str] = [
    r"\bunlimited\s+liabilit",
    r"\bresponsabilité\s+illimitée\b",
    r"\ball\s+intellectual\s+property\b",
    r"\ball\s+(?:current\s+and\s+future)\s+(?:works|inventions)\b",
    r"\bperpetual\b.*\birrevocable\b",
    r"\birrevocable\b.*\bperpetual\b",
    r"\bwaive(?:s|r)?\s+all\s+(?:rights|claims)\b",
    r"\brenounce\s+all\b",
]

# Patterns that downgrade severity to LOW
_LOW_DOWNGRADERS: list[str] = [
    r"\bmutually\s+agree\b",
    r"\breasonable\s+notice\b",
    r"\bstandard\s+terms\b",
    r"\bas\s+permitted\s+by\s+law\b",
]

# Jurisdiction → article cross-links for each risk type
_ARTICLE_MAP: dict[str, dict[RiskType, list[str]]] = {
    "FR": {
        RiskType.LIABILITY: ["fr-civil-1240", "fr-civil-1241", "fr-civil-1231-1"],
        RiskType.TERMINATION: ["fr-civil-1224", "fr-civil-1226", "fr-civil-1227"],
        RiskType.INDEMNIFICATION: ["fr-civil-1231", "fr-civil-1231-1", "fr-civil-1240"],
        RiskType.IP_TRANSFER: ["fr-cpi-l131-1", "fr-cpi-l131-3"],
        RiskType.NON_COMPETE: ["fr-civil-1104", "fr-civil-1170"],
        RiskType.GOVERNING_LAW: ["fr-civil-3", "fr-civil-2263"],
        RiskType.ARBITRATION: ["fr-cpc-1442", "fr-cpc-1448"],
        RiskType.FORCE_MAJEURE: ["fr-civil-1218", "fr-civil-1351"],
    },
    "EU": {
        RiskType.LIABILITY: ["eu-ucpd-11a", "eu-gdpr-82"],
        RiskType.IP_TRANSFER: ["eu-ctmr-17", "eu-dir-2001-29-art2"],
        RiskType.ARBITRATION: ["eu-reg-44-2001-art23"],
        RiskType.FORCE_MAJEURE: ["eu-cisg-79"],
        RiskType.GOVERNING_LAW: ["eu-rome-i-3", "eu-rome-i-4"],
        RiskType.TERMINATION: [],
        RiskType.INDEMNIFICATION: [],
        RiskType.NON_COMPETE: ["eu-tfeu-101", "eu-tfeu-102"],
    },
}


def _compile(patterns: list[str]) -> list[re.Pattern[str]]:
    return [re.compile(p, re.IGNORECASE) for p in patterns]


_COMPILED_TAXONOMY = [
    (rt, _compile(kws), base_sev) for rt, kws, base_sev in _TAXONOMY
]
_COMPILED_CRITICAL = _compile(_CRITICAL_ESCALATORS)
_COMPILED_LOW = _compile(_LOW_DOWNGRADERS)


class ClauseRiskScorer:
    """Score an individual clause text and return a :class:`RiskReport`."""

    def __init__(self, jurisdiction: str = "FR") -> None:
        self._jurisdiction = jurisdiction.upper()

    def score(self, clause_text: str) -> list[RiskReport]:
        """Identify all risk types present in *clause_text* and score each.

        Returns one :class:`RiskReport` per detected risk type (may be empty).
        """
        reports: list[RiskReport] = []
        for risk_type, patterns, base_severity in _COMPILED_TAXONOMY:
            if not any(p.search(clause_text) for p in patterns):
                continue
            severity = self._adjust_severity(clause_text, base_severity)
            reports.append(
                RiskReport(
                    clause_text=clause_text,
                    risk_type=risk_type,
                    severity=severity,
                    explanation=self._explain(risk_type, severity),
                    suggested_improvement=self._suggest(risk_type),
                    governing_articles=self._articles(risk_type),
                )
            )
        return reports

    def score_document(self, clauses: list[str]) -> list[RiskReport]:
        """Score all clauses in a document, highest severity first."""
        all_reports: list[RiskReport] = []
        for clause in clauses:
            all_reports.extend(self.score(clause))
        _order = {Severity.CRITICAL: 0, Severity.HIGH: 1, Severity.MEDIUM: 2, Severity.LOW: 3}
        all_reports.sort(key=lambda r: _order[r.severity])
        return all_reports

    def to_dict(self, report: RiskReport) -> dict[str, Any]:
        return {
            "clause_text": report.clause_text,
            "risk_type": report.risk_type.value,
            "severity": report.severity.value,
            "explanation": report.explanation,
            "suggested_improvement": report.suggested_improvement,
            "governing_articles": report.governing_articles,
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _adjust_severity(self, text: str, base: Severity) -> Severity:
        if any(p.search(text) for p in _COMPILED_CRITICAL):
            return Severity.CRITICAL
        if any(p.search(text) for p in _COMPILED_LOW) and base == Severity.HIGH:
            return Severity.MEDIUM
        return base

    def _articles(self, risk_type: RiskType) -> list[str]:
        jur_map = _ARTICLE_MAP.get(self._jurisdiction, _ARTICLE_MAP.get("FR", {}))
        return jur_map.get(risk_type, [])

    @staticmethod
    def _explain(risk_type: RiskType, severity: Severity) -> str:
        _EXPLANATIONS: dict[RiskType, str] = {
            RiskType.LIABILITY: "This clause modifies the default liability regime. Review caps, exclusions, and whether they comply with mandatory law.",
            RiskType.TERMINATION: "This clause governs the conditions under which the contract may be ended. Check for asymmetric rights and cure periods.",
            RiskType.INDEMNIFICATION: "Indemnification obligations may create unlimited financial exposure if not carefully scoped.",
            RiskType.IP_TRANSFER: "Intellectual property assignments can be broad and irrevocable. Ensure scope, territory, and duration are acceptable.",
            RiskType.NON_COMPETE: "Non-compete clauses restrict future economic activity. Verify geographic scope, duration, and proportionality.",
            RiskType.GOVERNING_LAW: "Choice of law and jurisdiction determines which courts have authority and which rules apply.",
            RiskType.ARBITRATION: "Arbitration clauses waive the right to litigate in state courts. Check seat, rules, and costs.",
            RiskType.FORCE_MAJEURE: "Force majeure definitions vary widely. Ensure the clause covers foreseeable disruptions.",
        }
        base = _EXPLANATIONS.get(risk_type, "Review this clause carefully.")
        if severity == Severity.CRITICAL:
            return f"CRITICAL: {base}"
        return base

    @staticmethod
    def _suggest(risk_type: RiskType) -> str:
        _SUGGESTIONS: dict[RiskType, str] = {
            RiskType.LIABILITY: "Add a mutual cap on liability (e.g., aggregate fees paid in the 12 months preceding the claim). Carve out fraud and wilful misconduct.",
            RiskType.TERMINATION: "Add a cure period (e.g., 30 days written notice) and ensure termination rights are mutual.",
            RiskType.INDEMNIFICATION: "Limit indemnification to third-party claims, cap at contract value, and require prompt notification.",
            RiskType.IP_TRANSFER: "Narrow the assignment to deliverables specifically created under this contract. Retain a licence-back for background IP.",
            RiskType.NON_COMPETE: "Limit to 12 months, define the restricted territory precisely, and ensure it is proportionate to the legitimate business interest.",
            RiskType.GOVERNING_LAW: "Consider a neutral seat (e.g., ICC Paris). Ensure the chosen law is familiar to all parties.",
            RiskType.ARBITRATION: "Specify the rules (ICC/AAA/LCIA), seat, language, and number of arbitrators. Consider an emergency arbitrator provision.",
            RiskType.FORCE_MAJEURE: "Add a non-exhaustive list of qualifying events (pandemic, cyberattack). Include notice and mitigation obligations.",
        }
        return _SUGGESTIONS.get(risk_type, "Review with qualified legal counsel.")
