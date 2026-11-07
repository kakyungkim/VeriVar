"""Tests for the HemaGuide head-to-head (third external comparator).

Offline: they read the committed ST6 extract (data/benchmark/hemaguide/hemaguide_st6.csv) and
the committed report. The end-to-end join test needs the gitignored Horak gold and rule-arm
outputs, so it is skipped when those are absent (e.g. on a fresh clone / CI)."""
import json
import os

import pytest

from scripts.run_hemaguide_headtohead import (
    DECISION_TO_3,
    GOLD,
    HEMA_CSV,
    OUR_PRED,
    OUT,
    PUBLISHED,
    join_and_check,
    load_gold,
    load_hemaguide,
    points_int,
    points_to_5class,
    score,
    variant_key,
)
from scripts.run_cancervar_headtohead import sens, spec


def test_decision_map_is_same_axis():
    assert DECISION_TO_3 == {"LO/O": "ONC", "VUS": "VUS", "LB/B": "BEN"}


def test_points_parsing_and_thresholds():
    assert points_int("10 points") == 10
    assert points_int("-5.0") == -5
    assert points_int("") is None
    # Horak 2022 thresholds: O >=10, LO 6..9, VUS 0..5, LB -6..-1, B <=-7
    assert [points_to_5class(p) for p in (10, 9, 6, 5, 0, -1, -6, -7)] == [
        "Oncogenic", "Likely Oncogenic", "Likely Oncogenic", "VUS", "VUS",
        "Likely Benign", "Likely Benign", "Benign"]


def test_variant_key_normalises_prefix():
    assert variant_key("FLT3", "D835Y") == variant_key("FLT3 ", "p.D835Y") == "FLT3 p.D835Y"


def test_st6_extract_shape():
    rows = load_hemaguide()
    assert len(rows) == 70
    assert len({variant_key(r["Gene"], r["AA_change"]) for r in rows}) == 70
    assert {r["Hemaguide_decision"] for r in rows} <= set(DECISION_TO_3)
    assert {r["Horak_2022_decision"] for r in rows} <= set(DECISION_TO_3)


def test_st6_reproduces_hemaguide_published_figures():
    """ST6 alone (its reference column vs its call) must give the paper's 56/70, 0.88, 0.84."""
    rows = load_hemaguide()
    gold = [DECISION_TO_3[r["Horak_2022_decision"]] for r in rows]
    pred = [DECISION_TO_3[r["Hemaguide_decision"]] for r in rows]
    assert sum(p == g for p, g in zip(pred, gold)) == PUBLISHED["concordant"] == 56
    assert round(sens(pred, gold), 2) == PUBLISHED["sensitivity_onc"]
    assert round(spec(pred, gold), 2) == PUBLISHED["specificity_onc"]
    # "no oncogenic variant was downgraded to benign"
    assert not any(g == "ONC" and p == "BEN" for p, g in zip(pred, gold))


def test_score_on_synthetic_rows():
    rows = [
        {"variant": "A p.X1Y", "gold": "Oncogenic", "ours": "VUS",
         "hemaguide_decision": "LO/O", "hemaguide_points": 10,
         "ours_points": 3, "ours_codes": [], "hemaguide_codes": ""},
        {"variant": "B p.X2Y", "gold": "VUS", "ours": "VUS",
         "hemaguide_decision": "LO/O", "hemaguide_points": 6,
         "ours_points": 2, "ours_codes": [], "hemaguide_codes": ""},
        {"variant": "C p.X3Y", "gold": "Benign", "ours": "Benign",
         "hemaguide_decision": "LB/B", "hemaguide_points": -8,
         "ours_points": -8, "ours_codes": [], "hemaguide_codes": ""},
    ]
    r = score(rows)
    assert r["ours"]["n_correct_3class"] == 2 and r["hemaguide"]["n_correct_3class"] == 2
    assert r["ours"]["misses"] == 1 and r["ours"]["over_calls"] == 0
    assert r["hemaguide"]["over_calls"] == 1 and r["hemaguide"]["misses"] == 0
    mc = r["paired_mcnemar_3class"]
    assert (mc["ours_only_correct"], mc["hemaguide_only_correct"]) == (1, 1)
    assert mc["p_two_sided"] == 1.0
    assert r["n_disagreements_3class"] == 2


def test_committed_report_consistent_with_st6():
    rep = json.load(open(OUT))
    assert rep["n_shared_variants"] == 70
    h = rep["hemaguide"]
    assert h["n_correct_3class"] == 56 and h["accuracy_3class"] == 0.8
    assert h["sensitivity_onc"] == 0.879 and h["specificity_onc"] == 0.838
    assert h["over_calls"] == 6 and h["onc_called_benign"] == 0
    mc = rep["paired_mcnemar_3class"]
    # Every one-sided-correct pair is a 3-class disagreement (both-wrong pairs may add more).
    assert mc["ours_only_correct"] + mc["hemaguide_only_correct"] <= rep["n_disagreements_3class"]
    assert mc["p_two_sided"] > 0.05  # not significant at n = 70; never claim superiority
    assert "CC BY 4.0" in rep["provenance"]["license"]


@pytest.mark.skipif(not (os.path.exists(GOLD) and os.path.exists(OUR_PRED)),
                    reason="Horak gold / rule-arm outputs are gitignored local artifacts")
def test_end_to_end_join_matches_committed_report():
    ours = {r["variant"]: r for r in json.load(open(OUR_PRED))["rows"]}
    rows = join_and_check(load_hemaguide(HEMA_CSV), load_gold(GOLD), ours)
    assert len(rows) == 70
    fresh = score(rows)
    rep = json.load(open(OUT))
    for arm in ("ours", "hemaguide"):
        for k in ("n_correct_3class", "accuracy_3class", "sensitivity_onc",
                  "specificity_onc", "over_calls", "misses"):
            assert fresh[arm][k] == rep[arm][k], (arm, k)
    assert fresh["paired_mcnemar_3class"] == rep["paired_mcnemar_3class"]
