"""Guards for the three named VICC rule-arm configurations (committed outputs)."""
import json
import os

import pytest

CMP = "data/benchmark/vicc_config_comparison.json"


@pytest.mark.skipif(not os.path.exists(CMP), reason="comparison not generated")
def test_three_configurations_and_headlines():
    r = json.load(open(CMP))["results"]
    assert {"original", "os2_fixed", "sop_strict"} <= set(r)
    head = {k: (v["horak"]["accuracy_3class"], v["horak"]["sensitivity_onc"],
                v["horak"]["specificity_onc"]) for k, v in r.items()}
    assert head["original"] == (0.843, 0.697, 0.973)      # as published before 2026-09-24
    assert head["os2_fixed"] == (0.786, 0.545, 1.0)
    assert head["sop_strict"] == (0.657, 0.424, 1.0)       # primary


@pytest.mark.skipif(not os.path.exists("data/benchmark/horak_vicc.json"), reason="no output")
def test_primary_output_is_sop_strict_and_consistent_with_comparison():
    hv = json.load(open("data/benchmark/horak_vicc.json"))
    assert hv["config"] == "sop_strict"
    if os.path.exists(CMP):
        prim = json.load(open(CMP))["results"]["sop_strict"]["horak"]
        assert prim["accuracy_3class"] == hv["accuracy_3class"]
        assert prim["auroc_onc"] == hv["auroc_onc"]


@pytest.mark.skipif(not os.path.exists(CMP), reason="comparison not generated")
def test_v2_family_reported_with_reference_tests_and_ablation():
    """Pre-registered improvement round: every v2-family configuration is reported, with
    McNemar vs sop_strict and the per-change ablation table (primary stays sop_strict)."""
    from src.classify.vicc_rules import PRIMARY_CONFIG, V2_FAMILY
    d = json.load(open(CMP))
    assert PRIMARY_CONFIG == "sop_strict"
    assert set(V2_FAMILY) <= set(d["results"])
    for c in V2_FAMILY:
        v = d["results"][c]["vs_sop_strict"]
        assert {"horak_3class", "clinvar_panel9_binary", "clinvar_all_binary"} <= set(v)
    ab = d["ablation"]
    assert set(ab["add_one_from_sop_strict"]) == {"a", "a0", "b", "c1", "c2"}
    assert set(ab["leave_one_out_from_sop_strict_v2"]) == {"a", "b", "c1", "c2"}
    # c1/c2 change no Horak input (input_coverage.json), so Horak must be unchanged
    for ch in ("c1", "c2"):
        assert (ab["add_one_from_sop_strict"][ch]["horak_acc3"]
                == ab["reference_sop_strict"]["horak_acc3"])
