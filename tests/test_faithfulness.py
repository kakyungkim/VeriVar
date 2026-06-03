"""Adversarial tests for the deterministic faithfulness-enforcement gate.

A faithful (mock) cohort already scores 1.0 on every metric, so to *demonstrate* the
gate raises faithfulness we feed it deliberately UNfaithful Mode-A calls — a fabricated
citation, an oncogenic call citing only benign evidence, and a confident call with no
evidence that fails to abstain — and show (a) the raw cohort violates the metrics and
(b) after enforcement every metric returns to 1.0 / 0.0, with an audit trail.
"""
from src.classify.faithfulness import enforce_faithfulness, enforce_cohort
from src.eval.metrics import (
    hallucination_rate, directional_faithfulness, abstention_metrics,
)


def _variant(key, onc, citations, evidences, abstained=False):
    return {
        "variant_key": key,
        "mode_a": {"oncogenicity": onc, "tier": "Tier I", "tier_level": "A",
                   "rationale": "r", "citations": citations, "confidence": 0.9,
                   "abstained": abstained},
        "mode_b": {"oncogenicity": onc, "tier": "Tier I"},
        "bundle": {"evidences": evidences},
    }


# Evidence fixtures
_ONCO_EV = {"id": "CIViC:EID1", "source": "CIViC", "direction": "Supports",
            "significance": "Oncogenic"}
_BENIGN_EV = {"id": "CIViC:EID2", "source": "CIViC", "direction": "Supports",
              "significance": "Benign"}


def test_fabricated_citation_is_dropped():
    """Gate 1: a cited id absent from the bundle is removed -> hallucination 0."""
    v = _variant("X", "Oncogenic", ["CIViC:EID1", "CIViC:FAKE999"], [_ONCO_EV])
    assert hallucination_rate([v])["hallucination_rate"] == 1.0       # raw: hallucinates
    out = enforce_faithfulness(v)
    assert out["mode_a"]["citations"] == ["CIViC:EID1"]
    assert "CIViC:FAKE999" in out["faithfulness_audit"]["citations_dropped"]
    assert hallucination_rate([out])["hallucination_rate"] == 0.0     # enforced: clean


def test_oncogenic_call_citing_only_benign_abstains():
    """Gate 3: a call that contradicts its own citations is forced to VUS."""
    v = _variant("Y", "Oncogenic", ["CIViC:EID2"], [_BENIGN_EV])
    assert directional_faithfulness([v])["faithfulness_rate"] == 0.0  # raw: contradicts
    out = enforce_faithfulness(v)
    assert out["mode_a"]["oncogenicity"] == "VUS"
    assert out["mode_a"]["abstained"] is True
    # After abstention there is no surviving directional call to violate (rate is
    # vacuously perfect: None = 0/0), and crucially zero violations remain.
    d = directional_faithfulness([out])
    assert d["violations"] == [] and d["faithfulness_rate"] in (1.0, None)


def test_no_evidence_forces_abstention():
    """Gate 2: a confident call with an empty bundle must abstain."""
    v = _variant("Z", "Oncogenic", [], [], abstained=False)
    assert abstention_metrics([v])["abstention_recall"] == 0.0        # raw: fails to abstain
    out = enforce_faithfulness(v)
    assert out["mode_a"]["abstained"] is True
    assert out["mode_a"]["oncogenicity"] == "VUS"
    assert abstention_metrics([out])["abstention_recall"] == 1.0


def test_faithful_call_is_untouched():
    """A genuinely faithful call passes through with no gates fired."""
    v = _variant("OK", "Oncogenic", ["CIViC:EID1"], [_ONCO_EV])
    out = enforce_faithfulness(v)
    assert out["faithfulness_audit"]["corrected"] is False
    assert out["mode_a"]["oncogenicity"] == "Oncogenic"


def test_cohort_enforcement_restores_all_metrics():
    """End-to-end: a cohort with one of each violation -> all metrics perfect after."""
    cohort = [
        _variant("a", "Oncogenic", ["CIViC:EID1", "CIViC:FAKE"], [_ONCO_EV]),
        _variant("b", "Oncogenic", ["CIViC:EID2"], [_BENIGN_EV]),
        _variant("c", "Oncogenic", [], []),
        _variant("d", "Oncogenic", ["CIViC:EID1"], [_ONCO_EV]),   # already faithful
    ]
    fixed = enforce_cohort(cohort)
    assert hallucination_rate(fixed)["hallucination_rate"] == 0.0
    assert directional_faithfulness(fixed)["faithfulness_rate"] == 1.0
    assert abstention_metrics(fixed)["abstention_recall"] == 1.0
    assert sum(f["faithfulness_audit"]["corrected"] for f in fixed) == 3
