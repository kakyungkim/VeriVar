"""Tests for the multi-model faithfulness ensemble (mock path, no model/API needed)."""
from scripts.run_multimodel_faithfulness import (
    call_mock, collapse3, ensemble, parse_json, risk_coverage,
)


def test_collapse3():
    assert collapse3("Oncogenic") == "ONC"
    assert collapse3("Likely Oncogenic") == "ONC"
    assert collapse3("VUS") == "VUS"
    assert collapse3("Benign") == "BEN"


def test_parse_json_extracts_and_validates():
    out = parse_json('blah {"oncogenicity": "Oncogenic", "tier": "Tier I", '
                     '"cited_ids": ["CIViC:EID1"]} trailing')
    assert out["oncogenicity"] == "Oncogenic" and out["tier"] == "Tier I"
    assert out["cited_ids"] == ["CIViC:EID1"]
    bad = parse_json('{"oncogenicity": "Nonsense", "tier": "X", "cited_ids": [1, "ok"]}')
    assert bad["oncogenicity"] == "VUS" and bad["tier"] == "Tier III"
    assert bad["cited_ids"] == ["ok"]            # non-str dropped
    assert parse_json("no json here") is None


def test_ensemble_unanimous_no_abstain():
    pm = {m: {"oncogenicity": "Oncogenic", "tier": "Tier I",
              "cited_ids": ["E1", "E2"]} for m in ("a", "b", "c")}
    e = ensemble(pm, abstain_threshold=0.66)
    assert e["ensemble_call"] == "ONC" and not e["abstained"]
    assert e["agreement"] == 1.0
    assert e["shared_citations"] == ["E1", "E2"]


def test_ensemble_shared_citations_are_intersection():
    pm = {"a": {"oncogenicity": "Oncogenic", "tier": "Tier I", "cited_ids": ["E1", "E2"]},
          "b": {"oncogenicity": "Oncogenic", "tier": "Tier I", "cited_ids": ["E2", "E3"]},
          "c": {"oncogenicity": "VUS", "tier": "Tier III", "cited_ids": []}}
    e = ensemble(pm, abstain_threshold=0.66)            # 2/3 ONC == 0.667 >= 0.66
    assert e["ensemble_call"] == "ONC" and not e["abstained"]
    assert e["shared_citations"] == ["E2"]              # intersection of the two ONC raters


def test_ensemble_disagreement_abstains():
    pm = {"a": {"oncogenicity": "Oncogenic", "tier": "Tier I", "cited_ids": []},
          "b": {"oncogenicity": "VUS", "tier": "Tier III", "cited_ids": []},
          "c": {"oncogenicity": "Benign", "tier": "Tier IV", "cited_ids": []}}
    e = ensemble(pm, abstain_threshold=0.66)            # no class reaches 0.66
    assert e["abstained"] and e["ensemble_call"] == "VUS"


def test_ensemble_majority_vus_abstains():
    pm = {"a": {"oncogenicity": "VUS", "tier": "Tier III", "cited_ids": []},
          "b": {"oncogenicity": "VUS", "tier": "Tier III", "cited_ids": []},
          "c": {"oncogenicity": "Oncogenic", "tier": "Tier I", "cited_ids": ["E1"]}}
    e = ensemble(pm, abstain_threshold=0.66)
    assert e["abstained"] and e["ensemble_call"] == "VUS"


def test_call_mock_is_deterministic_and_valid():
    v = {"variant_key": "BRAF p.V600E", "n_evidence": 3,
         "mode_a": {"oncogenicity": "Oncogenic", "tier": "Tier I",
                    "citations": ["CIViC:EID1398", "CIViC:EID1409"]}}
    r1 = call_mock("mock-A", v, ["CIViC:EID1398", "CIViC:EID1409"])
    r2 = call_mock("mock-A", v, ["CIViC:EID1398", "CIViC:EID1409"])
    assert r1 == r2                                     # deterministic
    assert r1["oncogenicity"] in ("Oncogenic", "Likely Oncogenic", "VUS")
    assert set(r1["cited_ids"]) <= {"CIViC:EID1398", "CIViC:EID1409"}   # cites only valid ids


def test_risk_coverage_orders_by_confidence():
    results = [
        {"confidence": 0.9, "ensemble_call": "ONC", "gold": "Oncogenic"},   # correct
        {"confidence": 0.5, "ensemble_call": "ONC", "gold": "VUS"},         # wrong
    ]
    curve = risk_coverage(results, "gold")
    assert curve[0]["coverage"] == 0.5 and curve[0]["selective_accuracy"] == 1.0
    assert curve[1]["coverage"] == 1.0 and curve[1]["selective_accuracy"] == 0.5
