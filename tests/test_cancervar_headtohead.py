"""Unit tests for the CancerVar head-to-head scoring helpers.

These guard the load-bearing logic of the second external comparator:
tier->3class mapping, oncogenicity collapse, error typing, and the exact paired
McNemar. They run offline (no network, no fetched data needed)."""
from scripts.run_cancervar_headtohead import (
    TIER_TO_3,
    classify_error,
    collapse,
    mcnemar_exact,
    spec,
    sens,
)


def test_tier_map_covers_all_four_tiers():
    assert TIER_TO_3 == {"Tier_I": "ONC", "Tier_II": "ONC",
                         "Tier_III": "VUS", "Tier_IV": "BEN"}


def test_collapse_vicc_labels():
    assert collapse("Oncogenic") == "ONC"
    assert collapse("Likely Oncogenic") == "ONC"
    assert collapse("VUS") == "VUS"
    assert collapse("Benign") == "BEN"
    assert collapse("Likely Benign") == "BEN"


def test_classify_error_types():
    assert classify_error("ONC", "ONC") == "correct"
    assert classify_error("VUS", "ONC") == "over_call"   # called significant, gold not ONC
    assert classify_error("BEN", "ONC") == "over_call"
    assert classify_error("ONC", "VUS") == "miss"        # missed a true oncogenic


def test_specificity_sensitivity():
    gold = ["ONC", "ONC", "VUS", "BEN"]
    pred = ["ONC", "VUS", "ONC", "BEN"]
    # ONC gold = 2 (1 caught -> sens 0.5); non-ONC gold = 2, 1 false ONC -> spec 0.5
    assert sens(pred, gold) == 0.5
    assert spec(pred, gold) == 0.5


def test_mcnemar_exact_directional():
    gold = ["ONC"] * 6
    a = ["ONC", "ONC", "ONC", "ONC", "VUS", "VUS"]   # a correct on first 4
    b = ["VUS", "VUS", "VUS", "VUS", "ONC", "ONC"]   # b correct on last 2
    p, a_wins, b_wins = mcnemar_exact(gold, a, b)
    assert a_wins == 4 and b_wins == 2
    assert 0.0 <= p <= 1.0


def test_mcnemar_no_discordance_is_one():
    gold = ["ONC", "VUS"]
    p, a_wins, b_wins = mcnemar_exact(gold, gold, gold)
    assert p == 1.0 and a_wins == 0 and b_wins == 0
