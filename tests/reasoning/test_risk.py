"""Tests for the ClauseRiskScorer."""

from __future__ import annotations

import pytest

from hammurabi.reasoning.risk import ClauseRiskScorer, RiskType, Severity


@pytest.fixture
def scorer() -> ClauseRiskScorer:
    return ClauseRiskScorer(jurisdiction="FR")


class TestClauseRiskScorer:
    def test_liability_clause_detected(self, scorer: ClauseRiskScorer) -> None:
        text = "The liability of either party shall not exceed €10,000 in aggregate."
        reports = scorer.score(text)
        types = {r.risk_type for r in reports}
        assert RiskType.LIABILITY in types

    def test_termination_clause_detected(self, scorer: ClauseRiskScorer) -> None:
        text = "Either party may terminate this agreement upon 30 days written notice."
        reports = scorer.score(text)
        types = {r.risk_type for r in reports}
        assert RiskType.TERMINATION in types

    def test_ip_transfer_detected(self, scorer: ClauseRiskScorer) -> None:
        text = "The contractor hereby assigns all intellectual property rights to the client."
        reports = scorer.score(text)
        types = {r.risk_type for r in reports}
        assert RiskType.IP_TRANSFER in types

    def test_force_majeure_low_severity(self, scorer: ClauseRiskScorer) -> None:
        text = "Neither party shall be liable for force majeure events beyond their control."
        reports = scorer.score(text)
        fm = next((r for r in reports if r.risk_type == RiskType.FORCE_MAJEURE), None)
        assert fm is not None
        assert fm.severity == Severity.LOW

    def test_critical_escalation(self, scorer: ClauseRiskScorer) -> None:
        text = "The client shall have unlimited liability for all claims arising under this agreement."
        reports = scorer.score(text)
        liab = next((r for r in reports if r.risk_type == RiskType.LIABILITY), None)
        assert liab is not None
        assert liab.severity == Severity.CRITICAL

    def test_no_risk_plain_text(self, scorer: ClauseRiskScorer) -> None:
        text = "The parties agree to meet on the first Monday of each month."
        reports = scorer.score(text)
        assert reports == []

    def test_governing_articles_fr(self, scorer: ClauseRiskScorer) -> None:
        text = "All disputes shall be submitted to arbitration under ICC rules."
        reports = scorer.score(text)
        arb = next((r for r in reports if r.risk_type == RiskType.ARBITRATION), None)
        assert arb is not None
        assert len(arb.governing_articles) > 0
        assert any("fr-cpc" in a for a in arb.governing_articles)

    def test_score_document_sorted_by_severity(self, scorer: ClauseRiskScorer) -> None:
        clauses = [
            "Either party may terminate this agreement.",  # MEDIUM
            "The contractor assigns all intellectual property rights.",  # HIGH
            "The client has unlimited liability.",  # CRITICAL
        ]
        reports = scorer.score_document(clauses)
        severities = [r.severity for r in reports]
        order = {Severity.CRITICAL: 0, Severity.HIGH: 1, Severity.MEDIUM: 2, Severity.LOW: 3}
        for i in range(len(severities) - 1):
            assert order[severities[i]] <= order[severities[i + 1]]

    def test_to_dict_structure(self, scorer: ClauseRiskScorer) -> None:
        text = "The contractor assigns all intellectual property rights to the client."
        reports = scorer.score(text)
        assert reports
        d = scorer.to_dict(reports[0])
        assert {"clause_text", "risk_type", "severity", "explanation", "suggested_improvement", "governing_articles"} <= d.keys()

    def test_non_compete_detected_french(self, scorer: ClauseRiskScorer) -> None:
        text = "Le prestataire s'engage à ne pas faire concurrence au client pendant 24 mois."
        reports = scorer.score(text)
        types = {r.risk_type for r in reports}
        assert RiskType.NON_COMPETE in types

    def test_eu_jurisdiction_articles(self) -> None:
        scorer_eu = ClauseRiskScorer(jurisdiction="EU")
        text = "The governing law of this agreement shall be that of the European Union."
        reports = scorer_eu.score(text)
        gov = next((r for r in reports if r.risk_type == RiskType.GOVERNING_LAW), None)
        assert gov is not None
        assert any("eu-rome" in a for a in gov.governing_articles)
