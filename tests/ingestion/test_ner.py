"""Tests for the LegalNERPipeline (regex fallback path — no spaCy model required)."""

from __future__ import annotations

from hammurabi.ingestion.ner import LegalNERPipeline, _regex_ner

# Force regex path so tests work without the fr_core_news_lg model
NER = LegalNERPipeline(spacy_model="__nonexistent_model__")


# ---------------------------------------------------------------------------
# Date extraction
# ---------------------------------------------------------------------------


def test_extracts_iso_dates() -> None:
    result = _regex_ner("The contract was signed on 2023-05-15 and expires on 2025-12-31.")
    assert any("2023" in d for d in result.dates)
    assert any("2025" in d for d in result.dates)


def test_extracts_french_dates() -> None:
    result = _regex_ner("La loi du 1 janvier 2016 est entrée en vigueur.")
    assert any("2016" in d for d in result.dates)


# ---------------------------------------------------------------------------
# Monetary amounts
# ---------------------------------------------------------------------------


def test_extracts_euro_amounts() -> None:
    result = _regex_ner("Le montant est de € 50,000 payable sous 30 jours.")
    assert any("50,000" in m or "50 000" in m for m in result.monetary_amounts)


def test_extracts_dollar_amounts() -> None:
    result = _regex_ner("The fee is USD 10,000.")
    assert any("10,000" in m for m in result.monetary_amounts)


# ---------------------------------------------------------------------------
# Jurisdiction detection
# ---------------------------------------------------------------------------


def test_detects_french_jurisdiction() -> None:
    result = _regex_ner("Le droit français s'applique au présent contrat.")
    assert "FR" in result.jurisdictions


def test_detects_eu_jurisdiction() -> None:
    result = _regex_ner("Pursuant to Regulation (EU) 2016/679 (GDPR).")
    assert "EU" in result.jurisdictions


def test_detects_us_jurisdiction() -> None:
    result = _regex_ner("This agreement is governed by the laws of the United States.")
    assert "EN-US" in result.jurisdictions


def test_no_jurisdiction() -> None:
    result = _regex_ner("A simple sentence with no jurisdiction keywords.")
    assert result.jurisdictions == []


# ---------------------------------------------------------------------------
# Tag normalisation
# ---------------------------------------------------------------------------


def test_detects_contract_tag() -> None:
    result = _regex_ner("This contract is entered into between the parties.")
    assert "contract" in result.tags


def test_detects_force_majeure_tag() -> None:
    result = _regex_ner("The obligations are suspended in case of force majeure.")
    assert "force_majeure" in result.tags


def test_detects_arbitration_tag() -> None:
    result = _regex_ner("All disputes shall be resolved by arbitration in Paris.")
    assert "arbitration" in result.tags


def test_normalize_tags_maps_to_canonical() -> None:
    canonical = LegalNERPipeline.normalize_tags(["arbitration clause", "force majeure event"])
    assert "arbitration" in canonical
    assert "force_majeure" in canonical


# ---------------------------------------------------------------------------
# Effective date / version
# ---------------------------------------------------------------------------


def test_extracts_effective_date() -> None:
    result = _regex_ner("This agreement is effective as of 2024-01-01.")
    assert result.effective_date is not None
    assert "2024" in result.effective_date


def test_extracts_version() -> None:
    result = _regex_ner("Version modifiée le 2022-06-15.")
    assert result.version is not None
    assert "2022" in result.version


# ---------------------------------------------------------------------------
# Parties extraction (basic)
# ---------------------------------------------------------------------------


def test_extracts_english_parties() -> None:
    result = _regex_ner("BETWEEN Alpha Corporation AND Beta Limited (the 'Supplier'),")
    # At least one side captured
    assert len(result.parties) >= 1


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def test_detect_jurisdiction_returns_code() -> None:
    code = NER.detect_jurisdiction("Le droit français s'applique.")
    assert code == "FR"


def test_detect_jurisdiction_returns_none() -> None:
    code = NER.detect_jurisdiction("Nothing here.")
    assert code is None


def test_extract_returns_ner_result() -> None:
    result = NER.extract("The contract was signed on 2023-01-01.")
    assert hasattr(result, "dates")
    assert hasattr(result, "tags")
