"""Tests for the ClinicalTrials.gov adapter (offline; no network)."""
import json

from src.knowledge.clinical_trials import ClinicalTrialsSource, _parse_study


def test_parse_study_extracts_core_fields():
    study = {"protocolSection": {
        "identificationModule": {"nctId": "NCT01234567", "briefTitle": "BRAF trial"},
        "statusModule": {"overallStatus": "RECRUITING"},
        "designModule": {"phases": ["PHASE2"]},
        "conditionsModule": {"conditions": ["Melanoma"]},
        "armsInterventionsModule": {"interventions": [{"name": "Vemurafenib"}]},
    }}
    rec = _parse_study(study)
    assert rec["nct_id"] == "NCT01234567"
    assert rec["status"] == "RECRUITING"
    assert rec["phase"] == "PHASE2"
    assert rec["interventions"] == ["Vemurafenib"]


def test_enrich_uses_cache_offline(tmp_path):
    cache = {"NCT01234567": {"nct_id": "NCT01234567", "title": "Cached trial",
                             "status": "COMPLETED", "phase": "PHASE3",
                             "conditions": ["Melanoma"], "interventions": ["Dabrafenib"],
                             "url": "https://clinicaltrials.gov/study/NCT01234567"}}
    p = tmp_path / "trials_cache.json"
    p.write_text(json.dumps(cache))

    src = ClinicalTrialsSource(cache_path=p, offline=True)
    trials = src.enrich(["NCT01234567", "NCT09999999"])
    assert len(trials) == 2
    cached = next(t for t in trials if t.nct_id == "NCT01234567")
    assert cached.title == "Cached trial" and cached.status == "COMPLETED"
    # Unknown id offline -> bare record (no network), still a valid ClinicalTrial.
    bare = next(t for t in trials if t.nct_id == "NCT09999999")
    assert bare.title == "" and bare.url.endswith("NCT09999999")


def test_enrich_dedups_and_skips_empty(tmp_path):
    src = ClinicalTrialsSource(cache_path=tmp_path / "none.json", offline=True)
    trials = src.enrich(["NCT1", "NCT1", "", None])
    assert [t.nct_id for t in trials] == ["NCT1"]
