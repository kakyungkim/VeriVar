"""Tests for the additional analyses (pure)."""
from src.eval.analyses import (
    cross_cancer_consistency, sensitivity_vs_resistance,
    alphamissense_llm_agreement, confidence_calibration, hotspot_vs_rare,
)


def _v(gene, hgvsp, cancer, onc="Oncogenic", tier="Tier I", tierA=None, evid=None,
        conf=1.0, discordant=False):
    return {"gene": gene, "hgvsp": hgvsp, "cancer_type": cancer, "variant_key": f"{gene} {hgvsp}",
            "evidence_tier": "civic", "discordant": discordant,
            "mode_a": {"oncogenicity": onc, "tier": tierA or tier, "confidence": conf, "rationale": ""},
            "mode_b": {"oncogenicity": onc, "tier": tier},
            "bundle": {"evidences": evid or []}}


def test_cross_cancer_stable_oncogenicity_variable_tier():
    vs = [_v("KRAS", "p.G12V", "Colorectal", tierA="Tier I"),
          _v("KRAS", "p.G12V", "Pancreatic", tierA="Tier II")]
    r = cross_cancer_consistency(vs)
    assert r["n_multi_cancer_variants"] == 1
    assert r["stable_oncogenicity"] == 1 and r["variable_tier"] == 1


def test_sensitivity_vs_resistance_buckets():
    sens = {"significance": "Sensitivity/Response", "direction": "Supports"}
    res = {"significance": "Resistance"}
    vs = [_v("A", "p.X", "C", evid=[res], tierA="Tier I"),
          _v("B", "p.Y", "C", evid=[sens])]
    r = sensitivity_vs_resistance(vs)
    assert r["resistance_only"] == 1 and r["sensitivity_only"] == 1
    assert r["resistance_only_tier_distribution"] == {"Tier I": 1}


def test_alphamissense_llm_agreement():
    path = {"source": "AlphaMissense", "score": 0.95}
    benign = {"source": "AlphaMissense", "score": 0.10}
    vs = [
        {**_v("A", "p.X", "C", onc="Likely Oncogenic"), "evidence_tier": "alphamissense",
         "bundle": {"evidences": [path]}},
        {**_v("B", "p.Y", "C", onc="Oncogenic"), "evidence_tier": "alphamissense",
         "bundle": {"evidences": [benign]}},  # AM benign but LLM oncogenic -> disagree
    ]
    r = alphamissense_llm_agreement(vs)
    assert r["checked"] == 2 and r["agree"] == 1 and r["agreement_rate"] == 0.5


def test_confidence_calibration_bins():
    vs = [_v("A", "p.X", "C", conf=1.0, discordant=False),
          _v("B", "p.Y", "C", conf=0.5, discordant=True)]
    r = confidence_calibration(vs)
    assert r["high (>=0.9)"]["n"] == 1 and r["low (<0.7)"]["discordance_rate"] == 1.0


def test_hotspot_vs_rare():
    vs = [_v("BRAF", "p.V600E", "Melanoma", discordant=False),
          _v("XYZ", "p.A1B", "Melanoma", discordant=True)]
    r = hotspot_vs_rare(vs)
    assert r["hotspot"]["n"] == 1 and r["non_hotspot"]["discordance_rate"] == 1.0


def test_verifier_effect_toward_and_away():
    from src.eval.analyses import verifier_effect
    verified = [
        _v("A", "p.X", "C", tier="Tier I"),                     # rule Tier I
        _v("B", "p.Y", "C", tier="Tier I"),
    ]
    verified[0]["mode_a"]["tier"] = "Tier I"   # verified A == rule -> toward
    verified[1]["mode_a"]["tier"] = "Tier IV"  # verified A far from rule -> away
    noverify = [
        _v("A", "p.X", "C", tier="Tier I"), _v("B", "p.Y", "C", tier="Tier I"),
    ]
    noverify[0]["mode_a"]["tier"] = "Tier III"  # was far, verifier moved to Tier I (toward)
    noverify[1]["mode_a"]["tier"] = "Tier I"    # was at rule, verifier moved to Tier IV (away)
    e = verifier_effect(verified, noverify)
    assert e["tier_changed_by_verifier"] == 2
    assert e["moved_toward_rule"] == 1 and e["moved_away_from_rule"] == 1
