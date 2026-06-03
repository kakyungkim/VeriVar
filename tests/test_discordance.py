"""Tests for typed discordance analysis (pure)."""
from src.eval.discordance import analyze, _category


def _v(key, oa, ta, ob, tb, rationale="", conf=1.0):
    return {"variant_key": key, "cancer_type": "Melanoma", "discordant": (oa != ob or ta != tb),
            "mode_a": {"oncogenicity": oa, "tier": ta, "rationale": rationale, "confidence": conf},
            "mode_b": {"oncogenicity": ob, "tier": tb}}


def test_category_rule_overcall():
    v = _v("EGFR p.E114K", "VUS", "Tier IV", "Oncogenic", "Tier II")
    assert _category(v) == "rule_overcall_corrected_by_llm"


def test_category_oncogenic_confidence():
    v = _v("BRAF p.V600E", "Likely Oncogenic", "Tier I", "Oncogenic", "Tier I")
    assert _category(v) == "oncogenic_confidence"


def test_category_tier_boundary():
    v = _v("KRAS p.G12V", "Oncogenic", "Tier II", "Oncogenic", "Tier I")
    assert _category(v) == "tier_boundary"


def test_category_benign_label():
    v = _v("X p.Y", "VUS", "Tier IV", "Likely Benign", "Tier IV")
    assert _category(v) == "benign_label"


def test_analyze_counts_and_adjacency():
    variants = [
        _v("a", "VUS", "Tier IV", "Oncogenic", "Tier II"),         # rule_overcall, gross
        _v("b", "Likely Oncogenic", "Tier I", "Oncogenic", "Tier I"),  # confidence, adjacent
        _v("c", "Oncogenic", "Tier I", "Oncogenic", "Tier I"),     # concordant (skipped)
    ]
    rep = analyze(variants)
    assert rep["n_discordant"] == 2
    assert rep["category_counts"]["rule_overcall_corrected_by_llm"] == 1
    assert rep["adjacent"] == 1 and rep["gross"] == 1
