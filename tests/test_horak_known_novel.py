"""Unit tests for the Known/Novel evidence stratification of the Horak-70 set.

Guard the load-bearing logic (label collapse, oncogenic-vs-rest confusion counts)
and the internal consistency of the committed stratification output. Offline: no
network, no LLM, no re-retrieval.
"""
import json
from pathlib import Path

import pytest

from scripts.run_horak_known_novel import _binary, collapse

OUT = Path("data/benchmark/horak_known_novel.json")


def test_collapse_maps_five_classes_to_three():
    assert collapse("Oncogenic") == "oncogenic"
    assert collapse("Likely Oncogenic") == "oncogenic"
    assert collapse("VUS") == "vus"
    assert collapse("Benign") == "benign"
    assert collapse("Likely Benign") == "benign"


def test_binary_confusion_counts():
    sub = [{"gold": "Oncogenic", "x": "Likely Oncogenic"},   # TP
           {"gold": "Likely Oncogenic", "x": "VUS"},         # FN
           {"gold": "VUS", "x": "Oncogenic"},                # FP
           {"gold": "Benign", "x": "VUS"}]                   # TN
    b = _binary(sub, "x")
    assert (b["tp"], b["fn"], b["fp"], b["tn"]) == (1, 1, 1, 1)
    assert b["sensitivity_onc"] == 0.5
    assert b["specificity_onc"] == 0.5


@pytest.fixture(scope="module")
def report():
    if not OUT.exists():
        pytest.skip("run `python -m scripts.run_horak_known_novel` first")
    return json.loads(OUT.read_text())


def test_strata_partition_the_benchmark(report):
    known, novel, all_ = (report["strata"][k]["n"] for k in ("known", "novel", "all"))
    assert known + novel == all_ == report["n_total"]
    assert {r["stratum"] for r in report["rows"]} == {"known", "novel"}


def test_stratum_definition_holds_per_row(report):
    for r in report["rows"]:
        assert (r["stratum"] == "known") == (r["n_civic"] > 0)


def test_pooled_arm_reproduces_the_published_operating_point(report):
    """The stratification must not change the headline numbers it decomposes: the pooled
    stratum equals data/benchmark/horak_vicc.json (SOP-strict primary, 2026-09-24;
    os2_fixed 0.786 / 0.545 / 1.0; original 0.843 / 0.697 / 0.973)."""
    hv = json.loads(Path("data/benchmark/horak_vicc.json").read_text())
    vicc = report["strata"]["all"]["arms"]["vicc"]
    assert vicc["accuracy_3class"]["point"] == hv["accuracy_3class"] == 0.657
    assert vicc["oncogenic_vs_rest"]["sensitivity_onc"] == hv["sensitivity_onc"] == 0.424
    assert vicc["oncogenic_vs_rest"]["specificity_onc"] == hv["specificity_onc"] == 1.0


def test_errors_are_localised_by_stratum(report):
    """SOP-strict: no oncogenic over-call; oncogenic-gold misses are abstentions (VUS) or,
    for one variant, a benign call; 9 in the known and 10 in the novel stratum."""
    assert report["vicc_arm_overcalls"] == []
    assert {m["vicc"] for m in report["vicc_arm_misses"]} <= {"VUS", "Likely Benign"}
    counts = {k: report["strata"][k]["arms"]["vicc"]["oncogenic_vs_rest"] for k in ("known", "novel")}
    assert counts["known"]["fp"] == 0 and counts["novel"]["fp"] == 0
    assert (counts["known"]["fn"], counts["novel"]["fn"]) == (9, 10)
    assert counts["known"]["fn"] + counts["novel"]["fn"] == len(report["vicc_arm_misses"])
