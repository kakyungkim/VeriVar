"""Tests for the evaluation metrics (pure)."""
import pytest

from src.eval.metrics import (
    cohens_kappa, hallucination_rate, citation_grounding_rate,
    abstention_metrics, directional_faithfulness, inter_mode_kappa,
)
from src.eval.benchmark import normalize_tier


def _row(key, onc_a, tier_a, citations, evidences, abstained=False,
         onc_b="Oncogenic", tier_b="Tier I"):
    return {
        "variant_key": key, "gene": key.split()[0], "hgvsp": key.split()[1],
        "cancer_type": "Melanoma",
        "mode_a": {"oncogenicity": onc_a, "tier": tier_a, "citations": citations,
                   "abstained": abstained},
        "mode_b": {"oncogenicity": onc_b, "tier": tier_b},
        "bundle": {"evidences": evidences},
    }


def _ev(eid, source="CIViC", direction="Supports", significance="Sensitivity/Response", score=None):
    return {"id": eid, "source": source, "direction": direction,
            "significance": significance, "score": score}


def test_cohens_kappa():
    assert cohens_kappa(["a", "a", "b"], ["a", "a", "b"]) == 1.0
    assert cohens_kappa(["a", "b"], ["b", "a"]) < 0.1  # no agreement beyond chance


def test_hallucination_detects_fabricated_citation():
    rows = [_row("BRAF V600E", "Oncogenic", "Tier I", ["CIViC:EID1", "CIViC:EID999"],
                 [_ev("CIViC:EID1")])]
    h = hallucination_rate(rows)
    assert h["n_hallucinating"] == 1
    assert h["examples"][0]["fabricated"] == ["CIViC:EID999"]


def test_no_hallucination_when_all_cited_present():
    rows = [_row("BRAF V600E", "Oncogenic", "Tier I", ["CIViC:EID1"], [_ev("CIViC:EID1")])]
    assert hallucination_rate(rows)["hallucination_rate"] == 0.0


def test_abstention_recall():
    rows = [
        _row("X p.A", "VUS", "Tier III", [], [], abstained=True),     # no evidence, abstained (good)
        _row("Y p.B", "Oncogenic", "Tier I", ["CIViC:EID2"], [_ev("CIViC:EID2")]),  # has evidence
    ]
    ab = abstention_metrics(rows)
    assert ab["no_evidence_variants"] == 1 and ab["abstention_recall"] == 1.0


def test_directional_faithfulness_flags_contradiction():
    # Claims Oncogenic but only cites a benign 'Unaltered Function' evidence.
    rows = [_row("EGFR E114K", "Oncogenic", "Tier II", ["CIViC:EID1"],
                 [_ev("CIViC:EID1", significance="Unaltered Function")])]
    f = directional_faithfulness(rows)
    assert f["faithful"] == 0 and f["faithfulness_rate"] == 0.0


def test_directional_faithfulness_ok():
    rows = [_row("BRAF V600E", "Oncogenic", "Tier I", ["CIViC:EID1"], [_ev("CIViC:EID1")])]
    assert directional_faithfulness(rows)["faithfulness_rate"] == 1.0


def test_inter_mode_kappa_runs():
    rows = [_row("X p.A", "Oncogenic", "Tier I", [], [], onc_b="Oncogenic", tier_b="Tier I")]
    k = inter_mode_kappa(rows)
    assert "oncogenicity_kappa" in k and "tier_kappa" in k


def test_normalize_tier():
    assert normalize_tier("Tier I - Level A") == "Tier I"
    assert normalize_tier("Tier III") == "Tier III"
    assert normalize_tier("") is None
