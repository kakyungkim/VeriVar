"""Offline tests for scripts/audit_gnomad_missingness.py (stubbed inputs)."""
import pytest

from scripts.audit_gnomad_missingness import (af_state, clinvar_records, clinvar_representative,
                                              horak_records, summarise, v2_status)


@pytest.mark.parametrize("af,state", [(None, "missing_none"), (0.0, "coded_zero"),
                                      (5e-5, "observed_below_op4"),
                                      (1e-4, "observed_at_or_above_op4"),
                                      (0.2, "observed_at_or_above_op4")])
def test_af_state(af, state):
    assert af_state(af) == state


def test_v2_status():
    assert v2_status(None) == "v2_not_returned"
    assert v2_status({"vep_returned": False}) == "v2_not_returned"
    assert v2_status({"vep_returned": True, "gnomad_freqs": {}}) == "v2_no_gnomad_key"
    assert v2_status({"vep_returned": True,
                      "gnomad_freqs": {"gnomade": 0.0}}) == "v2_gnomad_all_zero"
    assert v2_status({"vep_returned": True,
                      "gnomad_freqs": {"gnomade": 0.0, "gnomadg_nfe": 3e-5}}) == "v2_gnomad_nonzero"


V2_EMPTY = {"vep_returned": True, "gnomad_freqs": {}}
V2_ZERO = {"vep_returned": True, "gnomad_freqs": {"gnomade": 0.0}}
V2_POS = {"vep_returned": True, "gnomad_freqs": {"gnomade": 2e-5}}


def test_summarise_counts_and_curator_tab():
    recs = [
        {"variant": "a", "af": 0.0, "op4": True, "v2": V2_EMPTY, "curator_op4": True},
        {"variant": "b", "af": 0.0, "op4": True, "v2": V2_ZERO, "curator_op4": False},
        {"variant": "c", "af": 0.0, "op4": True, "v2": V2_POS, "curator_op4": True},
        {"variant": "d", "af": 3e-5, "op4": True, "v2": V2_POS, "curator_op4": True},
        {"variant": "e", "af": 0.3, "op4": False, "v2": V2_POS, "curator_op4": False},
    ]
    s = summarise(recs)
    assert s["af_state_counts"] == {"missing_none": 0, "coded_zero": 3,
                                    "observed_below_op4": 1, "observed_at_or_above_op4": 1}
    assert s["op4_fired"] == 4
    assert s["op4_fired_by_af_state"]["coded_zero"] == 3
    assert s["coded_zero_v2_crosscheck"] == {"v2_no_gnomad_key": 1, "v2_gnomad_all_zero": 1,
                                             "v2_gnomad_nonzero": 1}
    assert [d["variant"] for d in s["coded_zero_v2_nonzero_discrepancies"]] == ["c"]
    assert s["coded_zero_v2_all_zero_variants"] == ["b"]
    assert s["op4_vs_curator"] == {"both": 3, "engine_only": 1, "curator_only": 0, "neither": 1,
                                   "curator_op4_total": 3,
                                   "engine_only_by_af_state": {"coded_zero": 1}}


def test_summarise_without_curator_has_no_tab():
    assert "op4_vs_curator" not in summarise([{"af": None, "op4": False, "v2": None}])


def test_horak_join_and_order_check():
    bench = [{"gene": "BRAF", "aa": "p.V600E", "b37_chr": "7", "b37_pos": "140453136",
              "b37_ref": "A", "b37_alt": "T", "b38_chr": "chr7", "b38_pos": "140753336",
              "b38_ref": "A", "b38_alt": "T", "sop_codes": "OS2, OP4"}]
    gnomad = {"7 140453136 . A T . . .": 0.0}
    vep = {"7 140753336 A T": V2_EMPTY}
    rows = [{"variant": "BRAF p.V600E", "codes": ["OS2", "OP4"]}]
    r = horak_records(bench, gnomad, rows, vep)[0]
    assert r["af"] == 0.0 and r["op4"] and r["curator_op4"] and r["v2"] is V2_EMPTY
    with pytest.raises(ValueError):
        horak_records(bench, gnomad, [{"variant": "KRAS p.G12D", "codes": []}], vep)


def test_clinvar_representative_rule_and_records():
    snap = [{"variation_id": "10", "n_onc_scvs": "1", "gnomad_af": "0.0", "chrom": "1",
             "pos": "5", "ref": "A", "alt": "G"},
            {"variation_id": "7", "n_onc_scvs": "2", "gnomad_af": "0.00002", "chrom": "1",
             "pos": "6", "ref": "C", "alt": "T"},
            {"variation_id": "3", "n_onc_scvs": "2", "gnomad_af": "", "chrom": "1",
             "pos": "7", "ref": "G", "alt": "A"}]
    # most SCVs first, then lowest VariationID -> 3
    assert clinvar_representative(snap, "10|7|3")["variation_id"] == "3"
    recs = clinvar_records(snap, [{"key": "X p.A1B", "variation_ids": "10|7", "codes": ["OP4"]}],
                           {"1 6 C T": V2_POS})
    assert recs[0]["af"] == pytest.approx(2e-5) and recs[0]["op4"] and recs[0]["v2"] is V2_POS
    with pytest.raises(ValueError):
        clinvar_representative(snap, "999")
